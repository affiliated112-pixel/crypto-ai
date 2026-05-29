"""Smart signal filter — ASYNC + cached.
All external calls run in a thread pool and results are cached so the
Discord event loop is never blocked.
"""
import asyncio
import time
import feeds
import news
import exchanges

_CACHE = {
    "fg":   (0, None),
    "sent": (0, None),
    "arb":  {},  # symbol -> (ts, val)
}
TTL_FG = 600     # 10 min
TTL_SENT = 900   # 15 min
TTL_ARB = 60     # 60 sec (per symbol)


async def _cached_fear_greed():
    now = time.time()
    ts, val = _CACHE["fg"]
    if val is not None and now - ts < TTL_FG:
        return val
    try:
        val = await asyncio.to_thread(feeds.fear_greed_index)
        _CACHE["fg"] = (now, val)
        return val
    except Exception:
        return None


async def _cached_sentiment():
    now = time.time()
    ts, val = _CACHE["sent"]
    if val is not None and now - ts < TTL_SENT:
        return val
    try:
        val = await asyncio.to_thread(news.aggregate_sentiment)
        _CACHE["sent"] = (now, val)
        return val
    except Exception:
        return None


async def _cached_arbitrage(symbol):
    now = time.time()
    ts, val = _CACHE["arb"].get(symbol, (0, None))
    if val is not None and now - ts < TTL_ARB:
        return val
    try:
        val = await asyncio.to_thread(exchanges.arbitrage, symbol)
        _CACHE["arb"][symbol] = (now, val)
        return val
    except Exception:
        return None


async def evaluate_async(symbol, direction, price, base_conf):
    """Async evaluate — fetches all 3 data sources IN PARALLEL."""
    score = 50
    filters = []
    is_buy = direction == "BUY"

    if base_conf:
        if "HIGH" in base_conf:
            score += 15
        elif "MEDIUM" in base_conf:
            score += 5

    # Run all 3 sources concurrently — total time = slowest one (~0.3s) instead of sum
    fg, sent, arb = await asyncio.gather(
        _cached_fear_greed(),
        _cached_sentiment(),
        _cached_arbitrage(symbol),
        return_exceptions=True,
    )

    # ---- 1. Fear & Greed ----
    if isinstance(fg, dict) and "value" in fg:
        v = fg["value"]
        if is_buy:
            if v >= 85: score -= 20; filters.append(("Fear & Greed", False, f"Extreme Greed `{v}` — risky BUY"))
            elif v >= 70: score -= 5; filters.append(("Fear & Greed", True,  f"Greed `{v}` — caution"))
            elif v <= 30: score += 15; filters.append(("Fear & Greed", True,  f"Fear `{v}` — excellent BUY zone"))
            else: score += 5; filters.append(("Fear & Greed", True,  f"Neutral `{v}`"))
        else:
            if v <= 15: score -= 20; filters.append(("Fear & Greed", False, f"Extreme Fear `{v}` — risky SELL"))
            elif v <= 30: score -= 5; filters.append(("Fear & Greed", True,  f"Fear `{v}` — caution"))
            elif v >= 70: score += 15; filters.append(("Fear & Greed", True,  f"Greed `{v}` — excellent SELL zone"))
            else: score += 5; filters.append(("Fear & Greed", True,  f"Neutral `{v}`"))

    # ---- 2. News sentiment ----
    if isinstance(sent, dict):
        total = sent.get("total", 0)
        label = sent.get("label", "Neutral")
        if is_buy:
            if total <= -5: score -= 15; filters.append(("News Sentiment", False, f"{label} `{total:+d}`"))
            elif total >= 3: score += 10; filters.append(("News Sentiment", True,  f"{label} `{total:+d}`"))
            else: filters.append(("News Sentiment", True, f"{label} `{total:+d}`"))
        else:
            if total >= 5: score -= 15; filters.append(("News Sentiment", False, f"{label} `{total:+d}`"))
            elif total <= -3: score += 10; filters.append(("News Sentiment", True,  f"{label} `{total:+d}`"))
            else: filters.append(("News Sentiment", True, f"{label} `{total:+d}`"))

    # ---- 3. Cross-exchange ----
    if isinstance(arb, dict) and arb.get("spread_pct") is not None:
        spread = abs(arb["spread_pct"])
        if spread < 0.15: score += 10; filters.append(("Cross-Exchange", True,  f"Spread `{spread:.3f}%` — legit"))
        elif spread < 0.4: filters.append(("Cross-Exchange", True, f"Spread `{spread:.3f}%` — normal"))
        else: score -= 10; filters.append(("Cross-Exchange", False, f"Spread `{spread:.3f}%` — suspicious"))

    score = max(0, min(100, score))
    if score >= 80:   quality = "PREMIUM"
    elif score >= 60: quality = "STRONG"
    elif score >= 45: quality = "STANDARD"
    else:             quality = None
    suppressed = score < 45
    return score, quality, filters, suppressed


