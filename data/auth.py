"""
Auth helpers: username/password signup + login using bcrypt + Supabase users table.
Username can be any printable characters (letters, digits, symbols).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

import bcrypt

from data.supabase_client import get_supabase

_USERNAME_RE = re.compile(r'^[\w!@#$%^&*()\-+=\[\]{};:\'",.<>?/\\|`~]{2,64}$')


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


# ── User operations ───────────────────────────────────────────────────────────

def validate_username(username: str) -> Optional[str]:
    """Return an error string or None if valid."""
    if not username:
        return "Username is required."
    if len(username) < 2:
        return "Username must be at least 2 characters."
    if len(username) > 64:
        return "Username must be 64 characters or fewer."
    if not _USERNAME_RE.match(username):
        return "Username contains invalid characters."
    return None


def validate_password(password: str) -> Optional[str]:
    if not password:
        return "Password is required."
    if len(password) < 6:
        return "Password must be at least 6 characters."
    return None


def create_user(username: str, password: str) -> tuple[Optional[dict], Optional[str]]:
    """
    Create a new user. Returns (user_dict, None) on success or (None, error_str) on failure.
    """
    sb = get_supabase()

    err = validate_username(username)
    if err:
        return None, err
    err = validate_password(password)
    if err:
        return None, err

    # Check uniqueness (case-insensitive)
    existing = sb.table("users").select("id").ilike("username", username).execute()
    if existing.data:
        return None, "That ID is already taken — pick another."

    pw_hash = hash_password(password)
    res = sb.table("users").insert({
        "username": username,
        "password_hash": pw_hash,
        "created_at": _now_iso(),
    }).execute()

    if not res.data:
        return None, "Database error — could not create account."

    user = res.data[0]
    uid = user["id"]

    # Bootstrap related rows (best-effort)
    try:
        sb.table("profiles").insert({"user_id": uid}).execute()
    except Exception:
        pass
    try:
        sb.table("tv_config").insert({"user_id": uid}).execute()
    except Exception:
        pass

    return user, None


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Return the user dict on success, None on failure."""
    sb = get_supabase()
    res = sb.table("users").select("*").ilike("username", username).limit(1).execute()
    if not res.data:
        return None
    user = res.data[0]
    if not verify_password(password, user["password_hash"]):
        return None
    # Update last sign in (fire-and-forget)
    try:
        sb.table("users").update({"last_sign_in": _now_iso()}).eq("id", user["id"]).execute()
    except Exception:
        pass
    return user


def get_user(user_id: str) -> Optional[dict]:
    sb = get_supabase()
    try:
        res = sb.table("users").select("id, username, created_at, last_sign_in").eq("id", user_id).single().execute()
        return res.data
    except Exception:
        return None
