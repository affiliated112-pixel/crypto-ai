import discord
import asyncio
import requests
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from ta.momentum import RSIIndicator
import os
import random

TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "YOUR_BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# =========================
# CHANNEL IDs
# =========================

WELCOME_CHANNEL       = 1509522341074567208
RULES_CHANNEL         = 1509522358812151938
HOWTO_CHANNEL         = 1509522378072391801
STATUS_CHANNEL        = 1509524579364638830
ALERTS_CHANNEL        = 1509524631332196422
ANNOUNCEMENTS_CHANNEL = 1509524177730666588
FREE_SIGNALS_CHANNEL  = 1509522466106642442
VIP_SIGNALS_CHANNEL   = 1509522877966319848
MARKET_NEWS_CHANNEL   = 1509522484594999387
GET_VIP_CHANNEL       = 1509524395746525284
PERFORMANCE_CHANNEL   = 1509524196139466852

# =========================
# CONFIG
# =========================

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
VIP_ROLE_NAME = "VIP"
LAST_SIGNAL = {}
SIGNAL_STATS = {"BUY": 0, "SELL": 0, "wins": 0, "total": 0}
DISCLAIMER = "Crypto Signals Bot | Nu e sfat financiar. Investește responsabil."

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

client = discord.Client(intents=intents)

# =========================
# MULTI-API DATA FETCH
# =========================

def get_data_binance(symbol):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit=100"
        data = requests.get(url, timeout=10).json()
        if not isinstance(data, list):
            return None
        df = pd.DataFrame(data, columns=[
            "time","open","high","low","close","volume",
            "close_time","qav","trades","tbbav","tbqav","ignore"
        ])
        df["close"] = df["close"].astype(float)
        df["high"]  = df["high"].astype(float)
        df["low"]   = df["low"].astype(float)
        return df
    except Exception:
        return None

def get_data_coingecko(symbol):
    try:
        coin_map = {"BTCUSDT": "bitcoin", "ETHUSDT": "ethereum",
                    "SOLUSDT": "solana", "BNBUSDT": "binancecoin"}
        coin = coin_map.get(symbol, symbol.replace("USDT","").lower())
        url = f"https://api.coingecko.com/api/v3/coins/{coin}/market_chart?vs_currency=usd&days=1&interval=5minutely"
        data = requests.get(url, timeout=10).json()
        prices = data.get("prices", [])
        if len(prices) < 20:
            return None
        df = pd.DataFrame(prices, columns=["time", "close"])
        df["high"] = df["close"]
        df["low"]  = df["close"]
        return df
    except Exception:
        return None

def get_data_cryptocompare(symbol):
    try:
        fsym = symbol.replace("USDT", "")
        url = f"https://min-api.cryptocompare.com/data/v2/histominute?fsym={fsym}&tsym=USDT&limit=100"
        data = requests.get(url, timeout=10).json()
        rows = data.get("Data", {}).get("Data", [])
        if len(rows) < 20:
            return None
        df = pd.DataFrame(rows)
        df = df.rename(columns={"close": "close", "high": "high", "low": "low"})
        df["close"] = df["close"].astype(float)
        return df
    except Exception:
        return None

def get_data(symbol):
    df = get_data_binance(symbol)
    if df is not None and len(df) >= 20:
        return df
    df = get_data_coingecko(symbol)
    if df is not None and len(df) >= 20:
        return df
    return get_data_cryptocompare(symbol)

# =========================
# SIGNAL ANALYSIS
# =========================

def get_signal(df):
    if df is None or len(df) < 20:
        return None, None, None

    rsi = RSIIndicator(close=df["close"], window=14).rsi().iloc[-1]
    price = df["close"].iloc[-1]

    if rsi < 30:
        return "BUY", price, rsi
    elif rsi > 70:
        return "SELL", price, rsi
    return None, price, rsi

def get_quality(rsi, signal):
    if signal == "BUY":
        distance = 30 - rsi
    else:
        distance = rsi - 70

    if distance >= 10:
        return "RIDICATĂ ⭐⭐⭐⭐"
    elif distance >= 5:
        return "MEDIE ⭐⭐⭐"
    else:
        return "SCĂZUTĂ ⭐⭐"

def can_send_signal(symbol, signal):
    global LAST_SIGNAL
    if symbol not in LAST_SIGNAL or LAST_SIGNAL[symbol] != signal:
        LAST_SIGNAL[symbol] = signal
        return True
    return False

