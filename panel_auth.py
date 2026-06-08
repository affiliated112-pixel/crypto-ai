"""panel_auth.py — authentication & user management for the web panel.

Storage: a single JSON file (panel_users.json) next to this module.
No external dependencies — uses only Python stdlib (hashlib, hmac, secrets, json).

User record schema:
    {
      "username": str,
      "pw_hash": str,          # hex — pbkdf2_hmac sha256
      "pw_salt": str,          # hex
      "role": "master"|"admin"|"user",
      "status": "active"|"pending"|"rejected",
      "created_at": str,       # ISO UTC
      "approved_by": str|null,
      "approved_at": str|null,
    }

Token: HMAC-SHA256 signed, base64url-encoded JSON payload {u, r, exp}.
Cookie name: rcb_sess
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── constants ────────────────────────────────────────────────────────────────

COOKIE_NAME = "rcb_sess"
_TOKEN_TTL = 60 * 60 * 24 * 7        # 7 days in seconds
_MAX_ATTEMPTS = 6
_LOCKOUT_SECONDS = 900                # 15 min
_PBKDF2_ITERS = 260_000

# ── storage paths ─────────────────────────────────────────────────────────────

_HERE = Path(__file__).parent
_USERS_FILE = _HERE / "panel_users.json"
_SECRET_FILE = _HERE / "panel_secret.key"

# ── in-memory state ───────────────────────────────────────────────────────────

_lock = threading.Lock()
_users: dict[str, dict] = {}          # username → record
_failures: dict[str, list[float]] = {}   # ip → [timestamps]

# ── secret key (persisted across restarts) ────────────────────────────────────

def _load_secret() -> bytes:
    env_key = os.environ.get("PANEL_SECRET_KEY", "").strip()
    if len(env_key) >= 32:
        return env_key.encode()
    if _SECRET_FILE.is_file():
        try:
            return _SECRET_FILE.read_bytes().strip()
        except Exception:
            pass
    key = secrets.token_bytes(48)
    try:
        _SECRET_FILE.write_bytes(key)
    except Exception:
        pass
    return key

_SECRET = _load_secret()

# ── persistence helpers ───────────────────────────────────────────────────────

def _save_users() -> None:
    """Persist _users to disk (must be called with _lock held)."""
    try:
        tmp = _USERS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(list(_users.values()), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_USERS_FILE)
    except Exception as exc:
        print(f"[panel_auth] save error: {exc}", flush=True)

def _load_users() -> None:
    """Load users from disk into _users (must be called with _lock held)."""
    global _users
    if not _USERS_FILE.is_file():
        return
    try:
        data = json.loads(_USERS_FILE.read_text(encoding="utf-8"))
        _users = {rec["username"]: rec for rec in data if isinstance(rec, dict) and "username" in rec}
    except Exception as exc:
        print(f"[panel_auth] load error: {exc}", flush=True)

def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()

# ── password helpers ──────────────────────────────────────────────────────────

def _hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """Return (pw_hash_hex, salt_hex)."""
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        _PBKDF2_ITERS,
    )
    return dk.hex(), salt

def _check_password(password: str, pw_hash: str, salt: str) -> bool:
    dk, _ = _hash_password(password, salt=salt)
    return hmac.compare_digest(dk, pw_hash)

# ── token helpers ─────────────────────────────────────────────────────────────

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _sign(payload_bytes: bytes) -> str:
    sig = hmac.new(_SECRET, payload_bytes, hashlib.sha256).digest()
    return _b64url(payload_bytes) + "." + _b64url(sig)

def _verify_sig(token: str) -> Optional[bytes]:
    """Return payload bytes if signature valid, else None."""
    try:
        parts = token.rsplit(".", 1)
        if len(parts) != 2:
            return None
        payload_b64, sig_b64 = parts
        payload_bytes = base64.urlsafe_b64decode(payload_b64 + "==")
        expected_sig = hmac.new(_SECRET, payload_bytes, hashlib.sha256).digest()
        given_sig = base64.urlsafe_b64decode(sig_b64 + "==")
        if not hmac.compare_digest(expected_sig, given_sig):
            return None
        return payload_bytes
    except Exception:
        return None

def create_token(username: str, role: str) -> str:
    """Create a signed session token."""
    payload = json.dumps({"u": username, "r": role, "exp": int(time.time()) + _TOKEN_TTL}, separators=(",", ":")).encode()
    return _sign(payload)

def verify_token(token: str) -> Optional[dict]:
    """Return {u, r} if token valid and not expired, else None."""
    if not token:
        return None
    payload_bytes = _verify_sig(token)
    if not payload_bytes:
        return None
    try:
        data = json.loads(payload_bytes.decode())
        if data.get("exp", 0) < time.time():
            return None
        return {"u": data["u"], "r": data["r"]}
    except Exception:
        return None

# ── cookie helpers ────────────────────────────────────────────────────────────

def make_set_cookie(token: str, secure: bool = True) -> str:
    flags = "HttpOnly; SameSite=Lax; Path=/"
    if secure:
        flags += "; Secure"
    max_age = _TOKEN_TTL
    return f"{COOKIE_NAME}={token}; Max-Age={max_age}; {flags}"

def make_clear_cookie(secure: bool = True) -> str:
    flags = "HttpOnly; SameSite=Lax; Path=/"
    if secure:
        flags += "; Secure"
    return f"{COOKIE_NAME}=; Max-Age=0; {flags}"

def parse_cookie(cookie_header: str) -> dict:
    """Parse a raw Cookie header into a dict."""
    result: dict[str, str] = {}
    for part in (cookie_header or "").split(";"):
        if "=" in part:
            k, _, v = part.strip().partition("=")
            result[k.strip()] = v.strip()
    return result

# ── brute-force protection ────────────────────────────────────────────────────

def is_locked(ip: str) -> bool:
    now = time.time()
    window = _failures.get(ip, [])
    recent = [t for t in window if now - t < _LOCKOUT_SECONDS]
    return len(recent) >= _MAX_ATTEMPTS

def record_failure(ip: str) -> None:
    now = time.time()
    window = _failures.setdefault(ip, [])
    window.append(now)
    # keep only last hour
    _failures[ip] = [t for t in window if now - t < 3600]

def reset_attempts(ip: str) -> None:
    _failures.pop(ip, None)

def attempts_left(ip: str) -> int:
    now = time.time()
    recent = [t for t in _failures.get(ip, []) if now - t < _LOCKOUT_SECONDS]
    return max(0, _MAX_ATTEMPTS - len(recent))

# ── user management ───────────────────────────────────────────────────────────

def _ensure_master() -> None:
    """Create the master admin account if it doesn't exist yet."""
    master_user = os.environ.get("PANEL_ADMIN_USER", "admin").strip().lower()
    master_pass = os.environ.get("PANEL_ADMIN_PASS", "admin1234").strip()
    if master_user not in _users:
        pw_hash, salt = _hash_password(master_pass)
        _users[master_user] = {
            "username": master_user,
            "pw_hash": pw_hash,
            "pw_salt": salt,
            "role": "master",
            "status": "active",
            "created_at": _utcnow(),
            "approved_by": "system",
            "approved_at": _utcnow(),
        }
        _save_users()
        print(f"[panel_auth] Master account created: {master_user}", flush=True)
    else:
        # Always keep master role and active status for the master account.
        rec = _users[master_user]
        changed = False
        if rec.get("role") != "master":
            rec["role"] = "master"
            changed = True
        if rec.get("status") != "active":
            rec["status"] = "active"
            changed = True
        if changed:
            _save_users()

