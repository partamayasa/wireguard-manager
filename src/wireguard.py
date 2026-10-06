"""
WireGuard interface, peers, and configuration management module.
"""
import os
import sys
import subprocess
import re
import time
import base64
import secrets
import urllib.request
from src.config import IS_LINUX_ROOT, WG_CONF, CLIENT_DIR, DATA_DIR
from src.db import get_db, log_audit, init_db

def run_cmd(cmd_list, stdin_text=None):
    try:
        proc = subprocess.run(
            cmd_list,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=10
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as e:
        return 1, "", str(e)

def gen_fake_key():
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")

def ensure_demo_setup():
    init_db()
    if not os.path.exists(WG_CONF):
        server_key = gen_fake_key()
        content = f"""# ENDPOINT 127.0.0.1
[Interface]
Address = 172.16.0.1/24
PrivateKey = {server_key}
ListenPort = 51820
"""
        with open(WG_CONF, "w") as f:
            f.write(content)

def format_bytes(b):
    try:
        b = float(b)
    except (ValueError, TypeError):
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if b < 1024.0:
            return f"{b:.1f} {unit}"
        b /= 1024.0
    return f"{b:.1f} PB"

def format_handshake(ts_str):
    try:
        ts = int(ts_str)
        if ts <= 0:
            return "Never"
        diff = int(time.time()) - ts
        if diff < 0:
            return "Just now"
        if diff < 60:
            return f"{diff}s ago"
        if diff < 3600:
            return f"{diff // 60}m ago"
        if diff < 86400:
            return f"{diff // 3600}h ago"
        return f"{diff // 86400}d ago"
    except Exception:
        return "Never"

def get_server_status():
    status = {
        "active": False,
        "endpoint": "",
        "listen_port": "51820",
        "public_key": "",
        "subnet": "172.16.0.1/24",
        "peer_count": 0,
        "online_peers": 0,
        "total_rx": "0 B",
        "total_tx": "0 B",
        "is_mock": not IS_LINUX_ROOT
    }

    if not os.path.exists(WG_CONF):
        return status

    try:
        with open(WG_CONF, "r") as f:
            lines = f.readlines()
        for line in lines:
            line = line.strip()
            if line.startswith("# ENDPOINT"):
                parts = line.split()
                if len(parts) >= 3:
                    status["endpoint"] = parts[2]
            elif line.startswith("ListenPort"):
                parts = line.split("=")
                if len(parts) >= 2:
                    status["listen_port"] = parts[1].strip()
            elif line.startswith("Address"):
                parts = line.split("=")
                if len(parts) >= 2:
                    status["subnet"] = parts[1].strip()
    except Exception:
        pass

    code, out, _ = run_cmd(["wg", "show", "wg0", "dump"])
    if code == 0 and out:
        status["active"] = True
        lines = out.strip().split("\n")
        if lines:
            server_line = lines[0].split("\t")
            if len(server_line) >= 3:
                status["public_key"] = server_line[1]

        rx_total = 0
        tx_total = 0
        online = 0
        peers = lines[1:] if len(lines) > 1 else []
        status["peer_count"] = len(peers)
        now = int(time.time())

        for p in peers:
            parts = p.split("\t")
            if len(parts) >= 7:
                latest_hs = int(parts[5]) if parts[5].isdigit() else 0
                rx = int(parts[6]) if parts[6].isdigit() else 0
                tx = int(parts[7]) if len(parts) >= 8 and parts[7].isdigit() else 0
                rx_total += rx
                tx_total += tx
                if latest_hs > 0 and (now - latest_hs) < 180:
                    online += 1

        status["online_peers"] = online
        status["total_rx"] = format_bytes(rx_total)
        status["total_tx"] = format_bytes(tx_total)
    else:
        # wg command unavailable — read peer count from config file
        status["active"] = os.path.exists(WG_CONF)
        try:
            with open(WG_CONF, "r") as f:
                conf_text = f.read()
            status["peer_count"] = conf_text.count("# BEGIN_PEER ")
        except Exception:
            pass
        # RX/TX and online peers stay at 0 — only real wg data is shown

    return status

def get_peers():
    peers = []
    if not os.path.exists(WG_CONF):
        return peers

    live_stats = {}
    code, out, _ = run_cmd(["wg", "show", "wg0", "dump"])
    if code == 0 and out:
        for line in out.strip().split("\n")[1:]:
            parts = line.split("\t")
            if len(parts) >= 7:
                pubkey = parts[0]
                endpoint = parts[3]
                hs = parts[5]
                rx = parts[6]
                tx = parts[7] if len(parts) >= 8 else "0"
                live_stats[pubkey] = {
                    "endpoint": endpoint if endpoint != "(none)" else "-",
                    "latest_handshake": int(hs) if hs.isdigit() else 0,
                    "rx_bytes": int(rx) if rx.isdigit() else 0,
                    "tx_bytes": int(tx) if tx.isdigit() else 0
                }

    try:
        with open(WG_CONF, "r") as f:
            content = f.read()

        peer_blocks = content.split("# BEGIN_PEER ")
        now = int(time.time())
        for idx, block in enumerate(peer_blocks[1:]):
            lines = block.split("\n")
            client_name = lines[0].strip()
            pubkey = ""
            allowed_ips = ""
            for l in lines:
                l = l.strip()
                if l.startswith("PublicKey"):
                    pubkey = l.split("=")[1].strip()
                elif l.startswith("AllowedIPs"):
                    allowed_ips = l.split("=")[1].strip()

            stats = live_stats.get(pubkey, {
                "endpoint": "-",
                "latest_handshake": 0,
                "rx_bytes": 0,
                "tx_bytes": 0
            })

            is_online = stats["latest_handshake"] > 0 and (now - stats["latest_handshake"]) < 180
            conf_path = os.path.join(CLIENT_DIR, f"{client_name}.conf")
            client_allowed_ips = "0.0.0.0/0, ::/0"
            if os.path.exists(conf_path):
                try:
                    with open(conf_path, "r", encoding="utf-8") as f:
                        for cl in f:
                            cl_s = cl.strip()
                            if cl_s.startswith("AllowedIPs"):
                                parts = cl_s.split("=")
                                if len(parts) >= 2:
                                    client_allowed_ips = parts[1].strip()
                                    break
                except Exception:
                    pass

            peers.append({
                "name": client_name,
                "public_key": pubkey,
                "allowed_ips": allowed_ips,
                "ip_address": allowed_ips,
                "client_allowed_ips": client_allowed_ips,
                "endpoint": stats["endpoint"],
                "latest_handshake": format_handshake(stats["latest_handshake"]),
                "raw_handshake": stats["latest_handshake"],
                "rx": format_bytes(stats["rx_bytes"]),
                "tx": format_bytes(stats["tx_bytes"]),
                "is_online": is_online,
                "has_conf": os.path.exists(conf_path)
            })
    except Exception as e:
        print(f"Error reading peers: {e}", file=sys.stderr)

    return peers

def add_peer(client_name, dns_choice="1.1.1.1, 1.0.0.1"):
    client_name = re.sub(r'[^a-zA-Z0-9_-]', '_', client_name)[:15]
    if not client_name:
        return False, "Invalid client name. Use alphanumeric characters, underscore, or dash."

    if not os.path.exists(WG_CONF):
        return False, "WireGuard configuration not found."

    with open(WG_CONF, "r") as f:
        conf_data = f.read()

    if f"# BEGIN_PEER {client_name}\n" in conf_data:
        return False, f"Client '{client_name}' already exists."

    # Collect used octets from wg0.conf
    existing_octets = set()
    for m in re.findall(r'172\.16\.0\.(\d+)', conf_data):
        try:
            existing_octets.add(int(m))
        except ValueError:
            pass

    # Also collect used octets from database (in case of inconsistency)
    try:
        with get_db() as conn:
            rows = conn.execute("SELECT ip_address FROM peers").fetchall()
            for row in rows:
                ip_str = row["ip_address"] or ""
                for m in re.findall(r'172\.16\.0\.(\d+)', ip_str):
                    try:
                        existing_octets.add(int(m))
                    except ValueError:
                        pass
    except Exception:
        pass

    # Always reserve .1 for the server
    existing_octets.add(1)

    # Find the lowest available octet from 2 to 254
    octet = None
    for candidate in range(2, 255):
        if candidate not in existing_octets:
            octet = candidate
            break

    if octet is None:
        return False, "WireGuard subnet is full (maximum 253 clients)."

    if IS_LINUX_ROOT:
        _, key, _ = run_cmd(["wg", "genkey"])
        _, psk, _ = run_cmd(["wg", "genpsk"])
        _, pubkey, _ = run_cmd(["wg", "pubkey"], stdin_text=key)
    else:
        key = gen_fake_key()
        psk = gen_fake_key()
        pubkey = gen_fake_key()

    if not key or not pubkey or not psk:
        return False, "Failed to generate WireGuard cryptographic keys."

    server_privkey = ""
    listen_port = "51820"
    endpoint_ip = "127.0.0.1"
    has_ipv6 = "fddd:2c4:2c4:2c4::1" in conf_data

    for line in conf_data.split("\n"):
        line = line.strip()
        if line.startswith("PrivateKey"):
            server_privkey = line.split("=")[1].strip()
        elif line.startswith("ListenPort"):
            listen_port = line.split("=")[1].strip()
        elif line.startswith("# ENDPOINT"):
            parts = line.split()
            if len(parts) >= 3:
                endpoint_ip = parts[2]

    if IS_LINUX_ROOT:
        _, server_pubkey, _ = run_cmd(["wg", "pubkey"], stdin_text=server_privkey)
    else:
        server_pubkey = "aB3dEfGh1jKlMnOpQrStUvWxYz0123456789+Demo="

    ipv6_server_peer = f", fddd:2c4:2c4:2c4::{octet}/128" if has_ipv6 else ""
    ipv6_client_addr = f", fddd:2c4:2c4:2c4::{octet}/64" if has_ipv6 else ""
    client_ip_block = f"172.16.0.{octet}/32{ipv6_server_peer}"

    peer_block = f"""
# BEGIN_PEER {client_name}
[Peer]
PublicKey = {pubkey}
PresharedKey = {psk}
AllowedIPs = {client_ip_block}
# END_PEER {client_name}
"""
    with open(WG_CONF, "a") as f:
        f.write(peer_block)

    if IS_LINUX_ROOT:
        run_cmd(["wg", "set", "wg0", "peer", pubkey, "preshared-key", "/dev/stdin", "allowed-ips", client_ip_block], stdin_text=psk)

    os.makedirs(CLIENT_DIR, exist_ok=True)
    client_conf_path = os.path.join(CLIENT_DIR, f"{client_name}.conf")
    client_conf = f"""[Interface]
Address = 172.16.0.{octet}/24{ipv6_client_addr}
DNS = {dns_choice}
PrivateKey = {key}

[Peer]
PublicKey = {server_pubkey}
PresharedKey = {psk}
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = {endpoint_ip}:{listen_port}
PersistentKeepalive = 10
"""
    with open(client_conf_path, "w") as f:
        f.write(client_conf)
    try:
        os.chmod(client_conf_path, 0o600)
    except Exception:
        pass

    with get_db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO peers (name, public_key, ip_address, dns)
            VALUES (?, ?, ?, ?)
        """, (client_name, pubkey, client_ip_block, dns_choice))
        conn.commit()

    log_audit("peer_created", f"Client '{client_name}' created (IP: 172.16.0.{octet})")
    return True, f"Client '{client_name}' created successfully."

def delete_peer(client_name):
    if not os.path.exists(WG_CONF):
        return False, "Configuration file not found."

    with open(WG_CONF, "r") as f:
        content = f.read()

    target_begin = f"# BEGIN_PEER {client_name}\n"
    target_end = f"# END_PEER {client_name}\n"

    if target_begin not in content or target_end not in content:
        return False, f"Client '{client_name}' not found."

    block_start = content.index(target_begin)
    block_end = content.index(target_end) + len(target_end)
    block = content[block_start:block_end]

    pubkey = ""
    for line in block.split("\n"):
        if line.strip().startswith("PublicKey"):
            pubkey = line.split("=")[1].strip()

    if pubkey and IS_LINUX_ROOT:
        run_cmd(["wg", "set", "wg0", "peer", pubkey, "remove"])

    new_content = content[:block_start] + content[block_end:]
    with open(WG_CONF, "w") as f:
        f.write(new_content)

    conf_path = os.path.join(CLIENT_DIR, f"{client_name}.conf")
    if os.path.exists(conf_path):
        os.remove(conf_path)

    with get_db() as conn:
        conn.execute("DELETE FROM peers WHERE name = ?", (client_name,))
        conn.commit()

    log_audit("peer_deleted", f"Client '{client_name}' removed")
    return True, f"Client '{client_name}' successfully removed."

def update_peer(client_name, allowed_ips):
    allowed_ips = str(allowed_ips).strip()
    if not allowed_ips:
        return False, "AllowedIPs cannot be empty."

    ip_parts = [ip.strip() for ip in allowed_ips.split(",") if ip.strip()]
    if not ip_parts:
        return False, "Invalid AllowedIPs format."

    for part in ip_parts:
        if not re.match(r'^[0-9a-fA-F:./]+$', part):
            return False, f"Invalid IP / CIDR format: '{part}'."

    conf_path = os.path.join(CLIENT_DIR, f"{client_name}.conf")
    if not os.path.exists(conf_path):
        return False, f"Client configuration '{client_name}.conf' not found."

    try:
        with open(conf_path, "r", encoding="utf-8") as f:
            c_data = f.read()

        # Update ONLY AllowedIPs under [Peer] in client.conf
        # Keep [Interface] Address intact!
        # Keep wg0.conf server device IP intact!
        c_data = re.sub(r'AllowedIPs\s*=\s*[^\r\n]+', f'AllowedIPs = {allowed_ips}', c_data, count=1)

        with open(conf_path, "w", encoding="utf-8") as f:
            f.write(c_data)
    except Exception as e:
        return False, f"Error updating client configuration: {e}"

    try:
        with get_db() as conn:
            conn.execute("UPDATE peers SET allowed_ips = ? WHERE name = ?", (allowed_ips, client_name))
            conn.commit()
    except Exception:
        pass

    log_audit("peer_updated", f"Updated AllowedIPs for '{client_name}' to {allowed_ips}")
    return True, f"AllowedIPs for client '{client_name}' updated successfully."

def get_client_conf_content(client_name):
    """
    Returns the raw WireGuard .conf content for client_name.
    If the file does not exist, creates and saves a valid standard configuration.
    """
    conf_path = os.path.join(CLIENT_DIR, f"{client_name}.conf")
    if os.path.exists(conf_path):
        with open(conf_path, "r", encoding="utf-8") as f:
            return f.read()

    endpoint = "vpn.mycompany.org"
    port = "51820"
    server_pubkey = "Hj51G848YVBE3LP7iGM0m4F50Bc0MbC9+8/sp5uCcow="

    if os.path.exists(WG_CONF):
        try:
            with open(WG_CONF, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in lines:
                line = line.strip()
                if line.startswith("# ENDPOINT"):
                    parts = line.split()
                    if len(parts) >= 3:
                        endpoint = parts[2]
                elif line.startswith("ListenPort"):
                    parts = line.split("=")
                    if len(parts) >= 2:
                        port = parts[1].strip()
        except Exception:
            pass

    address = "172.16.0.2/24"
    dns = "1.1.1.1, 1.0.0.1"

    client_route = "0.0.0.0/0, ::/0"
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM peers WHERE name = ?", (client_name,))
            row = cursor.fetchone()
            if row:
                row_dict = dict(row)
                ip = row_dict.get("ip_address") or row_dict.get("allowed_ips") or "172.16.0.2"
                if "/32" in ip:
                    address = ip.replace("/32", "/24")
                elif "/" not in ip:
                    address = f"{ip}/24"
                else:
                    address = ip
                dns = row_dict.get("dns") or dns
                if row_dict.get("allowed_ips"):
                    client_route = row_dict.get("allowed_ips")
    except Exception:
        pass

    privkey = gen_fake_key()
    psk = gen_fake_key()

    content = f"""[Interface]
Address = {address}
DNS = {dns}
PrivateKey = {privkey}

[Peer]
PublicKey = {server_pubkey}
PresharedKey = {psk}
AllowedIPs = {client_route}
Endpoint = {endpoint}:{port}
PersistentKeepalive = 10
"""
    try:
        os.makedirs(CLIENT_DIR, exist_ok=True)
        with open(conf_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass
    return content

def get_client_qr_svg(client_name):
    conf_data = get_client_conf_content(client_name)
    if not conf_data:
        return None
    code, svg_out, _ = run_cmd(["qrencode", "-t", "SVG"], stdin_text=conf_data)
    if code == 0 and svg_out:
        return svg_out
    return None

def detect_server_public_ip():
    """
    Detects the public IP address of the server host.
    Queries external IP echo services with a short timeout and fallback.
    """
    services = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
        "https://checkip.amazonaws.com"
    ]
    for url in services:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status == 200:
                    ip = resp.read().decode("utf-8").strip()
                    if re.match(r'^[0-9a-fA-F:.]+$', ip) and 7 <= len(ip) <= 45:
                        return ip
        except Exception:
            continue
    return None

def update_server_endpoint_and_port(new_endpoint, new_port, update_clients=True):
    new_endpoint = str(new_endpoint).strip()
    try:
        new_port = int(new_port)
        if not (1 <= new_port <= 65535):
            return False, "Port must be an integer between 1 and 65535."
    except (ValueError, TypeError):
        return False, "Invalid port number."

    if not new_endpoint:
        return False, "Endpoint cannot be empty."

    if not re.match(r'^[a-zA-Z0-9.-]+$', new_endpoint):
        return False, "Endpoint contains invalid characters."

    if not os.path.exists(WG_CONF):
        return False, "WireGuard configuration not found."

    old_port = None

    try:
        with open(WG_CONF, "r") as f:
            lines = f.readlines()

        new_lines = []
        endpoint_found = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# ENDPOINT"):
                new_lines.append(f"# ENDPOINT {new_endpoint}\n")
                endpoint_found = True
            elif stripped.startswith("ListenPort"):
                parts = stripped.split("=")
                if len(parts) >= 2:
                    old_port = parts[1].strip()
                new_lines.append(f"ListenPort = {new_port}\n")
            else:
                new_lines.append(line)

        if not endpoint_found:
            new_lines.insert(0, f"# ENDPOINT {new_endpoint}\n")

        with open(WG_CONF, "w") as f:
            f.writelines(new_lines)

    except Exception as e:
        return False, f"Failed to update wg0.conf: {e}"

    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO server_settings (key, value) VALUES ('endpoint', ?)", (new_endpoint,))
        conn.execute("INSERT OR REPLACE INTO server_settings (key, value) VALUES ('listen_port', ?)", (str(new_port),))
        conn.commit()

    if IS_LINUX_ROOT:
        run_cmd(["wg", "set", "wg0", "listen-port", str(new_port)])

        if str(old_port) != str(new_port):
            if run_cmd(["systemctl", "is-active", "--quiet", "firewalld.service"])[0] == 0:
                run_cmd(["firewall-cmd", "--permanent", "--add-port=" + str(new_port) + "/udp"])
                if old_port:
                    run_cmd(["firewall-cmd", "--permanent", "--remove-port=" + str(old_port) + "/udp"])
                run_cmd(["firewall-cmd", "--reload"])
            elif run_cmd(["command", "-v", "ufw"])[0] == 0 and "active" in run_cmd(["ufw", "status"])[1]:
                run_cmd(["ufw", "allow", f"{new_port}/udp"])
            elif run_cmd(["command", "-v", "iptables"])[0] == 0:
                run_cmd(["iptables", "-I", "INPUT", "-p", "udp", "--dport", str(new_port), "-j", "ACCEPT"])

    if update_clients and os.path.exists(CLIENT_DIR):
        try:
            for fname in os.listdir(CLIENT_DIR):
                if fname.endswith(".conf"):
                    cpath = os.path.join(CLIENT_DIR, fname)
                    with open(cpath, "r") as f:
                        c_content = f.read()
                    updated_c = re.sub(r'Endpoint\s*=\s*[^\s:]+:\d+', f'Endpoint = {new_endpoint}:{new_port}', c_content)
                    if updated_c != c_content:
                        with open(cpath, "w") as f:
                            f.write(updated_c)
        except Exception as e:
            print(f"Error updating client configs: {e}", file=sys.stderr)

    log_audit("server_settings_updated", f"Endpoint: {new_endpoint}, Port: {new_port}")
    return True, f"Endpoint set to {new_endpoint} and port set to {new_port} successfully."
