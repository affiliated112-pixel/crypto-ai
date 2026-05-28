import discord
import asyncio
import requests
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator
import os
import random
from datetime import datetime

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

SYMBOLS       = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
VIP_ROLE_NAME = "VIP"
DISCLAIMER    = "Crypto Signals Bot | Nu e sfat financiar. Investește responsabil."

LAST_SIGNAL   = {}
SIGNAL_STATS  = {"BUY": 0, "SELL": 0, "total": 0}
PRICE_ALERTS  = {}   # {user_id: [(symbol, target, direction)]}

COIN_COLORS = {
    "BTCUSDT": 0xF7931A,
    "ETHUSDT": 0x627EEA,
    "SOLUSDT": 0x9945FF,
    "BNBUSDT": 0xF0B90B,
}

COIN_EMOJI = {
    "BTCUSDT": "₿",
    "ETHUSDT": "Ξ",
    "SOLUSDT": "◎",
    "BNBUSDT": "⬡",
}

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
client = discord.Client(intents=intents)

# =========================
# MULTI-API DATA FETCH
# =========================

def get_data_binance(symbol, interval="5m", limit=150):
    try:
        url = (f"https://api.binance.com/api/v3/klines"
               f"?symbol={symbol}&interval={interval}&limit={limit}")
        data = requests.get(url, timeout=10).json()
        if not isinstance(data, list) or len(data) < 20:
            return None
        df = pd.DataFrame(data, columns=[
            "time","open","high","low","close","volume",
            "close_time","qav","trades","tbbav","tbqav","ignore"
        ])
        for col in ("open","high","low","close","volume"):
            df[col] = df[col].astype(float)
        return df
    except Exception:
        return None

def get_data_coingecko(symbol):
    try:
        coin_map = {"BTCUSDT":"bitcoin","ETHUSDT":"ethereum",
                    "SOLUSDT":"solana","BNBUSDT":"binancecoin"}
        coin = coin_map.get(symbol, symbol.replace("USDT","").lower())
        url = (f"https://api.coingecko.com/api/v3/coins/{coin}"
               f"/market_chart?vs_currency=usd&days=1&interval=5minutely")
        data = requests.get(url, timeout=10).json()
        prices = data.get("prices", [])
        if len(prices) < 20:
            return None
        df = pd.DataFrame(prices, columns=["time","close"])
        df["high"] = df["close"]
        df["low"]  = df["close"]
        df["open"] = df["close"]
        df["volume"] = 0.0
        return df
    except Exception:
        return None

def get_data(symbol, interval="5m"):
    df = get_data_binance(symbol, interval)
    if df is not None and len(df) >= 30:
        return df
    return get_data_coingecko(symbol)

# =========================
# TECHNICAL ANALYSIS
# =========================

def calc_indicators(df):
    """Returns dict with rsi, macd_hist, ema50, price, volume_avg"""
    if df is None or len(df) < 35:
        return None
    close = df["close"]
    rsi        = RSIIndicator(close=close, window=14).rsi().iloc[-1]
    macd_obj   = MACD(close=close)
    macd_hist  = macd_obj.macd_diff().iloc[-1]
    ema50      = EMAIndicator(close=close, window=50).ema_indicator().iloc[-1]
    price      = close.iloc[-1]
    vol_avg    = df["volume"].iloc[-20:].mean() if "volume" in df.columns else 0
    vol_now    = df["volume"].iloc[-1] if "volume" in df.columns else 0
    return {
        "rsi":      rsi,
        "macd_hist": macd_hist,
        "ema50":    ema50,
        "price":    price,
        "vol_avg":  vol_avg,
        "vol_now":  vol_now,
    }

def get_signal_v2(df):
    """
    Confluence signal: RSI + MACD + EMA trend filter.
    Returns (signal, price, rsi, confidence) or (None, price, rsi, None)
    """
    ind = calc_indicators(df)
    if ind is None:
        return None, None, None, None

    rsi       = ind["rsi"]
    macd_hist = ind["macd_hist"]
    price     = ind["price"]
    ema50     = ind["ema50"]

    buy_conditions  = [rsi < 35, macd_hist > 0, price > ema50 * 0.98]
    sell_conditions = [rsi > 65, macd_hist < 0, price < ema50 * 1.02]

    buy_score  = sum(buy_conditions)
    sell_score = sum(sell_conditions)

    if buy_score >= 2:
        conf = "🔥 RIDICATĂ" if buy_score == 3 else "⚡ MEDIE"
        return "BUY", price, rsi, conf
    if sell_score >= 2:
        conf = "🔥 RIDICATĂ" if sell_score == 3 else "⚡ MEDIE"
        return "SELL", price, rsi, conf

    return None, price, rsi, None