def evaluate(symbol, direction, price, base_conf):
    """Sync wrapper — used in sync hot paths. Returns cached values only,
    never blocks on HTTP. If cache is empty, returns a neutral score.
    """
    score = 50
    filters = []
    is_buy = direction == "BUY"
    if base_conf:
        if "HIGH" in base_conf: score += 15
        elif "MEDIUM" in base_conf: score += 5

    # Use cached values ONLY — no HTTP calls
    now = time.time()
    fg_ts, fg = _CACHE["fg"]
    sent_ts, sent = _CACHE["sent"]
    arb_ts, arb = _CACHE["arb"].get(symbol, (0, None))

    if fg and now - fg_ts < TTL_FG and isinstance(fg, dict) and "value" in fg:
        v = fg["value"]
        if is_buy:
            if v >= 85: score -= 20; filters.append(("Fear & Greed", False, f"Extreme Greed `{v}`"))
            elif v <= 30: score += 15; filters.append(("Fear & Greed", True, f"Fear `{v}`"))
            else: filters.append(("Fear & Greed", True, f"`{v}`"))
        else:
            if v <= 15: score -= 20; filters.append(("Fear & Greed", False, f"Extreme Fear `{v}`"))
            elif v >= 70: score += 15; filters.append(("Fear & Greed", True, f"Greed `{v}`"))
            else: filters.append(("Fear & Greed", True, f"`{v}`"))

    if sent and now - sent_ts < TTL_SENT and isinstance(sent, dict):
        total = sent.get("total", 0)
        label = sent.get("label", "Neutral")
        if is_buy and total <= -5: score -= 15
        elif is_buy and total >= 3: score += 10
        elif not is_buy and total >= 5: score -= 15
        elif not is_buy and total <= -3: score += 10
        filters.append(("News Sentiment", True, f"{label} `{total:+d}`"))

    if arb and now - arb_ts < TTL_ARB and isinstance(arb, dict) and arb.get("spread_pct") is not None:
        spread = abs(arb["spread_pct"])
        if spread < 0.15: score += 10
        elif spread >= 0.4: score -= 10
        filters.append(("Cross-Exchange", spread < 0.4, f"Spread `{spread:.3f}%`"))

    score = max(0, min(100, score))
    if score >= 80:   quality = "PREMIUM"
    elif score >= 60: quality = "STRONG"
    elif score >= 45: quality = "STANDARD"
    else:             quality = None
    return score, quality, filters, score < 45


async def background_refresh_loop(symbols, interval=120):
    """Background task that refreshes all caches every `interval` seconds.
    This means the sync evaluate() always has fresh data without blocking.
    """
    while True:
        try:
            tasks = [_cached_fear_greed(), _cached_sentiment()]
            for s in symbols:
                tasks.append(_cached_arbitrage(s))
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            print(f"[smart_filter] refresh error: {e}", flush=True)
        await asyncio.sleep(interval)
