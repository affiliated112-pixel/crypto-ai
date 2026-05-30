"""Signal performance tracker + automatic SL/TP alerts.
Logs every signal to JSON, polls Binance every 2 min to check if price
hit SL or any TP, computes win rate. Fires alert callbacks on status
changes so the bot can post live updates to Discord.
"""
import asyncio
import json
import os
import time
from datetime import datetime, timezone
import requests
import market_data

DATA_FILE = os.environ.get("SIGNAL_TRACKER_FILE", "signal_tracker.json")
MAX_RECORDS = 500
POLL_SECONDS = 120
SIGNAL_EXPIRY_HOURS = 48

UA = {"User-Agent": "crypto-ai-bot/2026"}

# Alert callback: called when a signal's status changes (TP hit, SL hit, expired).
# Signature: async def callback(event_type, record, extra)
#   event_type: "TP1" | "TP2" | "TP3" | "SL" | "EXPIRED"
#   record: full signal dict
#   extra: dict with extra info (e.g. current_price, pnl_pct)
_alert_callback = None


def set_alert_callback(callback):
    """Register an async callback for status-change events."""
    global _alert_callback
    _alert_callback = callback
    print("[tracker] alert callback registered", flush=True)


def _load():
    if not os.path.isfile(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(records):
    if len(records) > MAX_RECORDS:
        records = records[-MAX_RECORDS:]
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
    except Exception as e:
        print(f"[tracker] save error: {e}", flush=True)


def record_signal(symbol, direction, entry, score=None, quality=None, levels=None):
    """Append a new signal to the log using real signal levels.

    levels may contain ATR-based `sl`, `tp1`, `tp2`, `tp3`. If omitted, the
    legacy percentage fallback is kept for backward compatibility.
    """
    records = _load()
    if levels and all(k in levels for k in ("sl", "tp1", "tp2", "tp3")):
        sl, tp1, tp2, tp3 = (float(levels["sl"]), float(levels["tp1"]),
                             float(levels["tp2"]), float(levels["tp3"]))
    elif direction == "BUY":
        sl, tp1, tp2, tp3 = entry * 0.98, entry * 1.02, entry * 1.04, entry * 1.07
    else:
        sl, tp1, tp2, tp3 = entry * 1.02, entry * 0.98, entry * 0.96, entry * 0.93
    rec = {
        "id": int(time.time() * 1000),
        "symbol": symbol,
        "direction": direction,
        "entry": float(entry),
        "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "score": score, "quality": quality,
        "level_source": "ATR" if levels else "legacy_pct",
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "status": "OPEN",
        "hit": [],
        "alerted": [],   # which events we've already fired alerts for
        "max_favor": entry, "max_against": entry,
        "closed_at": None,
    }
    records.append(rec)
    _save(records)
    return rec


def _get_price(symbol):
    return market_data.get_current_price(symbol)


def _pnl(rec, price):
    """Return P&L percentage from entry to current price."""
    if not rec.get("entry"):
        return 0
    if rec["direction"] == "BUY":
        return (price - rec["entry"]) / rec["entry"] * 100
    return (rec["entry"] - price) / rec["entry"] * 100


def _close_record(rec, status, price):
    rec["status"] = status
    rec["closed_at"] = datetime.now(timezone.utc).isoformat()
    rec["close_price"] = price
    rec["pnl_pct"] = _pnl(rec, price)


async def _evaluate_and_alert(rec, price):
    """Update record in place. Fire alerts for new events. Returns True if changed."""
    if rec["status"] != "OPEN":
        return False
    is_buy = rec["direction"] == "BUY"
    rec.setdefault("alerted", [])
    changed = False
    events_to_fire = []

    if is_buy:
        rec["max_favor"] = max(rec.get("max_favor", price), price)
        rec["max_against"] = min(rec.get("max_against", price), price)
        if price <= rec["sl"]:
            _close_record(rec, "SL", price)
            if "SL" not in rec["alerted"]:
                events_to_fire.append("SL")
                rec["alerted"].append("SL")
            changed = True
        else:
            for tp_key, tp_val in (("tp1", rec["tp1"]), ("tp2", rec["tp2"]), ("tp3", rec["tp3"])):
                if price >= tp_val and tp_key not in rec["hit"]:
                    rec["hit"].append(tp_key)
                    if tp_key.upper() not in rec["alerted"]:
                        events_to_fire.append(tp_key.upper())
                        rec["alerted"].append(tp_key.upper())
                    changed = True
            if "tp3" in rec["hit"]:
                _close_record(rec, "TP3", price)
    else:  # SELL
        rec["max_favor"] = min(rec.get("max_favor", price), price)
        rec["max_against"] = max(rec.get("max_against", price), price)
        if price >= rec["sl"]:
            _close_record(rec, "SL", price)
            if "SL" not in rec["alerted"]:
                events_to_fire.append("SL")
                rec["alerted"].append("SL")
            changed = True
        else:
            for tp_key, tp_val in (("tp1", rec["tp1"]), ("tp2", rec["tp2"]), ("tp3", rec["tp3"])):
                if price <= tp_val and tp_key not in rec["hit"]:
                    rec["hit"].append(tp_key)
                    if tp_key.upper() not in rec["alerted"]:
                        events_to_fire.append(tp_key.upper())
                        rec["alerted"].append(tp_key.upper())
                    changed = True
            if "tp3" in rec["hit"]:
                _close_record(rec, "TP3", price)

    # Expiry
    try:
        opened = datetime.fromisoformat(rec["opened_at"].replace("Z", "+00:00"))
        if rec["status"] == "OPEN" and (datetime.now(timezone.utc) - opened).total_seconds() > SIGNAL_EXPIRY_HOURS * 3600:
            _close_record(rec, "EXPIRED", price)
            if "EXPIRED" not in rec["alerted"]:
                events_to_fire.append("EXPIRED")
                rec["alerted"].append("EXPIRED")
            changed = True
    except Exception:
        pass

    # Fire alerts
    if events_to_fire and _alert_callback:
        pnl = _pnl(rec, price)
        for ev in events_to_fire:
            try:
                await _alert_callback(ev, rec, {"current_price": price, "pnl_pct": pnl})
            except Exception as e:
                print(f"[tracker] alert callback error: {e}", flush=True)

    return changed


async def poll_once_async():
    """Check all open signals once and fire alerts."""
    records = _load()
    open_recs = [r for r in records if r.get("status") == "OPEN"]
    if not open_recs:
        return
    symbols = list({r["symbol"] for r in open_recs})
    # Fetch prices in parallel
    loop = asyncio.get_event_loop()
    price_tasks = [loop.run_in_executor(None, _get_price, s) for s in symbols]
    prices = await asyncio.gather(*price_tasks)
    by_sym = {s: p for s, p in zip(symbols, prices) if p is not None}

    for r in records:
        if r.get("status") == "OPEN":
            price = by_sym.get(r["symbol"])
            if price is not None:
                await _evaluate_and_alert(r, price)
    _save(records)


# Keep sync poll_once for backward compatibility (no alerts fired)
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
    # Note: this sync version doesn't fire alerts (no event loop)
    for r in records:
        if r.get("status") == "OPEN":
            price = by_sym.get(r["symbol"])
            if price is not None:
                # inline sync evaluation (no alerts)
                _evaluate_sync(r, price)
    _save(records)


def _evaluate_sync(rec, price):
    """Sync evaluate (no alerts) for back-compat."""
    if rec["status"] != "OPEN":
        return
    is_buy = rec["direction"] == "BUY"
    if is_buy:
        rec["max_favor"] = max(rec.get("max_favor", price), price)
        if price <= rec["sl"]:
            _close_record(rec, "SL", price)
            return
        for k, v in (("tp1", rec["tp1"]), ("tp2", rec["tp2"]), ("tp3", rec["tp3"])):
            if price >= v and k not in rec["hit"]:
                rec["hit"].append(k)
        if "tp3" in rec["hit"]:
            _close_record(rec, "TP3", price)
    else:
        rec["max_favor"] = min(rec.get("max_favor", price), price)
        if price >= rec["sl"]:
            _close_record(rec, "SL", price)
            return
        for k, v in (("tp1", rec["tp1"]), ("tp2", rec["tp2"]), ("tp3", rec["tp3"])):
            if price <= v and k not in rec["hit"]:
                rec["hit"].append(k)
        if "tp3" in rec["hit"]:
            _close_record(rec, "TP3", price)


async def poll_loop():
    """Background loop: poll every POLL_SECONDS and fire alerts."""
    while True:
        try:
            await poll_once_async()
        except Exception as e:
            print(f"[tracker] poll error: {e}", flush=True)
        await asyncio.sleep(POLL_SECONDS)


def _closed_exit_price(rec):
    """Best known exit/decision price for a closed record, based on real SL/TP levels."""
    status = (rec.get("status") or "").upper()
    if status == "SL":
        return rec.get("sl")
    hits = rec.get("hit", []) or []
    for key in ("tp3", "tp2", "tp1"):
        if key in hits or status == key.upper():
            return rec.get(key)
    return None


def compute_stats(symbol=None, days=None):
    records = _load()
    if symbol:
        records = [r for r in records if r.get("symbol") == symbol.upper()]
    if days:
        cutoff = time.time() - days * 86400
        records = [r for r in records if (r.get("id", 0) / 1000) >= cutoff]

    open_count = len([r for r in records if r.get("status") == "OPEN"])
    closed = [r for r in records if r.get("status") != "OPEN"]

    tp1 = len([r for r in closed if "tp1" in r.get("hit", [])])
    tp2 = len([r for r in closed if "tp2" in r.get("hit", [])])
    tp3 = len([r for r in closed if "tp3" in r.get("hit", []) or r.get("status") == "TP3"])
    sl = len([r for r in closed if r.get("status") == "SL"])
    expired = len([r for r in closed if r.get("status") == "EXPIRED"])

    # Win-rate uses only decided outcomes: at least TP1 hit vs SL hit.
    # Expired signals are real outcomes too, but are reported separately.
    wins = len([r for r in closed if "tp1" in r.get("hit", []) or str(r.get("status", "")).startswith("TP")])
    losses = sl
    decided = wins + losses
    win_rate = (wins / decided * 100) if decided else 0

    pnl_values = []
    for r in closed:
        # Prefer the actual price seen by the tracker when the signal closed.
        # Older records may not have pnl_pct, so we fall back to the recorded
        # SL/TP level rather than inventing a synthetic value.
        try:
            if r.get("pnl_pct") is not None:
                pnl_values.append(float(r["pnl_pct"]))
                continue
        except Exception:
            pass
        exit_price = _closed_exit_price(r)
        if exit_price is None:
            continue
        try:
            pnl_values.append(_pnl(r, float(exit_price)))
        except Exception:
            continue
    avg_pnl = (sum(pnl_values) / len(pnl_values)) if pnl_values else 0

    by_quality = {}
    for r in closed:
        q = r.get("quality") or "—"
        by_quality.setdefault(q, {"w": 0, "l": 0})
        if "tp1" in r.get("hit", []) or str(r.get("status", "")).startswith("TP"):
            by_quality[q]["w"] += 1
        elif r.get("status") == "SL":
            by_quality[q]["l"] += 1

    return {
        "total": len(records),
        "closed": len(closed),
        "open": open_count,
        "tp1": tp1, "tp2": tp2, "tp3": tp3, "sl": sl, "expired": expired,
        "wins": wins, "losses": losses,
        "win_rate": win_rate,
        "avg_pnl": avg_pnl,
        "by_quality": by_quality,
    }


def recent(limit=10):
    return _load()[-limit:][::-1]
