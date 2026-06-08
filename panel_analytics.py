"""panel_analytics.py — visitor tracking & admin activity log for the web panel.

Tracks page views, unique visitors (by hashed IP), admin logins and online users.
All data is stored in the bot DB (bot_state table — no schema changes needed).
IPs are stored as SHA-256 hashes — never in plaintext.
"""
from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime, timezone
from typing import Any

try:
    import db
except Exception:
    db = None

_LOCK = threading.Lock()

# in-memory counters (fast path, flushed to DB every 60s)
_MEM: dict[str, Any] = {
    "total_views": 0,
    "unique_ips": set(),
    "active_ips": {},      # ip_hash -> last_seen_ts
    "login_log": [],       # list of dicts
    "last_flush": 0,
}
_FLUSH_INTERVAL = 60  # seconds

# ── helpers ──────────────────────────────────────────────────
def _now_ts() -> int:
    return int(time.time())

def _hash_ip(ip: str) -> str:
    return hashlib.sha256((ip or "unknown").encode()).hexdigest()[:16]

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _load_from_db() -> None:
    """Load persisted counters from DB on first use."""
    if db is None:
        return
    try:
        stored = db.get_state("panel_analytics")
        if isinstance(stored, dict):
            _MEM["total_views"] = int(stored.get("total_views", 0))
            _MEM["unique_ips"] = set(stored.get("unique_ip_hashes", []))
    except Exception:
        pass

def _flush_to_db() -> None:
    if db is None:
        return
    try:
        db.set_state("panel_analytics", {
            "total_views": _MEM["total_views"],
            "unique_ip_hashes": list(_MEM["unique_ips"])[-5000:],  # cap at 5k
            "updated_at": _utcnow_iso(),
        })
        _MEM["last_flush"] = _now_ts()
    except Exception:
        pass

_LOADED = False

def _ensure_loaded() -> None:
    global _LOADED
    if not _LOADED:
        _load_from_db()
        _LOADED = True

# ── public API ───────────────────────────────────────────────
def record_visit(ip: str) -> None:
    """Call on every GET / request."""
    _ensure_loaded()
    ip_hash = _hash_ip(ip)
    now = _now_ts()
    with _LOCK:
        _MEM["total_views"] += 1
        _MEM["unique_ips"].add(ip_hash)
        _MEM["active_ips"][ip_hash] = now
        # purge ips inactive for > 5 min
        cutoff = now - 300
        _MEM["active_ips"] = {k: v for k, v in _MEM["active_ips"].items() if v >= cutoff}
        if now - _MEM["last_flush"] > _FLUSH_INTERVAL:
            _flush_to_db()

def record_login(username: str, ip: str, success: bool) -> None:
    """Call after every login attempt."""
    _ensure_loaded()
    entry = {
        "username": username,
        "ip_hash": _hash_ip(ip),
        "success": success,
        "ts": _now_ts(),
        "iso": _utcnow_iso(),
    }
    with _LOCK:
        _MEM["login_log"].append(entry)
        _MEM["login_log"] = _MEM["login_log"][-200:]  # keep last 200
    if db is not None:
        try:
            db.log_event("panel_login", {
                "username": username,
                "ip_hash": _hash_ip(ip),
                "success": success,
            }, level="info" if success else "warn")
        except Exception:
            pass

def get_stats() -> dict:
    """Return analytics snapshot for the admin dashboard."""
    _ensure_loaded()
    now = _now_ts()
    with _LOCK:
        total_views = _MEM["total_views"]
        unique_count = len(_MEM["unique_ips"])
        active_count = sum(1 for v in _MEM["active_ips"].values() if now - v < 300)
        login_log = list(reversed(_MEM["login_log"]))[:50]  # most recent first

    # login stats from DB events
    recent_logins = []
    if db is not None:
        try:
            evts = db.recent_events(100)
            for e in evts:
                if e.get("event") == "panel_login":
                    p = e.get("payload") or {}
                    recent_logins.append({
                        "username": p.get("username"),
                        "ip_hash": p.get("ip_hash"),
                        "success": p.get("success"),
                        "ts": e.get("created_at"),
                    })
        except Exception:
            pass

    return {
        "total_views": total_views,
        "unique_visitors": unique_count,
        "active_now": active_count,
        "login_log": login_log,
        "recent_logins": recent_logins[:30],
    }
