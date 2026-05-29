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


def record_signal(symbol, direction, entry, score=None, quality=None):
    """Append a new signal to the log."""
    records = _load()
    if direction == "BUY":
        sl, tp1, tp2, tp3 = entry * 0.98, entry * 1.02, entry * 1.04, entry * 1.07
    else:
        sl, tp1, tp2, tp3 = entry * 1.02, entry * 0.98, entry * 0.96, entry * 0.93
    rec = {
        "id": int(time.time() * 1000),
        "symbol": symbol,
        "direction": direction,
        "entry": entry,
        "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "score": score, "quality": quality,
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
    try:
        r = requests.get(
            f"https://api.binance.us/api/v3/ticker/price?symbol={symbol}",
            headers=UA, timeout=8,
        )
        r.raise_for_status()
        return float(r.json()["price"])
    except Exception:
        return None


def _pnl(rec, price):
    """Return P&L percentage from entry to current price."""
    if not rec.get("entry"):
        return 0
    if rec["direction"] == "BUY":
        return (price - rec["entry"]) / rec["entry"] * 100
    return (rec["entry"] - price) / rec["entry"] * 100


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
            rec["status"] = "SL"
            rec["closed_at"] = datetime.now(timezone.utc).isoformat()
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
                rec["status"] = "TP3"
                rec["closed_at"] = datetime.now(timezone.utc).isoformat()
    else:  # SELL
        rec["max_favor"] = min(rec.get("max_favor", price), price)
        rec["max_against"] = max(rec.get("max_against", price), price)
        if price >= rec["sl"]:
            rec["status"] = "SL"
            rec["closed_at"] = datetime.now(timezone.utc).isoformat()
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
                rec["status"] = "TP3"
                rec["closed_at"] = datetime.now(timezone.utc).isoformat()

    # Expiry
    try:
        opened = datetime.fromisoformat(rec["opened_at"].replace("Z", "+00:00"))
        if rec["status"] == "OPEN" and (datetime.now(timezone.utc) - opened).total_seconds() > SIGNAL_EXPIRY_HOURS * 3600:
            rec["status"] = "EXPIRED"
            rec["closed_at"] = datetime.now(timezone.utc).isoformat()
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
            rec["status"] = "SL"; rec["closed_at"] = datetime.now(timezone.utc).isoformat()
            return
        for k, v in (("tp1", rec["tp1"]), ("tp2", rec["tp2"]), ("tp3", rec["tp3"])):
            if price >= v and k not in rec["hit"]:
                rec["hit"].append(k)
        if "tp3" in rec["hit"]:
            rec["status"] = "TP3"; rec["closed_at"] = datetime.now(timezone.utc).isoformat()
    else:
        rec["max_favor"] = min(rec.get("max_favor", price), price)
        if price >= rec["sl"]:
            rec["status"] = "SL"; rec["closed_at"] = datetime.now(timezone.utc).isoformat()
            return
        for k, v in (("tp1", rec["tp1"]), ("tp2", rec["tp2"]), ("tp3", rec["tp3"])):
            if price <= v and k not in rec["hit"]:
                rec["hit"].append(k)
        if "tp3" in rec["hit"]:
            rec["status"] = "TP3"; rec["closed_at"] = datetime.now(timezone.utc).isoformat()


async def poll_loop():
    """Background loop: poll every POLL_SECONDS and fire alerts."""
    while True:
        try:
            await poll_once_async()
        except Exception as e:
            print(f"[tracker] poll error: {e}", flush=True)
        await asyncio.sleep(POLL_SECONDS)


def compute_stats(symbol=None, days=None):
    records = _load()
    if symbol:
        records = [r for r in records if r["symbol"] == symbol.upper()]
    if days:
        cutoff = time.time() - days * 86400
        records = [r for r in records if r["id"] / 1000 >= cutoff]

    closed = [r for r in records if r["status"] != "OPEN"]
    if not closed:
        return {"total": 0, "open": len([r for r in records if r["status"] == "OPEN"])}

    tp1 = len([r for r in closed if "tp1" in r.get("hit", [])])
    tp2 = len([r for r in closed if "tp2" in r.get("hit", [])])
    tp3 = len([r for r in closed if "tp3" in r.get("hit", [])])
    sl = len([r for r in closed if r["status"] == "SL"])
    expired = len([r for r in closed if r["status"] == "EXPIRED"])
    wins = tp1
    losses = sl
    decided = wins + losses
    win_rate = (wins / decided * 100) if decided else 0
    avg_pnl_per_decided = ((wins * 2) - (losses * 2)) / decided if decided else 0

    by_quality = {}
    for r in closed:
        q = r.get("quality") or "—"
        by_quality.setdefault(q, {"w": 0, "l": 0})
        if "tp1" in r.get("hit", []):
            by_quality[q]["w"] += 1
        elif r["status"] == "SL":
            by_quality[q]["l"] += 1

    return {
        "total": len(records), "closed": len(closed),
        "open": len([r for r in records if r["status"] == "OPEN"]),
        "tp1": tp1, "tp2": tp2, "tp3": tp3, "sl": sl, "expired": expired,
        "wins": wins, "losses": losses,
        "win_rate": win_rate, "avg_pnl": avg_pnl_per_decided,
        "by_quality": by_quality,
    }


def recent(limit=10):
    return _load()[-limit:][::-1]
