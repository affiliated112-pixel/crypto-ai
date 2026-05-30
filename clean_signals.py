"""clean_signals.py — Professional, honest signal embeds.

The embed builders do not invent performance, probability or guarantees. They
show the real entry price and ATR-based TP/SL levels supplied by the signal
engine, plus a clear educational disclaimer.
"""
from __future__ import annotations

from datetime import datetime, timezone

import discord
import coins_config

try:
    import signal_engine
except Exception:  # keeps the module importable during isolated tests
    signal_engine = None

BUY_COLOR = 0x00D26A
SELL_COLOR = 0xFF4757


def _pct(a, b) -> float:
    return abs(float(a) - float(b)) / float(b) * 100 if b else 0.0


def _format_price(v: float) -> str:
    try:
        value = float(v)
    except Exception:
        return "—"
    if abs(value) >= 100:
        return f"{value:,.2f}"
    if abs(value) >= 1:
        return f"{value:,.4f}"
    return f"{value:,.8f}".rstrip("0").rstrip(".")


def _levels(price: float, signal: str, atr: float | None = None, ind: dict | None = None) -> dict:
    """Single source of truth for display levels.

    Prefer levels already computed by signal_engine. Otherwise compute the same
    ATR-based levels here. Only the legacy percentage fallback is used if the
    engine is unavailable.
    """
    if ind and isinstance(ind.get("_levels"), dict):
        lv = ind["_levels"]
        if all(k in lv for k in ("sl", "tp1", "tp2", "tp3")):
            return lv

    atr_val = float(atr or (ind or {}).get("atr") or price * 0.018)
    atr_pct = atr_val / price if price else 0.018
    if signal_engine is not None:
        try:
            return signal_engine.compute_levels(float(price), str(signal).upper(), atr_val, atr_pct)
        except Exception:
            pass

    pct = 0.02
    if str(signal).upper() == "BUY":
        return {
            "sl": price * (1 - pct),
            "tp1": price * (1 + pct * 1.2),
            "tp2": price * (1 + pct * 2.5),
            "tp3": price * (1 + pct * 4),
            "rr2": 2.5,
        }
    return {
        "sl": price * (1 + pct),
        "tp1": price * (1 - pct * 1.2),
        "tp2": price * (1 - pct * 2.5),
        "tp3": price * (1 - pct * 4),
        "rr2": 2.5,
    }


# ─── FREE SIGNAL ─────────────────────────────────────────────────────────────