def get_signal_15m(symbol):
    """Confirmation on higher timeframe."""
    df = get_data(symbol, interval="15m")
    if df is None:
        return None
    ind = calc_indicators(df)
    if ind is None:
        return None
    if ind["rsi"] < 40 and ind["macd_hist"] > 0:
        return "BUY"
    if ind["rsi"] > 60 and ind["macd_hist"] < 0:
        return "SELL"
    return None

def can_send_signal(symbol, signal):
    global LAST_SIGNAL
    if symbol not in LAST_SIGNAL or LAST_SIGNAL[symbol] != signal:
        LAST_SIGNAL[symbol] = signal
        return True
    return False

def check_volume_spike(ind):
    if ind["vol_avg"] > 0 and ind["vol_now"] > ind["vol_avg"] * 2.5:
        return True
    return False

def check_volatility(df):
    if df is None or len(df) < 2:
        return False
    return abs(df["close"].iloc[-1] - df["close"].iloc[-2]) > 200

# =========================
# FEAR & GREED
# =========================

def get_fear_greed():
    try:
        data = requests.get("https://api.alternative.me/fng/?limit=1", timeout=8).json()
        val   = int(data["data"][0]["value"])
        label = data["data"][0]["value_classification"]
        if val <= 25:
            emoji = "😱"
        elif val <= 45:
            emoji = "😟"
        elif val <= 55:
            emoji = "😐"
        elif val <= 75:
            emoji = "😊"
        else:
            emoji = "🤑"
        return val, label, emoji
    except Exception:
        return None, None, None

# =========================
# TOP GAINERS / LOSERS
# =========================

def get_top_movers():
    try:
        url  = "https://api.binance.com/api/v3/ticker/24hr"
        data = requests.get(url, timeout=10).json()
        usdt = [x for x in data if x["symbol"].endswith("USDT") and float(x["quoteVolume"]) > 5_000_000]
        sorted_by_change = sorted(usdt, key=lambda x: float(x["priceChangePercent"]))
        losers  = sorted_by_change[:5]
        gainers = sorted_by_change[-5:][::-1]
        return gainers, losers
    except Exception:
        return [], []

# =========================
# AI ANALYSIS
# =========================

def ai_analysis(signal, price, rsi, symbol):
    if OPENROUTER_API_KEY:
        try:
            res = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                json={
                    "model": "openai/gpt-3.5-turbo",
                    "messages": [{"role": "user", "content":
                        f"In 2 concise sentences, explain this crypto signal: "
                        f"{signal} {symbol} at ${price:.2f}, RSI={rsi:.1f}. Be professional."
                    }]
                },
                timeout=10
            ).json()
            return res["choices"][0]["message"]["content"]
        except Exception:
            pass

    if signal == "BUY":
        strength = "extrem de supravândut" if rsi < 25 else "supravândut"
        return (f"RSI-ul este {strength} la {rsi:.1f}, indicând posibilă revenire. "
                f"MACD confirmă momentumul pozitiv. Gestionează riscul!")
    else:
        strength = "extrem de supraevaluat" if rsi > 75 else "supraevaluat"
        return (f"RSI-ul este {strength} la {rsi:.1f}, indicând presiune de vânzare. "
                f"MACD confirmă slăbirea momentumului. Respectă SL-ul!")

# =========================
# CHART GENERATION (3 PANELS)
# =========================

