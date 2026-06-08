"""panel_userdata.py — server-side persistence for per-user panel data.

Stores each logged-in user's paper-trading portfolio and crypto holdings in the
bot DB (bot_state key-value table — no schema changes needed), so the data
follows the account across devices/browsers instead of living only in
localStorage.

Layout in bot_state:
    key   = "userdata:<username>"
    value = { "paper": {...}, "portfolio": [...], "alerts": [...], "updated_at": <iso> }

Only the keys a client sends are overwritten, so a portfolio save never wipes
the paper-trading state and vice-versa.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

try:
    import db
except Exception:  # pragma: no cover - db is always present in the bot runtime
    db = None

# Sections a client is allowed to persist. Anything else is ignored.
_ALLOWED_SECTIONS = ("paper", "portfolio", "alerts")

# Cap the serialized payload so a malicious client cannot bloat the DB.
_MAX_BYTES = 64 * 1024

_LOCK = threading.Lock()

def _key(username: str) -> str:
    return "userdata:" + (username or "").strip().lower()

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def get_user_data(username: str) -> dict:
    """Return the persisted data blob for a user (empty skeleton if none)."""
    base = {"paper": None, "portfolio": None, "alerts": None, "updated_at": None}
    if db is None or not username:
        return base
    try:
        stored = db.get_state(_key(username))
        if isinstance(stored, dict):
            base.update({k: stored.get(k) for k in base})
    except Exception:
        pass
    return base

def save_user_data(username: str, incoming: dict) -> tuple[bool, str]:
    """Merge and persist the allowed sections from `incoming` for a user.

    Returns (ok, message). Only sections present in `incoming` are updated.
    """
    if db is None:
        return False, "stocare indisponibilă"
    if not username:
        return False, "neautentificat"
    if not isinstance(incoming, dict):
        return False, "payload invalid"

    # Reject oversized payloads early.
    try:
        import json
        if len(json.dumps(incoming, default=str)) > _MAX_BYTES:
            return False, "date prea mari"
    except Exception:
        return False, "payload invalid"

    with _LOCK:
        current = get_user_data(username)
        for section in _ALLOWED_SECTIONS:
            if section in incoming and incoming[section] is not None:
                current[section] = incoming[section]
        current["updated_at"] = _utcnow_iso()
        try:
            db.set_state(_key(username), current)
        except Exception as exc:
            return False, str(exc)[:200]
    return True, "salvat"
