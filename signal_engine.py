"""signal_engine.py — Best-of-day signal engine.

Core philosophy:
  Scan everything every 15 min. Send NOTHING unless it's genuinely good.
  Pick the TOP candidates. Send max 3 FREE + max 5 VIP per day.
  A day with 0 signals is fine. A day with 1 elite signal is great.
  Spam kills trust. Quality builds it.

Flow:
  1. Every 15 min: scan all coins silently
  2. Score each coin with 15 indicators (0-100)
  3. Add candidates to a ranked queue
  4. Send only when score >= threshold AND daily budget not exhausted
  5. Never send 2 correlated coins in same direction within 2h
  6. Never send during low-liquidity hours (00:00–08:00 UTC)
"""

import time
from datetime import datetime, timezone, date
from typing import Optional

import coins_config

# ─── DAILY BUDGET (max signals per day) ──────────────────────────────────────
FREE_MAX_PER_DAY    = 3     # max 3 FREE signals per day total
VIP_MAX_PER_DAY     = 5     # max 5 VIP signals per day total

# ─── SCORE THRESHOLDS ────────────────────────────────────────────────────────
FREE_MIN_SCORE      = 58    # raised from 45 — only clear setups
VIP_MIN_SCORE       = 70    # raised from 65 — only high-probability setups

# ─── RISK:REWARD ─────────────────────────────────────────────────────────────
FREE_MIN_RR         = 1.8   # at least 1.8:1 R:R
VIP_MIN_RR          = 2.2   # at least 2.2:1 R:R

# ─── COOLDOWN (same coin, same direction) ────────────────────────────────────
FREE_COOLDOWN_H     = 12    # 12h cooldown per coin FREE
VIP_COOLDOWN_H      = 8     # 8h cooldown per coin VIP

# ─── ACTIVE HOURS (UTC) ──────────────────────────────────────────────────────
ACTIVE_START_UTC    = 8     # 08:00 UTC
ACTIVE_END_UTC      = 22    # 22:00 UTC

# ─── CORRELATION GROUPS ──────────────────────────────────────────────────────
# Don't send same direction for highly correlated coins within 2h
CORRELATION_GROUPS: list[set] = [
    {"BTCUSDT", "ETHUSDT"},
    {"SOLUSDT", "AVAXUSDT", "NEARUSDT", "APTUSDT", "SUIUSDT"},
    {"OPUSDT",  "ARBUSDT",  "MATICUSDT"},
    {"SANDUSDT","MANAUSDT"},
    {"SHIBUSDT","DOGEUSDT"},
    {"AAVEUSDT","UNIUSDT","GRTUSDT"},
]

# ─── STATE ────────────────────────────────────────────────────────────────────
_last_sent:         dict[str, dict] = {}          # symbol → {signal, ts}
_last_group:        dict[int, dict] = {}          # group_idx → {symbol, signal, ts}
_daily_free:        dict[date, int] = {}          # date → count sent FREE
_daily_vip:         dict[date, int] = {}          # date → count sent VIP
_candidate_queue:   list[dict]      = []          # ranked candidates waiting to send
_btc_cache:         dict            = {"signal": None, "ts": 0}

# ─── DAILY BUDGET ─────────────────────────────────────────────────────────────

def _today() -> date:
    return datetime.now(timezone.utc).date()

def free_budget_ok() -> bool:
    return _daily_free.get(_today(), 0) < FREE_MAX_PER_DAY

def vip_budget_ok() -> bool:
    return _daily_vip.get(_today(), 0) < VIP_MAX_PER_DAY

def _consume_free():
    d = _today()
    _daily_free[d] = _daily_free.get(d, 0) + 1

def _consume_vip():
    d = _today()
    _daily_vip[d] = _daily_vip.get(d, 0) + 1