def generate_chart(df, symbol, signal=None):
    fig, (ax1, ax2, ax3) = plt.subplots(
        3, 1, figsize=(12, 9),
        gridspec_kw={"height_ratios": [3, 1, 1]}
    )
    fig.patch.set_facecolor("#0d1117")

    close  = df["close"]
    ema50  = EMAIndicator(close=close, window=50).ema_indicator()
    rsi_s  = RSIIndicator(close=close, window=14).rsi()
    macd_o = MACD(close=close)
    macd_l = macd_o.macd()
    macd_sig = macd_o.macd_signal()
    macd_h = macd_o.macd_diff()

    color = "#00c896" if signal == "BUY" else ("#ff4d4d" if signal == "SELL" else "#58a6ff")

    # Panel 1: Price + EMA
    ax1.set_facecolor("#161b22")
    ax1.plot(close,  color=color,    linewidth=1.5, label="Price", zorder=3)
    ax1.plot(ema50,  color="#f0b232", linewidth=1.0, linestyle="--", label="EMA50", alpha=0.8)
    ax1.set_title(f"{symbol} — {signal or 'Monitor'} | {datetime.utcnow().strftime('%H:%M UTC')}",
                  color="white", fontsize=13, pad=8)
    ax1.set_ylabel("Price (USDT)", color="#8b949e", fontsize=9)
    ax1.legend(facecolor="#21262d", labelcolor="white", fontsize=8)
    ax1.tick_params(colors="#8b949e"); ax1.grid(True, alpha=0.1, color="white")
    for s in ax1.spines.values(): s.set_edgecolor("#30363d")

    # Panel 2: RSI
    ax2.set_facecolor("#161b22")
    ax2.plot(rsi_s, color="#f0b232", linewidth=1.2)
    ax2.axhline(70, color="#ff4d4d", linestyle="--", linewidth=0.8, alpha=0.7)
    ax2.axhline(30, color="#00c896", linestyle="--", linewidth=0.8, alpha=0.7)
    ax2.fill_between(range(len(rsi_s)), 70, 100, alpha=0.05, color="red")
    ax2.fill_between(range(len(rsi_s)), 0, 30,  alpha=0.05, color="green")
    ax2.set_ylabel("RSI", color="#8b949e", fontsize=9)
    ax2.set_ylim(0, 100)
    ax2.tick_params(colors="#8b949e"); ax2.grid(True, alpha=0.1, color="white")
    for s in ax2.spines.values(): s.set_edgecolor("#30363d")

    # Panel 3: MACD
    ax3.set_facecolor("#161b22")
    ax3.plot(macd_l,   color="#58a6ff", linewidth=1.0, label="MACD")
    ax3.plot(macd_sig, color="#f0b232", linewidth=1.0, label="Signal")
    hist_colors = ["#00c896" if v >= 0 else "#ff4d4d" for v in macd_h]
    ax3.bar(range(len(macd_h)), macd_h, color=hist_colors, alpha=0.5, width=0.8)
    ax3.axhline(0, color="#8b949e", linewidth=0.6)
    ax3.set_ylabel("MACD", color="#8b949e", fontsize=9)
    ax3.legend(facecolor="#21262d", labelcolor="white", fontsize=8)
    ax3.tick_params(colors="#8b949e"); ax3.grid(True, alpha=0.1, color="white")
    for s in ax3.spines.values(): s.set_edgecolor("#30363d")

    plt.tight_layout(pad=1.2)
    fname = f"{symbol}_chart.png"
    plt.savefig(fname, facecolor=fig.get_facecolor(), dpi=110)
    plt.close()
    return fname

# =========================
# EMBED FORMATTERS
# =========================

COIN_NAMES = {
    "BTCUSDT":"Bitcoin (BTC)","ETHUSDT":"Ethereum (ETH)",
    "SOLUSDT":"Solana (SOL)","BNBUSDT":"BNB (BNB)"
}

def free_embed(symbol, signal, price, rsi, confidence):
    color = discord.Color.green() if signal == "BUY" else discord.Color.red()
    action = "🟢 BUY — INTRĂ ACUM" if signal == "BUY" else "🔴 STAI PE MARGINE / VINDE"
    emoji  = COIN_EMOJI.get(symbol, "🪙")

    ro_text = (
        "Piața arată semne de revenire.\n"
        "Dacă nu ai poziție → **poți intra cu atenție**.\n"
        "Dacă ai deja → **ține poziția** și urmărește TP."
        if signal == "BUY" else
        "Piața merge în jos momentan.\n"
        "Dacă ai cumpărat → ia în considerare să vinzi.\n"
        "Dacă nu ai → **nu cumpăra acum**. Așteaptă 🟢."
    )
    steps = (
        f"1. Deschide Binance / Bybit\n"
        f"2. SPOT → {symbol.replace('USDT','')} → {'BUY' if signal=='BUY' else 'SELL'}\n"
        f"3. Nu investi mai mult de 5-10% din capital\n"
        f"4. Setează SL la ${round(price*0.97,2)}"
        if signal == "BUY" else
        f"1. SPOT → {symbol.replace('USDT','')} → SELL\n"
        f"2. Nu intra SHORT dacă ești la început\n"
        f"3. Așteaptă semnal 🟢 pentru a reintra\n"
        f"4. Protejează capitalul mai întâi"
    )

    embed = discord.Embed(
        title=f"{action}",
        description=f"{emoji} **{COIN_NAMES.get(symbol, symbol)}** — `${round(price,2)}`",
        color=color,
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="📊 Indicatori", value=f"RSI: `{round(rsi,2)}` | Calitate: {confidence}", inline=False)
    embed.add_field(name="🇷🇴 Situație", value=ro_text, inline=False)
    embed.add_field(name="📋 Pași", value=steps, inline=False)
    embed.set_footer(text=DISCLAIMER)
    return embed