def build_free_signal(
    symbol: str,
    signal: str,
    price: float,
    rsi: float,
    confidence: str,
    atr: float | None = None,
    score: int = 0,
) -> discord.Embed:
    signal = str(signal).upper().strip()
    is_buy = signal == "BUY"
    coin = symbol.replace("USDT", "")
    emoji = coins_config.COIN_EMOJI.get(symbol, "🪙")
    logo = coins_config.COIN_LOGOS.get(symbol)
    color = BUY_COLOR if is_buy else SELL_COLOR
    lv = _levels(float(price), signal, atr)

    tp1 = float(lv["tp1"])
    sl = float(lv["sl"])
    pct_tp = _pct(tp1, price)
    pct_sl = _pct(sl, price)

    arrow = "📈" if is_buy else "📉"
    action = "BUY setup" if is_buy else "SELL / risk-off setup"

    embed = discord.Embed(
        title=f"{arrow}  {emoji} {coin}  ·  {action}",
        description="Real market data · quality-filtered technical setup",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    if logo:
        embed.set_thumbnail(url=logo)

    embed.add_field(
        name="📌 Levels",
        value=(
            "```\n"
            f"Entry zone ${_format_price(price):>13}\n"
            f"TP1  {pct_tp:>5.1f}%  ${_format_price(tp1):>13}\n"
            f"SL   {pct_sl:>5.1f}%  ${_format_price(sl):>13}\n"
            "```"
            + ("🟢 Bullish setup detected — wait for your own confirmation" if is_buy else "🔴 Bearish/risk-off setup detected — manage exposure first")
        ),
        inline=False,
    )

    rsi_zone = (
        "🟢 Oversold area — possible bounce setup" if rsi < 35
        else "🔴 Overbought area — possible sell/profit-taking setup" if rsi > 65
        else "⚪ Neutral RSI zone"
    )
    embed.add_field(name=f"RSI `{rsi:.0f}`", value=rsi_zone, inline=True)

    if score > 0:
        grade = "🔥 Strong" if score >= 70 else ("⚡ Good" if score >= 58 else "📊 Watchlist")
        embed.add_field(name="Quality", value=f"`{score}/100`  {grade}", inline=True)

    embed.add_field(
        name="💎 VIP adds",
        value="3 TP levels, multi-timeframe checks, chart and deeper indicator breakdown.",
        inline=False,
    )

    embed.set_footer(text="⚠️ Educational only · Not financial advice · Use stop loss · Risk only 1–2% per trade")
    return embed


# ─── VIP SIGNAL ──────────────────────────────────────────────────────────────

def build_vip_signal(
    symbol: str,
    signal: str,
    price: float,
    rsi: float,
    confidence: str,
    ai_text: str,
    ind: dict,
    mtf: dict | None = None,
    smart_score: int = 0,
    sector: str = "Crypto",
) -> discord.Embed:
    signal = str(signal).upper().strip()
    is_buy = signal == "BUY"
    coin = symbol.replace("USDT", "")
    emoji = coins_config.COIN_EMOJI.get(symbol, "🪙")
    logo = coins_config.COIN_LOGOS.get(symbol)
    color = BUY_COLOR if is_buy else SELL_COLOR

    atr = float((ind or {}).get("atr") or price * 0.018)
    lv = _levels(float(price), signal, atr, ind or {})
    tp1, tp2, tp3, sl = (float(lv["tp1"]), float(lv["tp2"]), float(lv["tp3"]), float(lv["sl"]))
    pct1 = _pct(tp1, price)
    pct2 = _pct(tp2, price)
    pct3 = _pct(tp3, price)
    pct_sl = _pct(sl, price)
    rr = float(lv.get("rr2") or (pct2 / pct_sl if pct_sl else 0))

    arrow = "📈" if is_buy else "📉"
    action = "BUY setup" if is_buy else "SELL / risk-off setup"

    mtf_aligned = 0
    if mtf:
        mtf_aligned = sum(1 for tf in ("5m", "15m", "1h") if mtf.get(tf, {}).get("signal") == signal)
    mtf_str = {
        3: "🟢🟢🟢 3/3 charts agree",
        2: "🟢🟢⚪ 2/3 charts agree",
        1: "🟢⚪⚪ 1/3 chart agrees",
        0: "⚪ Not aligned",
    }.get(mtf_aligned, "—")

    grade = "🏆 Elite" if smart_score >= 85 else ("🔥 Excellent" if smart_score >= 70 else ("⚡ Good" if smart_score >= 58 else "📊 Watchlist"))

    embed = discord.Embed(
        title=f"💎  {arrow} {emoji} {coin}  ·  {action}",
        description=f"`{sector}` · real-data technical setup",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    if logo:
        embed.set_thumbnail(url=logo)

    embed.add_field(
        name="📌 Trade Plan",
        value=(
            "```\n"
            f"Entry zone ${_format_price(price):>13}\n"
            f"TP1 {pct1:>5.1f}%  ${_format_price(tp1):>13}\n"
            f"TP2 {pct2:>5.1f}%  ${_format_price(tp2):>13}\n"
            f"TP3 {pct3:>5.1f}%  ${_format_price(tp3):>13}\n"
            f"SL  {pct_sl:>5.1f}%  ${_format_price(sl):>13}\n"
            f"R:R {rr:.2f}:1\n"
            "```"
        ),
        inline=False,
    )

    rsi_text = (
        "🟢 Oversold — bounce conditions possible" if rsi < 35
        else "🔴 Overbought — pullback/profit-taking conditions possible" if rsi > 65
        else "⚪ Neutral"
    )

    ind_lines: list[str] = []
    if ind:
        adx = float(ind.get("adx", 20) or 20)
        cmf = float(ind.get("cmf", 0) or 0)
        ema200 = float(ind.get("ema200", price) or price)
        vwap = float(ind.get("vwap", price) or price)
        vol = bool(ind.get("vol_surge", False))
        ind_lines.append(f"{'🟢' if adx > 25 else '🟡'} **Trend strength:** {'Strong direction' if adx > 25 else 'Weak / mixed'}")
        ind_lines.append(f"{'🟢' if (cmf > 0) == is_buy else '🔴'} **Money flow:** {'Buy pressure' if cmf > 0.05 else ('Sell pressure' if cmf < -0.05 else 'Balanced')}")
        ind_lines.append(f"{'🟢' if (price > ema200) == is_buy else '🔴'} **Macro trend:** {'Price above EMA200' if price > ema200 else 'Price below EMA200'}")
        ind_lines.append(f"{'🟢' if (price <= vwap) == is_buy else '🔴'} **VWAP:** {'Below intraday average' if price <= vwap else 'Above intraday average'}")
        if vol:
            ind_lines.append("🔊 **Volume:** Unusual volume spike detected")

    embed.add_field(
        name=f"📊 Why this setup? `{smart_score}/100` {grade}",
        value=f"**RSI `{rsi:.0f}`** — {rsi_text}\n" + "\n".join(ind_lines),
        inline=False,
    )

    if mtf:
        tf5 = mtf.get("5m", {})
        tf15 = mtf.get("15m", {})
        tf1h = mtf.get("1h", {})

        def _tf_icon(tf_data, direction):
            s = tf_data.get("signal")
            return "🟢" if s == direction else ("🔴" if s else "⚪")

        embed.add_field(
            name=f"⏱ Timeframe Check · {mtf_str}",
            value=(
                f"{_tf_icon(tf5, signal)} **5 min** — `{tf5.get('signal', '—')}`  RSI `{tf5.get('rsi', 0):.0f}`\n"
                f"{_tf_icon(tf15, signal)} **15 min** — `{tf15.get('signal', '—')}`  RSI `{tf15.get('rsi', 0):.0f}`\n"
                f"{_tf_icon(tf1h, signal)} **1 hour** — `{tf1h.get('signal', '—')}`  RSI `{tf1h.get('rsi', 0):.0f}`"
            ),
            inline=False,
        )

    if ai_text:
        sentence = str(ai_text).split(".")[0].strip()
        if len(sentence) > 10:
            embed.add_field(name="🧠 Summary", value=f"*{sentence}.*", inline=False)

    embed.add_field(
        name="✅ Risk checklist",
        value=(
            f"1️⃣ Place/plan your **Stop Loss near `${_format_price(sl)}`** before entry.\n"
            "2️⃣ Consider taking partial profit at TP1 instead of waiting for TP3 only.\n"
            "3️⃣ Keep position risk small; this is not a guaranteed result."
        ),
        inline=False,
    )

    embed.set_footer(text="💎 VIP · Educational only · Not financial advice · Past results do not guarantee future results")
    return embed
