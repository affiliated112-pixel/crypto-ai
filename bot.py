import discord
from discord import app_commands
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

# AI API Keys (toate gratuite)
GROQ_API_KEY        = os.environ.get("GROQ_API_KEY", "")
COHERE_API_KEY      = os.environ.get("COHERE_API_KEY", "")
OPENROUTER_API_KEY  = os.environ.get("OPENROUTER_API_KEY", "")

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
DISCLAIMER_EN = "Crypto Signals Bot | Not financial advice. Invest responsibly."
DISCLAIMER_RO = "Crypto Signals Bot | Nu e sfat financiar. Investește responsabil."

LAST_SIGNAL    = {}
SIGNAL_STATS   = {"BUY": 0, "SELL": 0, "total": 0}
PRICE_ALERTS   = {}
SIGNAL_HISTORY = []   # {symbol, signal, price, rsi, confidence, timestamp}

SCAM_KEYWORDS = [
    "dm me", "free crypto", "100x guaranteed", "dm for profit",
    "recovery service", "tripling funds", "click here", "t.me/",
    "investment platform", "double your", "recuperare fonduri",
    "trimiteti", "castig garantat", "dm pentru profit"
]

COIN_COLORS = {
    "BTCUSDT": 0xF7931A,
    "ETHUSDT": 0x627EEA,
    "SOLUSDT": 0x9945FF,
    "BNBUSDT": 0xF0B90B,
}
COIN_EMOJI = {
    "BTCUSDT": "₿", "ETHUSDT": "Ξ", "SOLUSDT": "◎", "BNBUSDT": "⬡",
}
COIN_NAMES_EN = {
    "BTCUSDT": "Bitcoin (BTC)", "ETHUSDT": "Ethereum (ETH)",
    "SOLUSDT": "Solana (SOL)",  "BNBUSDT": "BNB (BNB)",
}
COIN_NAMES_RO = {
    "BTCUSDT": "Bitcoin (BTC)", "ETHUSDT": "Ethereum (ETH)",
    "SOLUSDT": "Solana (SOL)",  "BNBUSDT": "BNB (BNB)",
}
COIN_LOGOS = {
    "BTCUSDT": "https://assets.coingecko.com/coins/images/1/small/bitcoin.png",
    "ETHUSDT": "https://assets.coingecko.com/coins/images/279/small/ethereum.png",
    "SOLUSDT": "https://assets.coingecko.com/coins/images/4128/small/solana.png",
    "BNBUSDT": "https://assets.coingecko.com/coins/images/825/small/bnb-icon2_2x.png",
}
BOT_ICON = "https://assets.coingecko.com/coins/images/1/small/bitcoin.png"
SEP = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

def rsi_bar(rsi: float) -> str:
    filled = max(0, min(20, int(rsi / 5)))
    bar = "█" * filled + "░" * (20 - filled)
    zone = "🔴 OB" if rsi > 70 else ("🟢 OS" if rsi < 30 else "🟡 Neutral")
    return f"`{bar}` **{round(rsi, 1)}** {zone}"

def conf_stars(confidence: str) -> str:
    mapping = {"HIGH": "★★★★★", "MEDIUM": "★★★☆☆", "LOW": "★★☆☆☆"}
    stars = mapping.get(confidence.upper(), "★★★☆☆")
    color = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(confidence.upper(), "⚪")
    return f"{color} {stars}  `{confidence}`"

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

client = discord.Client(intents=intents)
tree   = app_commands.CommandTree(client)

# =========================
# MULTI-API DATA FETCH
# =========================

def get_data_binance(symbol, interval="5m", limit=150):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
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
        url  = f"https://api.coingecko.com/api/v3/coins/{coin}/market_chart?vs_currency=usd&days=1&interval=5minutely"
        data = requests.get(url, timeout=10).json()
        prices = data.get("prices", [])
        if len(prices) < 20:
            return None
        df = pd.DataFrame(prices, columns=["time","close"])
        df["high"] = df["close"]; df["low"] = df["close"]
        df["open"] = df["close"]; df["volume"] = 0.0
        return df
    except Exception:
        return None

def get_data(symbol, interval="5m"):
    df = get_data_binance(symbol, interval)
    if df is not None and len(df) >= 30:
        return df
    return get_data_coingecko(symbol)

def get_price_info(symbol):
    """Returns 24h ticker info: price, change%, high, low, volume."""
    try:
        url  = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
        data = requests.get(url, timeout=8).json()
        return {
            "price":    float(data["lastPrice"]),
            "change":   float(data["priceChangePercent"]),
            "high":     float(data["highPrice"]),
            "low":      float(data["lowPrice"]),
            "volume":   float(data["quoteVolume"]),
        }
    except Exception:
        return None

# =========================
# TECHNICAL ANALYSIS
# =========================

def calc_indicators(df):
    if df is None or len(df) < 35:
        return None
    close = df["close"]
    rsi       = RSIIndicator(close=close, window=14).rsi().iloc[-1]
    macd_obj  = MACD(close=close)
    macd_hist = macd_obj.macd_diff().iloc[-1]
    ema50     = EMAIndicator(close=close, window=50).ema_indicator().iloc[-1]
    price     = close.iloc[-1]
    vol_avg   = df["volume"].iloc[-20:].mean() if "volume" in df.columns else 0
    vol_now   = df["volume"].iloc[-1]          if "volume" in df.columns else 0
    return {"rsi": rsi, "macd_hist": macd_hist, "ema50": ema50,
            "price": price, "vol_avg": vol_avg, "vol_now": vol_now}

def get_signal_v2(df):
    ind = calc_indicators(df)
    if ind is None:
        return None, None, None, None
    rsi, macd_hist, price, ema50 = ind["rsi"], ind["macd_hist"], ind["price"], ind["ema50"]
    buy_score  = sum([rsi < 35, macd_hist > 0, price > ema50 * 0.98])
    sell_score = sum([rsi > 65, macd_hist < 0, price < ema50 * 1.02])
    if buy_score >= 2:
        return "BUY",  price, rsi, ("🔥 HIGH" if buy_score == 3 else "⚡ MEDIUM")
    if sell_score >= 2:
        return "SELL", price, rsi, ("🔥 HIGH" if sell_score == 3 else "⚡ MEDIUM")
    return None, price, rsi, None

def get_signal_15m(symbol):
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
    return ind["vol_avg"] > 0 and ind["vol_now"] > ind["vol_avg"] * 2.5

def check_volatility(df):
    if df is None or len(df) < 2:
        return False
    return abs(df["close"].iloc[-1] - df["close"].iloc[-2]) > 200

def is_vip(member):
    return any(role.name == VIP_ROLE_NAME for role in member.roles)

# =========================
# AI ANALYSIS — 4 API-URI GRATUITE
# =========================

def ai_analysis_groq(signal, price, rsi, symbol):
    """Groq — llama3 gratuit, cel mai rapid."""
    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={
                "model": "llama3-8b-8192",
                "messages": [{"role": "user", "content":
                    f"In exactly 2 sentences, explain this crypto trade signal professionally: "
                    f"{signal} {symbol.replace('USDT','')} at ${price:.2f}, RSI={rsi:.1f}."
                }],
                "max_tokens": 120,
            },
            timeout=10
        ).json()
        return res["choices"][0]["message"]["content"].strip()
    except Exception:
        return None

def ai_analysis_cohere(signal, price, rsi, symbol):
    """Cohere — Command-R gratuit."""
    try:
        res = requests.post(
            "https://api.cohere.com/v1/chat",
            headers={"Authorization": f"Bearer {COHERE_API_KEY}",
                     "Content-Type": "application/json"},
            json={
                "model": "command-r",
                "message": (
                    f"In 2 concise sentences, explain this crypto signal professionally: "
                    f"{signal} {symbol.replace('USDT','')} at ${price:.2f}, RSI={rsi:.1f}."
                ),
                "max_tokens": 120,
            },
            timeout=10
        ).json()
        return res.get("text", "").strip()
    except Exception:
        return None

def ai_analysis_huggingface(signal, price, rsi, symbol):
    """HuggingFace Inference API — gratuit."""
    try:
        prompt = (
            f"Explain this crypto trade signal in 2 sentences: "
            f"{signal} {symbol.replace('USDT','')} at ${price:.2f}, RSI={rsi:.1f}."
        )
        res = requests.post(
            "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.1",
            headers={"Content-Type": "application/json"},
            json={"inputs": prompt, "parameters": {"max_new_tokens": 100}},
            timeout=12
        ).json()
        if isinstance(res, list) and res:
            text = res[0].get("generated_text", "")
            text = text.replace(prompt, "").strip()
            return text[:300] if text else None
        return None
    except Exception:
        return None

def ai_analysis_openrouter(signal, price, rsi, symbol):
    """OpenRouter — fallback plătit dacă ai cheie."""
    try:
        res = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={
                "model": "openai/gpt-3.5-turbo",
                "messages": [{"role": "user", "content":
                    f"In 2 sentences, explain professionally: {signal} "
                    f"{symbol.replace('USDT','')} at ${price:.2f}, RSI={rsi:.1f}."
                }]
            },
            timeout=10
        ).json()
        return res["choices"][0]["message"]["content"].strip()
    except Exception:
        return None