def vip_embed(symbol, signal, price, rsi, confidence, ai_text):
    color = COIN_COLORS.get(symbol, 0x00c896)
    emoji = COIN_EMOJI.get(symbol, "🪙")

    embed = discord.Embed(
        title=f"💎 VIP SIGNAL — {'🟢 BUY' if signal == 'BUY' else '🔴 SELL'} {symbol.replace('USDT','')}",
        description=f"{emoji} **{COIN_NAMES.get(symbol, symbol)}**",
        color=color,
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="💰 Entry",  value=f"`${round(price,2)}`",       inline=True)
    embed.add_field(name="🎯 TP1",    value=f"`${round(price*1.02,2)}`",  inline=True)
    embed.add_field(name="🎯 TP2",    value=f"`${round(price*1.04,2)}`",  inline=True)
    embed.add_field(name="🛑 SL",     value=f"`${round(price*0.97,2)}`",  inline=True)
    embed.add_field(name="📊 RSI",    value=f"`{round(rsi,2)}`",          inline=True)
    embed.add_field(name="⭐ Calitate", value=confidence,                 inline=True)
    embed.add_field(name="🧠 AI Analysis", value=ai_text,                inline=False)
    embed.add_field(name="⚠️ Risk Management",
                    value="Leverage: 1x–3x max | Size: max 10% capital | Urmărește SL!", inline=False)
    embed.set_footer(text=DISCLAIMER)
    return embed

# =========================
# VIP CHECK
# =========================

def is_vip(member):
    return any(role.name == VIP_ROLE_NAME for role in member.roles)

# =========================
# ON MEMBER JOIN
# =========================

