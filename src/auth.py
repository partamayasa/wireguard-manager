"""
Authentication and session management module for WireGuard Web Dashboard.
"""
import time
import secrets
from src.db import get_db, hash_pw, log_audit

def verify_pw(password, username="admin"):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash, salt FROM admin_users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if not row:
            return False
        _, hashed = hash_pw(password, row["salt"])
        return secrets.compare_digest(hashed, row["password_hash"])

def create_session():
    token = secrets.token_hex(24)
    expires_at = time.time() + (86400 * 7) # 7 days
    with get_db() as conn:
        conn.execute("INSERT INTO sessions (token, expires_at) VALUES (?, ?)", (token, expires_at))
        conn.commit()
    return token

def is_valid_session(token):
    if not token:
        return False
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT expires_at FROM sessions WHERE token = ?", (token,))
        row = cursor.fetchone()
        if not row:
            return False
        if row["expires_at"] < time.time():
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
            return False
        return True

def delete_session(token):
    if not token:
        return
    with get_db() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()

def change_pw(old_pw, new_pw, username="admin"):
    if not verify_pw(old_pw, username):
        return False, "Current password incorrect"
    if len(new_pw) < 6:
        return False, "New password must be at least 6 characters"
    salt, hashed = hash_pw(new_pw)
    with get_db() as conn:
        conn.execute(
            "UPDATE admin_users SET password_hash = ?, salt = ?, updated_at = CURRENT_TIMESTAMP WHERE username = ?",
            (hashed, salt, username)
        )
        conn.commit()
    log_audit("password_changed", f"Password changed for user '{username}'")
    return True, "Password successfully changed"