def _init() -> None:
    with _lock:
        _load_users()
        _ensure_master()

def register_user(username: str, password: str, ip: str = "") -> tuple[bool, str]:
    """Register a new user (status=pending, awaiting admin approval)."""
    username = username.strip().lower()
    if len(username) < 3:
        return False, "Username prea scurt (minim 3 caractere)."
    if len(username) > 32:
        return False, "Username prea lung (maxim 32 caractere)."
    import re
    if not re.match(r'^[a-z0-9._\-]+$', username):
        return False, "Username poate conține doar litere, cifre, _, -, ."
    if len(password) < 6:
        return False, "Parola prea scurtă (minim 6 caractere)."
    with _lock:
        if username in _users:
            return False, "Username-ul este deja folosit."
        pw_hash, salt = _hash_password(password)
        _users[username] = {
            "username": username,
            "pw_hash": pw_hash,
            "pw_salt": salt,
            "role": "user",
            "status": "pending",
            "created_at": _utcnow(),
            "approved_by": None,
            "approved_at": None,
            "reg_ip": ip,
        }
        _save_users()
    print(f"[panel_auth] New registration: {username} from {ip}", flush=True)
    return True, "Cont creat cu succes! Așteaptă aprobarea unui administrator."

def check_credentials(username: str, password: str) -> tuple[bool, str]:
    """Return (ok, role). Role is empty string if not ok."""
    username = username.strip().lower()
    with _lock:
        rec = _users.get(username)
    if not rec:
        # Constant-time dummy to avoid user enumeration.
        _hash_password("dummy_constant_time_check")
        return False, ""
    if rec.get("status") != "active":
        return False, ""
    if not _check_password(password, rec["pw_hash"], rec["pw_salt"]):
        return False, ""
    return True, rec.get("role", "user")