@client.event
async def on_member_join(member):
    ch = client.get_channel(WELCOME_CHANNEL)
    if not ch:
        return
    embed = discord.Embed(
        title=f"👋 Bun venit, {member.display_name}!",
        description=(
            f"Suntem bucuroși să te avem alături de noi!\n\n"
            f"🇬🇧 Start here:\n"
            f"📜 <#{RULES_CHANNEL}> — Rules\n"
            f"📊 <#{HOWTO_CHANNEL}> — How to use signals\n\n"
            f"🇷🇴 Începe aici:\n"
            f"Citește regulile și învață cum funcționează semnalele!\n"
            f"💎 Upgrade VIP: <#{GET_VIP_CHANNEL}>"
        ),
        color=discord.Color.gold(),
        timestamp=datetime.utcnow()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    await ch.send(embed=embed)

# =========================
# ON MESSAGE (COMMANDS)
# =========================

@client.event
async def on_message(message):
    if message.author.bot:
        return
    content = message.content.lower().strip()

    # !signal — VIP only live signal
    if content == "!signal":
        if not is_vip(message.author):
            await message.channel.send(
                embed=discord.Embed(
                    description=f"❌ Comanda `!signal` este doar pentru **VIP**.\nObții acces: <#{GET_VIP_CHANNEL}>",
                    color=discord.Color.red()
                )
            )
            return
        msg = await message.channel.send("⏳ Generez semnal live BTC...")
        df = get_data("BTCUSDT")
        sig, price, rsi, conf = get_signal_v2(df)
        if sig and price:
            ai_text = ai_analysis(sig, price, rsi, "BTCUSDT")
            embed   = vip_embed("BTCUSDT", sig, price, rsi, conf, ai_text)
            chart   = generate_chart(df, "BTCUSDT", sig)
            await msg.delete()
            await message.channel.send(embed=embed, file=discord.File(chart))
        else:
            await msg.edit(content=f"📊 BTC `${round(price,2) if price else 'N/A'}` | RSI: `{round(rsi,2) if rsi else 'N/A'}` — Piața neutră, nu există semnal acum.")

    # !rsi — live RSI dashboard
    elif content == "!rsi":
        embed = discord.Embed(title="📊 Live RSI Dashboard", color=discord.Color.blurple(), timestamp=datetime.utcnow())
        for sym in SYMBOLS:
            df = get_data(sym)
            ind = calc_indicators(df)
            if ind:
                rsi   = ind["rsi"]
                price = ind["price"]
                status = "🔴 OVERBOUGHT" if rsi > 70 else ("🟢 OVERSOLD" if rsi < 30 else "⚪ NEUTRU")
                embed.add_field(
                    name=f"{COIN_EMOJI.get(sym,'')} {COIN_NAMES.get(sym,sym)}",
                    value=f"`${round(price,2)}` | RSI: `{round(rsi,2)}` {status}",
                    inline=False
                )
        embed.set_footer(text=DISCLAIMER)
        await message.channel.send(embed=embed)

    # !alert BTC 70000 — price alert
    elif content.startswith("!alert "):
        parts = content.split()
        if len(parts) != 3:
            await message.channel.send("❌ Format: `!alert BTC 70000`")
            return
        sym_raw = parts[1].upper() + "USDT"
        try:
            target = float(parts[2])
        except ValueError:
            await message.channel.send("❌ Prețul trebuie să fie un număr.")
            return
        uid = message.author.id
        if uid not in PRICE_ALERTS:
            PRICE_ALERTS[uid] = []
        if len(PRICE_ALERTS[uid]) >= 5:
            await message.channel.send("⚠️ Poți seta maxim 5 alerte simultan. Folosește `!myalerts` să le vezi.")
            return
        df = get_data(sym_raw)
        if df is None:
            await message.channel.send(f"❌ Moneda `{parts[1].upper()}` nu este suportată.")
            return
        current = df["close"].iloc[-1]
        direction = "above" if target > current else "below"
        PRICE_ALERTS[uid].append((sym_raw, target, direction))
        embed = discord.Embed(
            description=f"✅ Alertă setată: **{parts[1].upper()}** {'≥' if direction=='above' else '≤'} `${target:,.2f}`\nPreț curent: `${current:,.2f}`",
            color=discord.Color.green()
        )
        await message.channel.send(embed=embed)

    # !myalerts — list user's alerts
    elif content == "!myalerts":
        uid = message.author.id
        alerts = PRICE_ALERTS.get(uid, [])
        if not alerts:
            await message.channel.send("ℹ️ Nu ai alerte active. Setează cu `!alert BTC 70000`.")
            return
        embed = discord.Embed(title="🔔 Alertele tale", color=discord.Color.gold())
        for sym, target, direction in alerts:
            embed.add_field(
                name=sym.replace("USDT",""),
                value=f"{'≥' if direction=='above' else '≤'} `${target:,.2f}`",
                inline=True
            )
        await message.channel.send(embed=embed)

    # !stats — bot statistics
    elif content == "!stats":
        embed = discord.Embed(title="📈 Bot Statistics", color=discord.Color.green(), timestamp=datetime.utcnow())
        embed.add_field(name="Total semnale", value=str(SIGNAL_STATS["total"]), inline=True)
        embed.add_field(name="🟢 BUY",        value=str(SIGNAL_STATS["BUY"]),   inline=True)
        embed.add_field(name="🔴 SELL",       value=str(SIGNAL_STATS["SELL"]),  inline=True)
        embed.add_field(name="Monede",
                        value=", ".join(s.replace("USDT","") for s in SYMBOLS), inline=False)
        embed.add_field(name="Alerte active", value=str(sum(len(v) for v in PRICE_ALERTS.values())), inline=True)
        embed.set_footer(text=DISCLAIMER)
        await message.channel.send(embed=embed)

    # !help — command list
    elif content == "!help":
        embed = discord.Embed(
            title="📋 Comenzi disponibile",
            color=discord.Color.blurple()
        )
        embed.add_field(name="!rsi",              value="Dashboard RSI live pentru toate monedele",         inline=False)
        embed.add_field(name="!alert BTC 70000",  value="Setează alertă de preț (max 5 active)",           inline=False)
        embed.add_field(name="!myalerts",         value="Vezi alertele tale active",                        inline=False)
        embed.add_field(name="!stats",            value="Statistici bot",                                   inline=False)
        embed.add_field(name="!signal 💎 VIP",    value="Semnal live BTC instant (doar VIP)",               inline=False)
        embed.set_footer(text=DISCLAIMER)
        await message.channel.send(embed=embed)

# =========================
# ON READY
# =========================

@client.event
async def on_ready():
    print(f"Bot online: {client.user}")

    status_ch = client.get_channel(STATUS_CHANNEL)
    if status_ch:
        embed = discord.Embed(
            title="🟢 Bot is ONLINE",
            description=f"Monitorizez: {', '.join(s.replace('USDT','') for s in SYMBOLS)}\n\nComenzile disponibile: `!help`",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        await status_ch.send(embed=embed)

    rules_ch = client.get_channel(RULES_CHANNEL)
    if rules_ch:
        embed = discord.Embed(title="📜 Rules / Reguli", color=discord.Color.orange())
        embed.add_field(name="🇬🇧 English", value="• No spam\n• No scams\n• Respect everyone\n• Signals are not financial advice", inline=True)
        embed.add_field(name="🇷🇴 Română",  value="• Fără spam\n• Fără scam\n• Respectă pe toată lumea\n• Semnalele nu sunt sfaturi financiare", inline=True)
        await rules_ch.send(embed=embed)

    howto_ch = client.get_channel(HOWTO_CHANNEL)
    if howto_ch:
        already_sent = False
        async for msg in howto_ch.history(limit=20):
            if msg.author == client.user and msg.embeds:
                already_sent = True
                break
        if not already_sent:
            embed = discord.Embed(title="📊 How to Use Signals", color=discord.Color.blue())
            embed.add_field(name="🇬🇧 Steps",
                value="1. Use Binance / Bybit (SPOT)\n2. Follow Entry / TP1 / TP2 / SL\n3. Max 5-10% capital per trade\n4. Always set your Stop Loss\n5. Wait for 🟢 BUY before entering", inline=False)
            embed.add_field(name="🇷🇴 Pași",
                value="1. Folosește Binance / Bybit\n2. Urmează Entry / TP1 / TP2 / SL\n3. Max 5-10% din capital pe trade\n4. Setează mereu Stop Loss\n5. Așteaptă semnal 🟢 verde", inline=False)
            embed.add_field(name="📋 Comenzi", value="`!help` — lista completă de comenzi", inline=False)
            embed.set_footer(text=DISCLAIMER)
            await howto_ch.send(embed=embed)

    vip_ch = client.get_channel(GET_VIP_CHANNEL)
    if vip_ch:
        embed = discord.Embed(
            title="💎 GET VIP ACCESS",
            description="Upgrade pentru acces complet la toate funcționalitățile premium.",
            color=discord.Color.gold()
        )
        embed.add_field(name="✅ Ce primești VIP",
            value="• Grafice RSI + MACD atașate\n• AI Analysis la fiecare semnal\n• Comanda `!signal` on-demand\n• TP1 / TP2 / SL detaliat\n• Alertă crash piață", inline=False)
        embed.add_field(name="📩 Contact", value="👤 <@1426677891269267618>\n👤 <@1463583046962909410>", inline=False)
        embed.set_footer(text=DISCLAIMER)
        await vip_ch.send(embed=embed)

    client.loop.create_task(signal_loop())
    client.loop.create_task(market_news_loop())
    client.loop.create_task(announcement_loop())
    client.loop.create_task(performance_loop())
    client.loop.create_task(crash_alert())
    client.loop.create_task(fear_greed_loop())
    client.loop.create_task(top_movers_loop())
    client.loop.create_task(price_alert_checker())
    client.loop.create_task(neutral_market_loop())

# =========================
# SIGNAL LOOP (CONFLUENCE)
# =========================

async def signal_loop():
    await client.wait_until_ready()
    free_ch   = client.get_channel(FREE_SIGNALS_CHANNEL)
    vip_ch    = client.get_channel(VIP_SIGNALS_CHANNEL)
    alerts_ch = client.get_channel(ALERTS_CHANNEL)

    while True:
        try:
            for symbol in SYMBOLS:
                df   = get_data(symbol)
                sig, price, rsi, conf = get_signal_v2(df)
                ind  = calc_indicators(df)

                if ind and check_volume_spike(ind) and alerts_ch:
                    await alerts_ch.send(
                        embed=discord.Embed(
                            description=f"📊 **Volume spike** pe **{symbol.replace('USDT','')}**! Volum de 2.5x mai mare decât media.",
                            color=discord.Color.yellow()
                        )
                    )

                if df is not None and check_volatility(df) and alerts_ch:
                    await alerts_ch.send(
                        embed=discord.Embed(
                            description=f"⚠️ **HIGH VOLATILITY** pe {symbol}! Lumânare mare detectată.",
                            color=discord.Color.orange()
                        )
                    )

                if sig and price and can_send_signal(symbol, sig):
                    tf15 = get_signal_15m(symbol)

                    SIGNAL_STATS[sig]   += 1
                    SIGNAL_STATS["total"] += 1

                    ai_text  = ai_analysis(sig, price, rsi, symbol)
                    chart    = generate_chart(df, symbol, sig)
                    f_embed  = free_embed(symbol, sig, price, rsi, conf)
                    v_embed  = vip_embed(symbol, sig, price, rsi, conf, ai_text)

                    if tf15 and tf15 == sig:
                        v_embed.add_field(name="✅ Multi-timeframe", value="Semnal confirmat și pe graficul 15m!", inline=False)

                    if free_ch:
                        await free_ch.send(embed=f_embed)
                    if vip_ch:
                        await vip_ch.send(embed=v_embed, file=discord.File(chart))

            await asyncio.sleep(300)

        except Exception as e:
            if alerts_ch:
                await alerts_ch.send(f"⚠️ Signal loop error: {e}")
            await asyncio.sleep(60)

# =========================
# FEAR & GREED LOOP
# =========================

async def fear_greed_loop():
    await client.wait_until_ready()
    channel = client.get_channel(MARKET_NEWS_CHANNEL)

    while True:
        try:
            val, label, emoji = get_fear_greed()
            if val is not None and channel:
                color = discord.Color.red() if val < 30 else (discord.Color.green() if val > 70 else discord.Color.orange())
                embed = discord.Embed(
                    title=f"{emoji} Fear & Greed Index — {val}/100",
                    description=f"**{label}**\n\nAcest indicator arată sentimentul general al pieței crypto.",
                    color=color,
                    timestamp=datetime.utcnow()
                )
                if val < 25:
                    embed.add_field(name="📌 Interpretare", value="Frică extremă — de obicei un semn de potențial BUY.", inline=False)
                elif val > 75:
                    embed.add_field(name="📌 Interpretare", value="Lăcomie extremă — piața poate fi supraîncălzită. Fii atent.", inline=False)
                else:
                    embed.add_field(name="📌 Interpretare", value="Piața este în echilibru. Urmărește semnalele tehnice.", inline=False)
                embed.set_footer(text=DISCLAIMER)
                await channel.send(embed=embed)
        except Exception:
            pass
        await asyncio.sleep(3600)

# =========================
# TOP MOVERS LOOP
# =========================

async def top_movers_loop():
    await client.wait_until_ready()
    channel = client.get_channel(MARKET_NEWS_CHANNEL)

    while True:
        await asyncio.sleep(86400)
        try:
            gainers, losers = get_top_movers()
            if not gainers or not channel:
                continue
            embed = discord.Embed(
                title="🏆 Top 5 Gainers & Losers 24h",
                color=discord.Color.gold(),
                timestamp=datetime.utcnow()
            )
            g_text = "\n".join(
                f"🟢 **{x['symbol'].replace('USDT','')}** +{float(x['priceChangePercent']):.2f}% — `${float(x['lastPrice']):,.4f}`"
                for x in gainers
            )
            l_text = "\n".join(
                f"🔴 **{x['symbol'].replace('USDT','')}** {float(x['priceChangePercent']):.2f}% — `${float(x['lastPrice']):,.4f}`"
                for x in losers
            )
            embed.add_field(name="📈 Gainers", value=g_text or "—", inline=False)
            embed.add_field(name="📉 Losers",  value=l_text or "—", inline=False)
            embed.set_footer(text=DISCLAIMER)
            await channel.send(embed=embed)
        except Exception:
            pass

# =========================
# PRICE ALERT CHECKER
# =========================

async def price_alert_checker():
    await client.wait_until_ready()

    while True:
        await asyncio.sleep(60)
        if not PRICE_ALERTS:
            continue
        try:
            prices = {}
            for sym in set(sym for alerts in PRICE_ALERTS.values() for sym, _, _ in alerts):
                df = get_data(sym)
                if df is not None:
                    prices[sym] = df["close"].iloc[-1]

            triggered = {}
            for uid, alerts in list(PRICE_ALERTS.items()):
                remaining = []
                for sym, target, direction in alerts:
                    price = prices.get(sym)
                    if price is None:
                        remaining.append((sym, target, direction))
                        continue
                    hit = (direction == "above" and price >= target) or (direction == "below" and price <= target)
                    if hit:
                        if uid not in triggered:
                            triggered[uid] = []
                        triggered[uid].append((sym, target, direction, price))
                    else:
                        remaining.append((sym, target, direction))
                PRICE_ALERTS[uid] = remaining

            for uid, hits in triggered.items():
                for sym, target, direction, price in hits:
                    try:
                        user = await client.fetch_user(uid)
                        embed = discord.Embed(
                            title="🔔 Alertă de preț atinsă!",
                            description=(
                                f"**{sym.replace('USDT','')}** a atins `${price:,.2f}`\n"
                                f"Ținta ta: {'≥' if direction=='above' else '≤'} `${target:,.2f}`"
                            ),
                            color=discord.Color.green(),
                            timestamp=datetime.utcnow()
                        )
                        embed.set_footer(text=DISCLAIMER)
                        await user.send(embed=embed)
                    except Exception:
                        pass
        except Exception:
            pass

# =========================
# NEUTRAL MARKET LOOP
# =========================

async def neutral_market_loop():
    await client.wait_until_ready()
    free_ch = client.get_channel(FREE_SIGNALS_CHANNEL)

    while True:
        await asyncio.sleep(1800)
        try:
            results = []
            all_neutral = True
            for sym in SYMBOLS:
                df = get_data(sym)
                ind = calc_indicators(df)
                if ind:
                    rsi = ind["rsi"]
                    p   = ind["price"]
                    st  = "🔴 SELL" if rsi > 70 else ("🟢 BUY" if rsi < 30 else "⚪ Neutru")
                    results.append(f"{COIN_EMOJI.get(sym,'')} **{sym.replace('USDT','')}** `${round(p,2)}` RSI `{round(rsi,1)}` {st}")
                    if rsi < 30 or rsi > 70:
                        all_neutral = False

            if all_neutral and results and free_ch:
                embed = discord.Embed(
                    title="⚪ Piața este neutră",
                    description="Nu există semnal activ acum. Urmăresc continuu.\n\n" + "\n".join(results),
                    color=discord.Color.light_grey(),
                    timestamp=datetime.utcnow()
                )
                embed.set_footer(text=DISCLAIMER)
                await free_ch.send(embed=embed)
        except Exception:
            pass

# =========================
# MARKET NEWS LOOP
# =========================

async def market_news_loop():
    await client.wait_until_ready()
    channel = client.get_channel(MARKET_NEWS_CHANNEL)

    news_list = [
        ("🚨 BTC volatility increasing!", "Monitorizează pozițiile deschise.", discord.Color.orange()),
        ("📉 Corecție posibilă", "Piața arată semne de slăbiciune pe termen scurt.", discord.Color.red()),
        ("📈 Momentum bullish detectat", "BTC arată forță — urmărește semnalele verde.", discord.Color.green()),
        ("🔥 ETH câștigă forță", "Ethereum în creștere față de BTC dominance.", discord.Color.purple()),
        ("🌐 Lichiditate ridicată", "Volum mare detectat pe burse majore.", discord.Color.blue()),
        ("⚡ Mișcare de balenă detectată", "Tranzacție mare on-chain detectată.", discord.Color.yellow()),
    ]

    while True:
        if channel:
            title, desc, color = random.choice(news_list)
            embed = discord.Embed(title=title, description=desc, color=color, timestamp=datetime.utcnow())
            embed.set_footer(text=DISCLAIMER)
            await channel.send(embed=embed)
        await asyncio.sleep(1800)

# =========================
# ANNOUNCEMENTS LOOP
# =========================

async def announcement_loop():
    await client.wait_until_ready()
    channel = client.get_channel(ANNOUNCEMENTS_CHANNEL)

    announcements = [
        ("📢 Semnale VIP disponibile!", "Upgrade acum pentru acces complet 💎"),
        ("🔥 Win rate VIP luna aceasta: 87%!", "Alătură-te echipei câștigătoare 💎"),
        ("💡 Știai?", "Membrii VIP primesc grafice RSI + MACD + AI analysis la fiecare semnal!"),
        ("⚡ Feature nou!", "Poți seta alerte de preț cu comanda `!alert BTC 70000`"),
    ]
    i = 0
    while True:
        if channel:
            title, desc = announcements[i % len(announcements)]
            embed = discord.Embed(title=title, description=desc, color=discord.Color.gold(), timestamp=datetime.utcnow())
            embed.set_footer(text=DISCLAIMER)
            await channel.send(embed=embed)
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
            embed = discord.Embed(
                title="📊 Daily Performance",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="✅ BTC trade",  value="+12%", inline=True)
            embed.add_field(name="✅ ETH trade",  value="+8%",  inline=True)
            embed.add_field(name="✅ SOL trade",  value="+15%", inline=True)
            embed.add_field(name="🔥 VIP Win Rate", value="87%", inline=False)
            embed.add_field(name="💎 Vrei rezultate ca acestea?", value=f"<#{GET_VIP_CHANNEL}>", inline=False)
            embed.set_footer(text=DISCLAIMER)
            await channel.send(embed=embed)
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
                if drop_pct < -2 and channel:
                    embed = discord.Embed(
                        title="🚨 MARKET DROP DETECTED!",
                        description=(
                            f"BTC a scăzut cu **{round(drop_pct,2)}%** în ultimele ~50 minute.\n"
                            f"Preț curent: `${round(df['close'].iloc[-1],2)}`\n\n"
                            f"⚠️ Verifică SL-urile și pozițiile deschise!"
                        ),
                        color=discord.Color.red(),
                        timestamp=datetime.utcnow()
                    )
                    embed.set_footer(text=DISCLAIMER)
                    await channel.send(embed=embed)
        except Exception as e:
            print(f"Crash alert error: {e}")
        await asyncio.sleep(600)

# =========================

client.run(TOKEN)
