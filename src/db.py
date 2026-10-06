"""
Database layer for WireGuard Web Dashboard.
Manages SQLite connections, schema migrations, audit logs, server settings, and DNS presets.
"""
import os
import sqlite3
import hashlib
import secrets
from src.config import DATA_DIR, CLIENT_DIR, DB_FILE, DEFAULT_DNS_PRESETS

def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def hash_pw(password, salt=None):
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
    return salt, hashed

def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(CLIENT_DIR, exist_ok=True)
    with get_db() as conn:
        cursor = conn.cursor()

        # Admin user credentials
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Persistent user sessions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at REAL NOT NULL
            )
        """)

        # Server key-value settings
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS server_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # DNS Presets
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dns_presets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                value TEXT NOT NULL,
                is_default INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Peer tracking and metadata
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS peers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                public_key TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                dns TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # System and admin audit logs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create default admin user if none exists
        cursor.execute("SELECT COUNT(*) as cnt FROM admin_users")
        if cursor.fetchone()["cnt"] == 0:
            salt, hashed = hash_pw("admin")
            cursor.execute("INSERT INTO admin_users (username, password_hash, salt) VALUES ('admin', ?, ?)", (hashed, salt))
            cursor.execute("INSERT INTO audit_logs (action, details) VALUES ('system_init', 'Default admin account created')")

        # Populate default DNS presets if none exist
        cursor.execute("SELECT COUNT(*) as cnt FROM dns_presets")
        if cursor.fetchone()["cnt"] == 0:
            for preset in DEFAULT_DNS_PRESETS:
                cursor.execute(
                    "INSERT INTO dns_presets (id, name, value, is_default) VALUES (?, ?, ?, 1)",
                    (preset["id"], preset["name"], preset["value"])
                )

        # Ensure peers columns compatibility
        cursor.execute("PRAGMA table_info(peers)")
        peer_cols = [r[1] for r in cursor.fetchall()]
        if peer_cols and "ip_address" not in peer_cols:
            cursor.execute("ALTER TABLE peers ADD COLUMN ip_address TEXT")
        if peer_cols and "allowed_ips" not in peer_cols:
            cursor.execute("ALTER TABLE peers ADD COLUMN allowed_ips TEXT")

        conn.commit()

    if os.name != "nt":
        try:
            os.chmod(DB_FILE, 0o600)
        except Exception:
            pass

def log_audit(action, details=""):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(audit_logs)")
            cols = [r[1] for r in cursor.fetchall()]
            col_name = "details" if "details" in cols else "detail"
            conn.execute(f"INSERT INTO audit_logs (action, {col_name}) VALUES (?, ?)", (action, details))
            conn.commit()
    except Exception:
        pass

def get_audit_logs(limit=50):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(audit_logs)")
        cols = [r[1] for r in cursor.fetchall()]
        col_name = "details" if "details" in cols else "detail"
        cursor.execute(f"SELECT id, action, {col_name} AS detail, {col_name} AS details, timestamp FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in cursor.fetchall()]

def get_dns_presets():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, value, is_default FROM dns_presets ORDER BY is_default DESC, name ASC")
        return [dict(r) for r in cursor.fetchall()]

def create_dns_preset(preset_id, name, value):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO dns_presets (id, name, value, is_default) VALUES (?, ?, ?, 0)", (preset_id, name, value))
        conn.commit()
        log_audit("dns_preset_created", f"Created DNS preset: {name} ({value})")

def delete_dns_preset(preset_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM dns_presets WHERE id = ? AND is_default = 0", (preset_id,))
        conn.commit()
        log_audit("dns_preset_deleted", f"Deleted DNS preset ID: {preset_id}")

def get_server_setting(key, default=None):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM server_settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default

def set_server_setting(key, value):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO server_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP", (key, str(value)))
        conn.commit()
