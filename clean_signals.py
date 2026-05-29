"""clean_signals.py — Professional signal embeds. Simple. Clear. Actionable.

Design rules:
  1. Title = coin + direction. Instant recognition.
  2. Trade box = the ONLY numbers that matter: Entry, TP1/2/3, SL.
  3. Why = 3 words per indicator. Not a lecture.
  4. AI = 1 sentence. Max.
  5. Footer = disclaimer. Always.

No walls of text. No acronyms without explanation. No jargon.
If a 16-year-old can't understand it in 5 seconds — rewrite it.
"""

import discord
from datetime import datetime, timezone
import coins_config

BUY_COLOR  = 0x00D26A
SELL_COLOR = 0xFF4757

def _pct(a, b) -> float:
    return abs(a - b) / b * 100 if b else 0.0

# ─── FREE SIGNAL ─────────────────────────────────────────────────────────────

def build_free_signal(
    symbol: str, signal: str, price: float,
    rsi: float, confidence: str,
    atr: float | None = None, score: int = 0,
) -> discord.Embed:

    is_buy = signal == "BUY"
    coin   = symbol.replace("USDT", "")
    emoji  = coins_config.COIN_EMOJI.get(symbol, "🪙")
    logo   = coins_config.COIN_LOGOS.get(symbol)
    color  = BUY_COLOR if is_buy else SELL_COLOR
    _atr   = atr if atr else price * 0.018

    tp1    = round(price + 1.5 * _atr, 4) if is_buy else round(price - 1.5 * _atr, 4)
    sl     = round(price - 1.2 * _atr, 4) if is_buy else round(price + 1.2 * _atr, 4)
    pct_tp = _pct(tp1, price)
    pct_sl = _pct(sl,  price)

    arrow  = "📈" if is_buy else "📉"
    action = "BUY" if is_buy else "SELL"

    embed = discord.Embed(
        title=f"{arrow}  {emoji} {coin}  ·  {action}",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    if logo:
        embed.set_thumbnail(url=logo)

    # ── The only numbers that matter ─────────────────────────────────────
    embed.add_field(
        name="📌 Levels",
        value=(
            f"```\n"
            f"Entry   ${price:>13,.4f}\n"
            f"TP  +{pct_tp:.1f}%  ${tp1:>13,.4f}\n"
            f"SL  -{pct_sl:.1f}%  ${sl:>13,.4f}\n"
            f"```"
            f"{'🟢 Enter now — price is in the BUY zone' if is_buy else '🔴 Enter now — price is in the SELL zone'}"
        ),
        inline=False,
    )

    # ── RSI — simple explanation ──────────────────────────────────────────
    rsi_zone = "🟢 Oversold — good time to buy" if rsi < 35 else ("🔴 Overbought — good time to sell" if rsi > 65 else "⚪ Neutral zone")
    embed.add_field(
        name=f"RSI  `{rsi:.0f}`",
        value=rsi_zone,
        inline=True,
    )

    # ── Signal quality ────────────────────────────────────────────────────
    if score > 0:
        grade = "🔥 Strong" if score >= 70 else ("⚡ Good" if score >= 58 else "📊 OK")
        embed.add_field(name="Quality", value=f"`{score}/100`  {grade}", inline=True)

    # ── VIP upsell ────────────────────────────────────────────────────────
    embed.add_field(
        name="💎 Want more?",
        value="VIP gets **3 profit targets**, AI analysis, 30 coins → `/getvip`",
        inline=False,
    )

    embed.set_footer(text="⚠️ Not financial advice · Always set your Stop Loss · Risk only what you can afford to lose")
    return embed

# ─── VIP SIGNAL ──────────────────────────────────────────────────────────────

def build_vip_signal(
    symbol: str, signal: str, price: float,
    rsi: float, confidence: str, ai_text: str,
    ind: dict, mtf: dict | None = None,
    smart_score: int = 0, sector: str = "Crypto",
) -> discord.Embed:

    is_buy = signal == "BUY"
    coin   = symbol.replace("USDT", "")
    emoji  = coins_config.COIN_EMOJI.get(symbol, "🪙")
    logo   = coins_config.COIN_LOGOS.get(symbol)
    color  = BUY_COLOR if is_buy else SELL_COLOR

    atr    = ind.get("atr", price * 0.018) if ind else price * 0.018
    tp1    = round(price + 1.5 * atr, 4) if is_buy else round(price - 1.5 * atr, 4)
    tp2    = round(price + 3.0 * atr, 4) if is_buy else round(price - 3.0 * atr, 4)
    tp3    = round(price + 5.0 * atr, 4) if is_buy else round(price - 5.0 * atr, 4)
    sl     = round(price - 1.2 * atr, 4) if is_buy else round(price + 1.2 * atr, 4)

    pct1   = _pct(tp1, price)
    pct2   = _pct(tp2, price)
    pct3   = _pct(tp3, price)
    pct_sl = _pct(sl,  price)
    rr     = round(pct2 / pct_sl, 1) if pct_sl else 2.5

    arrow  = "📈" if is_buy else "📉"
    action = "BUY" if is_buy else "SELL"

    # ── MTF: how many timeframes agree ───────────────────────────────────
    mtf_aligned = 0
    if mtf:
        mtf_aligned = sum(1 for tf in ("5m","15m","1h") if mtf.get(tf,{}).get("signal") == signal)
    mtf_str = {3:"🟢🟢🟢 All 3 charts agree", 2:"🟢🟢⚪ 2 of 3 charts agree", 1:"🟢⚪⚪ 1 chart agrees", 0:"⚪ Weak"}.get(mtf_aligned,"—")

    # ── Score label ───────────────────────────────────────────────────────
    grade = "🏆 Elite" if smart_score>=85 else ("🔥 Excellent" if smart_score>=70 else ("⚡ Good" if smart_score>=58 else "📊 OK"))

    # ── Build embed ───────────────────────────────────────────────────────
    embed = discord.Embed(
        title=f"💎  {arrow} {emoji} {coin}  ·  {action}",
        description=f"`{sector}`",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    if logo:
        embed.set_thumbnail(url=logo)

    # ── BLOCK 1 — Trade plan (what to do) ────────────────────────────────
    embed.add_field(
        name="📌 Trade Plan",
        value=(
            f"```\n"
            f"Entry    ${price:>13,.4f}   ← enter here\n"
            f"TP1 +{pct1:.1f}%  ${tp1:>13,.4f}   ← sell 40%\n"
            f"TP2 +{pct2:.1f}%  ${tp2:>13,.4f}   ← sell 40%\n"
            f"TP3 +{pct3:.1f}%  ${tp3:>13,.4f}   ← sell 20%\n"
            f"SL  -{pct_sl:.1f}%  ${sl:>13,.4f}   ← exit if hit\n"
            f"R:R  {rr}:1\n"
            f"```"
        ),
        inline=False,
    )

    # ── BLOCK 2 — Signal strength (why we sent this) ──────────────────────
    rsi_text = "🟢 Oversold — buyers stepping in" if rsi < 35 else ("🔴 Overbought — sellers taking over" if rsi > 65 else "⚪ Neutral")

    # Indicator summary — plain English, no acronyms
    ind_lines = []
    if ind:
        adx    = ind.get("adx",  20)
        cmf    = ind.get("cmf",   0)
        ema200 = ind.get("ema200", price)
        vwap   = ind.get("vwap",   price)
        vol    = ind.get("vol_surge", False)

        ind_lines.append(f"{'🟢' if adx > 25 else '🟡'} **Trend strength:** {'Strong — clear direction' if adx > 25 else 'Weak — be careful'}")
        ind_lines.append(f"{'🟢' if (cmf>0)==is_buy else '🔴'} **Money flow:** {'Buyers are in control' if cmf > 0.05 else ('Sellers are in control' if cmf < -0.05 else 'Balanced')}")
        ind_lines.append(f"{'🟢' if (price>ema200)==is_buy else '🔴'} **Overall trend:** {'Bullish (price above 200-day avg)' if price > ema200 else 'Bearish (price below 200-day avg)'}")
        ind_lines.append(f"{'🟢' if (price<=vwap)==is_buy else '🔴'} **Fair value:** {'Price is cheap vs today avg' if price <= vwap else 'Price is expensive vs today avg'}")
        if vol:
            ind_lines.append("🔊 **Volume:** Unusual spike — big players moving")

    embed.add_field(
        name=f"📊 Why this signal?  `{smart_score}/100` {grade}",
        value=(
            f"**RSI `{rsi:.0f}`** — {rsi_text}\n"
            + "\n".join(ind_lines)
        ),
        inline=False,
    )

    # ── BLOCK 3 — Timeframe confirmation ─────────────────────────────────
    if mtf:
        tf5  = mtf.get("5m",  {})
        tf15 = mtf.get("15m", {})
        tf1h = mtf.get("1h",  {})
        def _tf_icon(tf_data, direction):
            s = tf_data.get("signal")
            return "🟢" if s == direction else ("🔴" if s else "⚪")

        embed.add_field(
            name=f"⏱ Timeframe Check  ·  {mtf_str}",
            value=(
                f"{_tf_icon(tf5, signal)} **5 min** — `{tf5.get('signal','—')}`  RSI `{tf5.get('rsi',0):.0f}`\n"
                f"{_tf_icon(tf15,signal)} **15 min** — `{tf15.get('signal','—')}`  RSI `{tf15.get('rsi',0):.0f}`\n"
                f"{_tf_icon(tf1h,signal)} **1 hour** — `{tf1h.get('signal','—')}`  RSI `{tf1h.get('rsi',0):.0f}`"
            ),
            inline=False,
        )

    # ── BLOCK 4 — AI summary (1 sentence) ────────────────────────────────
    if ai_text:
        sentence = ai_text.split(".")[0].strip()
        if len(sentence) > 10:
            embed.add_field(name="🧠 AI Summary", value=f"*{sentence}.*", inline=False)

    # ── BLOCK 5 — What to do (3 rules, always) ───────────────────────────
    embed.add_field(
        name="✅ What to do",
        value=(
            f"1️⃣ Set your **Stop Loss at `${sl:,.4f}`** on Binance before anything else\n"
            f"2️⃣ Take profit at **TP1 first** — don't wait for TP3 in one shot\n"
            f"3️⃣ Risk **max 5% of your portfolio** on this trade"
        ),
        inline=False,
    )

    embed.set_footer(text="💎 VIP · Not financial advice · Past results don't guarantee future profit")
    return embed