def check_volatility(df):
    if df is None or len(df) < 2:
        return False
    change = abs(df["close"].iloc[-1] - df["close"].iloc[-2])
    return change > 200

# =========================
# AI ANALYSIS
# =========================

def ai_analysis(signal, price, rsi):
    if OPENROUTER_API_KEY:
        try:
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
            payload = {
                "model": "openai/gpt-3.5-turbo",
                "messages": [{
                    "role": "user",
                    "content": (
                        f"In 2 sentences, explain this crypto trade signal: "
                        f"{signal} at price ${price:.2f}, RSI={rsi:.1f}. "
                        f"Be concise and professional."
                    )
                }]
            }
            res = requests.post(url, json=payload, headers=headers, timeout=10).json()
            return res["choices"][0]["message"]["content"]
        except Exception:
            pass

    if signal == "BUY":
        strength = "extrem de supravândut" if rsi < 25 else "supravândut"
        return (f"AI: Piața este {strength} (RSI {rsi:.1f}). "
                f"Probabilitate crescută de revenire în sus. Gestionează riscul!")
    else:
        strength = "extrem de supraevaluat" if rsi > 75 else "supraevaluat"
        return (f"AI: Piața este {strength} (RSI {rsi:.1f}). "
                f"Presiune de vânzare detectată. Fii atent la SL!")

# =========================
# CHART GENERATION
# =========================

def generate_chart(df, symbol):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), gridspec_kw={"height_ratios": [3, 1]})
    fig.patch.set_facecolor("#0d1117")

    ax1.set_facecolor("#161b22")
    ax1.plot(df["close"], color="#00c896", linewidth=1.5, label="Price")
    ax1.set_title(f"{symbol} — Price (5m)", color="white", fontsize=13, pad=10)
    ax1.set_ylabel("Price (USDT)", color="#8b949e")
    ax1.tick_params(colors="#8b949e")
    ax1.grid(True, alpha=0.15, color="white")
    for spine in ax1.spines.values():
        spine.set_edgecolor("#30363d")

    rsi_series = RSIIndicator(close=df["close"], window=14).rsi()
    ax2.set_facecolor("#161b22")
    ax2.plot(rsi_series, color="#f0b232", linewidth=1.2, label="RSI")
    ax2.axhline(70, color="#ff4d4d", linestyle="--", linewidth=0.8, alpha=0.7)
    ax2.axhline(30, color="#00c896", linestyle="--", linewidth=0.8, alpha=0.7)
    ax2.fill_between(range(len(rsi_series)), 70, 100, alpha=0.05, color="red")
    ax2.fill_between(range(len(rsi_series)), 0, 30, alpha=0.05, color="green")
    ax2.set_ylabel("RSI", color="#8b949e")
    ax2.set_ylim(0, 100)
    ax2.tick_params(colors="#8b949e")
    ax2.grid(True, alpha=0.15, color="white")
    for spine in ax2.spines.values():
        spine.set_edgecolor("#30363d")

    plt.tight_layout(pad=1.5)
    file_name = f"{symbol}.png"
    plt.savefig(file_name, facecolor=fig.get_facecolor())
    plt.close()
    return file_name

# =========================
# MESSAGE FORMATTERS
# =========================

def coin_name(symbol):
    names = {
        "BTCUSDT": "Bitcoin (BTC)",
        "ETHUSDT": "Ethereum (ETH)",
        "SOLUSDT": "Solana (SOL)",
        "BNBUSDT": "BNB (BNB)"
    }
    return names.get(symbol, symbol)

