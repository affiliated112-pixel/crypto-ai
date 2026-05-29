"""clean_signals.py — Professional, clean signal embeds.

Design philosophy:
  • One glance = full picture. No paragraphs, no steps, no explanations.
  • Numbers are the message. Entry, SL, TP1/2/3 in a clean table.
  • Color = direction. Green embed = BUY. Red embed = SELL.
  • Confidence is a bar, not text.
  • Footer carries the disclaimer — always present, never dominant.

FREE:  Entry + TP1 + SL + RSI + Confidence + upsell line
VIP:   Entry + TP1/2/3 + SL + R:R + 3-TF badge + Smart Score +
       AI line + Sector + Ichimoku (1 line) + Entry type
"""

import discord
from datetime import datetime, timezone

import coins_config

# ─── COLORS ──────────────────────────────────────────────────────────────────
BUY_COLOR  = 0x00D26A   # Professional green
SELL_COLOR = 0xFF4757   # Professional red

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _pct(a, b) -> float:
    return abs(a - b) / b * 100 if b else 0.0

def _rsi_bar(rsi: float) -> str:
    filled = max(0, min(20, int(rsi / 5)))
    bar    = "█" * filled + "░" * (20 - filled)
    zone   = "Overbought 🔴" if rsi > 70 else ("Oversold 🟢" if rsi < 30 else "Neutral ⚪")
    return f"`{bar}` **{rsi:.1f}** — {zone}"

def _score_bar(score: int) -> str:
    filled = round(score / 5)
    bar    = "█" * filled + "░" * (20 - filled)
    grade  = ("ELITE 🏆" if score >= 85 else "EXCELLENT 🔥" if score >= 70
              else "GOOD ⚡" if score >= 55 else "AVERAGE 📊" if score >= 40 else "WEAK ⚠️")
    return f"`{bar}` **{score}/100** {grade}"

def _conf_badge(confidence: str) -> str:
    mapping = {
        "VERY HIGH": "🌟🌟🌟🌟🌟 VERY HIGH",
        "HIGH":      "⭐⭐⭐⭐☆ HIGH",
        "MEDIUM":    "⭐⭐⭐☆☆ MEDIUM",
        "LOW":       "⭐⭐☆☆☆ LOW",
    }
    return mapping.get(confidence.upper().replace("🌟 ","").replace("🔥 ","").replace("⚡ ",""), f"⭐ {confidence}")

def _mtf_badge(mtf: dict, direction: str) -> str:
    aligned = sum(1 for tf in ("5m","15m","1h") if mtf.get(tf,{}).get("signal") == direction)
    icons   = {3: "🟢🟢🟢 All TFs aligned", 2: "🟢🟢⚪ 2/3 TFs aligned",
               1: "🟢⚪⚪ 1/3 TF aligned",  0: "⚪⚪⚪ No alignment"}
    return icons.get(aligned, "—")

# ─── FREE SIGNAL EMBED ───────────────────────────────────────────────────────

