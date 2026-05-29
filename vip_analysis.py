"""vip_analysis.py — Enhanced VIP deep signal engine.

Differences vs FREE:
  FREE  → 6 coins | 1 timeframe (5m) | TP1 only | no chart | no AI | no MTF
  VIP   → 30 coins | 3 timeframes (5m+15m+1h) | TP1+TP2+TP3 | 4-panel chart |
           AI analysis | Fibonacci | Ichimoku | Smart Score | Sector tag |
           Entry strategy | Position sizing advice

This module is imported by bot_extended.py and starts the VIP loop independently
of bot.py's signal_loop (which handles FREE only).
"""

import asyncio
import discord
from datetime import datetime, timezone

import bot
import coins_config
import signal_engine

try:
    from ta.trend import IchimokuIndicator
    _HAS_ICHIMOKU = True
except ImportError:
    _HAS_ICHIMOKU = False

# ─── COIN SECTOR TAGS ─────────────────────────────────────────────────────────
COIN_SECTORS: dict[str, str] = {
    "BTCUSDT":   "Store of Value",
    "ETHUSDT":   "Smart Contract L1",
    "SOLUSDT":   "High-Speed L1",
    "BNBUSDT":   "Exchange Token",
    "XRPUSDT":   "Payments",
    "DOGEUSDT":  "Meme Coin",
    "ADAUSDT":   "Smart Contract L1",
    "AVAXUSDT":  "Smart Contract L1",
    "DOTUSDT":   "Interoperability",
    "LINKUSDT":  "Oracle",
    "LTCUSDT":   "Payments",
    "MATICUSDT": "L2 Scaling",
    "UNIUSDT":   "DEX / DeFi",
    "ATOMUSDT":  "Interoperability",
    "XLMUSDT":   "Payments",
    "NEARUSDT":  "Smart Contract L1",
    "FTMUSDT":   "Smart Contract L1",
    "ALGOUSDT":  "Smart Contract L1",
    "SANDUSDT":  "Metaverse / Gaming",
    "MANAUSDT":  "Metaverse / Gaming",
    "FILUSDT":   "Storage / Web3",
    "TRXUSDT":   "Smart Contract L1",
    "ETCUSDT":   "Smart Contract L1",
    "AAVEUSDT":  "Lending / DeFi",
    "GRTUSDT":   "Data / Indexing",
    "SHIBUSDT":  "Meme Coin",
    "OPUSDT":    "L2 Scaling",
    "ARBUSDT":   "L2 Scaling",
    "INJUSDT":   "DeFi / DEX",
    "SUIUSDT":   "Smart Contract L1",
    "APTUSDT":   "Smart Contract L1",
}

# ─── ENTRY STRATEGY ENGINE ────────────────────────────────────────────────────

def _entry_strategy(signal: str, confidence: str, ind: dict, price: float) -> tuple[str, str]:
    """
    Returns (strategy_en, strategy_ro) based on confidence + indicators.
    """
    atr     = ind.get("atr", price * 0.02)
    bb_pct  = ind.get("bb_pct", 0.5)
    adx     = ind.get("adx", 20)
    rsi     = ind.get("rsi", 50)
    vol_surge = ind.get("vol_surge", False)

    is_buy  = signal == "BUY"

    # Strong trend + volume surge → single entry
    if adx > 28 and vol_surge and confidence in ("🌟 VERY HIGH", "🔥 HIGH"):
        en = ("🎯 **Single Entry** — Strong trend with volume surge.\n"
              "Enter 100% of your planned position NOW.\n"
              f"• Entry: `${price:,.4f}`\n"
              f"• Risk per trade: `1–2% of portfolio`")
        ro = ("🎯 **Intrare unică** — Trend puternic cu volum ridicat.\n"
              "Intră cu 100% din poziția planificată ACUM.\n"
              f"• Entry: `${price:,.4f}`\n"
              f"• Risc per trade: `1–2% din portofoliu`")
    # Medium confidence → DCA in 2 tranches
    elif confidence in ("🔥 HIGH", "⚡ MEDIUM"):
        tp1_approx = round(price + 1.5 * atr, 4) if is_buy else round(price - 1.5 * atr, 4)
        en = ("📊 **DCA (2 entries)** — Good signal, moderate confidence.\n"
              f"• Entry 1 (now): `50% of position` at `${price:,.4f}`\n"
              f"• Entry 2: `50% on pullback` near `${(price - 0.5 * atr):,.4f}`\n"
              f"• Combined risk: `1–2% of portfolio`")
        ro = ("📊 **DCA (2 intrări)** — Semnal bun, confidence moderat.\n"
              f"• Intrarea 1 (acum): `50% din poziție` la `${price:,.4f}`\n"
              f"• Intrarea 2: `50% pe corecție` la `${(price - 0.5 * atr):,.4f}`\n"
              f"• Risc combinat: `1–2% din portofoliu`")
    # Low confidence → wait or very small
    else:
        en = ("⏳ **Wait & Watch** — Low confidence signal.\n"
              "Consider entering only 25–30% of position.\n"
              "• Wait for confirmation on next candle\n"
              "• Strict stop-loss mandatory")
        ro = ("⏳ **Așteaptă și observă** — Semnal LOW confidence.\n"
              "Ia maximum 25–30% din poziție dacă intri.\n"
              "• Așteaptă confirmare pe lumânarea următoare\n"
              "• Stop-loss strict obligatoriu")
    return en, ro