def approve_user(username: str, by: str) -> tuple[bool, str]:
    username = username.strip().lower()
    with _lock:
        rec = _users.get(username)
        if not rec:
            return False, "Utilizatorul nu există."
        if rec.get("status") == "active":
            return False, "Contul este deja activ."
        rec["status"] = "active"
        rec["approved_by"] = by
        rec["approved_at"] = _utcnow()
        _save_users()
    print(f"[panel_auth] Approved: {username} by {by}", flush=True)
    return True, f"Contul '{username}' a fost aprobat."

def reject_user(username: str, by: str) -> tuple[bool, str]:
    username = username.strip().lower()
    with _lock:
        rec = _users.get(username)
        if not rec:
            return False, "Utilizatorul nu există."
        if rec.get("role") == "master":
            return False, "Nu poți respinge contul master."
        rec["status"] = "rejected"
        rec["approved_by"] = by
        rec["approved_at"] = _utcnow()
        _save_users()
    print(f"[panel_auth] Rejected: {username} by {by}", flush=True)
    return True, f"Contul '{username}' a fost respins."

def delete_user(username: str) -> tuple[bool, str]:
    username = username.strip().lower()
    with _lock:
        rec = _users.get(username)
        if not rec:
            return False, "Utilizatorul nu există."
        if rec.get("role") == "master":
            return False, "Nu poți șterge contul master."
        del _users[username]
        _save_users()
    print(f"[panel_auth] Deleted: {username}", flush=True)
    return True, f"Contul '{username}' a fost șters."

def list_accounts() -> list[dict]:
    """Return all accounts (without pw_hash/pw_salt) sorted by status."""
    with _lock:
        records = list(_users.values())
    safe = []
    for rec in records:
        safe.append({k: v for k, v in rec.items() if k not in ("pw_hash", "pw_salt")})
    # pending first, then active, then rejected
    order = {"pending": 0, "active": 1, "rejected": 2}
    safe.sort(key=lambda r: (order.get(r.get("status", ""), 9), r.get("created_at", "")))
    return safe

def change_password(username: str, new_password: str) -> tuple[bool, str]:
    username = username.strip().lower()
    if len(new_password) < 6:
        return False, "Parola prea scurtă."
    with _lock:
        rec = _users.get(username)
        if not rec:
            return False, "Utilizatorul nu există."
        pw_hash, salt = _hash_password(new_password)
        rec["pw_hash"] = pw_hash
        rec["pw_salt"] = salt
        _save_users()
    return True, "Parola a fost schimbată."

# ── module init ───────────────────────────────────────────────────────────────
_init()
print(f"[panel_auth] Loaded. Users: {len(_users)}  Master: {os.environ.get('PANEL_ADMIN_USER', 'admin')}", flush=True)
