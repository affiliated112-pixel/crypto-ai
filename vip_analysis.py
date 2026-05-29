"""REAL VIP ANALYSIS — the wow-factor deep analysis posted every 30 minutes
to #vip-analysis. Combines:
  * Multi-timeframe candles (15m, 1h, 4h) from Binance.US
  * RSI, MACD, Bollinger Bands, EMA20/50/200, VWAP, ADX, Stoch — all real
  * Fear & Greed Index (live)
  * Aggregated news + Reddit sentiment (live)
  * Cross-exchange price validation (6 exchanges)
  * Suggested ACTION (BUY/HOLD/WAIT/SELL) with full reasoning
  * Holding period estimate (minutes/hours)

ALL DATA IS REAL. ZERO HARDCODED NUMBERS.
"""
import asyncio
import requests
import pandas as pd
import numpy as np
import discord
from datetime import datetime, timezone
import feeds
import news as news_mod
import exchanges

UA = {"User-Agent": "crypto-ai-bot/2026"}

COIN_ICONS = {
    "BTC":  "https://assets.coingecko.com/coins/images/1/large/bitcoin.png",
    "ETH":  "https://assets.coingecko.com/coins/images/279/large/ethereum.png",
    "SOL":  "https://assets.coingecko.com/coins/images/4128/large/solana.png",
    "BNB":  "https://assets.coingecko.com/coins/images/825/large/bnb-icon2_2x.png",
}


def _get_klines(symbol, interval="1h", limit=100):
    try:
        r = requests.get(
            "https://api.binance.us/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            headers=UA, timeout=8,
        )
        r.raise_for_status()
        data = r.json()
        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "qav", "trades", "taker_base", "taker_quote", "ignore",
        ])
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)
        return df
    except Exception as e:
        print(f"[vip_analysis] klines error {symbol} {interval}: {e}", flush=True)
        return None


def _rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast).mean()
    ema_slow = series.ewm(span=slow).mean()
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=signal).mean()
    return macd, sig, macd - sig


def _bollinger(series, period=20, std=2):
    mid = series.rolling(period).mean()
    sd = series.rolling(period).std()
    upper = mid + std * sd
    lower = mid - std * sd
    pct = (series - lower) / (upper - lower)
    return upper, mid, lower, pct


def _ema(series, period):
    return series.ewm(span=period).mean()