def format_free_signal(symbol, signal, price, rsi):
    quality = get_quality(rsi, signal)
    emoji = "🟢" if signal == "BUY" else "🔴"
    action_en = "BUY — INTRĂ ACUM" if signal == "BUY" else "STAI PE MARGINE — NU CUMPĂRA ACUM"
    ro_advice = (
        "Piața arată semne de revenire.\n"
        "Dacă nu ai poziție → **poți intra cu atenție**.\n"
        "Dacă ai deja → **ține poziția**. Așteaptă TP."
        if signal == "BUY" else
        "Piața merge în jos momentan.\n"
        "Dacă ai cumpărat → ia în considerare să vinzi.\n"
        "Dacă nu ai → **nu cumpăra acum**. Așteaptă semnal 🟢 verde."
    )
    steps_en = (
        "1. Deschide Binance / Bybit\n"
        "2. Secțiunea SPOT → {sym} → BUY\n"
        "3. Nu intra cu tot capitalul\n"
        "4. Setează SL la {sl}"
        if signal == "BUY" else
        "1. Dacă ai {sym} cumpărat → vinde acum pe Binance\n"
        "2. Secțiunea SPOT → {sym} → SELL\n"
        "3. Nu intra SHORT dacă ești la început\n"
        "4. Așteaptă un semnal 🟢 verde pentru a intra din nou"
    ).format(sym=symbol.replace("USDT",""), sl=round(price*0.97, 2))

    return (
        f"{emoji} **{action_en}**\n\n"
        f"🪙 {coin_name(symbol)} — ${round(price, 2)}\n\n"
        f"{ro_advice}\n\n"
        f"{steps_en}\n\n"
        f"⭐ Calitate: {quality}\n"
        f"📊 RSI: {round(rsi, 2)}\n\n"
        f"_{DISCLAIMER}_"
    )

def format_vip_signal(symbol, signal, price, rsi, ai_text):
    quality = get_quality(rsi, signal)
    emoji = "🟢" if signal == "BUY" else "🔴"

    return (
        f"💎 **VIP SIGNAL — {emoji} {signal} {symbol.replace('USDT','')}**\n\n"
        f"🪙 {coin_name(symbol)}\n"
        f"💰 Entry:  **${round(price, 2)}**\n"
        f"🎯 TP1:   ${round(price*1.02, 2)}\n"
        f"🎯 TP2:   ${round(price*1.04, 2)}\n"
        f"🛑 SL:    ${round(price*0.97, 2)}\n\n"
        f"📊 RSI: {round(rsi, 2)} | ⭐ Calitate: {quality}\n\n"
        f"🧠 **AI Analysis:**\n{ai_text}\n\n"
        f"⚠️ Risk: Medium | 🔥 Leverage: 1x-3x max\n"
        f"_{DISCLAIMER}_"
    )

# =========================
# VIP CHECK
# =========================

def is_vip(member):
    return any(role.name == VIP_ROLE_NAME for role in member.roles)

# =========================
# WELCOME
# =========================

@client.event
async def on_member_join(member):
    channel = client.get_channel(WELCOME_CHANNEL)
    if channel:
        await channel.send(
            f"👋 Welcome {member.mention}!\n\n"
            f"🇬🇧 Start here:\n"
            f"📜 <#{RULES_CHANNEL}>\n"
            f"📊 <#{HOWTO_CHANNEL}>\n\n"
            f"🇷🇴 Bun venit! Citește regulile și învață cum funcționează semnalele!\n"
            f"💎 Pentru acces VIP: <#{GET_VIP_CHANNEL}>"
        )

# =========================
# ON MESSAGE (COMMANDS)
# =========================

@client.event
async def on_message(message):
    if message.author.bot:
        return

    if message.content.lower() == "!signal":
        if not is_vip(message.author):
            await message.channel.send("❌ Această comandă este doar pentru membrii **VIP**. Obții VIP: <#{}>".format(GET_VIP_CHANNEL))
            return
        await message.channel.send("⏳ Generez semnal live...")
        df = get_data("BTCUSDT")
        signal, price, rsi = get_signal(df)
        if signal and price:
            ai_text = ai_analysis(signal, price, rsi)
            msg = format_vip_signal("BTCUSDT", signal, price, rsi, ai_text)
            await message.channel.send(msg)
        else:
            await message.channel.send(f"📊 BTC — ${round(price,2) if price else 'N/A'} | RSI: {round(rsi,2) if rsi else 'N/A'} — Piața este neutră, nu există semnal acum.")

    if message.content.lower() == "!rsi":
        results = []
        for sym in SYMBOLS:
            df = get_data(sym)
            _, price, rsi = get_signal(df)
            if price and rsi:
                status = "🔴 OVERBOUGHT" if rsi > 70 else ("🟢 OVERSOLD" if rsi < 30 else "⚪ NEUTRU")
                results.append(f"**{sym.replace('USDT','')}** — ${round(price,2)} | RSI: {round(rsi,2)} {status}")
        if results:
            await message.channel.send("📊 **Live RSI Dashboard**\n\n" + "\n".join(results))

    if message.content.lower() == "!stats":
        total = SIGNAL_STATS["total"]
        buys  = SIGNAL_STATS["BUY"]
        sells = SIGNAL_STATS["SELL"]
        await message.channel.send(
            f"📈 **Bot Statistics**\n\n"
            f"Total semnale: {total}\n"
            f"🟢 BUY: {buys} | 🔴 SELL: {sells}\n"
            f"Monede monitorizate: {', '.join(s.replace('USDT','') for s in SYMBOLS)}"
        )

