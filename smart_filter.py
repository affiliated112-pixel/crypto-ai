"""Smart signal filter — scores every signal 0-100.
Uses: Fear & Greed Index, News sentiment, Cross-exchange validation.
Signals scoring below 45 are suppressed.
"""
import time
import feeds
import news
import exchanges

_CACHE = {"fg": (0, None), "sent": (0, None)}
CACHE_TTL_FG = 600    # 10 min
CACHE_TTL_SENT = 900  # 15 min


def _cached_fear_greed():
    now = time.time()
    ts, val = _CACHE["fg"]
    if val is not None and now - ts < CACHE_TTL_FG:
        return val
    try:
        val = feeds.fear_greed_index()
        _CACHE["fg"] = (now, val)
        return val
    except Exception:
        return None


def _cached_sentiment():
    now = time.time()
    ts, val = _CACHE["sent"]
    if val is not None and now - ts < CACHE_TTL_SENT:
        return val
    try:
        val = news.aggregate_sentiment()
        _CACHE["sent"] = (now, val)
        return val
    except Exception:
        return None


def evaluate(symbol, direction, price, base_conf):
    """Return (score, quality_label, filters_list, suppressed_bool).

    filters_list: list of (name, ok_bool, detail_string) for embed display.
    suppressed: True if score < 45 — caller should skip sending this signal.
    """
    score = 50  # baseline
    filters = []
    is_buy = direction == "BUY"

    # Bonus for base confidence label from bot.py
    if base_conf:
        if "HIGH" in base_conf:
            score += 15
        elif "MEDIUM" in base_conf:
            score += 5

    # ---- 1. Fear & Greed filter ----
    fg = _cached_fear_greed()
    if fg and isinstance(fg, dict) and "value" in fg:
        v = fg["value"]
        if is_buy:
            if v >= 85:
                score -= 20; filters.append(("Fear & Greed", False, f"Extreme Greed `{v}` — risky BUY"))
            elif v >= 70:
                score -= 5;  filters.append(("Fear & Greed", True,  f"Greed `{v}` — caution"))
            elif v <= 30:
                score += 15; filters.append(("Fear & Greed", True,  f"Fear `{v}` — excellent BUY zone"))
            else:
                score += 5;  filters.append(("Fear & Greed", True,  f"Neutral `{v}`"))
        else:  # SELL
            if v <= 15:
                score -= 20; filters.append(("Fear & Greed", False, f"Extreme Fear `{v}` — risky SELL"))
            elif v <= 30:
                score -= 5;  filters.append(("Fear & Greed", True,  f"Fear `{v}` — caution"))
            elif v >= 70:
                score += 15; filters.append(("Fear & Greed", True,  f"Greed `{v}` — excellent SELL zone"))
            else:
                score += 5;  filters.append(("Fear & Greed", True,  f"Neutral `{v}`"))

    # ---- 2. News sentiment ----
    sent = _cached_sentiment()
    if sent and isinstance(sent, dict):
        total = sent.get("total", 0)
        label = sent.get("label", "Neutral")
        if is_buy:
            if total <= -5:
                score -= 15; filters.append(("News Sentiment", False, f"{label} `{total:+d}` — bearish news"))
            elif total >= 3:
                score += 10; filters.append(("News Sentiment", True,  f"{label} `{total:+d}` — bullish news"))
            else:
                filters.append(("News Sentiment", True, f"{label} `{total:+d}`"))
        else:  # SELL
            if total >= 5:
                score -= 15; filters.append(("News Sentiment", False, f"{label} `{total:+d}` — bullish news"))
            elif total <= -3:
                score += 10; filters.append(("News Sentiment", True,  f"{label} `{total:+d}` — bearish news"))
            else:
                filters.append(("News Sentiment", True, f"{label} `{total:+d}`"))

    # ---- 3. Cross-exchange validation ----
    try:
        arb = exchanges.arbitrage(symbol)
        if arb and arb.get("spread_pct") is not None:
            spread = abs(arb["spread_pct"])
            if spread < 0.15:
                score += 10; filters.append(("Cross-Exchange", True,  f"Spread `{spread:.3f}%` — legit"))
            elif spread < 0.4:
                filters.append(("Cross-Exchange", True, f"Spread `{spread:.3f}%` — normal"))
            else:
                score -= 10; filters.append(("Cross-Exchange", False, f"Spread `{spread:.3f}%` — suspicious"))
    except Exception:
        pass

    # Clamp
    score = max(0, min(100, score))

    if score >= 80:   quality = "PREMIUM"
    elif score >= 60: quality = "STRONG"
    elif score >= 45: quality = "STANDARD"
    else:             quality = None

    suppressed = score < 45
    return score, quality, filters, suppressed