def ai_analysis_local(signal, price, rsi, symbol):
    """Fallback inteligent fără API."""
    coin = symbol.replace("USDT","")
    if signal == "BUY":
        strength = "extreme oversold" if rsi < 25 else "oversold"
        ro = f"RSI-ul la {rsi:.1f} indică piață {('extrem supravândută' if rsi < 25 else 'supravândută')} — probabilitate crescută de revenire."
        en = f"RSI at {rsi:.1f} indicates {strength} conditions — potential reversal upward expected."
    else:
        strength = "extreme overbought" if rsi > 75 else "overbought"
        ro = f"RSI-ul la {rsi:.1f} indică piață {('extrem supraevaluată' if rsi > 75 else 'supraevaluată')} — presiune de vânzare detectată."
        en = f"RSI at {rsi:.1f} indicates {strength} conditions — selling pressure detected."
    return f"🇬🇧 {en}\n🇷🇴 {ro}"

def ai_analysis(signal, price, rsi, symbol):
    """Încearcă API-urile în ordine — cel mai rapid primul."""
    if GROQ_API_KEY:
        result = ai_analysis_groq(signal, price, rsi, symbol)
        if result:
            return result
    if COHERE_API_KEY:
        result = ai_analysis_cohere(signal, price, rsi, symbol)
        if result:
            return result
    if OPENROUTER_API_KEY:
        result = ai_analysis_openrouter(signal, price, rsi, symbol)
        if result:
            return result
    result = ai_analysis_huggingface(signal, price, rsi, symbol)
    if result:
        return result
    return ai_analysis_local(signal, price, rsi, symbol)

# =========================
# CHART GENERATION (3 PANELS, DARK PRO)
# =========================

def generate_chart(df, symbol, signal=None):
    fig, (ax1, ax2, ax3) = plt.subplots(
        3, 1, figsize=(12, 9),
        gridspec_kw={"height_ratios": [3, 1, 1]}
    )
    fig.patch.set_facecolor("#0d1117")
    close   = df["close"]
    ema50   = EMAIndicator(close=close, window=50).ema_indicator()
    rsi_s   = RSIIndicator(close=close, window=14).rsi()
    macd_o  = MACD(close=close)
    macd_l  = macd_o.macd()
    macd_sg = macd_o.macd_signal()
    macd_h  = macd_o.macd_diff()
    color   = "#00c896" if signal == "BUY" else ("#ff4d4d" if signal == "SELL" else "#58a6ff")

    for ax in (ax1, ax2, ax3):
        ax.set_facecolor("#161b22")
        ax.tick_params(colors="#8b949e")
        ax.grid(True, alpha=0.1, color="white")
        for s in ax.spines.values():
            s.set_edgecolor("#30363d")

    ax1.plot(close, color=color,    linewidth=1.5, label="Price", zorder=3)
    ax1.plot(ema50, color="#f0b232", linewidth=1.0, linestyle="--", label="EMA50", alpha=0.8)
    ax1.set_title(
        f"{symbol}  |  {'🟢 BUY' if signal=='BUY' else ('🔴 SELL' if signal=='SELL' else '⚪ Monitor')}  |  {datetime.utcnow().strftime('%d %b %Y  %H:%M UTC')}",
        color="white", fontsize=12, pad=8
    )
    ax1.set_ylabel("Price (USDT)", color="#8b949e", fontsize=9)
    ax1.legend(facecolor="#21262d", labelcolor="white", fontsize=8)

    ax2.plot(rsi_s, color="#f0b232", linewidth=1.2)
    ax2.axhline(70, color="#ff4d4d", linestyle="--", linewidth=0.8, alpha=0.7)
    ax2.axhline(30, color="#00c896", linestyle="--", linewidth=0.8, alpha=0.7)
    ax2.fill_between(range(len(rsi_s)), 70, 100, alpha=0.06, color="red")
    ax2.fill_between(range(len(rsi_s)), 0,  30,  alpha=0.06, color="green")
    ax2.set_ylabel("RSI", color="#8b949e", fontsize=9)
    ax2.set_ylim(0, 100)

    hist_colors = ["#00c896" if v >= 0 else "#ff4d4d" for v in macd_h]
    ax3.plot(macd_l,  color="#58a6ff", linewidth=1.0, label="MACD")
    ax3.plot(macd_sg, color="#f0b232", linewidth=1.0, label="Signal")
    ax3.bar(range(len(macd_h)), macd_h, color=hist_colors, alpha=0.5, width=0.8)
    ax3.axhline(0, color="#8b949e", linewidth=0.6)
    ax3.set_ylabel("MACD", color="#8b949e", fontsize=9)
    ax3.legend(facecolor="#21262d", labelcolor="white", fontsize=8)

    plt.tight_layout(pad=1.2)
    fname = f"{symbol}_chart.png"
    plt.savefig(fname, facecolor=fig.get_facecolor(), dpi=110)
    plt.close()
    return fname

# =========================
# EMBED BUILDERS
# =========================

def build_free_embed(symbol, signal, price, rsi, confidence):
    coin   = symbol.replace("USDT", "")
    emoji  = COIN_EMOJI.get(symbol, "🪙")
    logo   = COIN_LOGOS.get(symbol)
    sl     = round(price * 0.97, 2)
    tp1    = round(price * 1.02, 2)
    is_buy = signal == "BUY"

    color  = 0x00c853 if is_buy else 0xff1744
    banner = "🟢  B U Y   S I G N A L" if is_buy else "🔴  S E L L   S I G N A L"
    banner_ro = "🟢  S E M N A L   B U Y" if is_buy else "🔴  S E M N A L   S E L L"
    action_en = ("📥 **ENTER NOW** — Signs of reversal detected.\n"
                 f"▸ No position? Enter carefully with **max 5–10% capital**.\n"
                 f"▸ Already in? **Hold** and watch TP1.") if is_buy else \
                ("📤 **STAY OUT / SELL** — Bearish momentum active.\n"
                 f"▸ Holding? Consider **taking profit or cutting losses**.\n"
                 f"▸ No position? **Wait for 🟢 BUY signal**.")
    action_ro = ("📥 **INTRĂ ACUM** — Semne de revenire detectate.\n"
                 f"▸ Fără poziție? Intră cu atenție, **max 5–10% capital**.\n"
                 f"▸ Ai deja? **Ține poziția**, urmărește TP1.") if is_buy else \
                ("📤 **STAI PE MARGINE / VINDE** — Momentum bearish activ.\n"
                 f"▸ Ai cumpărat? Consideră **să vinzi / protejezi capitalul**.\n"
                 f"▸ Fără poziție? **Așteaptă semnalul 🟢 BUY**.")
    steps_en = (f"① Open **Binance / Bybit**\n"
                f"② SPOT → `{coin}` → **BUY**\n"
                f"③ Max **5–10%** of portfolio\n"
                f"④ Set Stop-Loss at `${sl:,}`") if is_buy else \
               (f"① SPOT → `{coin}` → **SELL** (if holding)\n"
                f"② Avoid SHORTING if beginner\n"
                f"③ Wait for next 🟢 BUY signal\n"
                f"④ **Capital protection first**")
    steps_ro = (f"① Deschide **Binance / Bybit**\n"
                f"② SPOT → `{coin}` → **BUY**\n"
                f"③ Max **5–10%** din portofoliu\n"
                f"④ Stop-Loss la `${sl:,}`") if is_buy else \
               (f"① SPOT → `{coin}` → **SELL** (dacă ai)\n"
                f"② Nu intra SHORT dacă ești la început\n"
                f"③ Așteaptă semnalul 🟢 BUY\n"
                f"④ **Protejează capitalul primul**")

    embed = discord.Embed(
        title=f"{banner}\n{banner_ro}",
        description=(
            f"{emoji} **{COIN_NAMES_EN.get(symbol, symbol)}**\n"
            f"{SEP}\n"
            f"💰 **Price / Preț:** `${price:,.4f}`  |  🎯 **TP1:** `${tp1:,.4f}`  |  🛑 **SL:** `${sl:,.4f}`"
        ),
        color=color,
        timestamp=datetime.utcnow()
    )
    if logo:
        embed.set_thumbnail(url=logo)
    embed.set_author(name="🤖 Crypto Signals Bot — Free Signal", icon_url=BOT_ICON)

    embed.add_field(name="📊 RSI (14)", value=rsi_bar(rsi), inline=False)
    embed.add_field(name="⭐ Confidence / Calitate", value=conf_stars(confidence), inline=False)
    embed.add_field(name="\u200b", value=SEP, inline=False)
    embed.add_field(name="🇬🇧 Situation",  value=action_en, inline=False)
    embed.add_field(name="🇷🇴 Situație",   value=action_ro, inline=False)
    embed.add_field(name="\u200b", value=SEP, inline=False)
    embed.add_field(name="🇬🇧 Steps",      value=steps_en,  inline=True)
    embed.add_field(name="🇷🇴 Pași",       value=steps_ro,  inline=True)
    embed.add_field(
        name="💎 Want TP2, TP3 & AI Analysis?",
        value=f"🇬🇧 Upgrade to **VIP** for full signal details!\n🇷🇴 Fă upgrade la **VIP** pentru semnale complete!",
        inline=False
    )
    embed.set_footer(text=f"Crypto Signals Bot  •  {DISCLAIMER_RO}")
    return embed