def budget_status() -> dict:
    d = _today()
    return {
        "free_sent":  _daily_free.get(d, 0),
        "free_max":   FREE_MAX_PER_DAY,
        "vip_sent":   _daily_vip.get(d, 0),
        "vip_max":    VIP_MAX_PER_DAY,
        "free_ok":    free_budget_ok(),
        "vip_ok":     vip_budget_ok(),
    }

# ─── QUALITY SCORE (0–100) ────────────────────────────────────────────────────

def compute_quality_score(ind: dict, signal: str, mtf: dict | None = None) -> int:
    """
    Composite quality score from 15 technical indicators.
    Each indicator adds to score only if it CONFIRMS the signal direction.
    """
    if not ind:
        return 0

    score  = 0
    is_buy = signal == "BUY"

    rsi      = ind.get("rsi", 50)
    macd_h   = ind.get("macd_hist", 0)
    adx      = ind.get("adx", 20)
    adx_pos  = ind.get("adx_pos", 10)
    adx_neg  = ind.get("adx_neg", 10)
    cmf      = ind.get("cmf", 0)
    willr    = ind.get("willr", -50)
    bb_pct   = ind.get("bb_pct", 0.5)
    stoch_k  = ind.get("stoch_k", 0.5)
    obv_up   = ind.get("obv_up", False)
    vol_surge= ind.get("vol_surge", False)
    ema200   = ind.get("ema200", 0)
    vwap     = ind.get("vwap", 0)
    price    = ind.get("price", ind.get("vwap", 1))
    bull_div = ind.get("bull_div", False)
    bear_div = ind.get("bear_div", False)
    s_bull   = ind.get("struct_bull", False)
    s_bear   = ind.get("struct_bear", False)

    # 1. RSI — 0-18 pts
    if is_buy:
        if rsi < 25:   score += 18
        elif rsi < 35: score += 12
        elif rsi < 42: score += 6
        elif rsi > 65: score -= 8   # penalty: buying overbought
    else:
        if rsi > 75:   score += 18
        elif rsi > 65: score += 12
        elif rsi > 58: score += 6
        elif rsi < 35: score -= 8

    # 2. MACD histogram direction — 0-12 pts
    if (is_buy and macd_h > 0) or (not is_buy and macd_h < 0):
        score += 12
    # Bonus if histogram is growing (momentum increasing)
    macd_prev = ind.get("macd_prev", macd_h)
    if is_buy and macd_h > macd_prev > 0:   score += 4
    if not is_buy and macd_h < macd_prev < 0: score += 4

    # 3. ADX trend strength — 0-12 pts
    if adx > 35:   score += 12
    elif adx > 28: score += 8
    elif adx > 20: score += 4
    # DI alignment
    if is_buy and adx_pos > adx_neg:   score += 5
    if not is_buy and adx_neg > adx_pos: score += 5

    # 4. Volume (OBV + CMF + surge) — 0-12 pts
    if vol_surge:                                      score += 8
    if (is_buy and obv_up) or (not is_buy and not obv_up): score += 4
    if is_buy and cmf > 0.12:   score += 5
    elif is_buy and cmf > 0.05: score += 2
    elif not is_buy and cmf < -0.12: score += 5
    elif not is_buy and cmf < -0.05: score += 2

    # 5. Bollinger Band position — 0-7 pts
    if is_buy and bb_pct < 0.15:    score += 7   # very near lower band
    elif is_buy and bb_pct < 0.25:  score += 4
    elif not is_buy and bb_pct > 0.85: score += 7
    elif not is_buy and bb_pct > 0.75: score += 4

    # 6. StochRSI — 0-6 pts
    if is_buy and stoch_k < 0.20:   score += 6
    elif is_buy and stoch_k < 0.30: score += 3
    elif not is_buy and stoch_k > 0.80: score += 6
    elif not is_buy and stoch_k > 0.70: score += 3

    # 7. Williams %R — 0-5 pts
    if is_buy and willr < -85:      score += 5
    elif is_buy and willr < -75:    score += 3
    elif not is_buy and willr > -15: score += 5
    elif not is_buy and willr > -25: score += 3

    # 8. EMA200 trend context — 0-8 pts (trade WITH the trend)
    if ema200 and price:
        if is_buy and price > ema200:      score += 8
        elif not is_buy and price < ema200: score += 8
        # Penalty for counter-trend trades
        elif is_buy and price < ema200:    score -= 4
        elif not is_buy and price > ema200: score -= 4

    # 9. VWAP position — 0-5 pts
    if vwap and price:
        if is_buy and price <= vwap * 1.002:      score += 5
        elif not is_buy and price >= vwap * 0.998: score += 5

    # 10. Divergence — 0-12 pts (strongest signal of reversal)
    if is_buy and bull_div:   score += 12
    elif not is_buy and bear_div: score += 12

    # 11. Market structure — 0-8 pts
    if (is_buy and s_bull) or (not is_buy and s_bear):
        score += 8

    # 12. MTF alignment — 0-15 pts (VIP only)
    if mtf:
        aligned = sum(
            1 for tf in ("5m", "15m", "1h")
            if mtf.get(tf, {}).get("signal") == signal
        )
        score += aligned * 5   # 5, 10, or 15 pts

    return max(0, min(score, 100))

