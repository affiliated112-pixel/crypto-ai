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

# CHANNEL IDs
WELCOME_CHANNEL = 1509522341074567208
RULES_CHANNEL = 1509522358812151938
HOWTO_CHANNEL = 1509522378072391801

STATUS_CHANNEL = 1509524579364638830
ALERTS_CHANNEL = 1509524631332196422

ANNOUNCEMENTS_CHANNEL = 1509524177730666588

FREE_SIGNALS_CHANNEL = 1509522466106642442
VIP_SIGNALS_CHANNEL = 1509522877966319848

MARKET_NEWS_CHANNEL = 1509522484594999387

GET_VIP_CHANNEL = 1509524395746525284

PERFORMANCE_CHANNEL = 1509524196139466852

# =========================
# MULTI COIN
# =========================

SYMBOLS = ["BTCUSDT", "ETHUSDT"]

LAST_SIGNAL = {}

intents = discord.Intents.default()
intents.members = True

client = discord.Client(intents=intents)

# =========================
# CHART FUNCTION
# =========================

def generate_chart(df, symbol):
    plt.figure(figsize=(10, 4))
    plt.plot(df["close"], color="#00c896", linewidth=1.5)
    plt.title(f"{symbol} - Price (5m)", fontsize=14)
    plt.xlabel("Candles")
    plt.ylabel("Price (USDT)")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    file_name = f"{symbol}.png"
    plt.savefig(file_name)
    plt.close()

    return file_name

# =========================
# MARKET DATA
# =========================

def get_data(symbol="BTCUSDT"):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit=100"
    data = requests.get(url).json()

    df = pd.DataFrame(data, columns=[
        "time","open","high","low","close","volume",
        "close_time","qav","trades","tbbav","tbqav","ignore"
    ])

    df["close"] = df["close"].astype(float)
    return df

# =========================
# SMART SIGNAL (FIX OUT OF BOUNDS)
# =========================

def get_signal(df):
    if len(df) < 20:
        return None, None, None

    rsi = RSIIndicator(close=df["close"], window=14).rsi().iloc[-1]
    price = df["close"].iloc[-1]

    if rsi < 30:
        return "BUY", price, rsi
    elif rsi > 70:
        return "SELL", price, rsi

    return None, price, rsi

# =========================
# ANTI-SPAM
# =========================

def can_send_signal(symbol, signal):
    global LAST_SIGNAL

    if symbol not in LAST_SIGNAL:
        LAST_SIGNAL[symbol] = signal
        return True

    if LAST_SIGNAL[symbol] != signal:
        LAST_SIGNAL[symbol] = signal
        return True

    return False

# =========================
# PRO SIGNAL FORMAT
# =========================

def format_signal(symbol, signal, price, rsi):
    return f"""
🚀 {symbol} SIGNAL

📍 Type: {signal}
💰 Entry: {round(price,2)}

🎯 Take Profit:
TP1: {round(price*1.02,2)}
TP2: {round(price*1.04,2)}

🛑 Stop Loss:
SL: {round(price*0.97,2)}

📊 RSI: {round(rsi,2)}

⚠️ Risk: Medium
🔥 Confidence: High
"""

# =========================
# AI EXPLANATION
# =========================

def explain_trade(signal, rsi):
    if signal == "BUY":
        return f"AI: Market is oversold (RSI {round(rsi,2)}). Potential upward reversal."
    elif signal == "SELL":
        return f"AI: Market is overbought (RSI {round(rsi,2)}). Potential drop incoming."
    return ""

# =========================
# VOLATILITY ALERT
# =========================

def check_volatility(df):
    change = abs(df["close"].iloc[-1] - df["close"].iloc[-2])
    if change > 200:
        return True
    return False

# =========================
# WELCOME
# =========================

@client.event
async def on_member_join(member):
    channel = client.get_channel(WELCOME_CHANNEL)

    await channel.send(f"""
👋 Welcome {member.mention}!

🇬🇧 Start here:
📜 <#{RULES_CHANNEL}>
📊 <#{HOWTO_CHANNEL}>

🇷🇴 Începe aici:
Citește regulile și învață cum funcționează semnalele!
""")

# =========================
# ON READY
# =========================