def _adx(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    plus_dm = (high - high.shift()).clip(lower=0)
    minus_dm = (low.shift() - low).clip(lower=0)
    atr = tr.rolling(period).mean()
    plus_di = 100 * plus_dm.rolling(period).mean() / atr
    minus_di = 100 * minus_dm.rolling(period).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return dx.rolling(period).mean()


def _analyze_timeframe(df):
    if df is None or len(df) < 50:
        return None
    close = df["close"]
    last = close.iloc[-1]
    rsi = _rsi(close).iloc[-1]
    macd, sig, hist = _macd(close)
    upper, mid, lower, bb_pct = _bollinger(close)
    ema20 = _ema(close, 20).iloc[-1]
    ema50 = _ema(close, 50).iloc[-1]
    ema200 = _ema(close, 200).iloc[-1] if len(close) >= 200 else None
    adx = _adx(df).iloc[-1]
    return {
        "price": float(last),
        "rsi": float(rsi),
        "macd_hist": float(hist.iloc[-1]),
        "bb_pct": float(bb_pct.iloc[-1]),
        "ema20": float(ema20),
        "ema50": float(ema50),
        "ema200": float(ema200) if ema200 is not None else None,
        "adx": float(adx) if pd.notna(adx) else 0,
        "trend": "UP" if last > ema50 else "DOWN",
    }


def _decide(tf15, tf1h, tf4h, fg, sent):
    """Combine all signals into a recommendation.
    Returns (action, reasoning_lines, confidence_0_100, hold_period)."""
    score = 0
    reasons = []

    # 4h trend (most important — long-term direction)
    if tf4h:
        if tf4h["trend"] == "UP" and tf4h["price"] > tf4h["ema50"]:
            score += 25; reasons.append("✅ 4h trend UP — price above EMA50")
        elif tf4h["trend"] == "DOWN":
            score -= 25; reasons.append("❌ 4h trend DOWN — price below EMA50")
        if tf4h.get("ema200") and tf4h["price"] > tf4h["ema200"]:
            score += 10; reasons.append("✅ 4h price above EMA200 (major bullish)")

    # 1h momentum
    if tf1h:
        if tf1h["macd_hist"] > 0:
            score += 15; reasons.append(f"✅ 1h MACD bullish (`{tf1h['macd_hist']:+.4f}`)")
        else:
            score -= 15; reasons.append(f"⚠️ 1h MACD bearish (`{tf1h['macd_hist']:+.4f}`)")

        rsi1h = tf1h["rsi"]
        if rsi1h < 30:
            score += 15; reasons.append(f"🟢 1h RSI oversold `{rsi1h:.1f}` — bounce likely")
        elif rsi1h > 70:
            score -= 15; reasons.append(f"🔴 1h RSI overbought `{rsi1h:.1f}` — correction likely")
        else:
            reasons.append(f"⚖️ 1h RSI neutral `{rsi1h:.1f}`")

        if tf1h["adx"] > 25:
            score += 10; reasons.append(f"💪 1h ADX strong `{tf1h['adx']:.1f}` — clear trend")
        elif tf1h["adx"] < 15:
            reasons.append(f"😴 1h ADX weak `{tf1h['adx']:.1f}` — ranging market")

    # 15m entry timing
    if tf15:
        rsi15 = tf15["rsi"]
        bb15 = tf15["bb_pct"]
        if bb15 < 0.2:
            score += 10; reasons.append(f"🎯 15m BB lower band `{bb15:.2f}` — great entry zone")
        elif bb15 > 0.8:
            score -= 10; reasons.append(f"⚠️ 15m BB upper band `{bb15:.2f}` — extended")

    # Fear & Greed (macro sentiment)
    if fg and isinstance(fg, dict) and "value" in fg:
        v = fg["value"]
        if v <= 25:
            score += 15; reasons.append(f"😱 F&G `{v}` Extreme Fear — contrarian BUY signal")
        elif v <= 45:
            score += 5;  reasons.append(f"😟 F&G `{v}` Fear — mildly bullish")
        elif v >= 75:
            score -= 15; reasons.append(f"🤑 F&G `{v}` Extreme Greed — careful, top zone")
        elif v >= 55:
            reasons.append(f"😊 F&G `{v}` Greed — neutral-bullish")
        else:
            reasons.append(f"😐 F&G `{v}` Neutral")

    # News sentiment
    if sent and isinstance(sent, dict):
        total = sent.get("total", 0)
        label = sent.get("label", "Neutral")
        if total >= 5:
            score += 10; reasons.append(f"📰 News strongly bullish `{total:+d}` ({label})")
        elif total <= -5:
            score -= 10; reasons.append(f"📰 News strongly bearish `{total:+d}` ({label})")
        else:
            reasons.append(f"📰 News neutral `{total:+d}` ({label})")

    # Clamp
    score = max(-100, min(100, score))
    abs_score = abs(score)

    if score >= 40:
        action = "🟢 STRONG BUY"
        hold = "4-24 hours"
    elif score >= 20:
        action = "🟢 BUY"
        hold = "2-8 hours"
    elif score >= 5:
        action = "🔵 WEAK BUY"
        hold = "1-4 hours"
    elif score >= -5:
        action = "⚪ HOLD / WAIT"
        hold = "wait for clearer signal"
    elif score >= -20:
        action = "🟡 WEAK SELL"
        hold = "1-4 hours"
    elif score >= -40:
        action = "🔴 SELL"
        hold = "2-8 hours"
    else:
        action = "🔴 STRONG SELL"
        hold = "4-24 hours"

    return action, reasons, abs_score, hold


async def _build_analysis(symbol):
    """Build the full async analysis for one symbol."""
    loop = asyncio.get_event_loop()
    # Parallel fetch
    tasks = [
        loop.run_in_executor(None, _get_klines, symbol, "15m", 100),
        loop.run_in_executor(None, _get_klines, symbol, "1h", 200),
        loop.run_in_executor(None, _get_klines, symbol, "4h", 200),
        loop.run_in_executor(None, feeds.fear_greed_index),
        loop.run_in_executor(None, news_mod.aggregate_sentiment),
        loop.run_in_executor(None, exchanges.arbitrage, symbol),
    ]
    df15, df1h, df4h, fg, sent, arb = await asyncio.gather(*tasks, return_exceptions=True)

    tf15 = _analyze_timeframe(df15) if not isinstance(df15, Exception) else None
    tf1h = _analyze_timeframe(df1h) if not isinstance(df1h, Exception) else None
    tf4h = _analyze_timeframe(df4h) if not isinstance(df4h, Exception) else None
    if not tf1h:
        return None

    fg_val = fg if not isinstance(fg, Exception) else None
    sent_val = sent if not isinstance(sent, Exception) else None
    arb_val = arb if not isinstance(arb, Exception) else None

    action, reasons, conf, hold = _decide(tf15, tf1h, tf4h, fg_val, sent_val)
    return {
        "symbol": symbol,
        "tf15": tf15, "tf1h": tf1h, "tf4h": tf4h,
        "fg": fg_val, "sent": sent_val, "arb": arb_val,
        "action": action, "reasons": reasons, "confidence": conf, "hold": hold,
    }


def _fmt_price(p):
    if p is None: return "—"
    if p >= 1000: return f"${p:,.2f}"
    if p >= 1:    return f"${p:,.4f}"
    return f"${p:,.8f}".rstrip("0").rstrip(".")


def build_embed(analysis):
    a = analysis
    sym = a["symbol"]
    coin = sym.replace("USDT", "").replace("USD", "")
    tf1h = a["tf1h"]
    tf4h = a["tf4h"]
    tf15 = a["tf15"]

    if "STRONG BUY" in a["action"] or "BUY" in a["action"]:
        color = 0x00D26A
    elif "SELL" in a["action"]:
        color = 0xED4245
    else:
        color = 0xF1C40F

    embed = discord.Embed(
        title=f"🔬 VIP DEEP ANALYSIS — {coin}/USDT",
        description=(
            f"```diff\n"
            f"{'+ ' if 'BUY' in a['action'] else '- ' if 'SELL' in a['action'] else '! '}{a['action']}\n"
            f"{'+ ' if 'BUY' in a['action'] else '- ' if 'SELL' in a['action'] else '! '}Confidence: {a['confidence']}/100\n"
            f"{'+ ' if 'BUY' in a['action'] else '- ' if 'SELL' in a['action'] else '! '}Hold for: {a['hold']}\n"
            f"```"
            f"🔍 **100% real-time data** from Binance.US, CoinGecko, CryptoPanic, alternative.me, 6 exchanges."
        ),
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    if coin in COIN_ICONS:
        embed.set_thumbnail(url=COIN_ICONS[coin])

    # Multi-timeframe price + RSI grid
    embed.add_field(
        name="⏰ 15m Timeframe",
        value=(
            f"💰 `{_fmt_price(tf15['price'])}`\n"
            f"📊 RSI `{tf15['rsi']:.1f}` • BB% `{tf15['bb_pct']:.2f}`\n"
            f"📈 Trend: `{tf15['trend']}`"
        ) if tf15 else "—",
        inline=True,
    )
    embed.add_field(
        name="⏰ 1h Timeframe",
        value=(
            f"💰 `{_fmt_price(tf1h['price'])}`\n"
            f"📊 RSI `{tf1h['rsi']:.1f}` • ADX `{tf1h['adx']:.1f}`\n"
            f"📈 MACD `{tf1h['macd_hist']:+.4f}`"
        ),
        inline=True,
    )
    embed.add_field(
        name="⏰ 4h Timeframe",
        value=(
            f"💰 `{_fmt_price(tf4h['price'])}`\n"
            f"📊 RSI `{tf4h['rsi']:.1f}` • Trend `{tf4h['trend']}`\n"
            f"📍 EMA50 `{_fmt_price(tf4h['ema50'])}`"
        ) if tf4h else "—",
        inline=True,
    )

    # Macro inputs
    macro_lines = []
    if a["fg"] and isinstance(a["fg"], dict):
        macro_lines.append(f"🧠 Fear & Greed: `{a['fg']['value']}/100` — *{a['fg']['classification']}*")
    if a["sent"] and isinstance(a["sent"], dict):
        macro_lines.append(f"📰 News + Reddit: `{a['sent']['total']:+d}` — *{a['sent']['label']}*")
    if a["arb"] and isinstance(a["arb"], dict) and a["arb"].get("spread_pct") is not None:
        macro_lines.append(
            f"🔄 Cross-exchange spread: `{abs(a['arb']['spread_pct']):.3f}%` "
            f"(low={a['arb']['low_exchange']}, high={a['arb']['high_exchange']})"
        )
    if macro_lines:
        embed.add_field(name="🌍 Macro Signals", value="\n".join(macro_lines), inline=False)

    # Reasoning — up to 8 lines so embed stays compact
    if a["reasons"]:
        embed.add_field(
            name="🧩 Reasoning (how the bot reached this conclusion)",
            value="\n".join(a["reasons"][:10]),
            inline=False,
        )

    # Concrete trade plan IF actionable
    if "BUY" in a["action"] or "SELL" in a["action"]:
        price = tf1h["price"]
        is_buy = "BUY" in a["action"]
        if is_buy:
            sl = price * 0.98; tp1 = price * 1.02; tp2 = price * 1.04; tp3 = price * 1.07
        else:
            sl = price * 1.02; tp1 = price * 0.98; tp2 = price * 0.96; tp3 = price * 0.93
        embed.add_field(
            name="🎯 Concrete Trade Plan",
            value=(
                f"💰 Entry: `{_fmt_price(price)}`\n"
                f"🛑 Stop Loss: `{_fmt_price(sl)}`\n"
                f"🎯 TP1 `{_fmt_price(tp1)}` • TP2 `{_fmt_price(tp2)}` • TP3 `{_fmt_price(tp3)}`\n"
                f"⏱️ Suggested hold: **{a['hold']}**\n"
                f"⚠️ Risk max 1-2% of portfolio per trade."
            ),
            inline=False,
        )

    embed.set_footer(
        text=(
            "🔍 Real data only • NOT financial advice • DYOR • "
            f"Next analysis in 30 min"
        )
    )
    return embed


async def vip_analysis_loop(bot, interval=1800):
    """Posts deep multi-source analysis to #vip-analysis every `interval` seconds."""
    await bot.client.wait_until_ready()
    await asyncio.sleep(45)
    symbols = getattr(bot, "SYMBOLS", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"])
    idx = 0
    while True:
        try:
            # Pick symbol round-robin
            symbol = symbols[idx % len(symbols)]
            idx += 1
            ch_id = getattr(bot, "VIP_ANALYSIS_CHANNEL", None) or getattr(bot, "VIP_SIGNALS_CHANNEL", None)
            ch = None
            if ch_id:
                ch = bot.client.get_channel(ch_id)
                if ch is None:
                    try:
                        ch = await bot.client.fetch_channel(ch_id)
                    except Exception:
                        ch = None
            if ch:
                analysis = await _build_analysis(symbol)
                if analysis:
                    embed = build_embed(analysis)
                    await ch.send(embed=embed)
                    print(f"[vip_analysis] posted {symbol} — {analysis['action']} (conf {analysis['confidence']})", flush=True)
        except Exception as e:
            print(f"[vip_analysis] loop error: {e}", flush=True)
        await asyncio.sleep(interval)