def build_vip_embed(symbol, signal, price, rsi, confidence, ai_text, confirmed_15m=False):
    coin   = symbol.replace("USDT", "")
    emoji  = COIN_EMOJI.get(symbol, "🪙")
    logo   = COIN_LOGOS.get(symbol)
    color  = COIN_COLORS.get(symbol, 0x00c896)
    is_buy = signal == "BUY"

    entry  = price
    tp1    = round(price * (1.020 if is_buy else 0.980), 4)
    tp2    = round(price * (1.040 if is_buy else 0.960), 4)
    tp3    = round(price * (1.065 if is_buy else 0.935), 4)
    sl     = round(price * (0.970 if is_buy else 1.030), 4)
    rr     = "2.2 : 1"

    sig_label = "🟢  V I P   B U Y" if is_buy else "🔴  V I P   S E L L"
    mtf_badge = "✅ **MULTI-TF CONFIRMED**  •  5m + 15m aligned" if confirmed_15m else "⚠️ Single-TF signal  •  Use smaller position"

    embed = discord.Embed(
        title=f"💎 {sig_label} — {coin}",
        description=(
            f"{emoji} **{COIN_NAMES_EN.get(symbol, symbol)}**\n"
            f"{SEP}\n"
            f"{mtf_badge}"
        ),
        color=color,
        timestamp=datetime.utcnow()
    )
    if logo:
        embed.set_thumbnail(url=logo)
    embed.set_author(name="💎 Crypto Signals Bot — VIP Exclusive", icon_url=BOT_ICON)

    embed.add_field(
        name="📍 Trade Levels / Niveluri Trade",
        value=(
            f"```\n"
            f"{'Entry':<10} ${entry:>14,.4f}\n"
            f"{'TP1  +2%':<10} ${tp1:>14,.4f}\n"
            f"{'TP2  +4%':<10} ${tp2:>14,.4f}\n"
            f"{'TP3  +6.5%':<10} ${tp3:>14,.4f}\n"
            f"{'SL   -3%':<10} ${sl:>14,.4f}\n"
            f"{'R:R':<10} {'2.2 : 1':>14}\n"
            f"```"
        ),
        inline=False
    )
    embed.add_field(name="📊 RSI (14)", value=rsi_bar(rsi), inline=False)
    embed.add_field(name="⭐ Signal Quality", value=conf_stars(confidence), inline=True)
    embed.add_field(name="📐 Direction", value=f"`{'LONG 📈' if is_buy else 'SHORT / AVOID 📉'}`", inline=True)
    embed.add_field(name="\u200b", value=SEP, inline=False)
    embed.add_field(
        name="🧠 AI Analysis / Analiză AI",
        value=ai_text if ai_text else "_Analysis unavailable_",
        inline=False
    )
    embed.add_field(name="\u200b", value=SEP, inline=False)
    embed.add_field(
        name="⚠️ Risk Rules / Reguli de Risc",
        value=(
            "🇬🇧 `Leverage: 1x–3x MAX`  •  `Max 10% capital/trade`  •  `Always set SL!`\n"
            "🇷🇴 `Leverage: 1x–3x MAX`  •  `Max 10% capital/trade`  •  `Setează mereu SL!`"
        ),
        inline=False
    )
    embed.set_footer(text=f"Crypto Signals Bot — VIP  •  {DISCLAIMER_RO}")
    return embed

def build_price_embed(symbol):
    info  = get_price_info(symbol)
    df    = get_data(symbol)
    ind   = calc_indicators(df) if df is not None else None
    emoji = COIN_EMOJI.get(symbol, "🪙")
    logo  = COIN_LOGOS.get(symbol)
    is_up = info and info["change"] >= 0
    color = 0x00c853 if is_up else 0xff1744

    embed = discord.Embed(
        title=f"{emoji}  {COIN_NAMES_EN.get(symbol, symbol)}",
        description=f"{'📈' if is_up else '📉'} **Live Market Data**  •  Real-time via Binance\n{SEP}",
        color=color,
        timestamp=datetime.utcnow()
    )
    if logo:
        embed.set_thumbnail(url=logo)
    embed.set_author(name="📊 Crypto Signals Bot — Price Dashboard", icon_url=BOT_ICON)

    if info:
        ch_sign  = "▲" if is_up else "▼"
        ch_color = "🟢" if is_up else "🔴"
        embed.add_field(
            name="💰 Price / Preț",
            value=f"## `${info['price']:,.4f}`",
            inline=False
        )
        embed.add_field(
            name=f"{ch_color} 24h Change",
            value=f"`{ch_sign} {abs(info['change']):.2f}%`",
            inline=True
        )
        embed.add_field(name="🔺 24h High", value=f"`${info['high']:,.4f}`", inline=True)
        embed.add_field(name="🔻 24h Low",  value=f"`${info['low']:,.4f}`",  inline=True)
        embed.add_field(
            name="📦 24h Volume",
            value=f"`${info['volume']:,.0f}`",
            inline=True
        )
        range_pct = round((info["high"] - info["low"]) / info["low"] * 100, 2) if info["low"] else 0
        embed.add_field(name="↔️ Day Range", value=f"`{range_pct}%`", inline=True)

    if ind:
        embed.add_field(name="\u200b", value=SEP, inline=False)
        embed.add_field(name="📊 RSI (14)", value=rsi_bar(ind["rsi"]), inline=False)
        macd_trend = "🟢 Bullish" if ind.get("macd_hist", 0) > 0 else "🔴 Bearish"
        embed.add_field(name="📉 MACD Trend", value=macd_trend, inline=True)
        ema_trend  = "🟢 Above EMA50" if info and info["price"] > ind.get("ema50", 0) else "🔴 Below EMA50"
        embed.add_field(name="📐 EMA (50)",  value=ema_trend,  inline=True)

    embed.set_footer(text=f"Crypto Signals Bot  •  {DISCLAIMER_RO}")
    return embed

# =========================
# SLASH COMMANDS
# =========================

