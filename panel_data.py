"""panel_data.py — live data provider for the Romania Crypto Signals web panel.

Pulls real numbers from:
  - Discord client  (members, VIP, online, recent activity)
  - Bot database    (signals, performance, tracker)
  - Live market     (prices, sparklines, Fear & Greed)
  - Analytics       (visitors, active now, login log)

VIP signals are server-side locked: public callers get only symbol+side.
Full data (entry/TP/SL/score) is only included when is_admin=True.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

try:
    import db
except Exception:
    db = None

try:
    import market_data
except Exception:
    market_data = None

try:
    import feeds
except Exception:
    feeds = None

try:
    import requests as _req
except Exception:
    _req = None

try:
    import panel_analytics
except Exception:
    panel_analytics = None

_UA = {"User-Agent": "romania-crypto-signals-panel/2.0"}
_BINANCE_HOSTS = [
    "https://api.binance.com",
    "https://api.binance.us",
    "https://data-api.binance.vision",
]

# ── TTL cache ─────────────────────────────────────────────────
_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_LOCK = threading.Lock()

def _cache_get(key: str, ttl: float):
    with _CACHE_LOCK:
        item = _CACHE.get(key)
    if not item:
        return None
    ts, val = item
    return val if time.time() - ts <= ttl else None

def _cache_set(key: str, val: Any):
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), val)

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _safe_int(v: Any, d: int = 0) -> int:
    try: return int(v)
    except Exception: return d

def _safe_float(v: Any, d=None):
    try: return float(v)
    except Exception: return d

# ════════════════════════════════════════════════════════════
#   DISCORD GUILD STATS
# ════════════════════════════════════════════════════════════
def _guild_stats(client: Any, vip_role_name: str) -> dict:
    out = {
        "guild_name": None, "guild_icon": None, "total_members": 0,
        "online_members": 0, "vip_members": 0, "bot_members": 0,
        "human_members": 0, "guild_count": 0, "boosts": 0,
        "text_channels": 0, "voice_channels": 0, "roles": 0,
        "recent_joins": [],
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
    guild = max(guilds, key=lambda g: getattr(g, "member_count", 0) or 0)
    out["guild_name"] = getattr(guild, "name", None)
    try:
        icon = getattr(guild, "icon", None)
        out["guild_icon"] = str(icon.url) if icon else None
    except Exception:
        pass
    out["total_members"] = _safe_int(getattr(guild, "member_count", 0))
    try:
        out["boosts"] = _safe_int(getattr(guild, "premium_subscription_count", 0))
        channels = list(getattr(guild, "channels", []) or [])
        try:
            from discord import TextChannel, VoiceChannel
            out["text_channels"] = sum(1 for c in channels if isinstance(c, TextChannel))
            out["voice_channels"] = sum(1 for c in channels if isinstance(c, VoiceChannel))
        except Exception:
            out["text_channels"] = len(channels)
        out["roles"] = len(list(getattr(guild, "roles", []) or []))
    except Exception:
        pass

    online = vip = bots = humans = 0
    recent_joins = []
    try:
        members = list(guild.members)
        for member in members:
            try:
                if getattr(member, "bot", False):
                    bots += 1
                else:
                    humans += 1
                status = getattr(member, "status", None)
                sname = getattr(status, "name", str(status or "offline"))
                if sname and sname != "offline":
                    online += 1
                roles = getattr(member, "roles", []) or []
                if any(getattr(r, "name", "") == vip_role_name for r in roles):
                    vip += 1
                # recent joins (last 24h)
                joined = getattr(member, "joined_at", None)
                if joined:
                    try:
                        diff = (datetime.now(timezone.utc) - joined).total_seconds()
                        if diff < 86400:
                            recent_joins.append({
                                "name": str(member.display_name)[:32],
                                "joined_ago": int(diff),
                            })
                    except Exception:
                        pass
            except Exception:
                continue
    except Exception:
        pass

    out["online_members"] = online
    out["vip_members"] = vip
    out["bot_members"] = bots
    out["human_members"] = humans
    if out["total_members"] == 0 and (humans + bots) > 0:
        out["total_members"] = humans + bots
    out["recent_joins"] = sorted(recent_joins, key=lambda x: x["joined_ago"])[:10]
    return out

# ════════════════════════════════════════════════════════════
#   LIVE MARKET DATA
# ════════════════════════════════════════════════════════════
def _http_json(url: str, params: dict | None = None, timeout: int = 8):
    if _req is None:
        return None
    try:
        r = _req.get(url, params=params, headers=_UA, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def _sparkline(symbol: str) -> list[float]:
    key = f"spark:{symbol}"
    cached = _cache_get(key, 300)
    if cached is not None:
        return cached
    closes: list[float] = []
    for host in _BINANCE_HOSTS:
        data = _http_json(f"{host}/api/v3/klines",
                          params={"symbol": symbol, "interval": "1h", "limit": 24})
        if isinstance(data, list) and data:
            try:
                closes = [round(float(c[4]), 8) for c in data]
                break
            except Exception:
                closes = []
    _cache_set(key, closes)
    return closes

def _price_block(symbol: str, with_spark: bool = False) -> dict | None:
    if market_data is None:
        return None
    key = f"price:{symbol}"
    cached = _cache_get(key, 45)
    if cached is None:
        try:
            info = market_data.get_price_info(symbol)
        except Exception:
            info = None
        if not info:
            return None
        cached = {
            "symbol": symbol,
            "name": symbol.replace("USDT", ""),
            "price": _safe_float(info.get("price")),
            "change": _safe_float(info.get("change"), 0.0),
            "high": _safe_float(info.get("high")),
            "low": _safe_float(info.get("low")),
            "volume": _safe_float(info.get("volume"), 0.0),
        }
        _cache_set(key, cached)
    block = dict(cached)
    if with_spark:
        block["spark"] = _sparkline(symbol)
    return block

def _live_prices(free_symbols: list, vip_symbols: list) -> dict:
    free_syms = list(free_symbols or [])[:8]
    extra_vip = [s for s in (vip_symbols or []) if s not in free_syms][:6]
    free_prices = [b for s in free_syms if (b := _price_block(s, with_spark=True))]
    vip_teaser = [
        {"symbol": b["symbol"], "name": b["name"], "price": b["price"], "change": b["change"]}
        for s in extra_vip if (b := _price_block(s, with_spark=False))
    ]
    return {"free": free_prices, "vip_teaser": vip_teaser}

def _fear_greed() -> dict:
    cached = _cache_get("fng", 600)
    if cached is not None:
        return cached
    out = {"value": None, "classification": None}
    if feeds is not None:
        try:
            d = feeds.fear_greed_index()
            if isinstance(d, dict) and "value" in d:
                out = {"value": _safe_int(d["value"]), "classification": d.get("classification")}
        except Exception:
            pass
    _cache_set("fng", out)
    return out

# ════════════════════════════════════════════════════════════
#   SIGNALS
# ════════════════════════════════════════════════════════════
def _signal_counts(signal_stats: dict | None) -> dict:
    base = {"BUY": 0, "SELL": 0, "total": 0}
    if isinstance(signal_stats, dict):
        base["BUY"] = _safe_int(signal_stats.get("BUY"))
        base["SELL"] = _safe_int(signal_stats.get("SELL"))
        base["total"] = _safe_int(signal_stats.get("total"))
    return base

def _split_signals(is_admin: bool = False) -> dict:
    out: dict[str, list] = {"free": [], "vip": []}
    if db is None:
        return out
    try:
        rows = db.recent_sent(24)
    except Exception:
        rows = []
    for r in rows:
        tier = str(r.get("tier") or "free").lower()
        side = str(r.get("side") or "").upper()
        symbol = r.get("symbol")
        sent_at = r.get("sent_at") or r.get("reserved_at")
        if tier == "vip":
            if is_admin:
                m = r.get("meta") if isinstance(r.get("meta"), dict) else {}
                out["vip"].append({
                    "symbol": symbol, "name": (symbol or "").replace("USDT", ""),
                    "side": side, "tier": "vip",
                    "entry": _safe_float(r.get("entry")),
                    "score": r.get("score"), "rr": _safe_float(r.get("rr")),
                    "confidence": r.get("confidence"),
                    "tp": m.get("tp") or m.get("targets"),
                    "sl": m.get("sl") or m.get("stop"),
                    "status": r.get("status"), "sent_at": sent_at, "locked": False,
                })
            else:
                out["vip"].append({
                    "symbol": symbol, "name": (symbol or "").replace("USDT", ""),
                    "side": side, "tier": "vip",
                    "status": r.get("status"), "sent_at": sent_at, "locked": True,
                })
        else:
            out["free"].append({
                "symbol": symbol, "name": (symbol or "").replace("USDT", ""),
                "side": side, "tier": "free",
                "entry": _safe_float(r.get("entry")),
                "score": r.get("score"), "rr": _safe_float(r.get("rr")),
                "confidence": r.get("confidence"),
                "status": r.get("status"), "sent_at": sent_at, "locked": False,
            })
    out["free"] = out["free"][:10]
    out["vip"] = out["vip"][:10]
    return out

def _db_meta() -> dict:
    out = {"backend": None, "today_free": 0, "today_vip": 0, "performance_30d": {}}
    if db is None:
        return out
    try:
        out["backend"] = db.backend_name()
        out["today_free"] = _safe_int(db.get_daily_count("free"))
        out["today_vip"] = _safe_int(db.get_daily_count("vip"))
        out["performance_30d"] = db.result_summary(30)
    except Exception:
        pass
    return out

def _bot_activity() -> dict:
    """Recent bot ops events for the admin dashboard."""
    out = {"recent_events": [], "last_signal": None, "last_scan": None}
    if db is None:
        return out
    try:
        evts = db.recent_events(20)
        out["recent_events"] = [
            {"event": e.get("event"), "level": e.get("level"),
             "ts": e.get("created_at"), "payload": e.get("payload")}
            for e in evts
        ]
    except Exception:
        pass
    return out

# ════════════════════════════════════════════════════════════
#   PUBLIC ENTRY POINT
# ════════════════════════════════════════════════════════════
def collect_stats(client: Any = None, *, signal_stats: dict | None = None,
                  symbols: Optional[list] = None, all_symbols: Optional[list] = None,
                  vip_role_name: str = "VIP", started_at: Optional[str] = None,
                  discord_invite: str = "", vip_price: str = "",
                  is_admin: bool = False) -> dict:
    discord_ready = False
    bot_user = None
    try:
        discord_ready = bool(client and client.is_ready())
        bot_user = str(client.user) if (client and client.user) else None
    except Exception:
        discord_ready = False

    guild = _guild_stats(client, vip_role_name)
    counts = _signal_counts(signal_stats)
    meta = _db_meta()
    signals = _split_signals(is_admin=is_admin)
    prices = _live_prices(symbols or [], all_symbols or [])
    fng = _fear_greed()
    activity = _bot_activity() if is_admin else {}
    analytics = panel_analytics.get_stats() if (panel_analytics and is_admin) else {}

    payload: dict[str, Any] = {
        "ok": True,
        "updated_at": _utcnow_iso(),
        "discord_ready": discord_ready,
        "bot_user": bot_user,
        "is_admin": is_admin,
        "started_at": started_at,
        "links": {"discord_invite": discord_invite, "vip_price": vip_price},
        "server": {
            "name": guild["guild_name"] or "Romania Crypto Signals",
            "icon": guild["guild_icon"],
            "total_members": guild["total_members"],
            "online_members": guild["online_members"],
            "vip_members": guild["vip_members"],
            "human_members": guild["human_members"],
            "bot_members": guild["bot_members"],
            "guild_count": guild["guild_count"],
            "boosts": guild["boosts"],
            "text_channels": guild["text_channels"],
            "voice_channels": guild["voice_channels"],
            "roles": guild["roles"],
            "recent_joins": guild["recent_joins"],
        },
        "signals": {
            "buy": counts["BUY"], "sell": counts["SELL"], "total": counts["total"],
            "today_free": meta["today_free"], "today_vip": meta["today_vip"],
            "free": signals["free"], "vip": signals["vip"],
        },
        "performance": meta["performance_30d"],
        "market": {
            "prices": prices["free"],
            "vip_teaser": prices["vip_teaser"],
            "fear_greed": fng,
        },
        "coins": {
            "free": list(symbols or []),
            "free_count": len(symbols or []),
            "vip_count": len(all_symbols or []),
        },
        "backend": meta["backend"],
    }

    if is_admin:
        payload["activity"] = activity
        payload["analytics"] = analytics

    return payload
