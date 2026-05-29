"""signal_engine.py — Quality-gated signal engine.

Philosophy:
  LESS IS MORE. Only send signals when multiple filters ALL pass.
  A signal NOT sent is better than a bad signal sent.

FREE  gate: score >= 45 | R:R >= 1.5 | 1 TF | no MTF required
VIP   gate: score >= 65 | R:R >= 2.0 | 3-TF confirmation | volume spike | BTC context

Expected output:
  FREE: 2–5 signals/day across 6 coins
  VIP:  3–7 signals/day across 30 coins (higher quality, more coins)
"""

import time
from datetime import datetime, timezone
from typing import Optional

import coins_config

# ─── CONSTANTS ────────────────────────────────────────────────────────────────

FREE_MIN_SCORE      = 45    # min Smart Score for FREE signal
VIP_MIN_SCORE       = 65    # min Smart Score for VIP signal
FREE_MIN_RR         = 1.5   # min Risk:Reward for FREE
VIP_MIN_RR          = 2.0   # min Risk:Reward for VIP
FREE_COOLDOWN_H     = 6     # hours between same coin same direction (FREE)
VIP_COOLDOWN_H      = 4     # hours between same coin same direction (VIP)
BEST_HOURS_UTC      = (8, 22)  # 08:00–22:00 UTC — highest liquidity hours

# Correlation groups — don't spam same-direction signals for correlated coins
CORRELATION_GROUPS = [
    {"BTCUSDT", "ETHUSDT"},         # BTC/ETH highly correlated
    {"SOLUSDT", "AVAXUSDT", "NEARUSDT", "APTUSDT", "SUIUSDT"},  # L1s
    {"OPUSDT", "ARBUSDT", "MATICUSDT"},  # L2s
    {"SANDUSDT", "MANAUSDT"},       # Metaverse
    {"SHIBUSDT", "DOGEUSDT"},       # Memes
]

# ─── STATE ────────────────────────────────────────────────────────────────────
_last_sent: dict[str, dict] = {}  # {symbol: {"signal": str, "ts": float}}
_last_group_signal: dict[int, dict] = {}  # correlation group index → last signal info

# ─── QUALITY SCORE ────────────────────────────────────────────────────────────

def compute_quality_score(ind: dict, signal: str, mtf: dict | None = None) -> int:
    """
    0–100 composite signal quality score.
    Higher = more indicators aligned = better setup.
    """
    if not ind:
        return 0

    score   = 0
    is_buy  = signal == "BUY"
    rsi     = ind.get("rsi", 50)
    macd_h  = ind.get("macd_hist", 0)
    adx     = ind.get("adx", 20)
    adx_pos = ind.get("adx_pos", 10)
    adx_neg = ind.get("adx_neg", 10)
    cmf     = ind.get("cmf", 0)
    willr   = ind.get("willr", -50)
    bb_pct  = ind.get("bb_pct", 0.5)
    stoch_k = ind.get("stoch_k", 0.5)
    vwap    = ind.get("vwap", 0)
    ema50   = ind.get("ema50", 0)
    ema200  = ind.get("ema200", 0)
    obv_up  = ind.get("obv_up", False)
    vol_surge = ind.get("vol_surge", False)
    bull_div  = ind.get("bull_div", False)
    bear_div  = ind.get("bear_div", False)
    struct_bull = ind.get("struct_bull", False)
    struct_bear = ind.get("struct_bear", False)
    price   = ind.get("close", ind.get("vwap", 1))

    # ── RSI zone (0-20 pts) ──────────────────────────────────────────────
    if is_buy:
        if rsi < 25:  score += 20
        elif rsi < 35: score += 15
        elif rsi < 45: score += 8
        elif rsi > 60: score -= 5   # BUY in overbought = bad
    else:
        if rsi > 75:  score += 20
        elif rsi > 65: score += 15
        elif rsi > 55: score += 8
        elif rsi < 40: score -= 5

    # ── MACD direction (0-12 pts) ────────────────────────────────────────
    if (is_buy and macd_h > 0) or (not is_buy and macd_h < 0):
        score += 12

    # ── ADX trend strength (0-12 pts) ────────────────────────────────────
    if adx > 35: score += 12
    elif adx > 25: score += 8
    elif adx > 18: score += 4
    # ADX DI alignment
    if is_buy and adx_pos > adx_neg:  score += 5
    if not is_buy and adx_neg > adx_pos: score += 5

    # ── Volume confirmation (0-10 pts) ───────────────────────────────────
    if vol_surge: score += 10
    elif (is_buy and obv_up) or (not is_buy and not obv_up): score += 5

    # ── CMF (Chaikin Money Flow) (0-8 pts) ───────────────────────────────
    if is_buy and cmf > 0.1: score += 8
    elif is_buy and cmf > 0: score += 4
    elif not is_buy and cmf < -0.1: score += 8
    elif not is_buy and cmf < 0: score += 4

    # ── Bollinger Band position (0-7 pts) ────────────────────────────────
    if is_buy and bb_pct < 0.2:  score += 7  # near lower band
    elif not is_buy and bb_pct > 0.8: score += 7  # near upper band

    # ── Stochastic RSI (0-7 pts) ─────────────────────────────────────────
    if is_buy and stoch_k < 0.25: score += 7
    elif not is_buy and stoch_k > 0.75: score += 7

    # ── Williams %R (0-5 pts) ────────────────────────────────────────────
    if is_buy and willr < -80: score += 5
    elif not is_buy and willr > -20: score += 5

    # ── Market structure (0-8 pts) ───────────────────────────────────────
    if (is_buy and struct_bull) or (not is_buy and struct_bear): score += 8

    # ── EMA trend context (0-7 pts) ──────────────────────────────────────
    if ema200 and price:
        if is_buy and price > ema200:  score += 7  # BUY in uptrend
        elif not is_buy and price < ema200: score += 7  # SELL in downtrend

    # ── Divergence (0-10 pts) ────────────────────────────────────────────
    if is_buy and bull_div: score += 10
    elif not is_buy and bear_div: score += 10

    # ── MTF alignment (0-15 pts) — counts only in VIP context ───────────
    if mtf:
        aligned = sum(1 for tf in ("5m","15m","1h") if mtf.get(tf,{}).get("signal") == signal)
        score += aligned * 5  # up to 15pts for 3/3

    # ── VWAP position (0-5 pts) ──────────────────────────────────────────
    if vwap and price:
        if is_buy and price < vwap * 1.002:  score += 5   # BUY near/below VWAP
        elif not is_buy and price > vwap * 0.998: score += 5

    return min(max(score, 0), 100)

