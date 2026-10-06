"""
Web application HTTP server and API routing for WireGuard Dashboard.
Serves modular templates, static assets, and handles RESTful API endpoints.
"""
import http.server
import socketserver
import json
import os
import sys
import urllib.parse
from src.config import PORT, HOST, STATIC_DIR, TEMPLATES_DIR, CLIENT_DIR
from src.db import (
    init_db, log_audit, get_audit_logs,
    get_dns_presets, create_dns_preset, delete_dns_preset,
    get_server_setting, set_server_setting
)
from src.auth import (
    verify_pw, create_session, is_valid_session, delete_session, change_pw
)
from src.wireguard import (
    ensure_demo_setup, get_server_status, get_peers,
    add_peer, delete_peer, update_peer, update_server_endpoint_and_port,
    get_client_qr_svg, get_client_conf_content, detect_server_public_ip
)

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".conf": "text/plain; charset=utf-8"
}

class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Keep server logs tidy
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def is_authenticated(self):
        cookie = self.headers.get("Cookie", "")
        for item in cookie.split(";"):
            item = item.strip()
            if item.startswith("wg_session="):
                token = item.split("=", 1)[1]
                return is_valid_session(token)
        return False

    def serve_static(self, rel_path):
        clean_path = os.path.normpath(rel_path.lstrip("/\\"))
        if clean_path.startswith(".."):
            self.send_error(403, "Forbidden")
            return
        
        full_path = os.path.join(STATIC_DIR, clean_path)
        if not os.path.isfile(full_path):
            self.send_error(404, "Static file not found")
            return

        ext = os.path.splitext(full_path)[1].lower()
        content_type = MIME_TYPES.get(ext, "application/octet-stream")

        try:
            with open(full_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            if ext in (".css", ".js", ".html"):
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
            else:
                self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Error reading file: {e}")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # 1. Main HTML Interface
        if path == "/" or path == "/index.html":
            index_file = os.path.join(TEMPLATES_DIR, "index.html")
            try:
                with open(index_file, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_error(500, f"Error loading index template: {e}")
            return

        # 2. Static Assets
        if path.startswith("/static/"):
            static_subpath = path[len("/static/"):]
            self.serve_static(static_subpath)
            return

        # 3. API - Check Auth status
        if path == "/api/check-auth":
            auth = self.is_authenticated()
            return self.send_json({"authenticated": auth})

        # 4. Protected API Routes
        if not self.is_authenticated():
            return self.send_json({"error": "Unauthorized"}, 401)

        if path == "/api/status":
            status = get_server_status()
            return self.send_json(status)

        elif path == "/api/peers":
            peers = get_peers()
            return self.send_json({"peers": peers})

        elif (path.startswith("/api/peers/") and (path.endswith("/config") or path.endswith("/download"))) or path.startswith("/api/download/"):
            if path.startswith("/api/download/"):
                client_name = urllib.parse.unquote(path[len("/api/download/"):].strip("/"))
                if client_name.endswith(".conf"):
                    client_name = client_name[:-5]
                is_download = True
            else:
                parts = path.strip("/").split("/")
                client_name = urllib.parse.unquote(parts[2]) if len(parts) >= 3 else ""
                is_download = path.endswith("/download")

            if client_name:
                conf_data = get_client_conf_content(client_name)
                if conf_data:
                    encoded = conf_data.encode("utf-8")
                    self.send_response(200)
                    content_type = "application/octet-stream" if is_download else "text/plain; charset=utf-8"
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Disposition", f'attachment; filename="{client_name}.conf"')
                    self.send_header("Content-Length", str(len(encoded)))
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.send_header("Pragma", "no-cache")
                    self.send_header("Expires", "0")
                    self.end_headers()
                    self.wfile.write(encoded)
                    return
            return self.send_json({"error": "Config not found"}, 404)

        elif path == "/api/dns-presets":
            presets = get_dns_presets()
            return self.send_json({"presets": presets})

        elif path == "/api/audit-logs":
            logs = get_audit_logs()
            return self.send_json({"logs": logs})

        elif path == "/api/server-settings":
            status = get_server_status()
            return self.send_json({
                "endpoint": status["endpoint"],
                "listen_port": status["listen_port"]
            })

        elif path == "/api/detect-ip":
            ip = detect_server_public_ip()
            if ip:
                return self.send_json({"success": True, "ip": ip})
            else:
                return self.send_json({"success": False, "error": "Could not determine server public IP from external providers."}, 500)

        self.send_error(404, "API route not found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
        try:
            req_data = json.loads(body) if body else {}
        except Exception:
            req_data = {}

        if path == "/api/login":
            username = req_data.get("username", "admin").strip() or "admin"
            password = req_data.get("password", "")
            if verify_pw(password, username):
                token = create_session()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Set-Cookie", f"wg_session={token}; Path=/; HttpOnly; SameSite=Lax")
                res = json.dumps({"success": True}).encode("utf-8")
                self.send_header("Content-Length", str(len(res)))
                self.end_headers()
                self.wfile.write(res)
                log_audit("login_success", f"User '{username}' logged in successfully")
            else:
                log_audit("login_failed", f"Failed login attempt for user '{username}'")
                self.send_json({"error": "Incorrect username or password"}, 401)

        elif path == "/api/logout":
            cookie = self.headers.get("Cookie", "")
            for item in cookie.split(";"):
                item = item.strip()
                if item.startswith("wg_session="):
                    token = item.split("=", 1)[1]
                    delete_session(token)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie", "wg_session=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT")
            res = json.dumps({"success": True}).encode("utf-8")
            self.send_header("Content-Length", str(len(res)))
            self.end_headers()
            self.wfile.write(res)

        elif path == "/api/peers":
            if not self.is_authenticated():
                return self.send_json({"error": "Unauthorized"}, 401)
            name = req_data.get("name", "").strip()
            dns = req_data.get("dns", "1.1.1.1, 1.0.0.1").strip()
            save_preset = req_data.get("save_preset", False)
            preset_name = req_data.get("preset_name", "").strip()

            if save_preset and preset_name:
                import re
                preset_id = "custom_" + re.sub(r'[^a-zA-Z0-9]', '_', preset_name.lower())
                create_dns_preset(preset_id, preset_name, dns)

            ok, msg = add_peer(name, dns)
            return self.send_json({"success": ok, "message": msg}, 200 if ok else 400)

        elif path == "/api/dns-presets":
            if not self.is_authenticated():
                return self.send_json({"error": "Unauthorized"}, 401)
            name = req_data.get("name", "").strip()
            value = req_data.get("value", "").strip()
            if not name or not value:
                return self.send_json({"error": "Name and Value are required"}, 400)
            import re
            preset_id = "custom_" + re.sub(r'[^a-zA-Z0-9]', '_', name.lower())
            create_dns_preset(preset_id, name, value)
            return self.send_json({"success": True, "message": f"DNS preset '{name}' created"})

        elif path == "/api/server-settings":
            if not self.is_authenticated():
                return self.send_json({"error": "Unauthorized"}, 401)
            endpoint = req_data.get("endpoint", "")
            port = req_data.get("port", "")
            update_clients = req_data.get("update_clients", True)
            ok, msg = update_server_endpoint_and_port(endpoint, port, update_clients=update_clients)
            return self.send_json({"success": ok, "message": msg}, 200 if ok else 400)

        elif path == "/api/change-password":
            if not self.is_authenticated():
                return self.send_json({"error": "Unauthorized"}, 401)
            old_pw = req_data.get("old_password", "")
            new_pw = req_data.get("new_password", "")
            ok, msg = change_pw(old_pw, new_pw)
            return self.send_json({"success": ok, "message": msg}, 200 if ok else 400)

        elif path.startswith("/api/peers/") and (path.endswith("/settings") or path.endswith("/update")):
            if not self.is_authenticated():
                return self.send_json({"error": "Unauthorized"}, 401)
            parts = path.strip("/").split("/")
            if len(parts) >= 3:
                client_name = urllib.parse.unquote(parts[2])
                allowed_ips = req_data.get("allowed_ips", "").strip()
                ok, msg = update_peer(client_name, allowed_ips)
                return self.send_json({"success": ok, "message": msg}, 200 if ok else 400)
            return self.send_json({"error": "Invalid client request"}, 400)

        else:
            self.send_error(404, "Endpoint not found")

    def do_DELETE(self):
        if not self.is_authenticated():
            return self.send_json({"error": "Unauthorized"}, 401)

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/peers/"):
            parts = path.strip("/").split("/")
            if len(parts) == 3:
                name = parts[2]
                ok, msg = delete_peer(name)
                return self.send_json({"success": ok, "message": msg}, 200 if ok else 400)

        elif path.startswith("/api/dns-presets/"):
            parts = path.strip("/").split("/")
            if len(parts) == 3:
                preset_id = parts[2]
                delete_dns_preset(preset_id)
                return self.send_json({"success": True, "message": "Preset deleted"})

        self.send_error(404, "Endpoint not found")

class ReusableThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

def main():
    init_db()
    ensure_demo_setup()
    server = ReusableThreadingServer((HOST, PORT), DashboardHandler)
    print(f"WireGuard Dashboard running at http://{HOST}:{PORT}")
    print("Default credentials: admin / admin")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        server.server_close()

if __name__ == "__main__":
    main()
