"""Signal performance tracker with partial TP, fees and slippage.

The tracker keeps the existing JSON log for compatibility and mirrors updates to
DB when a signal_id is available.  Default management model:
  - TP1 closes 40% and moves remaining stop to breakeven
  - TP2 closes 30%
  - TP3 closes the remaining position
  - fees/slippage are included in realized PnL estimates
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone

import market_data

try:
    import db
except Exception:  # pragma: no cover
    db = None

DATA_FILE = os.environ.get("SIGNAL_TRACKER_FILE", "signal_tracker.json")
MAX_RECORDS = int(os.environ.get("SIGNAL_TRACKER_MAX_RECORDS", "1000"))
POLL_SECONDS = int(os.environ.get("SIGNAL_TRACKER_POLL_SECONDS", "120"))
SIGNAL_EXPIRY_HOURS = int(os.environ.get("SIGNAL_EXPIRY_HOURS", "48"))

def _position_pct_env(name: str, default: float) -> float:
    raw = float(os.environ.get(name, str(default)))
    # Accept both 40 and 0.40 as "40% of the position".
    return raw * 100.0 if 0 < raw <= 1 else raw

TP1_CLOSE_PCT = _position_pct_env("TRACKER_TP1_CLOSE_PCT", 40)
TP2_CLOSE_PCT = _position_pct_env("TRACKER_TP2_CLOSE_PCT", 30)
TP3_CLOSE_PCT = _position_pct_env("TRACKER_TP3_CLOSE_PCT", 30)
FEE_PCT = float(os.environ.get("TRACKER_FEE_PCT", "0.10"))       # total round-trip estimate in %
SLIPPAGE_PCT = float(os.environ.get("TRACKER_SLIPPAGE_PCT", "0.05"))

_alert_callback = None


def set_alert_callback(callback):
    global _alert_callback
    _alert_callback = callback
    print("[tracker] alert callback registered", flush=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load():
    if not os.path.isfile(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(records):
    if len(records) > MAX_RECORDS:
        records = records[-MAX_RECORDS:]
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[tracker] save error: {e}", flush=True)


def _levels(direction, entry, levels=None):
    if levels and all(k in levels for k in ("sl", "tp1", "tp2", "tp3")):
        return float(levels["sl"]), float(levels["tp1"]), float(levels["tp2"]), float(levels["tp3"])
    if direction == "BUY":
        return entry * 0.98, entry * 1.02, entry * 1.04, entry * 1.07
    return entry * 1.02, entry * 0.98, entry * 0.96, entry * 0.93


def record_signal(symbol, direction, entry, score=None, quality=None, levels=None, tier="free", signal_id=None):
    records = _load()
    signal_id = signal_id or f"legacy:{tier}:{symbol}:{direction}:{int(time.time()*1000)}"
    for existing in records:
        if existing.get("signal_id") == signal_id:
            return existing

    sl, tp1, tp2, tp3 = _levels(direction, float(entry), levels)
    rec = {
        "id": int(time.time() * 1000),
        "signal_id": signal_id,
        "tier": tier,
        "symbol": symbol,
        "direction": direction,
        "entry": float(entry),
        "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "score": score, "quality": quality,
        "level_source": "ATR" if levels else "legacy_pct",
        "opened_at": _now_iso(),
        "status": "OPEN",
        "hit": [],
        "alerted": [],
        "partials": [],
        "remaining_pct": 100.0,
        "realized_pnl_pct": 0.0,
        "fees_pct": FEE_PCT,
        "slippage_pct": SLIPPAGE_PCT,
        "break_even_active": False,
        "max_favor": float(entry),
        "max_against": float(entry),
        "closed_at": None,
    }
    records.append(rec)
    _save(records)
    try:
        if db:
            db.open_signal_result(signal_id, tier, symbol, direction, float(entry), {
                "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
                "fees_pct": FEE_PCT, "slippage_pct": SLIPPAGE_PCT,
            }, meta={"score": score, "quality": quality})
    except Exception as e:
        print(f"[tracker] DB open error: {e}", flush=True)
    return rec


def _get_price(symbol):
    return market_data.get_current_price(symbol)


def _pnl(rec, price):
    if not rec.get("entry"):
        return 0.0
    if rec["direction"] == "BUY":
        return (float(price) - rec["entry"]) / rec["entry"] * 100
    return (rec["entry"] - float(price)) / rec["entry"] * 100


def _net_slice_pnl(raw_pnl_pct: float, slice_pct: float) -> float:
    cost = (FEE_PCT + SLIPPAGE_PCT) * (slice_pct / 100.0)
    return raw_pnl_pct * (slice_pct / 100.0) - cost


def _mark_db(rec, closed=False):
    if not db or not rec.get("signal_id"):
        return
    try:
        db.update_signal_result(
            rec["signal_id"],
            status=rec.get("status"),
            remaining_pct=float(rec.get("remaining_pct") or 0),
            realized_pnl_pct=float(rec.get("realized_pnl_pct") or 0),
            hits=rec.get("hit") or [],
            meta={"partials": rec.get("partials") or [], "close_price": rec.get("close_price")},
            closed=closed,
        )
    except Exception as e:
        print(f"[tracker] DB update error: {e}", flush=True)


def _close_slice(rec, event: str, price: float, slice_pct: float):
    remaining = float(rec.get("remaining_pct") or 0)
    size = min(max(slice_pct, 0.0), remaining)
    if size <= 0:
        return
    raw = _pnl(rec, price)
    net = _net_slice_pnl(raw, size)
    rec["remaining_pct"] = round(remaining - size, 4)
    rec["realized_pnl_pct"] = round(float(rec.get("realized_pnl_pct") or 0) + net, 4)
    rec.setdefault("partials", []).append({
        "event": event,
        "price": float(price),
        "size_pct": size,
        "raw_pnl_pct": round(raw, 4),
        "net_contribution_pct": round(net, 4),
        "ts": _now_iso(),
    })


def _close_record(rec, status, price):
    if float(rec.get("remaining_pct") or 0) > 0:
        _close_slice(rec, status, price, float(rec.get("remaining_pct") or 0))
    rec["status"] = status
    rec["closed_at"] = _now_iso()
    rec["close_price"] = float(price)
    rec["pnl_pct"] = float(rec.get("realized_pnl_pct") or 0)
    _mark_db(rec, closed=True)


def _event_price(rec, event: str, current_price: float) -> float:
    if event == "TP1": return float(rec["tp1"])
    if event == "TP2": return float(rec["tp2"])
    if event == "TP3": return float(rec["tp3"])
    if event in {"SL", "BE"}: return float(rec.get("entry") if rec.get("break_even_active") else rec.get("sl"))
    return float(current_price)


async def _evaluate_and_alert(rec, price):
    if rec.get("status") != "OPEN":
        return False
    is_buy = rec["direction"] == "BUY"
    rec.setdefault("alerted", [])
    rec.setdefault("hit", [])
    changed = False
    events_to_fire = []

    if is_buy:
        rec["max_favor"] = max(float(rec.get("max_favor", price)), float(price))
        rec["max_against"] = min(float(rec.get("max_against", price)), float(price))
    else:
        rec["max_favor"] = min(float(rec.get("max_favor", price)), float(price))
        rec["max_against"] = max(float(rec.get("max_against", price)), float(price))

    def hit_target(level):
        return price >= rec[level] if is_buy else price <= rec[level]

    def hit_stop():
        effective_sl = rec["entry"] if rec.get("break_even_active") else rec["sl"]
        return price <= effective_sl if is_buy else price >= effective_sl

    # Stop comes first. If TP1 was hit previously, this is breakeven protection.
    if hit_stop():
        event = "BE" if rec.get("break_even_active") else "SL"
        close_px = _event_price(rec, event, price)
        _close_record(rec, event, close_px)
        if event not in rec["alerted"]:
            events_to_fire.append(event)
            rec["alerted"].append(event)
        changed = True
    else:
        for key, event, size in (("tp1", "TP1", TP1_CLOSE_PCT), ("tp2", "TP2", TP2_CLOSE_PCT), ("tp3", "TP3", TP3_CLOSE_PCT)):
            if hit_target(key) and key not in rec["hit"]:
                rec["hit"].append(key)
                _close_slice(rec, event, _event_price(rec, event, price), size if event != "TP3" else float(rec.get("remaining_pct") or size))
                if event == "TP1":
                    rec["break_even_active"] = True
                    rec["sl_after_tp1"] = rec["entry"]
                if event not in rec["alerted"]:
                    events_to_fire.append(event)
                    rec["alerted"].append(event)
                changed = True
        if float(rec.get("remaining_pct") or 0) <= 0 or "tp3" in rec["hit"]:
            rec["status"] = "TP3" if "tp3" in rec["hit"] else "CLOSED"
            rec["closed_at"] = _now_iso()
            rec["close_price"] = _event_price(rec, "TP3", price)
            rec["pnl_pct"] = float(rec.get("realized_pnl_pct") or 0)
            _mark_db(rec, closed=True)
        elif changed:
            _mark_db(rec, closed=False)

    # Expiry closes whatever remains at market price.
    try:
        opened = datetime.fromisoformat(str(rec["opened_at"]).replace("Z", "+00:00"))
        if rec.get("status") == "OPEN" and (datetime.now(timezone.utc) - opened).total_seconds() > SIGNAL_EXPIRY_HOURS * 3600:
            _close_record(rec, "EXPIRED", price)
            if "EXPIRED" not in rec["alerted"]:
                events_to_fire.append("EXPIRED")
                rec["alerted"].append("EXPIRED")
            changed = True
    except Exception:
        pass

    if events_to_fire and _alert_callback:
        for ev in events_to_fire:
            try:
                await _alert_callback(ev, rec, {"current_price": price, "pnl_pct": float(rec.get("realized_pnl_pct") or 0)})
            except Exception as e:
                print(f"[tracker] alert callback error: {e}", flush=True)

    return changed


async def poll_once_async():
    records = _load()
    open_recs = [r for r in records if r.get("status") == "OPEN"]
    if not open_recs:
        return
    symbols = list({r["symbol"] for r in open_recs})
    loop = asyncio.get_event_loop()
    price_tasks = [loop.run_in_executor(None, _get_price, s) for s in symbols]
    prices = await asyncio.gather(*price_tasks)
    by_sym = {s: p for s, p in zip(symbols, prices) if p is not None}

    changed_any = False
    for r in records:
        if r.get("status") == "OPEN":
            price = by_sym.get(r["symbol"])
            if price is not None:
                changed_any = bool(await _evaluate_and_alert(r, price)) or changed_any
    if changed_any:
        _save(records)


def poll_once():
    records = _load()
    open_recs = [r for r in records if r.get("status") == "OPEN"]
    if not open_recs:
        return
    by_sym = {}
    for sym in list({r["symbol"] for r in open_recs}):
        p = _get_price(sym)
        if p is not None:
            by_sym[sym] = p
    changed_any = False
    for r in records:
        if r.get("status") == "OPEN":
            price = by_sym.get(r["symbol"])
            if price is not None:
                # Sync mode cannot fire Discord alerts; apply minimal state by running
                # the async evaluator in a short private loop only when needed.
                try:
                    changed_any = bool(asyncio.run(_evaluate_and_alert(r, price))) or changed_any
                except RuntimeError:
                    pass
    if changed_any:
        _save(records)


async def poll_loop():
    while True:
        try:
            await poll_once_async()
        except Exception as e:
            print(f"[tracker] poll error: {e}", flush=True)
        await asyncio.sleep(POLL_SECONDS)