def build_free_signal(
    symbol:     str,
    signal:     str,
    price:      float,
    rsi:        float,
    confidence: str,
    atr:        float | None = None,
    score:      int = 0,
) -> discord.Embed:
    """
    Clean FREE signal embed.
    Single glance: direction, price, TP1, SL, RSI, quality.
    """
    is_buy  = signal == "BUY"
    coin    = symbol.replace("USDT", "")
    emoji   = coins_config.COIN_EMOJI.get(symbol, "🪙")
    logo    = coins_config.COIN_LOGOS.get(symbol)
    color   = BUY_COLOR if is_buy else SELL_COLOR

    _atr    = atr if atr else price * 0.018
    tp1     = round(price + 1.5 * _atr, 4) if is_buy else round(price - 1.5 * _atr, 4)
    sl      = round(price - 1.2 * _atr, 4) if is_buy else round(price + 1.2 * _atr, 4)
    pct_tp1 = _pct(tp1, price)
    pct_sl  = _pct(sl,  price)

    direction_label = "📈 LONG  /  BUY" if is_buy else "📉 SHORT  /  SELL"

    embed = discord.Embed(
        title=f"{emoji}  {coin}  —  {direction_label}",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    if logo:
        embed.set_thumbnail(url=logo)

    # ── Trade table ──────────────────────────────────────────────────────
    embed.add_field(
        name="📌 Trade Setup",
        value=(
            f"```\n"
            f"Entry    {price:>16,.4f} USDT\n"
            f"TP1  +{pct_tp1:.1f}%  {tp1:>16,.4f} USDT\n"
            f"SL   -{pct_sl:.1f}%  {sl:>16,.4f} USDT\n"
            f"```"
        ),
        inline=False,
    )

    # ── Indicators ───────────────────────────────────────────────────────
    embed.add_field(name="RSI (14)",   value=_rsi_bar(rsi),            inline=False)
    embed.add_field(name="Quality",    value=_conf_badge(confidence),   inline=True)
    embed.add_field(name="Direction",  value=f"`{'LONG 📈' if is_buy else 'SHORT 📉'}`", inline=True)

    # ── Quality score (honest) ───────────────────────────────────────────
    if score > 0:
        from signal_engine import quality_label as _ql
        embed.add_field(
            name="🎯 Signal Quality",
            value=f"`{score}/100` — {_ql(score)}",
            inline=True,
        )

    # ── VIP upsell (1 line only) ─────────────────────────────────────────
    embed.add_field(
        name="💎 VIP",
        value="TP2 · TP3 · AI Analysis · 3-TF · 30 coins → `/getvip`",
        inline=False,
    )

    embed.set_footer(text="⚠️ Not financial advice — Set SL immediately — Trade at your own risk")
    return embed

# ─── VIP SIGNAL EMBED ────────────────────────────────────────────────────────

def build_vip_signal(
    symbol:      str,
    signal:      str,
    price:       float,
    rsi:         float,
    confidence:  str,
    ai_text:     str,
    ind:         dict,
    mtf:         dict | None = None,
    smart_score: int = 0,
    sector:      str = "Crypto",
) -> discord.Embed:
    """
    Professional VIP signal — everything in one glance.
    No steps, no paragraphs. Numbers + bars + 1 AI sentence.
    """
    is_buy  = signal == "BUY"
    coin    = symbol.replace("USDT", "")
    emoji   = coins_config.COIN_EMOJI.get(symbol, "🪙")
    logo    = coins_config.COIN_LOGOS.get(symbol)
    color   = BUY_COLOR if is_buy else SELL_COLOR

    atr     = ind.get("atr", price * 0.018) if ind else price * 0.018
    tp1     = round(price + 1.5 * atr, 4) if is_buy else round(price - 1.5 * atr, 4)
    tp2     = round(price + 3.0 * atr, 4) if is_buy else round(price - 3.0 * atr, 4)
    tp3     = round(price + 5.0 * atr, 4) if is_buy else round(price - 5.0 * atr, 4)
    sl      = round(price - 1.2 * atr, 4) if is_buy else round(price + 1.2 * atr, 4)

    pct_tp1 = _pct(tp1, price)
    pct_tp2 = _pct(tp2, price)
    pct_tp3 = _pct(tp3, price)
    pct_sl  = _pct(sl,  price)
    rr      = round(pct_tp2 / pct_sl, 1) if pct_sl else 2.0

    # MTF badge
    mtf_line = _mtf_badge(mtf, signal) if mtf else "—"

    direction_label = "📈 LONG  /  BUY" if is_buy else "📉 SHORT  /  SELL"

    embed = discord.Embed(
        title=f"💎  {emoji} {coin}  —  {direction_label}",
        description=f"`{sector}`  ·  {mtf_line}",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    if logo:
        embed.set_thumbnail(url=logo)
    embed.set_author(name="💎 VIP Signal — Private Feed")

    # ── Trade table ──────────────────────────────────────────────────────
    embed.add_field(
        name="📌 Trade Levels",
        value=(
            f"```\n"
            f"Entry      {price:>14,.4f}\n"
            f"TP1  +{pct_tp1:>4.1f}%  {tp1:>14,.4f}  ◀ 40%\n"
            f"TP2  +{pct_tp2:>4.1f}%  {tp2:>14,.4f}  ◀ 40%\n"
            f"TP3  +{pct_tp3:>4.1f}%  {tp3:>14,.4f}  ◀ 20%\n"
            f"SL   -{pct_sl:>4.1f}%  {sl:>14,.4f}  ◀ EXIT\n"
            f"R:R  {rr}:1\n"
            f"```"
        ),
        inline=False,
    )

    # ── Smart Score + RSI inline ─────────────────────────────────────────
    embed.add_field(name="🏆 Smart Score", value=_score_bar(smart_score), inline=False)
    embed.add_field(name="RSI (14)",       value=_rsi_bar(rsi),           inline=False)
    embed.add_field(name="Quality",        value=_conf_badge(confidence), inline=True)

    # ── Indicators panel (compact) ────────────────────────────────────────
    if ind:
        adx     = ind.get("adx",    20)
        cmf     = ind.get("cmf",     0)
        vwap    = ind.get("vwap", price)
        ema200  = ind.get("ema200", price)

        trend   = "Above EMA200 🟢" if price > ema200 else "Below EMA200 🔴"
        vwap_p  = "Above VWAP 🔼"  if price > vwap   else "Below VWAP 🔽"
        adx_s   = f"ADX {adx:.0f} — {'Strong' if adx > 25 else 'Weak'} trend"
        cmf_s   = f"CMF {cmf:+.2f} — {'Buying' if cmf > 0.05 else ('Selling' if cmf < -0.05 else 'Neutral')} pressure"

        embed.add_field(
            name="🔬 Indicators",
            value=f"`{adx_s}`\n`{cmf_s}`\n`{trend}`\n`{vwap_p}`",
            inline=True,
        )

    # ── AI line (1 sentence max) ──────────────────────────────────────────
    if ai_text:
        # Trim to 1 sentence
        first_sentence = ai_text.split(".")[0].strip()
        if len(first_sentence) > 10:
            embed.add_field(name="🧠 AI", value=f"*{first_sentence}.*", inline=False)

    # ── Risk line (always last) ───────────────────────────────────────────
    embed.add_field(
        name="⚠️ Risk",
        value="`Set SL immediately` · `Max 5% capital/trade` · `TP1 first`",
        inline=False,
    )

    embed.set_footer(text="💎 VIP · Not financial advice · Trade at your own risk")
    return embed
