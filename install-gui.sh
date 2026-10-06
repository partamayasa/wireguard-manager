#!/bin/bash
#
# Installer for WireGuard Web Dashboard Service
#

if [[ "$EUID" -ne 0 ]]; then
	echo "This installer must be run with superuser (root / sudo) privileges."
	exit 1
fi

echo "WireGuard Web GUI Dashboard Installer"
echo

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# 1. Ensure Python 3 is installed
if ! command -v python3 &>/dev/null; then
	echo "Installing Python 3"
	if command -v apt-get &>/dev/null; then
		apt-get update && apt-get install -y python3
	elif command -v dnf &>/dev/null; then
		dnf install -y python3
	fi
fi

# 2. Port configuration
read -p "Enter port for Web GUI [5000]: " gui_port
gui_port=${gui_port:-5000}
until [[ "$gui_port" =~ ^[0-9]+$ && "$gui_port" -le 65535 ]]; do
	echo "Invalid port number."
	read -p "Enter port for Web GUI [5000]: " gui_port
	gui_port=${gui_port:-5000}
done

# 3. Admin password configuration
read -s -p "Enter Admin Password for Web GUI [default: admin]: " admin_pw
echo
admin_pw=${admin_pw:-admin}

# Copy dashboard application and modular src to /opt/wg-dashboard
mkdir -p /opt/wg-dashboard
cp "$SCRIPT_DIR/wg-dashboard.py" /opt/wg-dashboard/wg-dashboard.py
cp -r "$SCRIPT_DIR/src" /opt/wg-dashboard/
chmod +x /opt/wg-dashboard/wg-dashboard.py
ln -sf /opt/wg-dashboard/wg-dashboard.py /usr/local/bin/wg-dashboard.py

# Initialize SQLite database and credentials
mkdir -p /etc/wireguard
python3 -c "
import sys, os, sqlite3, hashlib, secrets
db_path = '/etc/wireguard/dashboard.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS admin_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')
salt = secrets.token_hex(16)
hashed = hashlib.pbkdf2_hmac('sha256', '$admin_pw'.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
c.execute('SELECT id FROM admin_users WHERE username = \"admin\"')
if c.fetchone():
    c.execute('UPDATE admin_users SET password_hash = ?, salt = ?, updated_at = CURRENT_TIMESTAMP WHERE username = \"admin\"', (hashed, salt))
else:
    c.execute('INSERT INTO admin_users (username, password_hash, salt) VALUES (\"admin\", ?, ?)', (hashed, salt))
conn.commit()
conn.close()
os.chmod(db_path, 0o600)
"


# 4. Create Systemd Service
cat << EOF > /etc/systemd/system/wg-dashboard.service
[Unit]
Description=WireGuard Web GUI Dashboard
After=network.target wg-quick@wg0.service

[Service]
Type=simple
User=root
WorkingDirectory=/etc/wireguard
Environment=WG_GUI_PORT=$gui_port
Environment=WG_GUI_HOST=0.0.0.0
ExecStart=/usr/bin/python3 /usr/local/bin/wg-dashboard.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 5. Configure Firewall
if systemctl is-active --quiet firewalld.service; then
	firewall-cmd --add-port="$gui_port"/tcp --permanent
	firewall-cmd --reload
elif command -v ufw &>/dev/null && ufw status | grep -qw "active"; then
	ufw allow "$gui_port"/tcp
elif command -v iptables &>/dev/null; then
	iptables -I INPUT -p tcp --dport "$gui_port" -j ACCEPT
fi

# 6. Enable and Start Service
systemctl daemon-reload
systemctl enable --now wg-dashboard.service

# Retrieve Public IP for display
public_ip=$(grep -m 1 -oE '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' <<< "$(wget -T 5 -t 1 -4qO- "https://api.ipify.org" 2>/dev/null || curl -m 5 -4Ls "https://api.ipify.org" 2>/dev/null || echo "SERVER_IP")")

echo
echo "WireGuard Web GUI Successfully Installed & Started!"
echo "Dashboard URL  : http://$public_ip:$gui_port"
echo "Admin Password : (the password you entered above)"
echo "Service Status : systemctl status wg-dashboard"