def compute_rr(price: float, signal: str, atr: float) -> float:
    """Risk:Reward using TP2 distance vs SL distance (ATR-based)."""
    if atr <= 0:
        return 1.0
    return round((3.0 * atr) / (1.2 * atr), 2)   # always 2.5 with standard ATR multiples

# ─── CONTEXT CHECKS ──────────────────────────────────────────────────────────

def is_active_hour() -> bool:
    h = datetime.now(timezone.utc).hour
    return ACTIVE_START_UTC <= h < ACTIVE_END_UTC

def cache_btc_signal(sig: str | None):
    _btc_cache["signal"] = sig
    _btc_cache["ts"]     = time.time()

def get_cached_btc_signal() -> str | None:
    if time.time() - _btc_cache["ts"] > 900:
        return None
    return _btc_cache["signal"]

def _btc_context_ok(symbol: str, signal: str) -> tuple[bool, str]:
    """Block altcoin signal if it's strongly against BTC direction."""
    if symbol == "BTCUSDT":
        return True, ""
    btc_sig = get_cached_btc_signal()
    if btc_sig is None:
        return True, ""
    if signal == "BUY" and btc_sig == "SELL":
        return False, "BTC trending down — altcoin BUY high risk"
    if signal == "SELL" and btc_sig == "BUY":
        return False, "BTC trending up — altcoin SELL high risk"
    return True, ""

def _cooldown_ok(symbol: str, signal: str, hours: int) -> bool:
    now  = time.time()
    last = _last_sent.get(symbol, {})
    if last.get("signal") == signal:
        elapsed = now - last.get("ts", 0)
        if elapsed < hours * 3600:
            return False
    return True

def _correlation_ok(symbol: str, signal: str) -> tuple[bool, str]:
    now = time.time()
    for i, group in enumerate(CORRELATION_GROUPS):
        if symbol not in group:
            continue
        last = _last_group.get(i, {})
        if (last.get("signal") == signal
                and last.get("symbol") != symbol
                and now - last.get("ts", 0) < 7200):   # 2h window
            return False, f"Correlated with recent {last.get('symbol','?')} signal"
    return True, ""

def _record_sent(symbol: str, signal: str):
    now = time.time()
    _last_sent[symbol] = {"signal": signal, "ts": now}
    for i, group in enumerate(CORRELATION_GROUPS):
        if symbol in group:
            _last_group[i] = {"symbol": symbol, "signal": signal, "ts": now}

# ─── CANDIDATE QUEUE ─────────────────────────────────────────────────────────