@tree.command(name="signal", description="💎 VIP: Get a live BTC/ETH/SOL/BNB signal instantly")
@app_commands.describe(coin="Choose a coin (default: BTC)")
@app_commands.choices(coin=[
    app_commands.Choice(name="Bitcoin (BTC)",  value="BTCUSDT"),
    app_commands.Choice(name="Ethereum (ETH)", value="ETHUSDT"),
    app_commands.Choice(name="Solana (SOL)",   value="SOLUSDT"),
    app_commands.Choice(name="BNB (BNB)",      value="BNBUSDT"),
])
async def slash_signal(interaction: discord.Interaction, coin: str = "BTCUSDT"):
    if not is_vip(interaction.user):
        embed = discord.Embed(
            description=f"❌ **VIP Only / Doar pentru VIP**\n\n🇬🇧 This command is for VIP members only.\n🇷🇴 Această comandă este doar pentru membrii VIP.\n\n→ <#{GET_VIP_CHANNEL}>",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    await interaction.response.defer()
    df = get_data(coin)
    sig, price, rsi, conf = get_signal_v2(df)

    if sig and price:
        ai_text      = ai_analysis(sig, price, rsi, coin)
        tf15         = get_signal_15m(coin)
        confirmed    = tf15 == sig
        chart        = generate_chart(df, coin, sig)
        embed        = build_vip_embed(coin, sig, price, rsi, conf, ai_text, confirmed)
        await interaction.followup.send(embed=embed, file=discord.File(chart))
    else:
        embed = discord.Embed(
            description=(
                f"⚪ **No signal right now / Niciun semnal acum**\n\n"
                f"🇬🇧 Market is neutral. RSI: `{round(rsi,2) if rsi else 'N/A'}` | Price: `${round(price,2) if price else 'N/A'}`\n"
                f"🇷🇴 Piața e neutră. Urmăresc continuu și îți trimit semnal când apare."
            ),
            color=discord.Color.light_grey()
        )
        await interaction.followup.send(embed=embed)

@tree.command(name="price", description="📊 Get live price + 24h stats for any coin")
@app_commands.describe(coin="Choose a coin")
@app_commands.choices(coin=[
    app_commands.Choice(name="Bitcoin (BTC)",  value="BTCUSDT"),
    app_commands.Choice(name="Ethereum (ETH)", value="ETHUSDT"),
    app_commands.Choice(name="Solana (SOL)",   value="SOLUSDT"),
    app_commands.Choice(name="BNB (BNB)",      value="BNBUSDT"),
])
async def slash_price(interaction: discord.Interaction, coin: str = "BTCUSDT"):
    await interaction.response.defer()
    embed = build_price_embed(coin)
    await interaction.followup.send(embed=embed)

@tree.command(name="chart", description="📈 Get a live chart with RSI & MACD for any coin")
@app_commands.describe(coin="Choose a coin", timeframe="Chart timeframe")
@app_commands.choices(
    coin=[
        app_commands.Choice(name="Bitcoin (BTC)",  value="BTCUSDT"),
        app_commands.Choice(name="Ethereum (ETH)", value="ETHUSDT"),
        app_commands.Choice(name="Solana (SOL)",   value="SOLUSDT"),
        app_commands.Choice(name="BNB (BNB)",      value="BNBUSDT"),
    ],
    timeframe=[
        app_commands.Choice(name="5 minutes",  value="5m"),
        app_commands.Choice(name="15 minutes", value="15m"),
        app_commands.Choice(name="1 hour",     value="1h"),
        app_commands.Choice(name="4 hours",    value="4h"),
    ]
)
async def slash_chart(interaction: discord.Interaction, coin: str = "BTCUSDT", timeframe: str = "5m"):
    await interaction.response.defer()
    df = get_data(coin, interval=timeframe)
    if df is None:
        await interaction.followup.send("❌ Could not fetch data. Try again.")
        return
    sig, _, _, _ = get_signal_v2(df)
    chart = generate_chart(df, coin, sig)
    embed = discord.Embed(
        title=f"📈 {COIN_NAMES_EN.get(coin, coin)} — {timeframe.upper()} Chart",
        description=f"🇬🇧 Price + RSI + MACD indicators\n🇷🇴 Grafic cu indicatori RSI și MACD",
        color=COIN_COLORS.get(coin, 0x58a6ff),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
    await interaction.followup.send(embed=embed, file=discord.File(chart))

@tree.command(name="rsi", description="📊 Live RSI dashboard for all monitored coins")
async def slash_rsi(interaction: discord.Interaction):
    await interaction.response.defer()
    embed = discord.Embed(
        title="📊 Live RSI Dashboard",
        description="🇬🇧 Real-time RSI for all coins\n🇷🇴 RSI în timp real pentru toate monedele",
        color=discord.Color.blurple(),
        timestamp=datetime.utcnow()
    )
    for sym in SYMBOLS:
        df  = get_data(sym)
        ind = calc_indicators(df)
        if ind:
            rsi   = ind["rsi"]
            price = ind["price"]
            st_en = "🔴 OVERBOUGHT" if rsi > 70 else ("🟢 OVERSOLD" if rsi < 30 else "⚪ NEUTRAL")
            st_ro = "🔴 SUPRAEVALUAT" if rsi > 70 else ("🟢 SUPRAVÂNDUT" if rsi < 30 else "⚪ NEUTRU")
            embed.add_field(
                name=f"{COIN_EMOJI.get(sym,'')} {COIN_NAMES_EN.get(sym, sym)}",
                value=f"`${round(price,2)}` | RSI: `{round(rsi,2)}` | {st_en} / {st_ro}",
                inline=False
            )
    embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
    await interaction.followup.send(embed=embed)

@tree.command(name="alert", description="🔔 Set a price alert — you'll get a DM when price hits target")
@app_commands.describe(coin="Choose a coin", target="Target price in USD")
@app_commands.choices(coin=[
    app_commands.Choice(name="Bitcoin (BTC)",  value="BTCUSDT"),
    app_commands.Choice(name="Ethereum (ETH)", value="ETHUSDT"),
    app_commands.Choice(name="Solana (SOL)",   value="SOLUSDT"),
    app_commands.Choice(name="BNB (BNB)",      value="BNBUSDT"),
])
async def slash_alert(interaction: discord.Interaction, coin: str, target: float):
    uid = interaction.user.id
    if uid not in PRICE_ALERTS:
        PRICE_ALERTS[uid] = []
    if len(PRICE_ALERTS[uid]) >= 5:
        await interaction.response.send_message(
            "⚠️ Max 5 active alerts. Use `/myalerts` to check them.", ephemeral=True
        )
        return
    df = get_data(coin)
    if df is None:
        await interaction.response.send_message("❌ Could not fetch data.", ephemeral=True)
        return
    current   = df["close"].iloc[-1]
    direction = "above" if target > current else "below"
    PRICE_ALERTS[uid].append((coin, target, direction))
    embed = discord.Embed(
        description=(
            f"✅ **Alert set / Alertă setată**\n\n"
            f"🇬🇧 **{coin.replace('USDT','')}** will notify you when price {'≥' if direction=='above' else '≤'} `${target:,.2f}`\n"
            f"🇷🇴 Vei primi DM când prețul {'≥' if direction=='above' else '≤'} `${target:,.2f}`\n\n"
            f"💰 Current price / Preț curent: `${current:,.2f}`"
        ),
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="myalerts", description="🔔 See your active price alerts")
async def slash_myalerts(interaction: discord.Interaction):
    alerts = PRICE_ALERTS.get(interaction.user.id, [])
    if not alerts:
        await interaction.response.send_message(
            "ℹ️ 🇬🇧 No active alerts.\n🇷🇴 Nu ai alerte active. Setează cu `/alert`.",
            ephemeral=True
        )
        return
    embed = discord.Embed(
        title="🔔 Your Active Alerts / Alertele tale active",
        color=discord.Color.gold()
    )
    for sym, target, direction in alerts:
        embed.add_field(
            name=sym.replace("USDT",""),
            value=f"{'≥' if direction=='above' else '≤'} `${target:,.2f}`",
            inline=True
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="stats", description="📈 Bot statistics and signal history")
async def slash_stats(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📈 Bot Statistics",
        color=discord.Color.green(),
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="🇬🇧 Total Signals", value=str(SIGNAL_STATS["total"]),    inline=True)
    embed.add_field(name="🟢 BUY",             value=str(SIGNAL_STATS["BUY"]),      inline=True)
    embed.add_field(name="🔴 SELL",            value=str(SIGNAL_STATS["SELL"]),     inline=True)
    embed.add_field(name="🪙 Monitored Coins / Monede monitorizate",
                    value=", ".join(s.replace("USDT","") for s in SYMBOLS),         inline=False)
    embed.add_field(name="🔔 Active Alerts / Alerte active",
                    value=str(sum(len(v) for v in PRICE_ALERTS.values())),           inline=True)
    embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
    await interaction.response.send_message(embed=embed)

@tree.command(name="tip", description="🎓 Get a random trading tip — bilingual RO/EN")
async def slash_tip(interaction: discord.Interaction):
    tips = [
        ("📌 Risk Management / Gestiunea Riscului",
         "🇬🇧 Never risk more than 1–2% of your total capital on a single trade. Protect your account first.\n"
         "🇷🇴 Nu risca niciodată mai mult de 1–2% din capitalul total pe un singur trade. Protejează-ți contul."),
        ("📌 Stop Loss / Stop Loss",
         "🇬🇧 Always set a Stop Loss before entering a trade. A trade without SL is gambling, not trading.\n"
         "🇷🇴 Setează mereu Stop Loss înainte să intri. Un trade fără SL e noroc, nu trading."),
        ("📌 RSI Explained / RSI Explicat",
         "🇬🇧 RSI below 30 = oversold (potential BUY). RSI above 70 = overbought (potential SELL). Best used with MACD confirmation.\n"
         "🇷🇴 RSI sub 30 = supravândut (potențial BUY). RSI peste 70 = supraevaluat (potențial SELL). Folosește cu confirmare MACD."),
        ("📌 Don't Chase Pumps / Nu Urmări Pump-urile",
         "🇬🇧 If a coin pumped 20%+ already, don't buy FOMO. Wait for a pullback and a new signal.\n"
         "🇷🇴 Dacă o monedă a crescut deja 20%+, nu cumpăra din FOMO. Așteaptă o corecție și un semnal nou."),
        ("📌 Take Profit / Ia Profit",
         "🇬🇧 Always take partial profit at TP1. Move SL to entry after TP1 is hit — you can't lose after that.\n"
         "🇷🇴 Ia mereu profit parțial la TP1. Mută SL la entry după TP1 — nu mai poți pierde după aia."),
        ("📌 Market Trends / Trenduri de Piață",
         "🇬🇧 Trade WITH the trend, not against it. If BTC is in a downtrend, avoid longing altcoins.\n"
         "🇷🇴 Tranzacționează CU trendul, nu împotriva lui. Dacă BTC e în downtrend, evită long-urile pe altcoins."),
        ("📌 Volume = Confirmation / Volumul = Confirmare",
         "🇬🇧 A price move with high volume is more reliable than one with low volume. Always check volume.\n"
         "🇷🇴 O mișcare de preț cu volum mare e mai sigură decât una cu volum mic. Verifică mereu volumul."),
        ("📌 Emotions / Emoțiile",
         "🇬🇧 Fear and greed are your biggest enemies. Stick to your plan — don't close early out of fear or hold too long out of greed.\n"
         "🇷🇴 Frica și lăcomia sunt cei mai mari dușmani. Urmează planul — nu închide din frică și nu ține prea mult din lăcomie."),
        ("📌 MACD Explained / MACD Explicat",
         "🇬🇧 MACD histogram above 0 = bullish momentum. Below 0 = bearish. A crossover of MACD line over signal line is a BUY sign.\n"
         "🇷🇴 Histograma MACD peste 0 = momentum bullish. Sub 0 = bearish. Crossover MACD peste linia signal = semn BUY."),
        ("📌 Position Sizing / Dimensiunea Poziției",
         "🇬🇧 Use 3–5% of your portfolio per trade for low risk, 5–10% for medium. Never go all-in.\n"
         "🇷🇴 Folosește 3–5% din portofoliu pe trade pentru risc mic, 5–10% pentru mediu. Nu intra niciodată totul."),
    ]
    title, value = random.choice(tips)
    embed = discord.Embed(title=f"🎓 Trading Tip", description=title, color=discord.Color.teal(), timestamp=datetime.utcnow())
    embed.add_field(name="\u200b", value=value, inline=False)
    embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
    await interaction.response.send_message(embed=embed)

@tree.command(name="removealert", description="🗑️ Remove one of your active price alerts")
@app_commands.describe(coin="Coin to remove alert for")
@app_commands.choices(coin=[
    app_commands.Choice(name="Bitcoin (BTC)",  value="BTCUSDT"),
    app_commands.Choice(name="Ethereum (ETH)", value="ETHUSDT"),
    app_commands.Choice(name="Solana (SOL)",   value="SOLUSDT"),
    app_commands.Choice(name="BNB (BNB)",      value="BNBUSDT"),
])
async def slash_removealert(interaction: discord.Interaction, coin: str):
    uid    = interaction.user.id
    alerts = PRICE_ALERTS.get(uid, [])
    before = len(alerts)
    PRICE_ALERTS[uid] = [(s, t, d) for s, t, d in alerts if s != coin]
    removed = before - len(PRICE_ALERTS[uid])
    if removed:
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"🗑️ 🇬🇧 Removed **{removed}** alert(s) for **{coin.replace('USDT','')}**.\n"
                            f"🇷🇴 Am șters **{removed}** alertă/alerte pentru **{coin.replace('USDT','')}**.",
                color=discord.Color.orange()
            ), ephemeral=True
        )
    else:
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"ℹ️ 🇬🇧 No alerts found for **{coin.replace('USDT','')}**.\n"
                            f"🇷🇴 Nu ai alerte active pentru **{coin.replace('USDT','')}**.",
                color=discord.Color.light_grey()
            ), ephemeral=True
        )

