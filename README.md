# WireGuard Web Dashboard

Web-based management dashboard for WireGuard VPN server. Built with Python 3 (standard library only — no pip dependencies), AdminLTE 4, and SQLite.

---

## Requirements

| Requirement | Minimum |
|---|---|
| OS | Ubuntu 22.04+ / Debian 11+ / CentOS 9+ / AlmaLinux 9+ / Fedora |
| Python | 3.8+ |
| Access | Root (`sudo`) |

---

## Deployment

### Step 1 — Upload project to server

```bash
scp -r ./wireguard-project root@YOUR_SERVER_IP:/opt/wg-dashboard
```

Or clone from your Git repository:

```bash
cd /opt
git clone https://your-repo-url.git wg-dashboard
```

### Step 2 — Install WireGuard

```bash
cd /opt/wg-dashboard
sudo bash wireguard-install.sh
```

This script will automatically:
- Detect your OS and install WireGuard
- Configure the server network interface, keys, and firewall
- Generate `/etc/wireguard/wg0.conf`
- Enable and start the `wg-quick@wg0` service

### Step 3 — Install the Web Dashboard

```bash
sudo bash install-gui.sh
```

You will be prompted for:
- **Dashboard port** (default: `5000`)
- **Admin password** (default: `admin`)

The installer will:
- Copy the app to `/opt/wg-dashboard`
- Create and start a systemd service (`wg-dashboard.service`)
- Open the firewall port

### Step 4 — Access the Dashboard

Open your browser and navigate to:

```
http://YOUR_SERVER_IP:5000
```

Default login credentials:

| Field | Value |
|---|---|
| Username | `admin` |
| Password | `admin` (or the password you set during install) |

> **Important:** Change the default password immediately via the user menu.

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `WG_GUI_PORT` | `5000` | Dashboard HTTP port |
| `WG_GUI_HOST` | `0.0.0.0` | Bind address |

To change the port after installation:

```bash
sudo systemctl edit wg-dashboard.service
```

Add:

```ini
[Service]
Environment=WG_GUI_PORT=8080
```

Then reload:

```bash
sudo systemctl daemon-reload
sudo systemctl restart wg-dashboard
```

---

## File Locations

| File | Path |
|---|---|
| WireGuard config | `/etc/wireguard/wg0.conf` |
| Client configs | `/home/wireguard/*.conf` |
| SQLite database | `/etc/wireguard/dashboard.db` |
| Dashboard app | `/opt/wg-dashboard/` |
| Systemd service | `/etc/systemd/system/wg-dashboard.service` |

---

## Service Management

```bash
# Check status
sudo systemctl status wg-dashboard

# Restart
sudo systemctl restart wg-dashboard

# View logs
sudo journalctl -u wg-dashboard -f

# Stop
sudo systemctl stop wg-dashboard

# Check WireGuard status
sudo wg show

# Restart WireGuard interface
sudo systemctl restart wg-quick@wg0
```

---

## HTTPS with Reverse Proxy (Optional)

For production use, place the dashboard behind Nginx with SSL:

```nginx
server {
    listen 443 ssl;
    server_name vpn.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/vpn.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/vpn.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

When using a reverse proxy, bind the dashboard to localhost only:

```bash
Environment=WG_GUI_HOST=127.0.0.1
```

---

## Updating

```bash
cd /opt/wg-dashboard
git pull origin main
sudo systemctl restart wg-dashboard
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Port already in use | Change `WG_GUI_PORT` to a different port |
| Cannot access from outside | Check firewall: `sudo ufw status` or `firewall-cmd --list-ports` |
| WireGuard not active | Run: `sudo systemctl start wg-quick@wg0` |
| Permission denied | Must run as root: `sudo python3 wg-dashboard.py` |
| Database error | Remove and let it recreate: `rm /etc/wireguard/dashboard.db && sudo systemctl restart wg-dashboard` |