def evaluate_candidate(
    symbol:     str,
    signal:     str,
    price:      float,
    ind:        dict,
    mtf:        dict | None = None,
    tier:       str = "free",   # "free" or "vip"
) -> dict | None:
    """
    Run all checks on a candidate. Returns a scored candidate dict
    if it COULD be sent (ignoring daily budget), or None if hard-blocked.
    Budget check is done separately at send time.
    """
    if not signal or not price:
        return None

    if not is_active_hour():
        return None

    min_score = FREE_MIN_SCORE if tier == "free" else VIP_MIN_SCORE
    min_rr    = FREE_MIN_RR    if tier == "free" else VIP_MIN_RR
    cool_h    = FREE_COOLDOWN_H if tier == "free" else VIP_COOLDOWN_H

    # Cooldown
    if not _cooldown_ok(symbol, signal, cool_h):
        return None

    # Quality score
    score = compute_quality_score(ind, signal, mtf if tier == "vip" else None)
    if score < min_score:
        return None

    # R:R
    atr = ind.get("atr", price * 0.018) if ind else price * 0.018
    rr  = compute_rr(price, signal, atr)
    if rr < min_rr:
        return None

    # MTF: VIP requires 2/3 TFs aligned
    mtf_aligned = 0
    if mtf:
        mtf_aligned = sum(
            1 for tf in ("5m", "15m", "1h")
            if mtf.get(tf, {}).get("signal") == signal
        )
        if tier == "vip" and mtf_aligned < 2:
            return None

    # BTC context
    btc_ok, btc_reason = _btc_context_ok(symbol, signal)
    if not btc_ok:
        return None

    # Correlation
    corr_ok, corr_reason = _correlation_ok(symbol, signal)
    if not corr_ok:
        return None

    return {
        "symbol":      symbol,
        "signal":      signal,
        "price":       price,
        "score":       score,
        "rr":          rr,
        "mtf_aligned": mtf_aligned,
        "tier":        tier,
        "ind":         ind,
        "mtf":         mtf,
        "ts":          time.time(),
    }

def approve_and_record(candidate: dict) -> bool:
    """
    Final gate at send time: check daily budget + correlation (again, since
    another coin may have fired since evaluate_candidate was called).
    Records the signal if approved. Returns True if approved.
    """
    tier   = candidate["tier"]
    symbol = candidate["symbol"]
    signal = candidate["signal"]

    # Budget
    if tier == "free" and not free_budget_ok():
        return False
    if tier == "vip" and not vip_budget_ok():
        return False

    # Correlation (re-check, another coin may have sent recently)
    corr_ok, _ = _correlation_ok(symbol, signal)
    if not corr_ok:
        return False

    # Cooldown (re-check)
    cool_h = FREE_COOLDOWN_H if tier == "free" else VIP_COOLDOWN_H
    if not _cooldown_ok(symbol, signal, cool_h):
        return False

    # Approve
    _record_sent(symbol, signal)
    if tier == "free":
        _consume_free()
    else:
        _consume_vip()

    return True

# ─── QUALITY LABEL ────────────────────────────────────────────────────────────

def quality_label(score: int) -> str:
    if score >= 88: return "🏆 ELITE"
    if score >= 75: return "🔥 EXCELLENT"
    if score >= 62: return "⚡ GOOD"
    if score >= 50: return "📊 STANDARD"
    return "⚠️ WEAK"

def quality_explanation(score: int, rr: float, mtf_aligned: int) -> str:
    """One honest sentence explaining signal quality."""
    grade = quality_label(score)
    mtf_s = f"{mtf_aligned}/3 timeframes" if mtf_aligned else "1 timeframe"
    return (
        f"{grade} — Score `{score}/100` · R:R `{rr}:1` · {mtf_s} confirmed.\n"
        f"{'High probability setup — indicators strongly aligned.' if score >= 75 else 'Solid setup — most indicators agree.' if score >= 62 else 'Acceptable setup — minimum criteria met.'}"
    )