# ─── 3-TIMEFRAME MTF ANALYSIS ─────────────────────────────────────────────────

def get_3tf_analysis(symbol: str) -> dict:
    """
    Returns signals on 5m, 15m, and 1h timeframes.
    Returns: {tf: {"signal": BUY/SELL/None, "rsi": float, "macd_bull": bool}}
    """
    result = {}
    for tf in ("5m", "15m", "1h"):
        df = bot.get_data(symbol, interval=tf)
        if df is None:
            result[tf] = {"signal": None, "rsi": 50.0, "macd_bull": False, "score": 0}
            continue
        sig, price, rsi, conf = bot.get_signal_v2(df)
        ind = bot.calc_indicators(df)
        macd_bull = bool(ind.get("macd_hist", 0) > 0) if ind else False
        # Count how many of the 10 conditions are BUY
        buy_score = 0
        if ind:
            rsi_v = ind.get("rsi", 50)
            buy_score = sum([
                rsi_v < 42,
                ind.get("macd_hist", 0) > 0,
                price > ind.get("ema50", price) * 0.985,
                ind.get("bb_pct", 0.5) < 0.35,
                ind.get("stoch_k", 0.5) < 0.35,
                ind.get("willr", -50) < -65,
                ind.get("obv_up", False),
                price < ind.get("vwap", price) * 1.005,
                ind.get("adx", 20) > 18 and ind.get("adx_pos", 10) > ind.get("adx_neg", 10),
                ind.get("bull_div", False),
            ])
        result[tf] = {
            "signal":    sig,
            "rsi":       rsi or 50.0,
            "macd_bull": macd_bull,
            "score":     buy_score,
        }
    return result

def _mtf_summary(mtf: dict, direction: str) -> tuple[str, int]:
    """
    Counts how many TFs agree with direction.
    Returns (badge_text, aligned_count)
    """
    aligned = sum(1 for tf in ("5m", "15m", "1h") if mtf[tf]["signal"] == direction)
    badges = {3: "✅✅✅ **ALL 3 TIMEFRAMES ALIGNED** — Maximum conviction!",
              2: "✅✅⬜ **2/3 Timeframes aligned** — Strong confirmation",
              1: "✅⬜⬜ **1/3 Timeframes aligned** — Weak confirmation",
              0: "⬜⬜⬜ **No alignment** — Very risky"}
    return badges.get(aligned, "—"), aligned

# ─── SMART SCORE ──────────────────────────────────────────────────────────────