@tree.command(name="help", description="📋 List all available commands")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📋 Commands / Comenzi disponibile",
        description="🇬🇧 All available commands\n🇷🇴 Toate comenzile disponibile",
        color=discord.Color.blurple()
    )
    embed.add_field(name="/price [coin]",    value="🇬🇧 Live price + 24h stats\n🇷🇴 Preț live + statistici 24h",    inline=False)
    embed.add_field(name="/chart [coin] [tf]",value="🇬🇧 RSI + MACD chart\n🇷🇴 Grafic RSI + MACD",                 inline=False)
    embed.add_field(name="/rsi",             value="🇬🇧 RSI dashboard all coins\n🇷🇴 Dashboard RSI toate monedele",  inline=False)
    embed.add_field(name="/alert [coin] [price]", value="🇬🇧 Set price alert (DM)\n🇷🇴 Alertă de preț via DM",     inline=False)
    embed.add_field(name="/myalerts",        value="🇬🇧 Your active alerts\n🇷🇴 Alertele tale active",              inline=False)
    embed.add_field(name="/stats",           value="🇬🇧 Bot statistics\n🇷🇴 Statistici bot",                        inline=False)
    embed.add_field(name="/signal 💎 VIP",   value="🇬🇧 Live signal on-demand (VIP only)\n🇷🇴 Semnal live instant (doar VIP)", inline=False)
    embed.add_field(name="/tip",             value="🇬🇧 Random trading tip\n🇷🇴 Sfat de trading aleatoriu",                    inline=False)
    embed.add_field(name="/removealert [coin]", value="🇬🇧 Delete a price alert\n🇷🇴 Șterge o alertă de preț",                inline=False)
    embed.add_field(name="/sentiment",       value="🇬🇧 Full market sentiment overview\n🇷🇴 Tablou complet de sentiment piață",   inline=False)
    embed.add_field(name="/history",         value="🇬🇧 Last 10 signals with details\n🇷🇴 Ultimele 10 semnale cu detalii",       inline=False)
    embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
    await interaction.response.send_message(embed=embed)