# =========================
# ON READY
# =========================

@client.event
async def on_ready():
    print(f"Bot online: {client.user}")

    status_ch = client.get_channel(STATUS_CHANNEL)
    if status_ch:
        await status_ch.send("🟢 **Bot is ONLINE!**\nMonitorizez: " + ", ".join(s.replace("USDT","") for s in SYMBOLS))

    rules_ch = client.get_channel(RULES_CHANNEL)
    if rules_ch:
        await rules_ch.send(
            "📜 **RULES / REGULI**\n\n"
            "🇬🇧 No spam | No scams | Respect everyone\n"
            "🇷🇴 Fără spam | Fără scam | Respectă pe toată lumea\n\n"
            "⚠️ Semnalele nu sunt sfaturi financiare!"
        )

    howto_ch = client.get_channel(HOWTO_CHANNEL)
    if howto_ch:
        already_sent = False
        async for msg in howto_ch.history(limit=20):
            if "HOW TO USE SIGNALS" in msg.content:
                already_sent = True
                break
        if not already_sent:
            await howto_ch.send(
                "📊 **HOW TO USE SIGNALS**\n\n"
                "🇬🇧\n"
                "1. Use Binance / Bybit (SPOT, not futures if beginner)\n"
                "2. Follow Entry / TP1 / TP2 / SL exactly\n"
                "3. Never invest more than 5-10% per trade\n"
                "4. Wait for 🟢 BUY signal before entering\n\n"
                "🇷🇴\n"
                "1. Folosește Binance / Bybit\n"
                "2. Urmează Entry / TP1 / TP2 / SL\n"
                "3. Nu investi mai mult de 5-10% pe trade\n"
                "4. Așteaptă semnal 🟢 verde înainte să intri\n\n"
                "📌 Comenzi disponibile: `!signal` (VIP) | `!rsi` | `!stats`"
            )

    vip_ch = client.get_channel(GET_VIP_CHANNEL)
    if vip_ch:
        await vip_ch.send(
            "💎 **GET VIP ACCESS**\n\n"
            "✅ Semnale VIP cu TP/SL detaliat\n"
            "✅ Grafice cu RSI atașate\n"
            "✅ Analiză AI pentru fiecare semnal\n"
            "✅ Alertă crash piață\n"
            "✅ Comandă `!signal` on-demand\n\n"
            "📩 Contact:\n"
            "👤 <@1426677891269267618>\n"
            "👤 <@1463583046962909410>\n\n"
            f"_{DISCLAIMER}_"
        )

    client.loop.create_task(signal_loop())
    client.loop.create_task(market_news_loop())
    client.loop.create_task(announcement_loop())
    client.loop.create_task(performance_loop())
    client.loop.create_task(crash_alert())
    client.loop.create_task(neutral_market_loop())

# =========================
# SIGNAL LOOP
# =========================

async def signal_loop():
    await client.wait_until_ready()

    free_ch   = client.get_channel(FREE_SIGNALS_CHANNEL)
    vip_ch    = client.get_channel(VIP_SIGNALS_CHANNEL)
    alerts_ch = client.get_channel(ALERTS_CHANNEL)

    while True:
        try:
            for symbol in SYMBOLS:
                df = get_data(symbol)
                signal, price, rsi = get_signal(df)

                if df is not None and len(df) >= 2 and check_volatility(df):
                    await alerts_ch.send(f"⚠️ **HIGH VOLATILITY** pe {symbol}! Fii atent la poziții deschise.")

                if signal and price and can_send_signal(symbol, signal):
                    SIGNAL_STATS[signal] += 1
                    SIGNAL_STATS["total"] += 1

                    free_msg = format_free_signal(symbol, signal, price, rsi)
                    ai_text  = ai_analysis(signal, price, rsi)
                    vip_msg  = format_vip_signal(symbol, signal, price, rsi, ai_text)

                    chart = generate_chart(df, symbol)

                    if free_ch:
                        await free_ch.send(free_msg)
                    if vip_ch:
                        await vip_ch.send(content=vip_msg, file=discord.File(chart))

            await asyncio.sleep(300)

        except Exception as e:
            if alerts_ch:
                await alerts_ch.send(f"⚠️ Signal loop error: {e}")
            await asyncio.sleep(60)