def _smart_score(ind: dict, signal: str, mtf_aligned: int) -> int:
    """
    Composite 0–100 score for signal quality. Higher = stronger setup.
    """
    if ind is None:
        return 0
    score = 0
    is_buy = signal == "BUY"

    # RSI (0-20 pts)
    rsi = ind.get("rsi", 50)
    if is_buy:
        if rsi < 30: score += 20
        elif rsi < 40: score += 14
        elif rsi < 50: score += 7
    else:
        if rsi > 70: score += 20
        elif rsi > 60: score += 14
        elif rsi > 50: score += 7

    # MACD (0-15 pts)
    macd_h = ind.get("macd_hist", 0)
    if (is_buy and macd_h > 0) or (not is_buy and macd_h < 0):
        score += 15

    # ADX — trend strength (0-15 pts)
    adx = ind.get("adx", 20)
    if adx > 35: score += 15
    elif adx > 25: score += 10
    elif adx > 18: score += 5

    # Volume (0-10 pts)
    if ind.get("vol_surge", False): score += 10
    elif ind.get("obv_up", False) == is_buy: score += 5

    # MTF alignment (0-20 pts)
    score += mtf_aligned * 6   # up to 18pts for 3/3

    # Divergence (0-10 pts)
    if is_buy and ind.get("bull_div", False): score += 10
    elif not is_buy and ind.get("bear_div", False): score += 10

    # Market structure (0-10 pts)
    if is_buy and ind.get("struct_bull", False): score += 10
    elif not is_buy and ind.get("struct_bear", False): score += 10

    return min(score, 100)

def _smart_score_bar(score: int) -> str:
    filled = round(score / 5)
    bar = "█" * filled + "░" * (20 - filled)
    grade = ("🏆 ELITE" if score >= 85
             else "🔥 EXCELLENT" if score >= 70
             else "⚡ GOOD" if score >= 55
             else "📊 AVERAGE" if score >= 40
             else "⚠️ WEAK")
    return f"`{bar}` **{score}/100** — {grade}"

# ─── ICHIMOKU ANALYSIS ────────────────────────────────────────────────────────

def _ichimoku_signal(df, price: float) -> str:
    """Returns a brief Ichimoku summary."""
    if not _HAS_ICHIMOKU or df is None or len(df) < 53:
        return "N/A (not enough data)"
    try:
        ich = IchimokuIndicator(high=df["high"], low=df["low"])
        kijun  = ich.ichimoku_base_line().iloc[-1]
        tenkan = ich.ichimoku_conversion_line().iloc[-1]
        span_a = ich.ichimoku_a().iloc[-1]
        span_b = ich.ichimoku_b().iloc[-1]
        cloud_top = max(span_a, span_b)
        cloud_bot = min(span_a, span_b)

        if price > cloud_top:
            cloud_pos = "🟢 **Above Kumo** (bullish zone)"
        elif price < cloud_bot:
            cloud_pos = "🔴 **Below Kumo** (bearish zone)"
        else:
            cloud_pos = "🟡 **Inside Kumo** (indecision)"

        tk_cross = "🟢 TK Cross (bullish)" if tenkan > kijun else "🔴 TK Cross (bearish)"
        return f"{cloud_pos}\n{tk_cross} | Tenkan: `${tenkan:,.4f}` | Kijun: `${kijun:,.4f}`"
    except Exception as e:
        return f"N/A ({e})"

# ─── FIBONACCI DISPLAY ────────────────────────────────────────────────────────

def _fib_display(ind: dict, price: float) -> str:
    fib = ind.get("fib_levels", {})
    if not fib:
        return "N/A"
    lines = []
    for level, val in sorted(fib.items(), key=lambda x: float(x[0])):
        marker = " ◀ PRICE" if abs(val - price) / price < 0.008 else ""
        direction = "↑" if val > price else "↓"
        lines.append(f"`Fib {level:<5}` ${val:>14,.4f} {direction}{marker}")
    return "\n".join(lines)

# ─── VIP DEEP EMBED BUILDER ───────────────────────────────────────────────────