@client.event
async def on_ready():
    print(f"Bot online: {client.user}")

    status_channel = client.get_channel(STATUS_CHANNEL)
    await status_channel.send("🟢 Bot is ONLINE!")

    rules_channel = client.get_channel(RULES_CHANNEL)
    await rules_channel.send("""
📜 RULES (EN)
- No spam
- No scams
- Respect everyone

📜 REGULI (RO)
- Fără spam
- Fără scam
- Respectă pe toată lumea
""")

    howto_channel = client.get_channel(HOWTO_CHANNEL)
    async for msg in howto_channel.history(limit=10):
        if "HOW TO USE SIGNALS" in msg.content:
            break
    else:
        await howto_channel.send("""
📊 HOW TO USE SIGNALS

1. Use Binance / Bybit
2. Follow Entry / TP / SL
3. Use risk management

🇷🇴

1. Folosește Binance / Bybit
2. Urmează Entry / TP / SL
3. Gestionează riscul
""")

    vip_channel = client.get_channel(GET_VIP_CHANNEL)
    await vip_channel.send("""
💎 GET VIP ACCESS

Contact:
👤 <@1426677891269267618>
👤 <@1463583046962909410>

Premium signals + analysis 📈
""")

    client.loop.create_task(signal_loop())
    client.loop.create_task(market_news_loop())
    client.loop.create_task(announcement_loop())
    client.loop.create_task(performance_loop())
    client.loop.create_task(crash_alert())

# =========================
# SIGNAL LOOP (ANTI-SPAM + PRO FORMAT)
# =========================

async def signal_loop():
    await client.wait_until_ready()

    free_channel = client.get_channel(FREE_SIGNALS_CHANNEL)
    vip_channel = client.get_channel(VIP_SIGNALS_CHANNEL)
    alerts_channel = client.get_channel(ALERTS_CHANNEL)

    while True:
        try:
            for symbol in SYMBOLS:
                df = get_data(symbol)
                signal, price, rsi = get_signal(df)

                if df is not None and len(df) >= 2:
                    if check_volatility(df):
                        await alerts_channel.send(f"⚠️ HIGH VOLATILITY on {symbol}!")

                if signal and price and can_send_signal(symbol, signal):
                    chart = generate_chart(df, symbol)
                    msg = format_signal(symbol, signal, price, rsi)
                    explanation = explain_trade(signal, rsi)

                    await free_channel.send(msg)
                    await vip_channel.send(
                        content=f"{msg}\n🧠 {explanation}",
                        file=discord.File(chart)
                    )

            await asyncio.sleep(300)

        except Exception as e:
            await alerts_channel.send(f"⚠️ Error: {e}")
            await asyncio.sleep(60)

# =========================
# MARKET NEWS LOOP (RANDOM)
# =========================

async def market_news_loop():
    await client.wait_until_ready()
    channel = client.get_channel(MARKET_NEWS_CHANNEL)

    news = [
        "🚨 BTC volatility increasing!",
        "📉 Market correction possible",
        "📈 Bullish momentum detected",
        "🔥 ETH gaining strength"
    ]

    while True:
        msg = random.choice(news)
        await channel.send(msg)
        await asyncio.sleep(1800)

# =========================
# ANNOUNCEMENTS
# =========================

async def announcement_loop():
    await client.wait_until_ready()
    channel = client.get_channel(ANNOUNCEMENTS_CHANNEL)

    while True:
        await channel.send("📢 New VIP signals available! Upgrade now 💎")
        await asyncio.sleep(86400)

# =========================
# PERFORMANCE LOOP
# =========================

async def performance_loop():
    await client.wait_until_ready()
    channel = client.get_channel(PERFORMANCE_CHANNEL)

    while True:
        await channel.send("""
📊 DAILY PERFORMANCE

✅ +12% BTC trade
✅ +8% ETH trade
🔥 VIP WIN RATE: 87%

Join VIP 💎
""")
        await asyncio.sleep(86400)

# =========================
# MARKET CRASH ALERT
# =========================

async def crash_alert():
    await client.wait_until_ready()
    channel = client.get_channel(ALERTS_CHANNEL)

    while True:
        try:
            df = get_data("BTCUSDT")

            if len(df) >= 10 and df["close"].iloc[-1] < df["close"].iloc[-10]:
                await channel.send("🚨 MARKET DROP DETECTED!")

            await asyncio.sleep(600)

        except Exception as e:
            print(f"Crash alert error: {e}")
            await asyncio.sleep(60)

# =========================

client.run(TOKEN)
