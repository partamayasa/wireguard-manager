"""
Configuration and Path definitions for WireGuard Web Dashboard.
"""
import os
import sys

PORT = int(os.environ.get("WG_GUI_PORT", 5000))
HOST = os.environ.get("WG_GUI_HOST", "0.0.0.0")

IS_WINDOWS = os.name == "nt"
IS_LINUX_ROOT = not IS_WINDOWS and hasattr(os, "geteuid") and os.geteuid() == 0 and os.path.exists("/etc/wireguard")

# Project directories
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SRC_DIR)
TEMPLATES_DIR = os.path.join(SRC_DIR, "templates")
STATIC_DIR = os.path.join(SRC_DIR, "static")

DATA_DIR = "/etc/wireguard" if IS_LINUX_ROOT else os.path.join(BASE_DIR, "data")
CLIENT_DIR = "/home/wireguard" if IS_LINUX_ROOT else os.path.join(DATA_DIR, "clients")
WG_CONF = os.path.join(DATA_DIR, "wg0.conf")
DB_FILE = os.path.join(DATA_DIR, "dashboard.db")

DEFAULT_DNS_PRESETS = [
    {"id": "cloudflare", "name": "Cloudflare", "value": "1.1.1.1, 1.0.0.1"},
    {"id": "google", "name": "Google", "value": "8.8.8.8, 8.8.4.4"},
    {"id": "quad9", "name": "Quad9", "value": "9.9.9.9, 149.112.112.112"},
    {"id": "adguard", "name": "AdGuard DNS", "value": "94.140.14.14, 94.140.15.15"},
    {"id": "opendns", "name": "OpenDNS", "value": "208.67.222.222, 208.67.220.220"}
]
