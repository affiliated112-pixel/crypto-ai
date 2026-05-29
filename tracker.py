"""Signal performance tracker.
Logs every signal to JSON, polls Binance every few minutes to check
if price hit SL or any TP, computes win rate.
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
    """Append a new signal to the log. Computes SL/TP from entry."""
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
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "score": score,
        "quality": quality,
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "status": "OPEN",
        "hit": [],
        "max_favor": entry,
        "max_against": entry,
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


def _evaluate(rec, price):
    """Update record in place. Returns True if status changed."""
    if rec["status"] != "OPEN":
        return False
    is_buy = rec["direction"] == "BUY"
    changed = False

    if is_buy:
        rec["max_favor"] = max(rec.get("max_favor", price), price)
        rec["max_against"] = min(rec.get("max_against", price), price)
        if price <= rec["sl"]:
            rec["status"] = "SL"
            rec["closed_at"] = datetime.now(timezone.utc).isoformat()
            return True
        for tp_key, tp_val in (("tp1", rec["tp1"]), ("tp2", rec["tp2"]), ("tp3", rec["tp3"])):
            if price >= tp_val and tp_key not in rec["hit"]:
                rec["hit"].append(tp_key); changed = True
        if "tp3" in rec["hit"]:
            rec["status"] = "TP3"
            rec["closed_at"] = datetime.now(timezone.utc).isoformat()
            return True
    else:  # SELL
        rec["max_favor"] = min(rec.get("max_favor", price), price)
        rec["max_against"] = max(rec.get("max_against", price), price)
        if price >= rec["sl"]:
            rec["status"] = "SL"
            rec["closed_at"] = datetime.now(timezone.utc).isoformat()
            return True
        for tp_key, tp_val in (("tp1", rec["tp1"]), ("tp2", rec["tp2"]), ("tp3", rec["tp3"])):
            if price <= tp_val and tp_key not in rec["hit"]:
                rec["hit"].append(tp_key); changed = True
        if "tp3" in rec["hit"]:
            rec["status"] = "TP3"
            rec["closed_at"] = datetime.now(timezone.utc).isoformat()
            return True

    # Expiry
    try:
        opened = datetime.fromisoformat(rec["opened_at"].replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - opened).total_seconds() > SIGNAL_EXPIRY_HOURS * 3600:
            rec["status"] = "EXPIRED"
            rec["closed_at"] = datetime.now(timezone.utc).isoformat()
            return True
    except Exception:
        pass

    return changed


def poll_once():
    """Check all open signals once."""
    records = _load()
    by_sym = {}
    open_recs = [r for r in records if r.get("status") == "OPEN"]
    if not open_recs:
        return
    symbols = list({r["symbol"] for r in open_recs})
    for sym in symbols:
        p = _get_price(sym)
        if p is not None:
            by_sym[sym] = p
    for r in records:
        if r.get("status") == "OPEN":
            price = by_sym.get(r["symbol"])
            if price is not None:
                _evaluate(r, price)
    _save(records)


async def poll_loop():
    """Background loop: poll every POLL_SECONDS."""
    while True:
        try:
            poll_once()
        except Exception as e:
            print(f"[tracker] poll error: {e}", flush=True)
        await asyncio.sleep(POLL_SECONDS)


def compute_stats(symbol=None, days=None):
    """Compute win rate over closed signals."""
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
    sl  = len([r for r in closed if r["status"] == "SL"])
    expired = len([r for r in closed if r["status"] == "EXPIRED"])
    wins = tp1
    losses = sl
    decided = wins + losses
    win_rate = (wins / decided * 100) if decided else 0

    # Average return assuming exit at TP1 / SL with no scaling
    # BUY: +2% if tp1 hit, -2% if SL. SELL: same magnitude.
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
        "total": len(records),
        "closed": len(closed),
        "open": len([r for r in records if r["status"] == "OPEN"]),
        "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "sl": sl, "expired": expired,
        "wins": wins, "losses": losses,
        "win_rate": win_rate,
        "avg_pnl": avg_pnl_per_decided,
        "by_quality": by_quality,
    }


def recent(limit=10):
    """Return most recent signals."""
    records = _load()
    return records[-limit:][::-1]
