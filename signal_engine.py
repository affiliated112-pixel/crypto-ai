"""signal_engine.py — Best-of-day signal engine.

Core philosophy:
  Scan everything every 15 min. Send NOTHING unless it's genuinely good.
  Pick the TOP candidates. Send max 3 FREE + max 5 VIP per day.
  A day with 0 signals is fine. A day with 1 elite signal is great.
  Spam kills trust. Quality builds it.

Flow:
  1. Every 15 min: scan all coins silently
  2. Score each coin with 20 indicators (0-100)
  3. Add candidates to a ranked queue
  4. Send only when score >= threshold AND daily budget not exhausted
  5. Never send 2 correlated coins in same direction within 2h
  6. Never send during low-liquidity hours (00:00–08:00 UTC)

V2 Improvements (2026):
  [1] MTF confluence — exponential bonus: 1TF=5, 2TF=12, 3TF=20 (+5 elite if ADX>28)
  [2] Market structure — proper HH/HL/LH/LL swing detection via ind["struct_score"]
  [3] Volume Profile POC — price near Point of Control → +8 pts
  [4] BTC macro filter — BTC drops >2% in 4h → all altcoin BUYs blocked
  [5] Dynamic TP/SL via compute_levels() — ATR-based, calibrated per volatility
"""

import os
import time
from datetime import datetime, timezone, date
from typing import Optional

import coins_config

# ─── BTC MACRO FILTER STATE ───────────────────────────────────────────────────
# Tracks BTC price over time to detect 4h macro drops
_btc_price_history: list[tuple[float, float]] = []   # [(unix_ts, price), ...]
_BTC_DROP_THRESHOLD = 0.02   # 2% drop in 4h blocks ALL altcoin BUYs
_BTC_HISTORY_MAX    = 50     # keep at most 50 price snapshots

# ─── RUNTIME SETTINGS ─────────────────────────────────────────────────────────
# Railway/Discord deployments need these to be adjustable without code edits.
# SIGNAL_MODE controls sensible defaults, and every value can still be overridden
# with a dedicated env var (FREE_MIN_SCORE, VIP_MIN_SCORE, etc.).
def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return int(default)
    try:
        return int(str(raw).strip())
    except ValueError:
        return int(default)


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return float(default)
    try:
        return float(str(raw).strip())
    except ValueError:
        return float(default)


_SIGNAL_MODE = os.environ.get("SIGNAL_MODE", "balanced").strip().lower()
_MODE_DEFAULTS = {
    # Original strict behaviour: very few signals, highest filtering.
    "strict": {
        "FREE_MAX_PER_DAY": 3, "VIP_MAX_PER_DAY": 5,
        "FREE_MIN_SCORE": 58, "VIP_MIN_SCORE": 70,
        "FREE_MIN_RR": 1.8, "VIP_MIN_RR": 2.2,
        "FREE_COOLDOWN_H": 12, "VIP_COOLDOWN_H": 8,
        "ACTIVE_START_UTC": 8, "ACTIVE_END_UTC": 22,
    },
    # Default for the Discord bot: sends valid medium setups, still keeps
    # R:R, cooldown, BTC macro and correlation protection.
    "balanced": {
        "FREE_MAX_PER_DAY": 5, "VIP_MAX_PER_DAY": 10,
        "FREE_MIN_SCORE": 42, "VIP_MIN_SCORE": 52,
        "FREE_MIN_RR": 1.6, "VIP_MIN_RR": 1.8,
        "FREE_COOLDOWN_H": 6, "VIP_COOLDOWN_H": 4,
        "ACTIVE_START_UTC": 0, "ACTIVE_END_UTC": 24,
    },
    # More frequent signals for testing/small communities. Use carefully.
    "aggressive": {
        "FREE_MAX_PER_DAY": 8, "VIP_MAX_PER_DAY": 16,
        "FREE_MIN_SCORE": 35, "VIP_MIN_SCORE": 45,
        "FREE_MIN_RR": 1.3, "VIP_MIN_RR": 1.5,
        "FREE_COOLDOWN_H": 3, "VIP_COOLDOWN_H": 2,
        "ACTIVE_START_UTC": 0, "ACTIVE_END_UTC": 24,
    },
}
_DEFAULTS = _MODE_DEFAULTS.get(_SIGNAL_MODE, _MODE_DEFAULTS["balanced"])