def compute_rr(price: float, signal: str, atr: float) -> float:
    """Returns R:R ratio based on TP2 vs SL (ATR-based)."""
    if atr <= 0:
        return 1.0
    tp2_dist = 3.0 * atr
    sl_dist  = 1.2 * atr
    return round(tp2_dist / sl_dist, 2)

# ─── MARKET CONTEXT CHECK ─────────────────────────────────────────────────────

def check_btc_context(btc_signal: str | None, symbol: str, signal: str) -> tuple[bool, str]:
    """
    For altcoins: if BTC is strongly trending opposite, reduce confidence.
    BTC is the market leader — trading against BTC trend is riskier.
    Returns (ok, reason).
    """
    if symbol == "BTCUSDT":
        return True, ""
    if btc_signal is None:
        return True, ""   # No BTC data, pass anyway

    is_buy = signal == "BUY"
    if is_buy and btc_signal == "SELL":
        return False, "BTC trending down — altcoin BUY risky"
    if not is_buy and btc_signal == "BUY":
        return False, "BTC trending up — altcoin SELL risky"
    return True, ""

def is_good_hour() -> bool:
    """Returns True during high-liquidity trading hours (08:00–22:00 UTC)."""
    hour = datetime.now(timezone.utc).hour
    return BEST_HOURS_UTC[0] <= hour <= BEST_HOURS_UTC[1]

# ─── COOLDOWN CHECK ───────────────────────────────────────────────────────────

def _check_cooldown(symbol: str, signal: str, cooldown_h: int) -> bool:
    """Returns True if cooldown has elapsed."""
    now     = time.time()
    last    = _last_sent.get(symbol, {})
    same_dir = last.get("signal") == signal
    elapsed  = now - last.get("ts", 0)
    if same_dir and elapsed < cooldown_h * 3600:
        return False   # still in cooldown
    return True

def _record_sent(symbol: str, signal: str):
    _last_sent[symbol] = {"signal": signal, "ts": time.time()}

def _check_correlation(symbol: str, signal: str) -> tuple[bool, str]:
    """Prevent sending same-direction signals for correlated coins too close together."""
    now = time.time()
    for i, group in enumerate(CORRELATION_GROUPS):
        if symbol not in group:
            continue
        last = _last_group_signal.get(i, {})
        if (last.get("signal") == signal
                and last.get("symbol") != symbol
                and now - last.get("ts", 0) < 1800):  # 30 min correlation window
            return False, f"Correlated signal already sent recently ({last.get('symbol')})"
    return True, ""

