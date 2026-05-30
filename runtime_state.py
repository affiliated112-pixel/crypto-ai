"""Small runtime state used by /health and admin commands."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

try:
    import db
except Exception:
    db = None

STATE: dict[str, Any] = {
    "started_at": datetime.now(timezone.utc).isoformat(),
    "discord_ready": False,
    "loop_alive": False,
    "last_scan_at": None,
    "last_scan_finished_at": None,
    "last_successful_market_fetch": None,
    "last_signal_sent_at": None,
    "last_error": None,
    "last_market_symbol": None,
    "last_signal": None,
    "scan_symbols": 0,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _persist() -> None:
    if db:
        try:
            db.set_state("runtime", STATE)
        except Exception:
            pass


def mark_discord_ready(value: bool) -> None:
    STATE["discord_ready"] = bool(value)
    _persist()


def mark_loop_alive(value: bool = True) -> None:
    STATE["loop_alive"] = bool(value)
    _persist()


def mark_scan_start(count: int | None = None) -> None:
    STATE["loop_alive"] = True
    STATE["last_scan_at"] = _now()
    if count is not None:
        STATE["scan_symbols"] = int(count)
    _persist()


def mark_scan_finished() -> None:
    STATE["last_scan_finished_at"] = _now()
    _persist()


def mark_market_fetch(symbol: str | None = None, source: str | None = None) -> None:
    STATE["last_successful_market_fetch"] = _now()
    if symbol:
        STATE["last_market_symbol"] = symbol
    if source:
        STATE["last_market_source"] = source
    _persist()


def mark_signal_sent(symbol: str, side: str, tier: str, signal_id: str | None = None) -> None:
    STATE["last_signal_sent_at"] = _now()
    STATE["last_signal"] = {"symbol": symbol, "side": side, "tier": tier, "signal_id": signal_id}
    _persist()


def mark_error(error: object) -> None:
    STATE["last_error"] = str(error)[:900]
    _persist()


def health_payload(extra: dict | None = None) -> dict:
    out = dict(STATE)
    if db:
        try:
            out["database"] = db.health_summary()
        except Exception as exc:
            out["database_error"] = str(exc)[:500]
    if extra:
        out.update(extra)
    return out