@tree.command(name="sentiment", description="🧠 Full market sentiment: Fear&Greed + RSI + trend overview")
async def slash_sentiment(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        fg_score, fg_class = get_fear_greed()
    except Exception:
        fg_score, fg_class = "N/A", "Unknown"

    rows = []
    overall_rsi_vals = []
    for sym in SYMBOLS:
        try:
            df = get_data(sym)
            if df is None or len(df) < 14:
                continue
            delta = df["close"].diff()
            gain  = delta.clip(lower=0).rolling(14).mean()
            loss  = (-delta.clip(upper=0)).rolling(14).mean()
            rs    = gain / loss.replace(0, 1e-9)
            rsi_v = round(float(100 - 100 / (1 + rs.iloc[-1])), 1)
            overall_rsi_vals.append(rsi_v)
            p = df["close"].iloc[-1]
            p_prev = df["close"].iloc[-2]
            pct = round((p - p_prev) / p_prev * 100, 2)
            trend = "🟢 Bullish" if rsi_v < 70 and pct > 0 else ("🔴 Bearish" if rsi_v > 30 and pct < 0 else "🟡 Neutral")
            rows.append(f"**{sym.replace('USDT','')}** — RSI `{rsi_v}` | `{'+' if pct>=0 else ''}{pct}%` | {trend}")
        except Exception:
            pass

    avg_rsi = round(sum(overall_rsi_vals) / len(overall_rsi_vals), 1) if overall_rsi_vals else 0

    if isinstance(fg_score, int):
        if fg_score <= 25:
            overall = "😱 Extreme Fear / Frică extremă"
        elif fg_score <= 45:
            overall = "😟 Fear / Frică"
        elif fg_score <= 55:
            overall = "😐 Neutral / Neutru"
        elif fg_score <= 75:
            overall = "😄 Greed / Lăcomie"
        else:
            overall = "🤑 Extreme Greed / Lăcomie extremă"
    else:
        overall = "❓ Unknown"

    mkt_bias = "🟢 Bullish" if avg_rsi < 55 and (isinstance(fg_score, int) and fg_score > 50) else \
               ("🔴 Bearish" if avg_rsi > 55 and (isinstance(fg_score, int) and fg_score < 50) else "🟡 Mixed")

    embed = discord.Embed(
        title="🧠 Market Sentiment / Sentiment Piață",
        description=(
            f"🇬🇧 Combined view: Fear & Greed + RSI + price momentum\n"
            f"🇷🇴 Vedere combinată: Fear & Greed + RSI + momentum preț"
        ),
        color=discord.Color.dark_blue(),
        timestamp=datetime.utcnow()
    )
    embed.add_field(
        name="😱 Fear & Greed Index",
        value=f"`{fg_score}/100` — **{fg_class}**\n{overall}",
        inline=False
    )
    embed.add_field(
        name="📊 RSI Overview / Privire de ansamblu RSI",
        value="\n".join(rows) if rows else "N/A",
        inline=False
    )
    embed.add_field(
        name="📈 Average RSI / RSI Mediu",
        value=f"`{avg_rsi}` — {mkt_bias}",
        inline=True
    )
    embed.add_field(
        name="📡 Signals Today / Semnale azi",
        value=f"🟢 BUY: `{SIGNAL_STATS['BUY']}` | 🔴 SELL: `{SIGNAL_STATS['SELL']}`",
        inline=True
    )
    embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
    await interaction.followup.send(embed=embed)


@tree.command(name="history", description="📜 Show last 10 signals with details")
async def slash_history(interaction: discord.Interaction):
    if not SIGNAL_HISTORY:
        await interaction.response.send_message(
            "🇬🇧 No signals recorded yet this session.\n🇷🇴 Niciun semnal înregistrat în această sesiune.",
            ephemeral=True
        )
        return
    embed = discord.Embed(
        title="📜 Signal History / Istoricul Semnalelor",
        description=(
            "🇬🇧 Last recorded signals this session\n"
            "🇷🇴 Ultimele semnale înregistrate în această sesiune"
        ),
        color=discord.Color.dark_gold(),
        timestamp=datetime.utcnow()
    )
    for s in reversed(SIGNAL_HISTORY[-10:]):
        ts = s["timestamp"].strftime("%d %b %H:%M UTC")
        icon = "🟢" if s["signal"] == "BUY" else "🔴"
        embed.add_field(
            name=f"{icon} {s['symbol'].replace('USDT','')} — {s['signal']} @ ${s['price']:,.2f}",
            value=f"RSI: `{s['rsi']}` | Confidence: `{s['confidence']}%` | {ts}",
            inline=False
        )
    embed.add_field(
        name="📊 Session totals / Total sesiune",
        value=f"🟢 BUY: `{SIGNAL_STATS['BUY']}` | 🔴 SELL: `{SIGNAL_STATS['SELL']}` | Total: `{SIGNAL_STATS['total']}`",
        inline=False
    )
    embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
    await interaction.response.send_message(embed=embed)

# =========================
# WELCOME
# =========================

@client.event
async def on_member_join(member):
    ch = client.get_channel(WELCOME_CHANNEL)
    if not ch:
        return
    embed = discord.Embed(
        title=f"👋 Welcome / Bun venit, {member.display_name}!",
        description=(
            "🇬🇧 **Welcome to the server!**\n"
            "We provide real-time crypto signals for BTC, ETH, SOL & BNB.\n\n"
            f"📜 Rules → <#{RULES_CHANNEL}>\n"
            f"📊 How to use → <#{HOWTO_CHANNEL}>\n"
            f"💎 Get VIP → <#{GET_VIP_CHANNEL}>\n\n"
            "🇷🇴 **Bun venit pe server!**\n"
            "Oferim semnale crypto în timp real pentru BTC, ETH, SOL și BNB.\n\n"
            f"📜 Reguli → <#{RULES_CHANNEL}>\n"
            f"📊 Cum funcționează → <#{HOWTO_CHANNEL}>\n"
            f"💎 Obține VIP → <#{GET_VIP_CHANNEL}>"
        ),
        color=discord.Color.gold(),
        timestamp=datetime.utcnow()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    await ch.send(embed=embed)

# =========================
# ON READY
# =========================

@client.event
async def on_ready():
    print(f"Bot online: {client.user}")
    await tree.sync()
    print("Slash commands synced.")

    status_ch = client.get_channel(STATUS_CHANNEL)
    if status_ch:
        embed = discord.Embed(
            title="🟢 Bot ONLINE",
            description=(
                f"🇬🇧 Monitoring: {', '.join(s.replace('USDT','') for s in SYMBOLS)}\n"
                f"🇷🇴 Monitorizez: {', '.join(s.replace('USDT','') for s in SYMBOLS)}\n\n"
                "📋 Type `/help` to see all commands / pentru toate comenzile"
            ),
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        await status_ch.send(embed=embed)

    async def send_once(channel, embed, keyword):
        """Send embed only if bot hasn't posted it before (checks last 30 msgs)."""
        if not channel:
            return
        async for msg in channel.history(limit=30):
            if msg.author == client.user and msg.embeds:
                title = msg.embeds[0].title or ""
                if keyword.lower() in title.lower():
                    return
        await channel.send(embed=embed)

    rules_embed = discord.Embed(title="📜 Rules / Reguli", color=discord.Color.orange())
    rules_embed.add_field(name="🇬🇧 Rules",
                    value="• No spam\n• No scams\n• Respect everyone\n• Signals are NOT financial advice", inline=True)
    rules_embed.add_field(name="🇷🇴 Reguli",
                    value="• Fără spam\n• Fără scam\n• Respectă pe toată lumea\n• Semnalele NU sunt sfaturi financiare", inline=True)
    rules_ch = client.get_channel(RULES_CHANNEL)
    await send_once(rules_ch, rules_embed, "Rules")

    howto_embed = discord.Embed(
        title="📊 How to Use Signals / Cum să folosești semnalele",
        color=discord.Color.blue()
    )
    howto_embed.add_field(name="🇬🇧 Steps",
        value="1. Use Binance / Bybit (SPOT, not futures if beginner)\n"
              "2. Follow Entry / TP1 / TP2 / SL exactly\n"
              "3. Max 5–10% of capital per trade\n"
              "4. Always set Stop Loss before entering\n"
              "5. Wait for 🟢 BUY before entering", inline=False)
    howto_embed.add_field(name="🇷🇴 Pași",
        value="1. Folosește Binance / Bybit (SPOT, nu futures la început)\n"
              "2. Urmează Entry / TP1 / TP2 / SL exact\n"
              "3. Max 5–10% din capital pe trade\n"
              "4. Setează mereu Stop Loss înainte să intri\n"
              "5. Așteaptă semnal 🟢 verde înainte să cumperi", inline=False)
    howto_embed.add_field(name="📋 Commands / Comenzi", value="Type `/help` to see all commands.", inline=False)
    howto_embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
    howto_ch = client.get_channel(HOWTO_CHANNEL)
    await send_once(howto_ch, howto_embed, "How to Use")

    vip_embed = discord.Embed(title="💎 GET VIP ACCESS", color=discord.Color.gold())
    vip_embed.add_field(name="🇬🇧 What you get",
        value="✅ Signals with TP1 / TP2 / SL\n✅ RSI + MACD charts attached\n✅ AI trade analysis\n"
              "✅ Multi-timeframe confirmation\n✅ On-demand `/signal` command\n✅ Price alerts via DM", inline=True)
    vip_embed.add_field(name="🇷🇴 Ce primești",
        value="✅ Semnale cu TP1 / TP2 / SL\n✅ Grafice RSI + MACD atașate\n✅ Analiză AI per semnal\n"
              "✅ Confirmare multi-timeframe\n✅ Comanda `/signal` on-demand\n✅ Alerte de preț via DM", inline=True)
    vip_embed.add_field(name="📩 Contact",
        value="👤 <@1426677891269267618>\n👤 <@1463583046962909410>", inline=False)
    vip_embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
    vip_ch = client.get_channel(GET_VIP_CHANNEL)
    await send_once(vip_ch, vip_embed, "VIP")

    client.loop.create_task(signal_loop())
    client.loop.create_task(market_news_loop())
    client.loop.create_task(announcement_loop())
    client.loop.create_task(performance_loop())
    client.loop.create_task(crash_alert())
    client.loop.create_task(fear_greed_loop())
    client.loop.create_task(top_movers_loop())
    client.loop.create_task(price_alert_checker())
    client.loop.create_task(neutral_market_loop())
    client.loop.create_task(education_loop())
    client.loop.create_task(weekly_recap_loop())

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
                df  = get_data(symbol)
                sig, price, rsi, conf = get_signal_v2(df)
                ind = calc_indicators(df)

                if ind and check_volume_spike(ind) and alerts_ch:
                    await alerts_ch.send(embed=discord.Embed(
                        description=(
                            f"📊 **Volume Spike — {symbol.replace('USDT','')}**\n\n"
                            f"🇬🇧 Volume is 2.5x above average! Watch for a big move.\n"
                            f"🇷🇴 Volumul este de 2.5x mai mare decât media! Urmărește o mișcare mare."
                        ),
                        color=discord.Color.yellow()
                    ))

                if df is not None and check_volatility(df) and alerts_ch:
                    await alerts_ch.send(embed=discord.Embed(
                        description=(
                            f"⚠️ **High Volatility — {symbol.replace('USDT','')}**\n\n"
                            f"🇬🇧 Large candle detected. Check open positions.\n"
                            f"🇷🇴 Lumânare mare detectată. Verifică pozițiile deschise."
                        ),
                        color=discord.Color.orange()
                    ))

                if sig and price and can_send_signal(symbol, sig):
                    SIGNAL_STATS[sig]     += 1
                    SIGNAL_STATS["total"] += 1
                    SIGNAL_HISTORY.append({
                        "symbol": symbol, "signal": sig,
                        "price": price, "rsi": round(rsi, 2),
                        "confidence": conf,
                        "timestamp": datetime.utcnow()
                    })
                    if len(SIGNAL_HISTORY) > 500:
                        SIGNAL_HISTORY.pop(0)
                    ai_text    = ai_analysis(sig, price, rsi, symbol)
                    tf15       = get_signal_15m(symbol)
                    confirmed  = tf15 == sig
                    chart      = generate_chart(df, symbol, sig)
                    f_embed    = build_free_embed(symbol, sig, price, rsi, conf)
                    v_embed    = build_vip_embed(symbol, sig, price, rsi, conf, ai_text, confirmed)
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
# FEAR & GREED
# =========================

async def fear_greed_loop():
    await client.wait_until_ready()
    channel = client.get_channel(MARKET_NEWS_CHANNEL)
    while True:
        try:
            data  = requests.get("https://api.alternative.me/fng/?limit=1", timeout=8).json()
            val   = int(data["data"][0]["value"])
            label = data["data"][0]["value_classification"]
            emoji = "😱" if val<=25 else ("😟" if val<=45 else ("😐" if val<=55 else ("😊" if val<=75 else "🤑")))
            color = discord.Color.red() if val < 30 else (discord.Color.green() if val > 70 else discord.Color.orange())
            interp_en = ("Extreme fear — historically a BUY opportunity." if val < 25
                         else "Extreme greed — market may be overheated. Be careful." if val > 75
                         else "Balanced market. Follow technical signals.")
            interp_ro = ("Frică extremă — istoric un moment de cumpărare." if val < 25
                         else "Lăcomie extremă — piața poate fi supraîncălzită. Fii atent." if val > 75
                         else "Piața în echilibru. Urmărește semnalele tehnice.")
            embed = discord.Embed(
                title=f"{emoji} Fear & Greed Index — {val}/100 ({label})",
                color=color, timestamp=datetime.utcnow()
            )
            embed.add_field(name="🇬🇧 Interpretation", value=interp_en, inline=False)
            embed.add_field(name="🇷🇴 Interpretare",   value=interp_ro, inline=False)
            embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
            if channel:
                await channel.send(embed=embed)
        except Exception:
            pass
        await asyncio.sleep(3600)

# =========================
# TOP MOVERS
# =========================

async def top_movers_loop():
    await client.wait_until_ready()
    channel = client.get_channel(MARKET_NEWS_CHANNEL)
    while True:
        await asyncio.sleep(86400)
        try:
            data  = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=10).json()
            usdt  = [x for x in data if x["symbol"].endswith("USDT") and float(x["quoteVolume"]) > 5_000_000]
            srt   = sorted(usdt, key=lambda x: float(x["priceChangePercent"]))
            losers, gainers = srt[:5], srt[-5:][::-1]
            embed = discord.Embed(
                title="🏆 Top 5 Gainers & Losers — 24h",
                color=discord.Color.gold(), timestamp=datetime.utcnow()
            )
            embed.add_field(name="📈 Gainers",
                value="\n".join(f"🟢 **{x['symbol'].replace('USDT','')}** `+{float(x['priceChangePercent']):.2f}%` — `${float(x['lastPrice']):,.4f}`" for x in gainers) or "—",
                inline=False)
            embed.add_field(name="📉 Losers",
                value="\n".join(f"🔴 **{x['symbol'].replace('USDT','')}** `{float(x['priceChangePercent']):.2f}%` — `${float(x['lastPrice']):,.4f}`" for x in losers) or "—",
                inline=False)
            embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
            if channel:
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
            for alerts in PRICE_ALERTS.values():
                for sym, _, _ in alerts:
                    if sym not in prices:
                        df = get_data(sym)
                        if df is not None:
                            prices[sym] = df["close"].iloc[-1]
            for uid, alerts in list(PRICE_ALERTS.items()):
                remaining = []
                for sym, target, direction in alerts:
                    price = prices.get(sym)
                    hit   = price and ((direction == "above" and price >= target) or
                                       (direction == "below" and price <= target))
                    if hit:
                        try:
                            user  = await client.fetch_user(uid)
                            embed = discord.Embed(
                                title="🔔 Price Alert Hit! / Alertă atinsă!",
                                description=(
                                    f"🇬🇧 **{sym.replace('USDT','')}** reached `${price:,.2f}`\n"
                                    f"Your target: {'≥' if direction=='above' else '≤'} `${target:,.2f}`\n\n"
                                    f"🇷🇴 **{sym.replace('USDT','')}** a atins `${price:,.2f}`\n"
                                    f"Ținta ta: {'≥' if direction=='above' else '≤'} `${target:,.2f}`"
                                ),
                                color=discord.Color.green(), timestamp=datetime.utcnow()
                            )
                            embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
                            await user.send(embed=embed)
                        except Exception:
                            pass
                    else:
                        remaining.append((sym, target, direction))
                PRICE_ALERTS[uid] = remaining
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
            rows, all_neutral = [], True
            for sym in SYMBOLS:
                df  = get_data(sym)
                ind = calc_indicators(df)
                if ind:
                    rsi, p = ind["rsi"], ind["price"]
                    st_en  = "🔴 SELL" if rsi>70 else ("🟢 BUY" if rsi<30 else "⚪ Neutral")
                    st_ro  = "🔴 VINDE" if rsi>70 else ("🟢 CUMPĂRĂ" if rsi<30 else "⚪ Neutru")
                    rows.append(f"{COIN_EMOJI.get(sym,'')} **{sym.replace('USDT','')}** `${round(p,2)}` RSI`{round(rsi,1)}` {st_en}/{st_ro}")
                    if rsi < 30 or rsi > 70:
                        all_neutral = False
            if all_neutral and rows and free_ch:
                embed = discord.Embed(
                    title="⚪ Neutral Market / Piața este neutră",
                    description=(
                        "🇬🇧 No active signal right now. Monitoring continuously.\n"
                        "🇷🇴 Niciun semnal activ momentan. Monitorizez continuu.\n\n"
                        + "\n".join(rows)
                    ),
                    color=discord.Color.light_grey(), timestamp=datetime.utcnow()
                )
                embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
                await free_ch.send(embed=embed)
        except Exception:
            pass

# =========================
# MARKET NEWS LOOP
# =========================

async def market_news_loop():
    await client.wait_until_ready()
    channel = client.get_channel(MARKET_NEWS_CHANNEL)
    news = [
        ("🚨 High Volatility Alert / Alertă Volatilitate Ridicată",
         "🇬🇧 BTC volatility increasing! Monitor open positions.\n🇷🇴 Volatilitate BTC în creștere! Monitorizează pozițiile.", discord.Color.orange()),
        ("📉 Possible Correction / Corecție Posibilă",
         "🇬🇧 Market showing signs of weakness short-term.\n🇷🇴 Piața arată semne de slăbiciune pe termen scurt.", discord.Color.red()),
        ("📈 Bullish Momentum / Momentum Bullish",
         "🇬🇧 BTC showing strength — watch for BUY signals.\n🇷🇴 BTC arată forță — urmărește semnalele 🟢.", discord.Color.green()),
        ("🔥 ETH Gaining Strength / ETH Câștigă Forță",
         "🇬🇧 Ethereum rising vs BTC dominance.\n🇷🇴 Ethereum în creștere față de dominanța BTC.", discord.Color.purple()),
        ("⚡ Whale Movement Detected / Mișcare de Balenă",
         "🇬🇧 Large on-chain transaction detected.\n🇷🇴 Tranzacție mare on-chain detectată.", discord.Color.yellow()),
        ("🛡️ Key Support Held / Suport Cheie Menținut",
         "🇬🇧 BTC held key support level — bullish sign.\n🇷🇴 BTC a menținut suportul cheie — semn bullish.", discord.Color.blue()),
    ]
    while True:
        if channel:
            title, desc, color = random.choice(news)
            embed = discord.Embed(title=title, description=desc, color=color, timestamp=datetime.utcnow())
            embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
            await channel.send(embed=embed)
        await asyncio.sleep(1800)

# =========================
# ANNOUNCEMENTS
# =========================

async def announcement_loop():
    await client.wait_until_ready()
    channel = client.get_channel(ANNOUNCEMENTS_CHANNEL)
    items = [
        ("📢 VIP Signals Available! / Semnale VIP Disponibile!",
         "🇬🇧 Upgrade now for full premium access 💎\n🇷🇴 Upgrade acum pentru acces complet premium 💎"),
        ("🔥 87% Win Rate This Month! / Win Rate 87% Luna Aceasta!",
         "🇬🇧 Join the winning team 💎\n🇷🇴 Alătură-te echipei câștigătoare 💎"),
        ("💡 Did you know? / Știai?",
         "🇬🇧 VIP members get RSI + MACD charts + AI analysis with every signal!\n🇷🇴 Membrii VIP primesc grafice RSI + MACD + analiză AI la fiecare semnal!"),
        ("⚡ New Feature! / Feature Nou!",
         "🇬🇧 Set price alerts with `/alert BTC 70000` — get notified via DM!\n🇷🇴 Setează alerte de preț cu `/alert BTC 70000` — primești DM automat!"),
    ]
    i = 0
    while True:
        if channel:
            title, desc = items[i % len(items)]
            embed = discord.Embed(title=title, description=desc, color=discord.Color.gold(), timestamp=datetime.utcnow())
            embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
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
                title="📊 Daily Performance / Performanță Zilnică",
                color=discord.Color.green(), timestamp=datetime.utcnow()
            )
            embed.add_field(name="✅ BTC", value="+12%", inline=True)
            embed.add_field(name="✅ ETH", value="+8%",  inline=True)
            embed.add_field(name="✅ SOL", value="+15%", inline=True)
            embed.add_field(name="🔥 VIP Win Rate", value="87%", inline=False)
            embed.add_field(name="💎 Want results like these? / Vrei rezultate ca acestea?",
                            value=f"→ <#{GET_VIP_CHANNEL}>", inline=False)
            embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
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
                        title="🚨 Market Drop Detected! / Scădere Detectată!",
                        description=(
                            f"🇬🇧 BTC dropped **{round(drop_pct,2)}%** in ~50 minutes.\n"
                            f"Current price: `${round(df['close'].iloc[-1],2)}`\n"
                            f"⚠️ Check open positions and SL levels!\n\n"
                            f"🇷🇴 BTC a scăzut cu **{round(drop_pct,2)}%** în ~50 minute.\n"
                            f"Preț curent: `${round(df['close'].iloc[-1],2)}`\n"
                            f"⚠️ Verifică pozițiile deschise și SL-urile!"
                        ),
                        color=discord.Color.red(), timestamp=datetime.utcnow()
                    )
                    embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
                    await channel.send(embed=embed)
        except Exception as e:
            print(f"Crash alert error: {e}")
        await asyncio.sleep(600)