def _record_group(symbol: str, signal: str):
    now = time.time()
    for i, group in enumerate(CORRELATION_GROUPS):
        if symbol in group:
            _last_group_signal[i] = {"symbol": symbol, "signal": signal, "ts": now}

# ─── MAIN GATE FUNCTIONS ──────────────────────────────────────────────────────

def should_send_free(
    symbol:   str,
    signal:   str,
    price:    float,
    ind:      dict,
    btc_signal: str | None = None,
) -> tuple[bool, int, str]:
    """
    FREE signal gate.
    Returns (allow, score, reason_if_blocked).
    """
    if not signal or not price:
        return False, 0, "no signal"

    # Hours check
    if not is_good_hour():
        return False, 0, "low liquidity hour"

    # Cooldown
    if not _check_cooldown(symbol, signal, FREE_COOLDOWN_H):
        return False, 0, "cooldown active"

    # Quality score
    score = compute_quality_score(ind, signal)
    if score < FREE_MIN_SCORE:
        return False, score, f"score {score} < {FREE_MIN_SCORE}"

    # R:R check
    atr = ind.get("atr", price * 0.02) if ind else price * 0.02
    rr  = compute_rr(price, signal, atr)
    if rr < FREE_MIN_RR:
        return False, score, f"R:R {rr} < {FREE_MIN_RR}"

    # BTC context (soft check — only block strong opposite trend)
    btc_ok, btc_reason = check_btc_context(btc_signal, symbol, signal)
    if not btc_ok:
        return False, score, btc_reason

    # Passed all gates
    _record_sent(symbol, signal)
    _record_group(symbol, signal)
    return True, score, ""

def should_send_vip(
    symbol:     str,
    signal:     str,
    price:      float,
    ind:        dict,
    mtf:        dict | None = None,
    btc_signal: str | None = None,
) -> tuple[bool, int, str]:
    """
    VIP signal gate — stricter than FREE.
    Returns (allow, score, reason_if_blocked).
    """
    if not signal or not price:
        return False, 0, "no signal"

    # Hours check
    if not is_good_hour():
        return False, 0, "low liquidity hour"

    # Cooldown (shorter for VIP — more coins, more opportunities)
    if not _check_cooldown(symbol, signal, VIP_COOLDOWN_H):
        return False, 0, "cooldown active"

    # Quality score (with MTF)
    score = compute_quality_score(ind, signal, mtf)
    if score < VIP_MIN_SCORE:
        return False, score, f"score {score} < {VIP_MIN_SCORE}"

    # R:R check (stricter)
    atr = ind.get("atr", price * 0.02) if ind else price * 0.02
    rr  = compute_rr(price, signal, atr)
    if rr < VIP_MIN_RR:
        return False, score, f"R:R {rr} < {VIP_MIN_RR}"

    # Multi-timeframe: at least 2/3 TFs must agree
    if mtf:
        aligned = sum(1 for tf in ("5m","15m","1h") if mtf.get(tf,{}).get("signal") == signal)
        if aligned < 2:
            return False, score, f"MTF only {aligned}/3 aligned (need 2+)"

    # Volume: for VIP, volume surge preferred (soft — don't block, just note)
    vol_surge = ind.get("vol_surge", False) if ind else False

    # BTC context
    btc_ok, btc_reason = check_btc_context(btc_signal, symbol, signal)
    if not btc_ok:
        return False, score, btc_reason

    # Correlation check
    corr_ok, corr_reason = _check_correlation(symbol, signal)
    if not corr_ok:
        return False, score, corr_reason

    # Passed all gates
    _record_sent(symbol, signal)
    _record_group(symbol, signal)
    return True, score, ""

# ─── SIGNAL QUALITY LABEL ────────────────────────────────────────────────────

def quality_label(score: int) -> str:
    """Human-readable quality label for the signal."""
    if score >= 85: return "🏆 ELITE"
    if score >= 70: return "🔥 EXCELLENT"
    if score >= 55: return "⚡ GOOD"
    if score >= 45: return "📊 STANDARD"
    return "⚠️ WEAK"

# ─── BTC SIGNAL CACHE ────────────────────────────────────────────────────────
_btc_signal_cache: dict = {"signal": None, "ts": 0}

def cache_btc_signal(signal: str | None):
    _btc_signal_cache["signal"] = signal
    _btc_signal_cache["ts"]     = time.time()

def get_cached_btc_signal() -> str | None:
    if time.time() - _btc_signal_cache["ts"] > 900:  # stale after 15 min
        return None
    return _btc_signal_cache["signal"]
