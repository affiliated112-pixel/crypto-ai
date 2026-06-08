"""panel_data.py — gathers real, live data for the Romania Crypto Signals web panel.

It pulls numbers straight from the running Discord client (member counts, VIP role,
guild info) and from the bot database (signals sent, performance, recent signals).
Everything here is read-only and defensive: the panel must never crash the bot.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

try:
    import db
except Exception:  # pragma: no cover
    db = None

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default

def _guild_stats(client: Any, vip_role_name: str) -> dict:
    """Read live member / VIP / online counts from the Discord guild cache."""
    out = {
        "guild_name": None,
        "guild_icon": None,
        "total_members": 0,
        "online_members": 0,
        "vip_members": 0,
        "bot_members": 0,
        "human_members": 0,
        "guild_count": 0,
    }
    if client is None:
        return out
    try:
        guilds = list(getattr(client, "guilds", []) or [])
    except Exception:
        guilds = []
    out["guild_count"] = len(guilds)
    if not guilds:
        return out

    # Use the largest guild as the "main" server for the panel.
    guild = max(guilds, key=lambda g: getattr(g, "member_count", 0) or 0)
    out["guild_name"] = getattr(guild, "name", None)
    try:
        icon = getattr(guild, "icon", None)
        out["guild_icon"] = str(icon.url) if icon else None
    except Exception:
        out["guild_icon"] = None

    out["total_members"] = _safe_int(getattr(guild, "member_count", 0))

    online = 0
    vip = 0
    bots = 0
    humans = 0
    try:
        for member in guild.members:
            try:
                if getattr(member, "bot", False):
                    bots += 1
                else:
                    humans += 1
                status = getattr(member, "status", None)
                status_name = getattr(status, "name", str(status or "offline"))
                if status_name and status_name != "offline":
                    online += 1
                roles = getattr(member, "roles", []) or []
                if any(getattr(r, "name", "") == vip_role_name for r in roles):
                    vip += 1
            except Exception:
                continue
    except Exception:
        pass

    out["online_members"] = online
    out["vip_members"] = vip
    out["bot_members"] = bots
    out["human_members"] = humans
    # If presence intent is off, members cache may be partial; fall back to member_count.
    if out["total_members"] == 0 and (humans + bots) > 0:
        out["total_members"] = humans + bots
    return out

def _signal_stats(signal_stats: dict | None) -> dict:
    base = {"BUY": 0, "SELL": 0, "total": 0}
    if isinstance(signal_stats, dict):
        base["BUY"] = _safe_int(signal_stats.get("BUY"))
        base["SELL"] = _safe_int(signal_stats.get("SELL"))
        base["total"] = _safe_int(signal_stats.get("total"))
    return base

def _db_block() -> dict:
    out: dict[str, Any] = {
        "backend": None,
        "today_free": 0,
        "today_vip": 0,
        "performance_30d": {},
        "recent_signals": [],
    }
    if db is None:
        return out
    try:
        out["backend"] = db.backend_name()
    except Exception:
        pass
    try:
        out["today_free"] = _safe_int(db.get_daily_count("free"))
        out["today_vip"] = _safe_int(db.get_daily_count("vip"))
    except Exception:
        pass
    try:
        out["performance_30d"] = db.result_summary(30)
    except Exception:
        out["performance_30d"] = {}
    try:
        rows = db.recent_sent(12)
        clean = []
        for r in rows:
            clean.append({
                "symbol": r.get("symbol"),
                "side": r.get("side"),
                "tier": r.get("tier"),
                "entry": r.get("entry"),
                "score": r.get("score"),
                "rr": r.get("rr"),
                "confidence": r.get("confidence"),
                "status": r.get("status"),
                "sent_at": r.get("sent_at") or r.get("reserved_at"),
            })
        out["recent_signals"] = clean
    except Exception:
        out["recent_signals"] = []
    return out

def collect_stats(
    client: Any = None,
    *,
    signal_stats: dict | None = None,
    symbols: Optional[list] = None,
    all_symbols: Optional[list] = None,
    vip_role_name: str = "VIP",
    started_at: Optional[str] = None,
) -> dict:
    """Build the full payload consumed by the web panel front-end."""
    discord_ready = False
    bot_user = None
    try:
        discord_ready = bool(client and client.is_ready())
        bot_user = str(client.user) if (client and client.user) else None
    except Exception:
        discord_ready = False

    guild = _guild_stats(client, vip_role_name)
    signals = _signal_stats(signal_stats)
    dbb = _db_block()

    return {
        "ok": True,
        "updated_at": _utcnow_iso(),
        "discord_ready": discord_ready,
        "bot_user": bot_user,
        "started_at": started_at,
        "server": {
            "name": guild["guild_name"] or "Romania Crypto Signals",
            "icon": guild["guild_icon"],
            "total_members": guild["total_members"],
            "online_members": guild["online_members"],
            "vip_members": guild["vip_members"],
            "human_members": guild["human_members"],
            "bot_members": guild["bot_members"],
            "guild_count": guild["guild_count"],
        },
        "signals": {
            "buy": signals["BUY"],
            "sell": signals["SELL"],
            "total": signals["total"],
            "today_free": dbb["today_free"],
            "today_vip": dbb["today_vip"],
        },
        "performance": dbb["performance_30d"],
        "recent_signals": dbb["recent_signals"],
        "coins": {
            "free": list(symbols or []),
            "free_count": len(symbols or []),
            "vip_count": len(all_symbols or []),
        },
        "backend": dbb["backend"],
    }
