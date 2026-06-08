"""panel_auth.py — server-side authentication & security for the web panel.

Design goals (security first):
  * Passwords are NEVER stored or compared in plaintext. We use PBKDF2-HMAC-SHA256
    with a per-user random salt and constant-time comparison.
  * Sessions are stateless, signed tokens (HMAC-SHA256) with an expiry — they cannot
    be forged without the server SECRET_KEY.
  * The SECRET_KEY comes from the SECRET_KEY env var; if missing we generate one and
    persist it (so tokens survive restarts) — but you SHOULD set it in Railway.
  * Login is rate-limited per IP to stop brute-force attacks.
  * Admin self-registration requires a secret code (ADMIN_REGISTER_CODE) so randoms
    can't create admin accounts.

The bot's HTTP handler calls into this module; it has no Discord dependencies.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional

try:
    import db
except Exception:
    db = None

# ── tuning ──
PBKDF2_ROUNDS = 200_000
TOKEN_TTL_SECONDS = 60 * 60 * 8          # 8h session
LOGIN_MAX_ATTEMPTS = 6                    # per IP
LOGIN_WINDOW_SECONDS = 15 * 60           # lockout window
COOKIE_NAME = "rcs_session"

# ── in-memory brute-force tracker {ip: [timestamps]} ──
_ATTEMPTS: dict[str, list[float]] = {}

# ════════════════════════════════════════════════════════════
#   SECRET KEY
# ════════════════════════════════════════════════════════════
def _secret_key() -> bytes:
    env = os.environ.get("SECRET_KEY") or os.environ.get("PANEL_SECRET_KEY")
    if env and len(env) >= 16:
        return env.encode("utf-8")
    # fall back to a persisted random key so tokens survive restarts
    key = None
    if db is not None:
        try:
            key = db.get_state("panel_secret_key")
        except Exception:
            key = None
    if not key:
        key = secrets.token_hex(32)
        if db is not None:
            try:
                db.set_state("panel_secret_key", key)
            except Exception:
                pass
    return str(key).encode("utf-8")

# ════════════════════════════════════════════════════════════
#   PASSWORD HASHING
# ════════════════════════════════════════════════════════════
def hash_password(password: str, salt: Optional[str] = None) -> str:
    """Return 'pbkdf2$<rounds>$<salt_hex>$<hash_hex>'."""
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ROUNDS)
    return f"pbkdf2${PBKDF2_ROUNDS}${salt}${dk.hex()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt, hexhash = stored.split("$", 3)
        if algo != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(rounds))
        return hmac.compare_digest(dk.hex(), hexhash)
    except Exception:
        return False

# ════════════════════════════════════════════════════════════
#   ADMIN USER STORE  (env default + db-persisted extras)
# ════════════════════════════════════════════════════════════
def _default_admin() -> tuple[str, str]:
    """Primary admin from env, defaulting to admin / admin666."""
    user = os.environ.get("ADMIN_USERNAME", "admin").strip()
    pw = os.environ.get("ADMIN_PASSWORD", "admin666")
    return user, pw

def _load_admins() -> dict:
    """Return {username_lower: password_hash} for registered (extra) admins."""
    if db is None:
        return {}
    try:
        data = db.get_state("panel_admins")
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}

def _save_admins(admins: dict) -> None:
    if db is not None:
        try:
            db.set_state("panel_admins", admins)
        except Exception:
            pass

def check_credentials(username: str, password: str) -> bool:
    username = (username or "").strip()
    password = password or ""
    if not username or not password:
        return False
    # 1) primary env admin (constant-time on both fields)
    d_user, d_pass = _default_admin()
    user_ok = hmac.compare_digest(username.lower().encode(), d_user.lower().encode())
    pass_ok = hmac.compare_digest(password.encode(), d_pass.encode())
    if user_ok and pass_ok:
        return True
    # 2) extra registered admins (hashed)
    admins = _load_admins()
    stored = admins.get(username.lower())
    if stored and verify_password(password, stored):
        return True
    return False

def register_admin(username: str, password: str, code: str) -> tuple[bool, str]:
    """Create an extra admin. Requires the ADMIN_REGISTER_CODE secret."""
    expected = os.environ.get("ADMIN_REGISTER_CODE", "").strip()
    if not expected:
        return False, "Înregistrarea este dezactivată (lipsește ADMIN_REGISTER_CODE)."
    if not hmac.compare_digest((code or "").strip().encode(), expected.encode()):
        return False, "Cod de înregistrare invalid."
    username = (username or "").strip()
    password = password or ""
    if len(username) < 3:
        return False, "Username prea scurt (min 3 caractere)."
    if len(password) < 6:
        return False, "Parolă prea scurtă (min 6 caractere)."
    d_user, _ = _default_admin()
    if username.lower() == d_user.lower():
        return False, "Username rezervat."
    admins = _load_admins()
    if username.lower() in admins:
        return False, "Username deja folosit."
    admins[username.lower()] = hash_password(password)
    _save_admins(admins)
    return True, "Cont admin creat cu succes."

# ════════════════════════════════════════════════════════════
#   SESSION TOKENS  (stateless, signed)
# ════════════════════════════════════════════════════════════
def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)

def create_token(username: str) -> str:
    payload = {"u": username, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_secret_key(), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64e(sig)}"

def verify_token(token: str) -> Optional[str]:
    """Return the username if the token is valid & unexpired, else None."""
    if not token or "." not in token:
        return None
    try:
        body, sig = token.split(".", 1)
        expected = hmac.new(_secret_key(), body.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64e(expected), sig):
            return None
        payload = json.loads(_b64d(body))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload.get("u")
    except Exception:
        return None

# ════════════════════════════════════════════════════════════
#   RATE LIMITING
# ════════════════════════════════════════════════════════════
def _clean(ip: str) -> None:
    now = time.time()
    arr = [t for t in _ATTEMPTS.get(ip, []) if now - t < LOGIN_WINDOW_SECONDS]
    if arr:
        _ATTEMPTS[ip] = arr
    else:
        _ATTEMPTS.pop(ip, None)

def is_locked(ip: str) -> bool:
    _clean(ip)
    return len(_ATTEMPTS.get(ip, [])) >= LOGIN_MAX_ATTEMPTS

def record_failure(ip: str) -> None:
    _ATTEMPTS.setdefault(ip, []).append(time.time())

def reset_attempts(ip: str) -> None:
    _ATTEMPTS.pop(ip, None)

def attempts_left(ip: str) -> int:
    _clean(ip)
    return max(0, LOGIN_MAX_ATTEMPTS - len(_ATTEMPTS.get(ip, [])))

# ════════════════════════════════════════════════════════════
#   COOKIE HELPERS
# ════════════════════════════════════════════════════════════
def parse_cookie(cookie_header: str) -> dict:
    out: dict[str, str] = {}
    if not cookie_header:
        return out
    for part in cookie_header.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            out[k.strip()] = v.strip()
    return out

def make_set_cookie(token: str, secure: bool = True, max_age: int = TOKEN_TTL_SECONDS) -> str:
    attrs = [
        f"{COOKIE_NAME}={token}",
        "Path=/",
        "HttpOnly",
        "SameSite=Strict",
        f"Max-Age={max_age}",
    ]
    if secure:
        attrs.append("Secure")
    return "; ".join(attrs)

def make_clear_cookie(secure: bool = True) -> str:
    attrs = [f"{COOKIE_NAME}=", "Path=/", "HttpOnly", "SameSite=Strict", "Max-Age=0"]
    if secure:
        attrs.append("Secure")
    return "; ".join(attrs)