# ─── DAILY BUDGET (max signals per day) ──────────────────────────────────────
FREE_MAX_PER_DAY    = _int_env("FREE_MAX_PER_DAY", _DEFAULTS["FREE_MAX_PER_DAY"])
VIP_MAX_PER_DAY     = _int_env("VIP_MAX_PER_DAY",  _DEFAULTS["VIP_MAX_PER_DAY"])

# ─── SCORE THRESHOLDS ────────────────────────────────────────────────────────
FREE_MIN_SCORE      = _int_env("FREE_MIN_SCORE", _DEFAULTS["FREE_MIN_SCORE"])
VIP_MIN_SCORE       = _int_env("VIP_MIN_SCORE",  _DEFAULTS["VIP_MIN_SCORE"])

# ─── RISK:REWARD ─────────────────────────────────────────────────────────────
FREE_MIN_RR         = _float_env("FREE_MIN_RR", _DEFAULTS["FREE_MIN_RR"])
VIP_MIN_RR          = _float_env("VIP_MIN_RR",  _DEFAULTS["VIP_MIN_RR"])

# ─── COOLDOWN (same coin, same direction) ────────────────────────────────────
FREE_COOLDOWN_H     = _int_env("FREE_COOLDOWN_H", _DEFAULTS["FREE_COOLDOWN_H"])
VIP_COOLDOWN_H      = _int_env("VIP_COOLDOWN_H",  _DEFAULTS["VIP_COOLDOWN_H"])