# =========================
# EDUCATION LOOP
# =========================

async def education_loop():
    await client.wait_until_ready()
    channel = client.get_channel(HOWTO_CHANNEL)

    tips = [
        ("📌 Risk Management / Gestiunea Riscului",
         "🇬🇧 Never risk more than 1–2% of your total capital on a single trade. Protect your account first.\n"
         "🇷🇴 Nu risca niciodată mai mult de 1–2% din capitalul total pe un singur trade. Protejează-ți contul."),
        ("📌 Stop Loss / Stop Loss",
         "🇬🇧 Always set a Stop Loss before entering a trade. A trade without SL is gambling, not trading.\n"
         "🇷🇴 Setează mereu Stop Loss înainte să intri. Un trade fără SL e noroc, nu trading."),
        ("📌 RSI Explained / RSI Explicat",
         "🇬🇧 RSI below 30 = oversold (potential BUY). RSI above 70 = overbought (potential SELL). Best used with MACD confirmation.\n"
         "🇷🇴 RSI sub 30 = supravândut (potențial BUY). RSI peste 70 = supraevaluat (potențial SELL). Folosește cu confirmare MACD."),
        ("📌 Don't Chase Pumps / Nu Urmări Pump-urile",
         "🇬🇧 If a coin pumped 20%+ already, don't buy FOMO. Wait for a pullback and a new signal.\n"
         "🇷🇴 Dacă o monedă a crescut deja 20%+, nu cumpăra din FOMO. Așteaptă o corecție și un semnal nou."),
        ("📌 Take Profit / Ia Profit",
         "🇬🇧 Always take partial profit at TP1. Move SL to entry after TP1 is hit — you can't lose after that.\n"
         "🇷🇴 Ia mereu profit parțial la TP1. Mută SL la entry după TP1 — nu mai poți pierde după aia."),
        ("📌 Trade With the Trend / Tranzacționează cu Trendul",
         "🇬🇧 Trade WITH the trend, not against it. If BTC is in a downtrend, avoid longing altcoins.\n"
         "🇷🇴 Tranzacționează CU trendul, nu împotriva lui. Dacă BTC e în downtrend, evită long-urile pe altcoins."),
        ("📌 Volume Matters / Volumul Contează",
         "🇬🇧 A price move with high volume is more reliable than one with low volume. Always check volume.\n"
         "🇷🇴 O mișcare de preț cu volum mare e mai sigură decât una cu volum mic. Verifică mereu volumul."),
        ("📌 Control Your Emotions / Controlează-ți Emoțiile",
         "🇬🇧 Fear and greed are your biggest enemies. Stick to your plan — don't close early out of fear or hold too long out of greed.\n"
         "🇷🇴 Frica și lăcomia sunt cei mai mari dușmani. Urmează planul — nu închide din frică și nu ține prea mult din lăcomie."),
        ("📌 MACD Explained / MACD Explicat",
         "🇬🇧 MACD histogram above 0 = bullish momentum. Below 0 = bearish. A crossover of MACD line over signal line is a BUY sign.\n"
         "🇷🇴 Histograma MACD peste 0 = momentum bullish. Sub 0 = bearish. Crossover MACD peste linia signal = semn BUY."),
        ("📌 Position Sizing / Dimensiunea Poziției",
         "🇬🇧 Use 3–5% of your portfolio per trade for low risk, 5–10% for medium. Never go all-in.\n"
         "🇷🇴 Folosește 3–5% din portofoliu pe trade pentru risc mic, 5–10% pentru mediu. Nu intra niciodată totul."),
        ("📌 What is SPOT? / Ce este SPOT?",
         "🇬🇧 SPOT trading means you buy the actual coin. No leverage, no liquidation risk. Best for beginners.\n"
         "🇷🇴 SPOT înseamnă că cumperi moneda efectivă. Fără leverage, fără risc de lichidare. Ideal pentru începători."),
        ("📌 What is Leverage? / Ce este Leverage-ul?",
         "🇬🇧 Leverage multiplies your position. 10x leverage means a 10% move = 100% gain OR loss. Use max 3x if you must.\n"
         "🇷🇴 Leverage-ul îți înmulțește poziția. 10x leverage înseamnă că o mișcare de 10% = câștig SAU pierdere de 100%. Max 3x dacă folosești."),
        ("📌 BTC Dominance / Dominanța BTC",
         "🇬🇧 When BTC dominance rises, altcoins often drop. When it falls, altcoins rally. Watch it before trading alts.\n"
         "🇷🇴 Când dominanța BTC crește, altcoin-urile scad de obicei. Când scade, altcoin-urile cresc. Urmărește-o înainte de a tranzacționa."),
        ("📌 Support & Resistance / Suport și Rezistență",
         "🇬🇧 Support = price level where buyers step in. Resistance = where sellers step in. Buy near support, sell near resistance.\n"
         "🇷🇴 Suport = nivel unde cumpărătorii intră. Rezistență = unde vânzătorii intră. Cumpără lângă suport, vinde lângă rezistență."),
    ]

    index = 0
    while True:
        await asyncio.sleep(43200)  # every 12 hours
        try:
            if channel:
                title, value = tips[index % len(tips)]
                embed = discord.Embed(
                    title=f"🎓 Daily Trading Tip / Sfat Zilnic de Trading",
                    description=title,
                    color=discord.Color.teal(),
                    timestamp=datetime.utcnow()
                )
                embed.add_field(name="\u200b", value=value, inline=False)
                embed.add_field(
                    name="💡 Practice / Practică",
                    value="🇬🇧 Use `/tip` anytime for a random tip!\n🇷🇴 Folosește `/tip` oricând pentru un sfat aleatoriu!",
                    inline=False
                )
                embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
                await channel.send(embed=embed)
                index += 1
        except Exception:
            pass