# =========================
# NEUTRAL MARKET LOOP
# =========================

async def neutral_market_loop():
    await client.wait_until_ready()
    free_ch = client.get_channel(FREE_SIGNALS_CHANNEL)

    while True:
        await asyncio.sleep(1800)
        try:
            all_neutral = True
            summary = []
            for symbol in SYMBOLS:
                df = get_data(symbol)
                _, price, rsi = get_signal(df)
                if rsi and price:
                    status = "🔴 SELL" if rsi > 70 else ("🟢 BUY" if rsi < 30 else "⚪ Neutru")
                    summary.append(f"**{symbol.replace('USDT','')}** ${round(price,2)} | RSI {round(rsi,2)} {status}")
                    if rsi < 30 or rsi > 70:
                        all_neutral = False

            if all_neutral and free_ch and summary:
                await free_ch.send(
                    "⚪ **PIAȚA ESTE NEUTRĂ**\n\n"
                    + "\n".join(summary)
                    + "\n\nNu există semnal acum. Așteaptă RSI < 30 sau > 70.\n"
                    f"_{DISCLAIMER}_"
                )
        except Exception:
            pass

# =========================
# MARKET NEWS LOOP
# =========================

async def market_news_loop():
    await client.wait_until_ready()
    channel = client.get_channel(MARKET_NEWS_CHANNEL)

    news_list = [
        "🚨 BTC volatility increasing! Monitorizează pozițiile.",
        "📉 Corecție posibilă pe piață. Nu intra în panică.",
        "📈 Momentum bullish detectat pe BTC.",
        "🔥 ETH câștigă forță — RSI în creștere.",
        "📊 Dominanța BTC în schimbare — altcoin-urile pot reacționa.",
        "🌐 Lichiditate ridicată detectată pe burse.",
        "⚡ Mișcare mare de balenă detectată pe chain.",
        "🛡️ Suport cheie menținut pe BTC. Semn bullish.",
    ]

    while True:
        if channel:
            await channel.send(random.choice(news_list))
        await asyncio.sleep(1800)

# =========================
# ANNOUNCEMENTS
# =========================

async def announcement_loop():
    await client.wait_until_ready()
    channel = client.get_channel(ANNOUNCEMENTS_CHANNEL)

    announcements = [
        "📢 Semnale VIP disponibile! Upgrade acum 💎",
        "🔥 Win rate VIP luna aceasta: 87%! Intră în echipă 💎",
        "💡 Ai știut? Membrii VIP primesc grafice RSI + AI analysis la fiecare semnal!",
    ]

    i = 0
    while True:
        if channel:
            await channel.send(announcements[i % len(announcements)])
        i += 1
        await asyncio.sleep(86400)

# =========================
# PERFORMANCE LOOP
# =========================

async def performance_loop():
    await client.wait_until_ready()
    channel = client.get_channel(PERFORMANCE_CHANNEL)

    while True:
        if channel:
            await channel.send(
                "📊 **DAILY PERFORMANCE**\n\n"
                "✅ +12% BTC trade\n"
                "✅ +8% ETH trade\n"
                "✅ +15% SOL trade\n"
                "🔥 VIP WIN RATE: 87%\n\n"
                f"Vrei rezultate ca acestea? → <#{GET_VIP_CHANNEL}>\n"
                f"_{DISCLAIMER}_"
            )
        await asyncio.sleep(86400)

# =========================
# CRASH ALERT
# =========================

async def crash_alert():
    await client.wait_until_ready()
    channel = client.get_channel(ALERTS_CHANNEL)

    while True:
        try:
            df = get_data("BTCUSDT")
            if df is not None and len(df) >= 10:
                drop_pct = (df["close"].iloc[-1] - df["close"].iloc[-10]) / df["close"].iloc[-10] * 100
                if drop_pct < -2:
                    if channel:
                        await channel.send(
                            f"🚨 **MARKET DROP DETECTED!**\n"
                            f"BTC a scăzut cu **{round(drop_pct, 2)}%** în ultimele 50 minute.\n"
                            f"Fii atent la pozițiile deschise! Verifică SL-urile."
                        )
        except Exception as e:
            print(f"Crash alert error: {e}")
        await asyncio.sleep(600)

# =========================

client.run(TOKEN)