# ─── ACTIVE HOURS (UTC) ──────────────────────────────────────────────────────
# 0 → 24 means crypto signals are allowed all day. Set SIGNAL_MODE=strict or
# override SIGNAL_ACTIVE_START_UTC / SIGNAL_ACTIVE_END_UTC for a quiet window.
ACTIVE_START_UTC    = max(0, min(23, _int_env("SIGNAL_ACTIVE_START_UTC", _DEFAULTS["ACTIVE_START_UTC"])))
ACTIVE_END_UTC      = max(0, min(24, _int_env("SIGNAL_ACTIVE_END_UTC",   _DEFAULTS["ACTIVE_END_UTC"])))

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
_btc_cache:         dict            = {"signal": None, "ts": 0, "price": None}

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
    Composite quality score from 20 technical indicators (0–100).
    Each indicator adds to score only if it CONFIRMS the signal direction.

    V2 improvements applied:
      [1] MTF — exponential bonus (1TF→5, 2TF→12, 3TF→20) + elite ADX bonus
      [2] Market structure — uses struct_score (0-3) from proper HH/HL detection
      [3] Volume Profile POC — price proximity to Point of Control adds 0-8 pts
    """
    if not ind:
        return 0

    score  = 0
    is_buy = signal == "BUY"

    rsi        = ind.get("rsi", 50)
    macd_h     = ind.get("macd_hist", 0)
    adx        = ind.get("adx", 20)
    adx_pos    = ind.get("adx_pos", 10)
    adx_neg    = ind.get("adx_neg", 10)
    cmf        = ind.get("cmf", 0)
    willr      = ind.get("willr", -50)
    bb_pct     = ind.get("bb_pct", 0.5)
    stoch_k    = ind.get("stoch_k", 0.5)
    obv_up     = ind.get("obv_up", False)
    vol_surge  = ind.get("vol_surge", False)
    ema200     = ind.get("ema200", 0)
    vwap       = ind.get("vwap", 0)
    price      = ind.get("price", ind.get("vwap", 1))
    bull_div   = ind.get("bull_div", False)
    bear_div   = ind.get("bear_div", False)
    # [2] struct_score: 0=neutral, 1=weak, 2=moderate, 3=strong HH/HL or LH/LL
    struct_score = ind.get("struct_score", 0)
    s_bull     = ind.get("struct_bull", False)
    s_bear     = ind.get("struct_bear", False)
    # [3] Volume Profile POC
    poc        = ind.get("poc", None)

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
    # Bonus if histogram is growing (momentum accelerating)
    macd_prev = ind.get("macd_prev", macd_h)
    if is_buy and macd_h > macd_prev > 0:   score += 4
    if not is_buy and macd_h < macd_prev < 0: score += 4

    # 3. ADX trend strength — 0-12 pts
    if adx > 35:   score += 12
    elif adx > 28: score += 8
    elif adx > 20: score += 4
    # DI alignment
    if is_buy and adx_pos > adx_neg:    score += 5
    if not is_buy and adx_neg > adx_pos: score += 5

    # 4. Volume (OBV + CMF + surge) — 0-12 pts
    if vol_surge:                                           score += 8
    if (is_buy and obv_up) or (not is_buy and not obv_up): score += 4
    if is_buy and cmf > 0.12:        score += 5
    elif is_buy and cmf > 0.05:      score += 2
    elif not is_buy and cmf < -0.12: score += 5
    elif not is_buy and cmf < -0.05: score += 2

    # 5. Bollinger Band position — 0-7 pts
    if is_buy and bb_pct < 0.15:        score += 7
    elif is_buy and bb_pct < 0.25:      score += 4
    elif not is_buy and bb_pct > 0.85:  score += 7
    elif not is_buy and bb_pct > 0.75:  score += 4

    # 6. StochRSI — 0-6 pts
    if is_buy and stoch_k < 0.20:       score += 6
    elif is_buy and stoch_k < 0.30:     score += 3
    elif not is_buy and stoch_k > 0.80: score += 6
    elif not is_buy and stoch_k > 0.70: score += 3

    # 7. Williams %R — 0-5 pts
    if is_buy and willr < -85:           score += 5
    elif is_buy and willr < -75:         score += 3
    elif not is_buy and willr > -15:     score += 5
    elif not is_buy and willr > -25:     score += 3

    # 8. EMA200 trend context — 0-8 pts (trade WITH the macro trend)
    if ema200 and price:
        if is_buy and price > ema200:       score += 8
        elif not is_buy and price < ema200: score += 8
        elif is_buy and price < ema200:     score -= 4   # counter-trend penalty
        elif not is_buy and price > ema200: score -= 4

    # 9. VWAP position — 0-5 pts
    if vwap and price:
        if is_buy and price <= vwap * 1.002:       score += 5
        elif not is_buy and price >= vwap * 0.998: score += 5

    # 10. Divergence — 0-12 pts (strongest reversal signal)
    if is_buy and bull_div:        score += 12
    elif not is_buy and bear_div:  score += 12

    # 11. [IMPROVEMENT 2] Market structure — 0-10 pts
    #     Uses proper HH/HL (uptrend) or LH/LL (downtrend) swing detection
    #     struct_score 0=none, 1=weak, 2=moderate, 3=strong
    if is_buy and s_bull:
        score += 4 + min(struct_score, 3) * 2   # 4-10 pts based on strength
    elif not is_buy and s_bear:
        score += 4 + min(struct_score, 3) * 2
    # Penalty for trading against confirmed structure
    elif is_buy and s_bear and struct_score >= 2:  score -= 5
    elif not is_buy and s_bull and struct_score >= 2: score -= 5

    # 12. [IMPROVEMENT 3] Volume Profile POC proximity — 0-8 pts
    #     Price near Point of Control = high-volume price magnet
    if poc and price and price > 0:
        poc_dist = abs(price - poc) / price   # relative distance
        if poc_dist < 0.003:    score += 8    # within 0.3% of POC
        elif poc_dist < 0.007:  score += 5    # within 0.7%
        elif poc_dist < 0.015:  score += 2    # within 1.5%

    # 13. [IMPROVEMENT 1] MTF confluence — exponential bonus (not linear)
    #     1 TF aligned = 5 pts | 2 TF = 12 pts | 3 TF = 20 pts
    #     Elite bonus: all 3 TFs + strong trend (ADX>28) = +5 extra
    if mtf:
        aligned = sum(
            1 for tf in ("5m", "15m", "1h")
            if mtf.get(tf, {}).get("signal") == signal
        )
        mtf_pts = {0: 0, 1: 5, 2: 12, 3: 20}.get(aligned, 0)
        score += mtf_pts
        # Elite bonus: perfect alignment + strong trend
        if aligned == 3 and adx > 28:
            score += 5

    return max(0, min(score, 100))

def compute_rr(price: float, signal: str, atr: float, volatility_pct: float | None = None) -> float:
    """
    [IMPROVEMENT 5] Dynamic Risk:Reward based on actual ATR.
    Returns TP2:SL ratio — TP2 is the primary target used for R:R.
    volatility_pct: price % that ATR represents (atr/price).
    High-volatility coins get wider multipliers to avoid premature SL hits.
    """
    if atr <= 0 or price <= 0:
        return 1.5
    levels = compute_levels(price, signal, atr, volatility_pct)
    return levels["rr2"]   # R:R to TP2

def compute_levels(price: float, signal: str, atr: float,
                   volatility_pct: float | None = None) -> dict:
    """
    [IMPROVEMENT 5] Compute dynamic TP1 / TP2 / TP3 and SL.
    ATR multipliers scale with coin volatility so that:
      - Low-vol coins (BTC, ETH): tighter SL, smaller TP
      - High-vol coins (DOGE, SHIB, altcoins): wider SL, bigger TP
    This prevents premature SL triggers on volatile coins.
    """
    if atr <= 0 or price <= 0:
        # Fallback: percentage-based levels
        pct = 0.02
        if signal == "BUY":
            return {"sl": round(price*(1-pct),6), "tp1": round(price*(1+pct*1.2),6),
                    "tp2": round(price*(1+pct*2.5),6), "tp3": round(price*(1+pct*4),6),
                    "rr1": 1.2, "rr2": 2.5, "rr3": 4.0}
        else:
            return {"sl": round(price*(1+pct),6), "tp1": round(price*(1-pct*1.2),6),
                    "tp2": round(price*(1-pct*2.5),6), "tp3": round(price*(1-pct*4),6),
                    "rr1": 1.2, "rr2": 2.5, "rr3": 4.0}

    # Determine volatility tier from ATR % of price
    atr_pct = volatility_pct if volatility_pct else (atr / price)
    if atr_pct < 0.008:        # low vol  (BTC, ETH in calm markets)
        sl_m, tp1_m, tp2_m, tp3_m = 1.0, 1.3, 2.2, 3.5
    elif atr_pct < 0.018:     # medium vol (SOL, BNB, most L1s)
        sl_m, tp1_m, tp2_m, tp3_m = 1.2, 1.5, 2.5, 4.0
    elif atr_pct < 0.035:     # high vol   (AVAX, LINK, mid-caps)
        sl_m, tp1_m, tp2_m, tp3_m = 1.4, 1.8, 3.0, 5.0
    else:                      # very high vol (DOGE, SHIB, micro-caps)
        sl_m, tp1_m, tp2_m, tp3_m = 1.6, 2.0, 3.5, 6.0

    if signal == "BUY":
        sl  = round(price - atr * sl_m,  8)
        tp1 = round(price + atr * tp1_m, 8)
        tp2 = round(price + atr * tp2_m, 8)
        tp3 = round(price + atr * tp3_m, 8)
    else:   # SELL
        sl  = round(price + atr * sl_m,  8)
        tp1 = round(price - atr * tp1_m, 8)
        tp2 = round(price - atr * tp2_m, 8)
        tp3 = round(price - atr * tp3_m, 8)

    rr1 = round(tp1_m / sl_m, 2)
    rr2 = round(tp2_m / sl_m, 2)
    rr3 = round(tp3_m / sl_m, 2)

    return {"sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
            "rr1": rr1, "rr2": rr2, "rr3": rr3,
            "sl_m": sl_m, "tp1_m": tp1_m, "tp2_m": tp2_m, "tp3_m": tp3_m,
            "atr_pct": round(atr_pct * 100, 3)}

# ─── CONTEXT CHECKS ──────────────────────────────────────────────────────────

def is_active_hour() -> bool:
    """Return True when automatic signals are allowed.

    Supports normal windows (08→22), overnight windows (22→06), and 24/7
    mode (0→24 or start == end).
    """
    if ACTIVE_START_UTC == ACTIVE_END_UTC or (ACTIVE_START_UTC == 0 and ACTIVE_END_UTC == 24):
        return True
    h = datetime.now(timezone.utc).hour
    if ACTIVE_START_UTC < ACTIVE_END_UTC:
        return ACTIVE_START_UTC <= h < ACTIVE_END_UTC
    return h >= ACTIVE_START_UTC or h < ACTIVE_END_UTC


def settings_summary() -> dict:
    """Small helper for startup logs/status/debugging."""
    return {
        "mode": _SIGNAL_MODE,
        "free_min_score": FREE_MIN_SCORE,
        "vip_min_score": VIP_MIN_SCORE,
        "free_min_rr": FREE_MIN_RR,
        "vip_min_rr": VIP_MIN_RR,
        "free_max_per_day": FREE_MAX_PER_DAY,
        "vip_max_per_day": VIP_MAX_PER_DAY,
        "free_cooldown_h": FREE_COOLDOWN_H,
        "vip_cooldown_h": VIP_COOLDOWN_H,
        "active_start_utc": ACTIVE_START_UTC,
        "active_end_utc": ACTIVE_END_UTC,
    }

def cache_btc_signal(sig: str | None, price: float | None = None):
    """Cache BTC signal AND price for macro filter tracking."""
    now = time.time()
    _btc_cache["signal"] = sig
    _btc_cache["ts"]     = now
    if price and price > 0:
        _btc_cache["price"] = price
        _btc_price_history.append((now, price))
        # Keep only last 50 snapshots (≈12h at 15min intervals)
        while len(_btc_price_history) > _BTC_HISTORY_MAX:
            _btc_price_history.pop(0)

def get_cached_btc_signal() -> str | None:
    if time.time() - _btc_cache["ts"] > 900:
        return None
    return _btc_cache["signal"]

def _btc_4h_change() -> float | None:
    """
    Compute BTC % price change over the last ~4 hours.
    Returns None if not enough history. Negative = BTC dropped.
    """
    if len(_btc_price_history) < 2:
        return None
    now      = time.time()
    cutoff   = now - 4 * 3600   # 4 hours ago
    # Find the oldest snapshot within the 4h window
    baseline = None
    for ts, px in _btc_price_history:
        if ts >= cutoff:
            baseline = px
            break
    if baseline is None:
        baseline = _btc_price_history[0][1]
    current = _btc_price_history[-1][1]
    if baseline <= 0:
        return None
    return (current - baseline) / baseline   # signed % change

def _btc_context_ok(symbol: str, signal: str) -> tuple[bool, str]:
    """
    [IMPROVEMENT 4] BTC macro filter:
      - Block altcoin BUY if BTC dropped >2% in last 4h (macro sell pressure)
      - Block altcoin SELL if BTC rose >2% in last 4h (macro buy pressure)
      - Also block if BTC signal is directly opposite
    """
    if symbol == "BTCUSDT":
        return True, ""

    # ── Check 4h BTC price change (macro filter) ─────────────────
    chg = _btc_4h_change()
    if chg is not None:
        if signal == "BUY" and chg < -_BTC_DROP_THRESHOLD:
            pct = abs(chg) * 100
            return False, f"BTC down {pct:.1f}% in 4h — macro sell pressure, altcoin BUY blocked"
        if signal == "SELL" and chg > _BTC_DROP_THRESHOLD:
            pct = chg * 100
            return False, f"BTC up {pct:.1f}% in 4h — macro buy pressure, altcoin SELL blocked"

    # ── Check BTC directional signal ─────────────────────────────
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

    # R:R — [IMPROVEMENT 5] dynamic ATR-based
    atr     = ind.get("atr", price * 0.018) if ind else price * 0.018
    atr_pct = atr / price if price > 0 else 0.018
    rr  = compute_rr(price, signal, atr, atr_pct)
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

# ─── QUALITY CHECK API ────────────────────────────────────────────────────────

def check_signal_quality(
    symbol: str,
    signal: str,
    price: float,
    ind: dict,
    mtf: dict | None = None,
    tier: str = "free",
    consume: bool = False,
) -> tuple[bool, int, str, dict | None]:
    """
    Honest signal gate used by Discord commands and loops.

    Returns ``(allow, score, reason, candidate)``. When ``consume=True`` it also
    records cooldown/correlation and consumes the daily budget. On-demand commands
    should keep ``consume=False`` so checking a coin never uses up the auto-signal
    daily budget.
    """
    tier = (tier or "free").lower()
    if tier not in ("free", "vip"):
        tier = "free"

    if not signal:
        return False, 0, "No BUY/SELL signal is active", None
    if not price or price <= 0:
        return False, 0, "Missing live price", None
    if not ind:
        return False, 0, "Not enough indicator data", None

    min_score = FREE_MIN_SCORE if tier == "free" else VIP_MIN_SCORE
    min_rr    = FREE_MIN_RR    if tier == "free" else VIP_MIN_RR
    cool_h    = FREE_COOLDOWN_H if tier == "free" else VIP_COOLDOWN_H

    if not is_active_hour():
        return False, 0, f"Outside active signal hours ({ACTIVE_START_UTC}:00-{ACTIVE_END_UTC}:00 UTC)", None

    if not _cooldown_ok(symbol, signal, cool_h):
        return False, 0, f"Cooldown active for {symbol} {signal} ({cool_h}h)", None

    score = compute_quality_score(ind, signal, mtf if tier == "vip" else None)
    if score < min_score:
        return False, score, f"Quality score {score}/100 below {min_score}/100", None

    atr     = ind.get("atr", price * 0.018) if ind else price * 0.018
    atr_pct = atr / price if price > 0 else 0.018
    rr      = compute_rr(price, signal, atr, atr_pct)
    if rr < min_rr:
        return False, score, f"Risk:Reward {rr}:1 below required {min_rr}:1", None

    mtf_aligned = 0
    if mtf:
        mtf_aligned = sum(
            1 for tf in ("5m", "15m", "1h")
            if mtf.get(tf, {}).get("signal") == signal
        )
    if tier == "vip" and mtf_aligned < 2:
        return False, score, f"VIP requires 2/3 timeframe agreement; got {mtf_aligned}/3", None

    btc_ok, btc_reason = _btc_context_ok(symbol, signal)
    if not btc_ok:
        return False, score, btc_reason or "BTC macro context blocks this setup", None

    corr_ok, corr_reason = _correlation_ok(symbol, signal)
    if not corr_ok:
        return False, score, corr_reason or "Correlated signal sent recently", None

    candidate = {
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

    if consume:
        if tier == "free" and not free_budget_ok():
            return False, score, f"FREE daily budget reached ({FREE_MAX_PER_DAY}/day)", candidate
        if tier == "vip" and not vip_budget_ok():
            return False, score, f"VIP daily budget reached ({VIP_MAX_PER_DAY}/day)", candidate
        if not approve_and_record(candidate):
            return False, score, "Blocked by final cooldown/correlation/budget check", candidate

    return True, score, "OK", candidate

# ─── QUALITY LABEL ────────────────────────────────────────────────────────────

def _normalise_gate_inputs(price_or_ind, ind: dict | None):
    """Accept both old and new call styles.

    New style: should_send_free(symbol, signal, price, ind, ...)
    Old style: should_send_free(symbol, signal, ind, mtf=None)
    """
    if isinstance(price_or_ind, dict):
        out = dict(price_or_ind)
        price = float(out.get("price") or 0)
    else:
        price = float(price_or_ind or 0)
        out = dict(ind or {})
        if price > 0:
            out.setdefault("price", price)
    return price, out


def _gate_decision(
    symbol: str,
    signal: str,
    price: float,
    ind: dict,
    *,
    tier: str,
    mtf: dict | None = None,
    btc_signal: str | None = None,
    consume: bool = False,
) -> tuple[bool, int, str]:
    """Return (allow, score, reason) with honest, non-destructive checks.

    consume=True is used only by automatic loops that are about to send a
    signal, so daily budgets/cooldowns are recorded only when a signal is
    actually approved. On-demand commands can inspect quality without burning
    the daily allowance.
    """
    symbol = (symbol or "").upper().strip()
    signal = (signal or "").upper().strip()
    tier = "vip" if tier == "vip" else "free"

    if btc_signal:
        cache_btc_signal(btc_signal)

    if not symbol or signal not in {"BUY", "SELL"}:
        return False, 0, "No valid BUY/SELL signal."
    if not ind:
        return False, 0, "Indicator data is missing."
    if price <= 0:
        price = float(ind.get("price") or 0)
    if price <= 0:
        return False, 0, "Live price is missing."
    ind = dict(ind)
    ind.setdefault("price", price)

    min_score = FREE_MIN_SCORE if tier == "free" else VIP_MIN_SCORE
    min_rr    = FREE_MIN_RR    if tier == "free" else VIP_MIN_RR
    cool_h    = FREE_COOLDOWN_H if tier == "free" else VIP_COOLDOWN_H

    if not is_active_hour():
        return False, 0, f"Outside active hours ({ACTIVE_START_UTC}:00–{ACTIVE_END_UTC}:00 UTC)."

    if consume:
        if tier == "free" and not free_budget_ok():
            return False, 0, f"Daily FREE budget used ({FREE_MAX_PER_DAY}/{FREE_MAX_PER_DAY})."
        if tier == "vip" and not vip_budget_ok():
            return False, 0, f"Daily VIP budget used ({VIP_MAX_PER_DAY}/{VIP_MAX_PER_DAY})."

    if not _cooldown_ok(symbol, signal, cool_h):
        return False, 0, f"Cooldown active for {symbol} {signal} ({cool_h}h)."

    score = compute_quality_score(ind, signal, mtf if tier == "vip" else None)
    if score < min_score:
        return False, score, f"Quality score {score}/100 is below {min_score}/100 minimum."

    atr = float(ind.get("atr", price * 0.018) or 0)
    atr_pct = atr / price if price > 0 else 0.018
    rr = compute_rr(price, signal, atr, atr_pct)
    if rr < min_rr:
        return False, score, f"Risk/reward {rr}:1 is below {min_rr}:1 minimum."

    mtf_aligned = 0
    if mtf:
        mtf_aligned = sum(
            1 for tf in ("5m", "15m", "1h")
            if mtf.get(tf, {}).get("signal") == signal
        )
        if tier == "vip" and mtf_aligned < 2:
            return False, score, f"VIP needs 2/3 timeframe alignment; current alignment is {mtf_aligned}/3."

    btc_ok, btc_reason = _btc_context_ok(symbol, signal)
    if not btc_ok:
        return False, score, btc_reason or "BTC macro context blocks this signal."

    corr_ok, corr_reason = _correlation_ok(symbol, signal)
    if not corr_ok:
        return False, score, corr_reason or "Correlation filter blocks this signal."

    if not consume:
        return True, score, f"Qualified: score {score}/100, R:R {rr}:1."

    candidate = {
        "symbol": symbol,
        "signal": signal,
        "price": price,
        "score": score,
        "rr": rr,
        "mtf_aligned": mtf_aligned,
        "tier": tier,
        "ind": ind,
        "mtf": mtf,
        "ts": time.time(),
    }
    if approve_and_record(candidate):
        return True, score, f"Approved: score {score}/100, R:R {rr}:1."
    return False, score, "Budget/cooldown/correlation changed before send."


def should_send_free(
    symbol: str,
    signal: str,
    price_or_ind,
    ind: dict | None = None,
    btc_signal: str | None = None,
    *,
    mtf: dict | None = None,
    consume: bool = False,
) -> tuple[bool, int, str]:
    """FREE gate returning (allow, score, reason).

    Keeps backward compatibility with older callers while giving the UI an
    honest reason instead of just True/False.
    """
    price, indicators = _normalise_gate_inputs(price_or_ind, ind)
    return _gate_decision(
        symbol, signal, price, indicators,
        tier="free", mtf=None, btc_signal=btc_signal, consume=consume,
    )


def should_send_vip(
    symbol: str,
    signal: str,
    price_or_ind,
    ind: dict | None = None,
    btc_signal: str | None = None,
    *,
    mtf: dict | None = None,
    consume: bool = False,
) -> tuple[bool, int, str]:
    """VIP gate returning (allow, score, reason)."""
    price, indicators = _normalise_gate_inputs(price_or_ind, ind)
    return _gate_decision(
        symbol, signal, price, indicators,
        tier="vip", mtf=mtf, btc_signal=btc_signal, consume=consume,
    )

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
        f"{'High-quality setup — indicators strongly aligned.' if score >= 75 else 'Solid setup — most indicators agree.' if score >= 62 else 'Acceptable setup — minimum criteria met.'}"
    )