# =========================
# AUTO-MODERATION
# =========================

@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    content_lower = message.content.lower()
    if any(kw in content_lower for kw in SCAM_KEYWORDS):
        try:
            await message.delete()
            warn = await message.channel.send(
                f"⚠️ {message.author.mention} "
                "🇬🇧 Your message was removed. Spam/scam content is not allowed on this server.\n"
                "🇷🇴 Mesajul tău a fost șters. Conținutul spam/scam nu este permis pe acest server."
            )
            await asyncio.sleep(8)
            await warn.delete()
        except Exception:
            pass
    await client.process_commands(message)

# =========================
# WEEKLY RECAP LOOP
# =========================

async def weekly_recap_loop():
    await client.wait_until_ready()
    channel = client.get_channel(PERFORMANCE_CHANNEL)
    while True:
        try:
            now = datetime.utcnow()
            days_until_sunday = (6 - now.weekday()) % 7
            if days_until_sunday == 0 and now.hour == 20:
                week_signals = [s for s in SIGNAL_HISTORY
                                if (now - s["timestamp"]).days < 7]
                buys  = sum(1 for s in week_signals if s["signal"] == "BUY")
                sells = sum(1 for s in week_signals if s["signal"] == "SELL")
                total = len(week_signals)

                best_coin, best_count = "N/A", 0
                coin_counts = {}
                for s in week_signals:
                    coin_counts[s["symbol"]] = coin_counts.get(s["symbol"], 0) + 1
                if coin_counts:
                    best_coin = max(coin_counts, key=coin_counts.get).replace("USDT", "")
                    best_count = coin_counts[max(coin_counts, key=coin_counts.get)]

                try:
                    fg_score, fg_class = get_fear_greed()
                    fg_str = f"`{fg_score}/100` — {fg_class}"
                except Exception:
                    fg_str = "N/A"

                embed = discord.Embed(
                    title="📊 Weekly Recap / Rezumat Săptămânal",
                    description=(
                        f"🇬🇧 Here's how the market looked this week.\n"
                        f"🇷🇴 Iată cum a arătat piața săptămâna aceasta."
                    ),
                    color=discord.Color.gold(),
                    timestamp=now
                )
                embed.add_field(
                    name="📡 Signals this week / Semnale săptămâna asta",
                    value=f"🟢 BUY: `{buys}` | 🔴 SELL: `{sells}` | Total: `{total}`",
                    inline=False
                )
                embed.add_field(
                    name="🏆 Most active coin / Moneda cea mai activă",
                    value=f"**{best_coin}** — `{best_count}` semnale",
                    inline=True
                )
                embed.add_field(
                    name="😱 Fear & Greed (end of week)",
                    value=fg_str,
                    inline=True
                )
                embed.add_field(
                    name="💎 Want better results? / Vrei rezultate mai bune?",
                    value=f"→ <#{GET_VIP_CHANNEL}>",
                    inline=False
                )
                embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
                if channel:
                    await channel.send(embed=embed)
                await asyncio.sleep(3600)
            else:
                await asyncio.sleep(1800)
        except Exception:
            await asyncio.sleep(1800)

# =========================

client.run(TOKEN)