def build_vip_deep_embed(
    symbol: str,
    signal: str,
    price: float,
    rsi: float,
    confidence: str,
    ai_text: str,
    ind: dict,
    mtf: dict,
    smart_score_val: int,
    mtf_badge: str,
    mtf_aligned: int,
) -> discord.Embed:
    """Build the enhanced VIP signal embed with all premium data."""
    coin    = symbol.replace("USDT", "")
    emoji   = coins_config.COIN_EMOJI.get(symbol, "🪙")
    logo    = coins_config.COIN_LOGOS.get(symbol)
    color   = coins_config.COIN_COLORS.get(symbol, 0x00c896)
    sector  = COIN_SECTORS.get(symbol, "Crypto Asset")
    is_buy  = signal == "BUY"

    # ATR-based levels
    atr = ind.get("atr", price * 0.02) if ind else price * 0.02
    tp1 = round(price + 1.5 * atr, 4) if is_buy else round(price - 1.5 * atr, 4)
    tp2 = round(price + 3.0 * atr, 4) if is_buy else round(price - 3.0 * atr, 4)
    tp3 = round(price + 5.0 * atr, 4) if is_buy else round(price - 5.0 * atr, 4)
    sl  = round(price - 1.2 * atr, 4) if is_buy else round(price + 1.2 * atr, 4)

    pct1  = abs(tp1 - price) / price * 100
    pct2  = abs(tp2 - price) / price * 100
    pct3  = abs(tp3 - price) / price * 100
    pct_sl = abs(sl  - price) / price * 100
    rr_val = round(pct2 / pct_sl, 2) if pct_sl else 2.0

    sig_label = "💎 VIP BUY" if is_buy else "💎 VIP SELL"

    embed = discord.Embed(
        title=f"{sig_label} — {emoji} {coin}  [{sector}]",
        description=(
            f"**{coins_config.COIN_NAMES_EN.get(symbol, symbol)}**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{mtf_badge}"
        ),
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    if logo:
        embed.set_thumbnail(url=logo)
    embed.set_author(name="💎 VIP Deep Analysis — 3-TF | Fibonacci | Ichimoku | Smart Score")

    # ── Smart Score ──────────────────────────────────────────────────────
    embed.add_field(
        name="🏆 Smart Score",
        value=_smart_score_bar(smart_score_val),
        inline=False,
    )

    # ── ATR-based trade levels ────────────────────────────────────────────
    embed.add_field(
        name="📍 Trade Levels (ATR-based)",
        value=(
            f"```\n"
            f"{'Entry':<12} ${price:>15,.4f}\n"
            f"{'TP1 +{:.1f}%'.format(pct1):<12} ${tp1:>15,.4f}  ◀ take 40%\n"
            f"{'TP2 +{:.1f}%'.format(pct2):<12} ${tp2:>15,.4f}  ◀ take 40%\n"
            f"{'TP3 +{:.1f}%'.format(pct3):<12} ${tp3:>15,.4f}  ◀ let ride\n"
            f"{'SL -{:.1f}%'.format(pct_sl):<12} ${sl:>15,.4f}  ◀ HARD STOP\n"
            f"{'ATR':<12} ${atr:>15,.4f}\n"
            f"{'R:R Ratio':<12} {'{}:1'.format(rr_val):>15}\n"
            f"```"
        ),
        inline=False,
    )

    # ── 3-TF MTF breakdown ────────────────────────────────────────────────
    embed.add_field(
        name="⏱ Multi-Timeframe Analysis (5m | 15m | 1h)",
        value=(
            f"```\n"
            f"{'TF':<6} {'Signal':<7} {'RSI':<7} {'MACD'}\n"
            f"{'─'*35}\n"
            + "\n".join(
                f"{'5m' if tf=='5m' else ('15m' if tf=='15m' else '1h'):<6} "
                f"{(mtf[tf]['signal'] or 'NONE'):<7} "
                f"{mtf[tf]['rsi']:<7.1f} "
                f"{'Bull ▲' if mtf[tf]['macd_bull'] else 'Bear ▼'}"
                for tf in ("5m", "15m", "1h")
            )
            + f"\n```"
        ),
        inline=False,
    )

    # ── RSI + Confidence ─────────────────────────────────────────────────
    embed.add_field(name="📊 RSI (14)", value=bot.rsi_bar(rsi), inline=False)
    embed.add_field(name="⭐ Signal Quality", value=bot.conf_stars(confidence), inline=True)
    embed.add_field(name="📐 Direction", value=f"`{'LONG 📈' if is_buy else 'SHORT 📉'}`", inline=True)
    embed.add_field(name="\u200b", value="━━━━━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)

    # ── Advanced indicator panel ──────────────────────────────────────────
    if ind:
        adx    = ind.get("adx", 0)
        vwap   = ind.get("vwap", price)
        cmf    = ind.get("cmf", 0)
        willr  = ind.get("willr", -50)
        ema200 = ind.get("ema200", price)
        struct_bull = ind.get("struct_bull", False)
        struct_bear = ind.get("struct_bear", False)
        struct_str  = "Higher Highs / Higher Lows 📈" if struct_bull else ("Lower Highs / Lower Lows 📉" if struct_bear else "Ranging / Consolidation ↔️")
        trend_ema   = "Above EMA200 🟢 (Bull)" if price > ema200 else "Below EMA200 🔴 (Bear)"
        vwap_pos    = "Above VWAP 🔼" if price > vwap else "Below VWAP 🔽"
        adx_str     = f"{adx:.1f} — " + ("Strong trend" if adx > 25 else ("Moderate" if adx > 18 else "Weak/Ranging"))
        cmf_str     = f"{cmf:+.3f} — " + ("Bullish flow 🟢" if cmf > 0.05 else ("Bearish flow 🔴" if cmf < -0.05 else "Neutral ⚪"))
        willr_str   = f"{willr:.0f} — " + ("Oversold 🟢" if willr < -80 else ("Overbought 🔴" if willr > -20 else "Neutral"))

        embed.add_field(
            name="🔬 Advanced Indicator Panel",
            value=(
                f"**ADX Trend Strength:** `{adx_str}`\n"
                f"**Williams %R:** `{willr_str}`\n"
                f"**Chaikin Money Flow:** `{cmf_str}`\n"
                f"**VWAP Position:** `{vwap_pos}`\n"
                f"**Market Structure:** `{struct_str}`\n"
                f"**Long-term Trend:** `{trend_ema}`"
            ),
            inline=False,
        )

    # ── Fibonacci levels ──────────────────────────────────────────────────
    if ind:
        df5 = bot.get_data(symbol, interval="5m")
        embed.add_field(
            name="📐 Fibonacci Retracement Levels",
            value=_fib_display(ind, price) if ind.get("fib_levels") else "N/A",
            inline=False,
        )

    # ── Ichimoku ──────────────────────────────────────────────────────────
    df5 = bot.get_data(symbol, interval="1h")
    embed.add_field(
        name="☁️ Ichimoku Cloud (1h)",
        value=_ichimoku_signal(df5, price),
        inline=False,
    )
    embed.add_field(name="\u200b", value="━━━━━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)

    # ── Entry strategy ────────────────────────────────────────────────────
    if ind:
        strat_en, strat_ro = _entry_strategy(signal, confidence, ind, price)
        embed.add_field(name="🎯 Entry Strategy 🇬🇧", value=strat_en, inline=False)
        embed.add_field(name="🎯 Strategie Intrare 🇷🇴", value=strat_ro, inline=False)
        embed.add_field(name="\u200b", value="━━━━━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)

    # ── AI Analysis ───────────────────────────────────────────────────────
    embed.add_field(
        name="🧠 AI Analysis",
        value=ai_text or "_Analysis unavailable — all data shown above_",
        inline=False,
    )
    embed.add_field(name="\u200b", value="━━━━━━━━━━━━━━━━━━━━━━━━━━━━", inline=False)

    # ── Risk reminder ─────────────────────────────────────────────────────
    embed.add_field(
        name="⚠️ Risk Management",
        value=(
            "🇬🇧 `Max 10% capital/trade` • `Set SL immediately` • `Take TP1 first`\n"
            "🇷🇴 `Max 10% capital/trade` • `Setează SL imediat` • `Ia TP1 primul`"
        ),
        inline=False,
    )

    embed.set_footer(text="💎 VIP Exclusive — 30 coins | 3-TF | Fibonacci | Ichimoku | Smart Score  •  Not financial advice")
    return embed

# ─── VIP SIGNAL LOOP ─────────────────────────────────────────────────────────

async def vip_deep_signal_loop(client, vip_ch_id: int, free_ch_id: int, interval: int = 300):
    """
    Enhanced VIP loop — scans ALL 30 coins every `interval` seconds.
    Sends to VIP channel only. FREE channel still gets basic signals from bot.signal_loop.
    """
    await client.wait_until_ready()
    await asyncio.sleep(30)  # Let bot fully start

    vip_last_signal: dict[str, str]            = {}
    vip_last_ts:     dict[str, datetime]        = {}
    COOLDOWN_H = 4

    print(f"[VIP LOOP] Starting — scanning {len(coins_config.ALL_VIP_SYMBOLS)} coins every {interval//60} min", flush=True)

    while True:
        vip_ch = client.get_channel(vip_ch_id)
        if vip_ch is None:
            try:
                vip_ch = await client.fetch_channel(vip_ch_id)
            except Exception:
                vip_ch = None

        try:
            now = datetime.now(timezone.utc)
            print(f"[VIP LOOP] Scanning {len(coins_config.ALL_VIP_SYMBOLS)} coins at {now.strftime('%H:%M:%S')}", flush=True)

            for symbol in coins_config.ALL_VIP_SYMBOLS:
                try:
                    # ── Get main data + signal ──────────────────────────
                    df5m = bot.get_data(symbol, interval="5m")
                    if df5m is None:
                        continue

                    sig, price, rsi, conf = bot.get_signal_v2(df5m)
                    if not sig or not price:
                        continue

                    ind = bot.calc_indicators(df5m)
                    if ind is None:
                        continue

                    # ── Cooldown check ───────────────────────────────────
                    last_sig  = vip_last_signal.get(symbol)
                    last_ts   = vip_last_ts.get(symbol)
                    dir_changed  = last_sig != sig
                    time_ok   = last_ts is None or (now - last_ts).total_seconds() >= COOLDOWN_H * 3600

                    if not (dir_changed or time_ok):
                        continue

                    vip_last_signal[symbol] = sig
                    vip_last_ts[symbol]     = now

                    # ── 3-TF MTF ─────────────────────────────────────────
                    mtf         = get_3tf_analysis(symbol)
                    mtf_badge, mtf_aligned = _mtf_summary(mtf, sig)

                    # ── Smart Score ───────────────────────────────────────
                    smart_val   = _smart_score(ind, sig, mtf_aligned)

                    # Skip very weak signals (Smart Score < 35)
                    if smart_val < 35:
                        print(f"  [VIP] {symbol}: SKIP (SmartScore={smart_val} < 35)", flush=True)
                        continue

                    # ── AI Analysis ───────────────────────────────────────
                    ai_text = bot.ai_analysis(sig, price, rsi, symbol)

                    # ── Chart ─────────────────────────────────────────────
                    try:
                        chart_file = bot.generate_chart(df5m, symbol, sig)
                    except Exception:
                        chart_file = None

                    # ── Build enhanced embed ──────────────────────────────
                    embed = build_vip_deep_embed(
                        symbol, sig, price, rsi, conf, ai_text,
                        ind, mtf, smart_val, mtf_badge, mtf_aligned
                    )

                    print(f"  [VIP] SENDING {sig} {symbol} | Score={smart_val} | MTF={mtf_aligned}/3", flush=True)

                    if vip_ch:
                        if chart_file:
                            await vip_ch.send(embed=embed, file=discord.File(chart_file))
                        else:
                            await vip_ch.send(embed=embed)

                    # Track in bot's global stats too
                    bot.SIGNAL_STATS[sig]     = bot.SIGNAL_STATS.get(sig, 0) + 1
                    bot.SIGNAL_STATS["total"] = bot.SIGNAL_STATS.get("total", 0) + 1

                    await asyncio.sleep(2)  # Small delay between sends

                except Exception as coin_err:
                    print(f"  [VIP] Error on {symbol}: {coin_err}", flush=True)
                    continue

            print(f"[VIP LOOP] Done. Next in {interval//60} min.", flush=True)

        except Exception as loop_err:
            print(f"[VIP LOOP ERROR] {loop_err}", flush=True)

        await asyncio.sleep(interval)

def start_vip_loop(client, vip_ch_id: int, free_ch_id: int, interval: int = 300):
    """Called from bot_extended.py to kick off the VIP loop as a background task."""
    client.loop.create_task(
        vip_deep_signal_loop(client, vip_ch_id, free_ch_id, interval)
    )
    print(f"[VIP LOOP] Task registered — {len(coins_config.ALL_VIP_SYMBOLS)} coins, every {interval//60} min", flush=True)

async def vip_analysis_loop(bot_module, interval: int = 1800):
    """
    Compatibility wrapper called by bot_extended.py:
        bot.client.loop.create_task(vip_analysis.vip_analysis_loop(bot, interval=1800))

    Reads VIP_SIGNALS_CHANNEL + FREE_SIGNALS_CHANNEL from bot_module
    and delegates to the full vip_deep_signal_loop.
    """
    client     = bot_module.client
    vip_ch_id  = getattr(bot_module, "VIP_SIGNALS_CHANNEL",  0) or 0
    free_ch_id = getattr(bot_module, "FREE_SIGNALS_CHANNEL", 0) or 0
    await vip_deep_signal_loop(client, vip_ch_id, free_ch_id, interval=interval)
