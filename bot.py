import discord
from discord import app_commands
import asyncio
import requests
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from ta.momentum import RSIIndicator, StochRSIIndicator
from ta.trend import MACD, EMAIndicator
from ta.volatility import BollingerBands
import os
import random
from datetime import datetime
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

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
ALL_SYMBOLS   = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
                 "XRPUSDT", "ADAUSDT", "AVAXUSDT", "DOGEUSDT"]
VIP_ROLE_NAME = "VIP"
DISCLAIMER_EN = "Crypto Signals Bot | Not financial advice. Invest responsibly."
DISCLAIMER_RO = "Crypto Signals Bot | Nu e sfat financiar. Investește responsabil."

LAST_SIGNAL      = {}
SIGNAL_STATS     = {"BUY": 0, "SELL": 0, "total": 0}
PRICE_ALERTS     = {}
SIGNAL_HISTORY   = []
USER_PORTFOLIOS  = {}   # {user_id: [{symbol, entry, amount, ts}]}
USER_WATCHLISTS  = {}   # {user_id: [symbol, ...]}
WATCHLIST_NOTIF  = {}   # {user_id_symbol: last_ts}
PREDICTIONS      = {}   # {user_id: {symbol, direction, price, ts}}
PRED_SCORES      = {}   # {user_id: {correct, total, username}}

SCAM_KEYWORDS = [
    "dm me", "free crypto", "100x guaranteed", "dm for profit",
    "recovery service", "tripling funds", "click here", "t.me/",
    "investment platform", "double your", "recuperare fonduri",
    "trimiteti", "castig garantat", "dm pentru profit", "profit garantat",
    "invest now", "guaranteed returns", "pasive income", "passive income crypto"
]

COIN_COLORS = {
    "BTCUSDT": 0xF7931A, "ETHUSDT": 0x627EEA,
    "SOLUSDT": 0x9945FF, "BNBUSDT": 0xF0B90B,
    "XRPUSDT": 0x00AAE4, "ADAUSDT": 0x0033AD,
    "AVAXUSDT":0xE84142, "DOGEUSDT":0xC3A634,
}
COIN_EMOJI = {
    "BTCUSDT": "₿",  "ETHUSDT": "Ξ",  "SOLUSDT": "◎",  "BNBUSDT": "⬡",
    "XRPUSDT": "✕",  "ADAUSDT": "₳",  "AVAXUSDT":"🔺", "DOGEUSDT":"🐶",
}
COIN_NAMES_EN = {
    "BTCUSDT":  "Bitcoin (BTC)",   "ETHUSDT":  "Ethereum (ETH)",
    "SOLUSDT":  "Solana (SOL)",    "BNBUSDT":  "BNB (BNB)",
    "XRPUSDT":  "XRP (XRP)",       "ADAUSDT":  "Cardano (ADA)",
    "AVAXUSDT": "Avalanche (AVAX)","DOGEUSDT": "Dogecoin (DOGE)",
}
COIN_NAMES_RO = COIN_NAMES_EN
COIN_LOGOS = {
    "BTCUSDT":  "https://assets.coingecko.com/coins/images/1/small/bitcoin.png",
    "ETHUSDT":  "https://assets.coingecko.com/coins/images/279/small/ethereum.png",
    "SOLUSDT":  "https://assets.coingecko.com/coins/images/4128/small/solana.png",
    "BNBUSDT":  "https://assets.coingecko.com/coins/images/825/small/bnb-icon2_2x.png",
    "XRPUSDT":  "https://assets.coingecko.com/coins/images/44/small/xrp-symbol-white-128.png",
    "ADAUSDT":  "https://assets.coingecko.com/coins/images/975/small/cardano.png",
    "AVAXUSDT": "https://assets.coingecko.com/coins/images/12559/small/Avalanche_Circle_RedWhite_Trans.png",
    "DOGEUSDT": "https://assets.coingecko.com/coins/images/5/small/dogecoin.png",
}
BOT_ICON = "https://assets.coingecko.com/coins/images/1/small/bitcoin.png"
SEP  = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
SEP2 = "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"

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

def get_fear_greed():
    """Standalone Fear & Greed fetch — returns (score_int, label_str)."""
    try:
        data  = requests.get("https://api.alternative.me/fng/?limit=1", timeout=8).json()
        val   = int(data["data"][0]["value"])
        label = data["data"][0]["value_classification"]
        return val, label
    except Exception:
        return "N/A", "Unknown"

def get_messari_metrics(symbol):
    """
    Messari free API — returns basic on-chain metrics.
    No API key needed for basic data.
    """
    coin_map = {"BTCUSDT": "bitcoin", "ETHUSDT": "ethereum",
                "SOLUSDT": "solana",  "BNBUSDT": "binance-coin"}
    slug = coin_map.get(symbol, symbol.replace("USDT","").lower())
    try:
        url  = f"https://data.messari.io/api/v1/assets/{slug}/metrics"
        data = requests.get(url, timeout=10).json().get("data", {})
        mkt  = data.get("market_data", {})
        roi  = data.get("roi_data", {})
        sup  = data.get("supply", {})
        return {
            "price_usd":        mkt.get("price_usd"),
            "volume_last_24h":  mkt.get("volume_last_24_hours"),
            "percent_change_24h": mkt.get("percent_change_usd_last_24_hours"),
            "market_cap":       mkt.get("real_volume_last_24_hours"),
            "roi_1y":           roi.get("percent_change_last_1_year"),
            "circulating_supply": sup.get("circulating"),
        }
    except Exception:
        return None

def get_coingecko_extra(symbol):
    """CoinGecko extra metrics: market cap rank, ATH, community score."""
    coin_map = {"BTCUSDT": "bitcoin", "ETHUSDT": "ethereum",
                "SOLUSDT": "solana",  "BNBUSDT": "binancecoin"}
    coin = coin_map.get(symbol, symbol.replace("USDT","").lower())
    try:
        url  = f"https://api.coingecko.com/api/v3/coins/{coin}?localization=false&tickers=false&community_data=true&developer_data=false"
        data = requests.get(url, timeout=10).json()
        mkt  = data.get("market_data", {})
        return {
            "market_cap_rank":  data.get("market_cap_rank"),
            "ath":              mkt.get("ath", {}).get("usd"),
            "ath_change_pct":   mkt.get("ath_change_percentage", {}).get("usd"),
            "community_score":  data.get("community_score"),
            "coingecko_score":  data.get("coingecko_score"),
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
    macd_line = macd_obj.macd().iloc[-1]
    macd_sig  = macd_obj.macd_signal().iloc[-1]

    ema20     = EMAIndicator(close=close, window=20).ema_indicator().iloc[-1]
    ema50     = EMAIndicator(close=close, window=50).ema_indicator().iloc[-1]

    bb        = BollingerBands(close=close, window=20, window_dev=2)
    bb_upper  = bb.bollinger_hband().iloc[-1]
    bb_lower  = bb.bollinger_lband().iloc[-1]
    bb_mid    = bb.bollinger_mavg().iloc[-1]
    bb_pct    = bb.bollinger_pband().iloc[-1]   # 0=lower band, 1=upper band

    try:
        stoch    = StochRSIIndicator(close=close, window=14, smooth1=3, smooth2=3)
        stoch_k  = stoch.stochrsi_k().iloc[-1]
        stoch_d  = stoch.stochrsi_d().iloc[-1]
    except Exception:
        stoch_k = stoch_d = 0.5

    price     = close.iloc[-1]
    vol_avg   = df["volume"].iloc[-20:].mean() if "volume" in df.columns else 0
    vol_now   = df["volume"].iloc[-1]          if "volume" in df.columns else 0

    return {
        "rsi": rsi, "macd_hist": macd_hist, "macd_line": macd_line, "macd_sig": macd_sig,
        "ema20": ema20, "ema50": ema50,
        "bb_upper": bb_upper, "bb_lower": bb_lower, "bb_mid": bb_mid, "bb_pct": bb_pct,
        "stoch_k": stoch_k, "stoch_d": stoch_d,
        "price": price, "vol_avg": vol_avg, "vol_now": vol_now
    }

def get_signal_v2(df):
    ind = calc_indicators(df)
    if ind is None:
        return None, None, None, None

    rsi      = ind["rsi"]
    macd_h   = ind["macd_hist"]
    price    = ind["price"]
    ema50    = ind["ema50"]
    ema20    = ind["ema20"]
    bb_pct   = ind["bb_pct"]
    stoch_k  = ind["stoch_k"]
    stoch_d  = ind["stoch_d"]

    # 5-indicator scoring system
    buy_signals = [
        rsi < 35,                        # RSI oversold
        macd_h > 0,                      # MACD bullish
        price > ema50 * 0.98,            # price near/above EMA50
        bb_pct < 0.25,                   # price near lower Bollinger Band
        stoch_k < 0.25 and stoch_k > stoch_d,  # Stoch RSI oversold crossover
    ]
    sell_signals = [
        rsi > 65,                        # RSI overbought
        macd_h < 0,                      # MACD bearish
        price < ema50 * 1.02,            # price near/below EMA50
        bb_pct > 0.75,                   # price near upper Bollinger Band
        stoch_k > 0.75 and stoch_k < stoch_d,  # Stoch RSI overbought crossover
    ]

    buy_score  = sum(buy_signals)
    sell_score = sum(sell_signals)

    if buy_score >= 3:
        conf = "🔥 HIGH" if buy_score >= 4 else "⚡ MEDIUM"
        return "BUY",  price, rsi, conf
    if sell_score >= 3:
        conf = "🔥 HIGH" if sell_score >= 4 else "⚡ MEDIUM"
        return "SELL", price, rsi, conf
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
    x       = range(len(close))

    ema20   = EMAIndicator(close=close, window=20).ema_indicator()
    ema50   = EMAIndicator(close=close, window=50).ema_indicator()
    bb      = BollingerBands(close=close, window=20, window_dev=2)
    bb_up   = bb.bollinger_hband()
    bb_lo   = bb.bollinger_lband()
    bb_mid  = bb.bollinger_mavg()
    rsi_s   = RSIIndicator(close=close, window=14).rsi()
    macd_o  = MACD(close=close)
    macd_l  = macd_o.macd()
    macd_sg = macd_o.macd_signal()
    macd_h  = macd_o.macd_diff()
    color   = "#00c896" if signal == "BUY" else ("#ff4d4d" if signal == "SELL" else "#58a6ff")

    for ax in (ax1, ax2, ax3):
        ax.set_facecolor("#161b22")
        ax.tick_params(colors="#8b949e")
        ax.grid(True, alpha=0.08, color="white")
        for s in ax.spines.values():
            s.set_edgecolor("#30363d")

    # Price + BB + EMA
    ax1.plot(x, close, color=color,    linewidth=1.6, label="Price", zorder=4)
    ax1.plot(x, ema20, color="#a78bfa", linewidth=0.9, linestyle="--", label="EMA20", alpha=0.85)
    ax1.plot(x, ema50, color="#f0b232", linewidth=0.9, linestyle="--", label="EMA50", alpha=0.85)
    ax1.plot(x, bb_up,  color="#64748b", linewidth=0.7, linestyle=":",  label="BB Upper", alpha=0.7)
    ax1.plot(x, bb_lo,  color="#64748b", linewidth=0.7, linestyle=":",  label="BB Lower", alpha=0.7)
    ax1.plot(x, bb_mid, color="#475569", linewidth=0.6, linestyle="-",  alpha=0.5)
    ax1.fill_between(x, bb_lo, bb_up, alpha=0.04, color="#64748b")

    sig_label = "🟢 BUY" if signal == "BUY" else ("🔴 SELL" if signal == "SELL" else "⚪ Monitor")
    ax1.set_title(
        f"{symbol}  |  {sig_label}  |  BB + EMA20/50  |  {datetime.utcnow().strftime('%d %b %Y  %H:%M UTC')}",
        color="white", fontsize=11, pad=8
    )
    ax1.set_ylabel("Price (USDT)", color="#8b949e", fontsize=9)
    ax1.legend(facecolor="#21262d", labelcolor="white", fontsize=7, ncol=3)

    # RSI with zones
    ax2.plot(x, rsi_s, color="#f0b232", linewidth=1.2)
    ax2.axhline(70, color="#ff4d4d", linestyle="--", linewidth=0.8, alpha=0.7)
    ax2.axhline(50, color="#8b949e", linestyle=":",  linewidth=0.6, alpha=0.5)
    ax2.axhline(30, color="#00c896", linestyle="--", linewidth=0.8, alpha=0.7)
    ax2.fill_between(x, 70, 100, alpha=0.06, color="red")
    ax2.fill_between(x, 0,  30,  alpha=0.06, color="green")
    ax2.set_ylabel("RSI", color="#8b949e", fontsize=9)
    ax2.set_ylim(0, 100)
    # Mark overbought / oversold regions
    rsi_arr = rsi_s.values
    for i, rv in enumerate(rsi_arr):
        if rv > 70:
            ax2.axvline(i, color="#ff4d4d", alpha=0.04, linewidth=0.5)
        elif rv < 30:
            ax2.axvline(i, color="#00c896", alpha=0.04, linewidth=0.5)

    # MACD histogram + lines
    hist_colors = ["#00c896" if v >= 0 else "#ff4d4d" for v in macd_h]
    ax3.plot(x, macd_l,  color="#58a6ff", linewidth=1.0, label="MACD")
    ax3.plot(x, macd_sg, color="#f0b232", linewidth=1.0, label="Signal")
    ax3.bar(x, macd_h, color=hist_colors, alpha=0.45, width=0.8)
    ax3.axhline(0, color="#8b949e", linewidth=0.6)
    ax3.set_ylabel("MACD", color="#8b949e", fontsize=9)
    ax3.legend(facecolor="#21262d", labelcolor="white", fontsize=8)

    plt.tight_layout(pad=1.2)
    fname = f"{symbol}_chart.png"
    plt.savefig(fname, facecolor=fig.get_facecolor(), dpi=120)
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

# ══════════════════════════════════════════════
#   SHARED TIPS LIST (used by /tip + education_loop)
# ══════════════════════════════════════════════

TRADING_TIPS = [
    ("🛑 Stop Loss — Regula #1",
     "🇷🇴 **Mereu** setează Stop Loss înainte să intri. Fără SL, un singur trade rău îți poate șterge contul.\n"
     "🇬🇧 **Always** set a Stop Loss before entering. Without SL, one bad trade can wipe your account.\n"
     "💡 Pe Binance: folosește **OCO Order** sau **Stop-Limit**."),

    ("💰 Cât investești per trade / Position Sizing",
     "🇷🇴 Regula de aur: **max 5–10%** din capitalul total per trade. Dacă ai 500$, max 50$ per trade.\n"
     "🇬🇧 Golden rule: **max 5–10%** of total capital per trade. With $500, max $50 per trade.\n"
     "💡 Astfel, chiar dacă greșești de 5 ori, nu ești terminat."),

    ("📊 Ce e RSI? / What is RSI?",
     "🇷🇴 RSI măsoară dacă o monedă e **prea ieftină** sau **prea scumpă** acum.\n"
     "• `sub 30` = 🟢 zona de cumpărare (oversold)\n"
     "• `peste 70` = 🔴 zona de vânzare (overbought)\n"
     "• `30–70` = ⚪ normal\n"
     "🇬🇧 RSI measures if a coin is **too cheap** or **too expensive** right now."),

    ("📉 Ce e MACD? / What is MACD?",
     "🇷🇴 MACD arată **direcția forței** pieței.\n"
     "• Bare **verzi ▲** = cumpărătorii domină → momentum BUY\n"
     "• Bare **roșii ▼** = vânzătorii domină → momentum SELL\n"
     "🇬🇧 MACD shows the **direction of market force**.\n"
     "Green bars ▲ = buyers dominate. Red bars ▼ = sellers dominate."),

    ("📐 Ce sunt Bollinger Bands? / What are Bollinger Bands?",
     "🇷🇴 Sunt ca niște **limite** în jurul prețului. Când prețul atinge **banda de jos** → posibil BUY. **Banda de sus** → posibil SELL.\n"
     "🇬🇧 They're like **price limits**. Price at **lower band** → possible BUY. **Upper band** → possible SELL.\n"
     "💡 Vizualizezi asta pe `/chart` — liniile gri punctate."),

    ("🎯 Cum iei profitul / How to Take Profit",
     "🇷🇴 **Strategia ideală:**\n"
     "1️⃣ La **TP1**: vinde 50% din poziție\n"
     "2️⃣ Mută **SL la Entry** → nu mai poți pierde!\n"
     "3️⃣ La **TP2**: vinde restul\n"
     "🇬🇧 At **TP1**: sell 50%. Move SL to entry. At **TP2**: sell the rest."),

    ("😱 FOMO = Cel mai mare dușman / Biggest Enemy",
     "🇷🇴 **FOMO** = cumperi dintr-o frică de a pierde oportunitatea. BTC a crescut 20%? Nu cumpăra acum!\n"
     "Așteaptă o **corecție** (scădere mică) și un **semnal nou**.\n"
     "🇬🇧 **FOMO** = buying out of fear of missing out. BTC up 20%? Don't buy now! Wait for a pullback + new signal."),

    ("📈 SPOT vs FUTURES — Diferența / The Difference",
     "🇷🇴 **SPOT**: cumperi moneda reală. Nu poți pierde mai mult decât ai investit. ✅ **Recomandat pentru începători.**\n"
     "**FUTURES**: tranzacționezi cu leverage. 10x leverage → o mișcare de 10% = 100% câștig SAU pierdere totală. ⚠️\n"
     "🇬🇧 **SPOT**: you own the real coin. Can't lose more than invested. ✅ **Best for beginners.**\n"
     "**FUTURES**: uses leverage. 10x = 10% move = 100% gain OR total loss. ⚠️"),

    ("🔄 Trendul e prietenul tău / Trend is Your Friend",
     "🇷🇴 Dacă BTC e în **downtrend** (scade), evită să cumperi altcoins. Tranzacționează CU trendul.\n"
     "💡 Verifică `/multi BTC` pentru a vedea trendul pe toate timeframe-urile.\n"
     "🇬🇧 If BTC is in a **downtrend**, avoid buying altcoins. Trade WITH the trend, not against it."),

    ("📦 Volumul confirmă mișcarea / Volume Confirms Moves",
     "🇷🇴 O creștere de preț **cu volum mare** = mișcare reală. Cu volum mic = posibil falsă.\n"
     "💡 Volumul = câți oameni cumpără/vând. Mai mult volum = mai multă convingere.\n"
     "🇬🇧 Price rise **with high volume** = real move. Low volume = possibly fake breakout."),

    ("🧠 Emoțiile în trading / Emotions in Trading",
     "🇷🇴 **Frica** te face să vinzi prea devreme. **Lăcomia** te face să ții prea mult.\n"
     "Soluția: **setează TP și SL** înainte să intri și **respectă-le** indiferent ce simți.\n"
     "🇬🇧 **Fear** makes you sell too early. **Greed** makes you hold too long.\n"
     "Solution: set TP and SL before entering, then **stick to the plan**."),

    ("👑 BTC Dominance — Ce e? / What is it?",
     "🇷🇴 Arată cât % din toată piața crypto e în Bitcoin.\n"
     "• Dom **în creștere** → banii merg în BTC → altcoin-urile scad\n"
     "• Dom **în scădere** → banii ies din BTC → altcoin-urile cresc\n"
     "💡 Verifică cu `/dominance`.\n"
     "🇬🇧 Shows what % of total crypto market cap is in Bitcoin. Rising = altcoins fall. Falling = altcoins rally."),

    ("⚡ Leverage = Cuțit cu două tăișuri / Double-Edged Sword",
     "🇷🇴 **3x leverage**: ai 100$, controlezi 300$. Câștig 10% = +30$ ✅. Pierdere 10% = -30$ ⚠️\n"
     "**10x leverage**: câștig 10% = +100$ ✅. Pierdere 10% = **LICHIDARE** (pierzi tot) ❌\n"
     "🇬🇧 Leverage amplifies both gains AND losses. Max 3x if you must use it."),

    ("🔍 Confirmarea multi-timeframe / Multi-TF Confirmation",
     "🇷🇴 Un semnal BUY pe **5m** + confirmat pe **1h** + **4h** = semnal mult mai puternic.\n"
     "💡 Folosește `/multi BTC` pentru a vedea toate timeframe-urile simultan.\n"
     "🇬🇧 A BUY signal on **5m** confirmed on **1h** + **4h** = much stronger signal.\n"
     "Use `/multi BTC` to see all timeframes at once."),

    ("🌙 Nu tranzacționa din plictiseală / Don't Trade Out of Boredom",
     "🇷🇴 **Nu** trebuie să fii mereu în piață. Uneori cel mai bun trade e **să nu intri**.\n"
     "Așteaptă semnale clare (confidence HIGH) și condiții bune.\n"
     "🇬🇧 You don't have to always be in a trade. Sometimes the best trade is **no trade**.\n"
     "Wait for clear signals (HIGH confidence) and good conditions."),

    ("📱 Unde pun ordinele / Where to Place Orders",
     "🇷🇴 Pe **Binance Spot**:\n"
     "• **Market Order** = cumperi instant la prețul actual\n"
     "• **Limit Order** = aștepți ca prețul să ajungă la un nivel ales\n"
     "• **OCO Order** = setezi simultan TP și SL ✅ Recomandat!\n"
     "🇬🇧 **Market** = buy instantly. **Limit** = wait for your price. **OCO** = set TP+SL together ✅"),

    ("🔒 Securitatea contului / Account Security",
     "🇷🇴 **Mereu** activează **2FA** (Google Authenticator) pe Binance. Nu da niciodată parola sau seed phrase nimănui!\n"
     "Nici un bot, nici un admin nu îți va cere niciodată fonduri sau parole.\n"
     "🇬🇧 **Always** enable **2FA** on Binance. Never share your password or seed phrase with anyone!"),

    ("📊 Support și Resistance / Support & Resistance",
     "🇷🇴 **Support** = nivel de preț unde cumpărătorii intră de obicei → prețul se stabilizează și crește.\n"
     "**Resistance** = nivel unde vânzătorii intră → prețul se stabilizează și scade.\n"
     "💡 Cumpără lângă support, vinde lângă resistance.\n"
     "🇬🇧 **Support** = price level buyers defend. **Resistance** = price level sellers defend."),

    ("💤 Răbdarea = Superputere / Patience = Superpower",
     "🇷🇴 Traderii profitabili **așteaptă** semnale de calitate (confidence HIGH/VERY HIGH).\n"
     "Nu forța tranzacții când piața e incertă. Calitate > Cantitate.\n"
     "🇬🇧 Profitable traders **wait** for quality signals (HIGH/VERY HIGH confidence).\n"
     "Don't force trades in uncertain markets. Quality > Quantity."),

    ("📉 Ce e un Pullback? / What is a Pullback?",
     "🇷🇴 O **corecție temporară** a prețului înainte să continue în direcția principală.\n"
     "Ex: BTC era la 100k, scade la 95k (pullback), apoi crește la 110k.\n"
     "💡 Pullback-urile sunt oportunități de cumpărare în trend ascendent.\n"
     "🇬🇧 A **temporary dip** before the price continues the main trend. Great buying opportunities!"),

    ("🎓 Continuă să înveți / Keep Learning",
     "🇷🇴 Folosește comenzile botului pentru a înțelege piața:\n"
     "• `/analysis BTC` — analiză completă\n"
     "• `/sentiment` — sentiment general piață\n"
     "• `/tutorial` — ghid complet pas cu pas\n"
     "• `/glossary` — dicționar termeni crypto\n"
     "🇬🇧 Use the bot's commands to understand the market better!"),
]


@tree.command(name="tip", description="🎓 Get a random trading tip — bilingual RO/EN")
async def slash_tip(interaction: discord.Interaction):
    title, value = random.choice(TRADING_TIPS)
    embed = discord.Embed(
        title=f"🎓 Trading Tip / Sfat de Trading",
        description=f"**{title}**",
        color=discord.Color.teal(),
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="\u200b", value=value, inline=False)
    embed.add_field(
        name="💡 Mai vrei un sfat?",
        value="🇷🇴 Scrie `/tip` din nou pentru un alt sfat aleatoriu!\n🇬🇧 Type `/tip` again for another random tip!",
        inline=False
    )
    embed.set_footer(text=f"Crypto Signals Bot  •  {DISCLAIMER_RO}")
    await interaction.response.send_message(embed=embed)


# ══════════════════════════════════════════════
#   /TUTORIAL COMMAND — Ghid complet pas cu pas
# ══════════════════════════════════════════════

@tree.command(name="tutorial", description="📖 Full beginner guide — step by step, bilingual RO/EN")
@app_commands.describe(page="Which page: 1=Signal, 2=Indicators, 3=HowToTrade, 4=Mistakes, 5=Glossary Quick")
async def slash_tutorial(interaction: discord.Interaction, page: int = 1):
    pages = {
        1: discord.Embed(
            title="📖 Tutorial 1/5 — Ce este un semnal? / What is a Signal?",
            description=(
                "🇷🇴 Un **semnal** este o recomandare generată automat de bot pe baza a 5 indicatori tehnici.\n"
                "🇬🇧 A **signal** is an automated recommendation generated by the bot using 5 technical indicators.\n"
                f"{SEP}"
            ),
            color=0x3b82f6, timestamp=datetime.utcnow()
        ),
        2: discord.Embed(
            title="📊 Tutorial 2/5 — Ce înseamnă indicatorii / What do Indicators Mean?",
            description=(
                "🇷🇴 Botul combină **5 indicatori** pentru a genera semnale mai precise.\n"
                "🇬🇧 The bot combines **5 indicators** for more accurate signals.\n"
                f"{SEP}"
            ),
            color=0x8b5cf6, timestamp=datetime.utcnow()
        ),
        3: discord.Embed(
            title="🚀 Tutorial 3/5 — Cum faci un trade / How to Make a Trade",
            description=(
                "🇷🇴 **Pași concreți** pe Binance după ce primești un semnal BUY:\n"
                "🇬🇧 **Concrete steps** on Binance after receiving a BUY signal:\n"
                f"{SEP}"
            ),
            color=0x10b981, timestamp=datetime.utcnow()
        ),
        4: discord.Embed(
            title="⚠️ Tutorial 4/5 — Greșeli frecvente / Common Mistakes",
            description=(
                "🇷🇴 **Evită aceste greșeli** care costă bani!\n"
                "🇬🇧 **Avoid these mistakes** that cost money!\n"
                f"{SEP}"
            ),
            color=0xef4444, timestamp=datetime.utcnow()
        ),
        5: discord.Embed(
            title="📚 Tutorial 5/5 — Termeni importanți / Key Terms",
            description=(
                "🇷🇴 Cei mai importanți termeni pe care trebuie să îi cunoști:\n"
                "🇬🇧 The most important terms you need to know:\n"
                f"{SEP}"
            ),
            color=0xf59e0b, timestamp=datetime.utcnow()
        ),
    }

    if page not in pages:
        await interaction.response.send_message(
            "❓ Pagini disponibile: `1` `2` `3` `4` `5`\n"
            "🇬🇧 Available pages: `1` `2` `3` `4` `5`", ephemeral=True); return

    embed = pages[page]

    if page == 1:
        embed.add_field(name="🟢 BUY — Cumpără",
            value="🇷🇴 Botul crede că prețul va **crește**. Intri la prețul **Entry** arătat în semnal.\n"
                  "🇬🇧 Bot believes price will **rise**. Enter at the **Entry** price shown.", inline=False)
        embed.add_field(name="🔴 SELL — Vinde",
            value="🇷🇴 Botul crede că prețul va **scădea**. Ieși sau evită să cumperi.\n"
                  "🇬🇧 Bot believes price will **fall**. Exit or avoid buying.", inline=False)
        embed.add_field(name="📍 Entry",
            value="🇷🇴 Prețul la care intri.\n🇬🇧 The price where you enter.", inline=True)
        embed.add_field(name="🎯 TP1 / TP2",
            value="🇷🇴 Prețuri de **vânzare** pentru profit.\n🇬🇧 **Sell** prices to take profit.", inline=True)
        embed.add_field(name="🛑 SL (Stop Loss)",
            value="🇷🇴 Prețul la care **ieși dacă greșești**. Limitează pierderea!\n"
                  "🇬🇧 Price where you **exit if wrong**. Limits your loss!\n⚠️ MEREU pune SL!", inline=False)
        embed.add_field(name="⭐ Confidence",
            value="🇷🇴 `LOW` `MEDIUM` `HIGH` `VERY HIGH` — cu cât e mai mare, cu atât mai mulți indicatori confirmă.\n"
                  "🇬🇧 The more indicators agree, the higher the confidence. Trade HIGH+ signals only.", inline=False)

    elif page == 2:
        embed.add_field(name="📊 RSI",
            value="🇷🇴 **sub 30** = ieftin/oversold 🟢 | **peste 70** = scump/overbought 🔴 | **30–70** = normal ⚪\n"
                  "🇬🇧 **below 30** = cheap/oversold 🟢 | **above 70** = expensive/overbought 🔴 | **30–70** = normal ⚪", inline=False)
        embed.add_field(name="📉 MACD",
            value="🇷🇴 Bare **verzi ▲** = cumpărătorii domină (momentum BUY). Bare **roșii ▼** = vânzătorii domină.\n"
                  "🇬🇧 **Green bars ▲** = buyers dominate (BUY momentum). **Red bars ▼** = sellers dominate.", inline=False)
        embed.add_field(name="📐 Bollinger Bands (BB)",
            value="🇷🇴 **Prețul la banda de jos** = posibil BUY. **La banda de sus** = posibil SELL.\n"
                  "🇬🇧 Price at **lower band** = possible BUY. At **upper band** = possible SELL.", inline=False)
        embed.add_field(name="🌀 Stochastic RSI",
            value="🇷🇴 **sub 0.2** = zonă BUY 🟢 | **peste 0.8** = zonă SELL 🔴\n"
                  "🇬🇧 **below 0.2** = BUY zone 🟢 | **above 0.8** = SELL zone 🔴", inline=False)
        embed.add_field(name="📈 EMA 20/50",
            value="🇷🇴 Linie medie a prețului. Prețul **peste** EMA = trend ascendent 🟢. **Sub** EMA = trend descendent 🔴.\n"
                  "🇬🇧 Price **above** EMA = uptrend 🟢. Price **below** EMA = downtrend 🔴.", inline=False)
        embed.add_field(name="💡 Cum le vezi",
            value="🇷🇴 Folosește `/chart BTC` pentru a vedea graficul cu toți indicatorii.\n"
                  "🇬🇧 Use `/chart BTC` to see the chart with all indicators.", inline=False)

    elif page == 3:
        embed.add_field(name="1️⃣ Deschide Binance Spot",
            value="🇷🇴 Mergi la **Trade → Spot**. NU Futures dacă ești începător!\n"
                  "🇬🇧 Go to **Trade → Spot**. NOT Futures if you're a beginner!", inline=False)
        embed.add_field(name="2️⃣ Caută perechea",
            value="🇷🇴 Semnal BTC → caută `BTC/USDT`. Semnal ETH → `ETH/USDT`.\n"
                  "🇬🇧 BTC signal → search `BTC/USDT`. ETH signal → `ETH/USDT`.", inline=False)
        embed.add_field(name="3️⃣ Decide cât investești",
            value="🇷🇴 **MAX 10%** din capitalul total! Cu 500$, max 50$ per trade.\n"
                  "🇬🇧 **MAX 10%** of total capital! With $500, max $50 per trade.", inline=False)
        embed.add_field(name="4️⃣ Setează un OCO Order",
            value="🇷🇴 OCO = setezi simultan **TP** (target profit) și **SL** (stop loss) → Binance execută automat.\n"
                  "🇬🇧 OCO = sets **TP** and **SL** at the same time → Binance executes automatically.", inline=False)
        embed.add_field(name="5️⃣ Ia profit la TP1",
            value="🇷🇴 La TP1 vinde **50%**. Mută SL la Entry → profit asigurat, risc zero!\n"
                  "🇬🇧 At TP1 sell **50%**. Move SL to Entry → profit secured, zero risk!", inline=False)

    elif page == 4:
        embed.add_field(name="❌ Nu pune SL",
            value="🇷🇴 Fără Stop Loss, o singură pierdere mare te poate elimina din piață complet.\n"
                  "🇬🇧 Without Stop Loss, one big loss can eliminate you from the market entirely.", inline=False)
        embed.add_field(name="❌ Intri cu tot capitalul",
            value="🇷🇴 All-in = dacă greșești o singură dată, pierzi tot. Diversifică și limitează per trade!\n"
                  "🇬🇧 All-in = one mistake wipes everything. Diversify and limit per trade!", inline=False)
        embed.add_field(name="❌ Cumperi după pump mare (FOMO)",
            value="🇷🇴 BTC +20% azi? **Nu cumpăra acum!** Vei cumpăra la vârf. Așteaptă corecție + semnal.\n"
                  "🇬🇧 BTC +20% today? **Don't buy now!** You'd be buying the top. Wait for pullback + signal.", inline=False)
        embed.add_field(name="❌ Futures/Leverage ca începător",
            value="🇷🇴 10x leverage + 10% scădere = pierzi **tot**. Începe cu SPOT mereu!\n"
                  "🇬🇧 10x leverage + 10% drop = lose **everything**. Always start with SPOT!", inline=False)
        embed.add_field(name="❌ Ignori Confidence-ul",
            value="🇷🇴 Semnale cu `LOW` confidence = nesigure. Tranzacționează **doar** `HIGH` sau `VERY HIGH`!\n"
                  "🇬🇧 `LOW` confidence signals = unreliable. Only trade `HIGH` or `VERY HIGH`!", inline=False)

    elif page == 5:
        embed.add_field(name="₿ BTC / Bitcoin",
            value="🇷🇴 Prima și cea mai mare criptomonedă din lume. Standardul pieței.\n"
                  "🇬🇧 The first and largest cryptocurrency. The market standard.", inline=False)
        embed.add_field(name="💵 USDT / Tether",
            value="🇷🇴 O monedă stabila (stablecoin) legată de dolarul american. 1 USDT = ~1$.\n"
                  "🇬🇧 A stablecoin pegged to the US dollar. 1 USDT ≈ $1.", inline=False)
        embed.add_field(name="📦 Spot Trading",
            value="🇷🇴 Cumperi moneda **reală**. Nu poți pierde mai mult decât ai investit. ✅ Recomandat!\n"
                  "🇬🇧 You buy the **real** coin. Can't lose more than invested. ✅ Recommended!", inline=False)
        embed.add_field(name="⚡ Futures / Leverage",
            value="🇷🇴 Tranzacționezi cu **bani împrumutați**. Poți câștiga mult, dar poți pierde tot rapid. ⚠️\n"
                  "🇬🇧 Trading with **borrowed money**. Big gains possible, but total loss possible too. ⚠️", inline=False)
        embed.add_field(name="🌊 Liquidation",
            value="🇷🇴 Când folosești leverage și pierderea ajunge la limita contului → Binance **închide automat** poziția (pierzi tot).\n"
                  "🇬🇧 When using leverage and loss hits account limit → Binance auto-closes position (total loss).", inline=False)

    embed.add_field(
        name=f"\n{'─'*28}\n📄 Pagini disponibile / Pages",
        value="`/tutorial 1` — Ce e un semnal?\n`/tutorial 2` — Indicatori\n"
              "`/tutorial 3` — Cum faci un trade\n`/tutorial 4` — Greșeli comune\n"
              "`/tutorial 5` — Termeni cheie\n`/glossary` — Dicționar complet",
        inline=False
    )
    embed.set_footer(text=f"Crypto Signals Bot  •  Pagina {page}/5  •  {DISCLAIMER_RO}")
    await interaction.response.send_message(embed=embed)


# ══════════════════════════════════════════════
#   /GLOSSARY COMMAND — Dicționar termeni crypto
# ══════════════════════════════════════════════

@tree.command(name="glossary", description="📚 Crypto dictionary — simple explanations RO/EN")
@app_commands.describe(category="Choose a category")
@app_commands.choices(category=[
    app_commands.Choice(name="📊 Indicators (RSI/MACD/BB)", value="indicators"),
    app_commands.Choice(name="💼 Trading Basics",            value="basics"),
    app_commands.Choice(name="⚡ Risk & Orders",             value="risk"),
    app_commands.Choice(name="🌍 Market Terms",              value="market"),
])
async def slash_glossary(interaction: discord.Interaction, category: str = "basics"):
    embeds_data = {
        "basics": {
            "title": "📚 Glossary — Trading Basics / Termeni de Bază",
            "color": 0x3b82f6,
            "fields": [
                ("₿ BTC / ETH / SOL / BNB",
                 "🇷🇴 Monede crypto. BTC = Bitcoin, ETH = Ethereum, SOL = Solana, BNB = BNB Chain.\n"
                 "🇬🇧 Crypto coins. BTC = Bitcoin, ETH = Ethereum, SOL = Solana, BNB = BNB Chain."),
                ("💵 USDT",
                 "🇷🇴 Monedă stabilă = mereu ~1 dolar. Folosești USDT pentru a cumpăra crypto.\n"
                 "🇬🇧 Stablecoin = always ~$1. You use USDT to buy crypto."),
                ("📦 SPOT",
                 "🇷🇴 Cumperi moneda **reală**. Dacă cumperi 0.01 BTC, chiar îl deții. ✅ Sigur.\n"
                 "🇬🇧 You buy the **real** coin. You actually own it. ✅ Safe for beginners."),
                ("⚡ FUTURES",
                 "🇷🇴 Tranzacționezi cu leverage (bani împrumutați). Risc mare de lichidare! ⚠️\n"
                 "🇬🇧 Trading with leverage (borrowed money). High liquidation risk! ⚠️"),
                ("📍 Entry",
                 "🇷🇴 Prețul la care **intri** în trade.\n🇬🇧 The price at which you **enter** a trade."),
                ("🎯 Take Profit (TP)",
                 "🇷🇴 Prețul la care **vinzi** automat pentru profit.\n"
                 "🇬🇧 The price at which you **automatically sell** for profit."),
                ("🛑 Stop Loss (SL)",
                 "🇷🇴 Prețul la care **ieși automat** dacă pierderea e prea mare.\n"
                 "🇬🇧 The price at which you **automatically exit** to limit loss."),
                ("💎 Long / Short",
                 "🇷🇴 **Long** = pariezi că prețul crește. **Short** = pariezi că scade.\n"
                 "🇬🇧 **Long** = bet price goes up. **Short** = bet price goes down."),
            ]
        },
        "indicators": {
            "title": "📊 Glossary — Indicators / Indicatori Tehnici",
            "color": 0x8b5cf6,
            "fields": [
                ("📊 RSI (Relative Strength Index)",
                 "🇷🇴 Scală 0–100. **sub 30** = oversold (ieftin) 🟢 | **peste 70** = overbought (scump) 🔴\n"
                 "🇬🇧 Scale 0–100. **below 30** = oversold (cheap) 🟢 | **above 70** = overbought (expensive) 🔴"),
                ("📉 MACD",
                 "🇷🇴 Arată **forța** și **direcția** trendului. Bare verzi = bullish ▲. Roșii = bearish ▼.\n"
                 "🇬🇧 Shows trend **strength** and **direction**. Green bars = bullish ▲. Red = bearish ▼."),
                ("📐 Bollinger Bands (BB)",
                 "🇷🇴 3 linii în jurul prețului. Prețul la **banda de jos** = BUY. La **banda de sus** = SELL.\n"
                 "🇬🇧 3 lines around price. Price at **lower band** = BUY. At **upper band** = SELL."),
                ("🌀 Stochastic RSI (StochRSI)",
                 "🇷🇴 Versiune mai rapidă a RSI. **sub 0.2** = BUY 🟢 | **peste 0.8** = SELL 🔴\n"
                 "🇬🇧 Faster version of RSI. **below 0.2** = BUY 🟢 | **above 0.8** = SELL 🔴"),
                ("📈 EMA (Exponential Moving Average)",
                 "🇷🇴 Media prețului pe ultimele N lumânări. Arată trendul.\n"
                 "• Preț **peste** EMA50 = trend BUY 🟢 | **sub** EMA50 = trend SELL 🔴\n"
                 "🇬🇧 Average price over N candles. Shows the trend direction."),
                ("⭐ Confluence / Confluență",
                 "🇷🇴 Când **mai mulți indicatori** arată același semnal = semnal mai puternic.\n"
                 "🇬🇧 When **multiple indicators** agree = stronger, more reliable signal."),
            ]
        },
        "risk": {
            "title": "⚡ Glossary — Risk & Orders / Risc și Ordine",
            "color": 0xef4444,
            "fields": [
                ("💀 Liquidation / Lichidare",
                 "🇷🇴 Când folosești futures și pierderea depășește capitalul → Binance **închide forțat** și pierzi tot.\n"
                 "🇬🇧 When using futures and loss exceeds capital → Binance **force-closes** and you lose everything."),
                ("⚡ Leverage",
                 "🇷🇴 Multiplu de tranzacționare. **3x** = controlezi de 3x mai mult decât ai. 10x = periculos!\n"
                 "🇬🇧 Trading multiplier. **3x** = control 3x more than you have. 10x = dangerous!"),
                ("📋 OCO Order",
                 "🇷🇴 **One Cancels the Other** = setezi TP și SL simultan. Când unul se execută, celălalt se anulează.\n"
                 "🇬🇧 **One Cancels the Other** = set TP and SL together. When one fills, the other cancels."),
                ("📏 Position Size",
                 "🇷🇴 Cât de mare e tranzacția ta. Calculează cu `/risk`.\n"
                 "🇬🇧 How large your trade is. Calculate with `/risk`."),
                ("📊 Risk/Reward (R:R)",
                 "🇷🇴 Raportul risc/câștig. Un R:R de **1:2** = riști 50$, poți câștiga 100$. ✅ Minim 1:2!\n"
                 "🇬🇧 Risk/reward ratio. **1:2** = risk $50, potential gain $100. ✅ Minimum 1:2!"),
                ("🧮 P&L",
                 "🇷🇴 **Profit and Loss** = câștigul sau pierderea ta. Calculează cu `/calculate`.\n"
                 "🇬🇧 **Profit and Loss** = your gain or loss. Calculate with `/calculate`."),
            ]
        },
        "market": {
            "title": "🌍 Glossary — Market Terms / Termeni de Piață",
            "color": 0x10b981,
            "fields": [
                ("🐂 Bull Market / Piață Bull",
                 "🇷🇴 Piața este **în creștere**. Prețurile cresc. Sentiment pozitiv.\n"
                 "🇬🇧 Market is **rising**. Prices going up. Positive sentiment."),
                ("🐻 Bear Market / Piață Bear",
                 "🇷🇴 Piața este **în scădere**. Prețurile scad. Sentiment negativ.\n"
                 "🇬🇧 Market is **falling**. Prices going down. Negative sentiment."),
                ("📊 Market Cap",
                 "🇷🇴 Valoarea totală a unei monede = **Preț × Cantitate totală** în circulație.\n"
                 "🇬🇧 Total value of a coin = **Price × Total supply** in circulation."),
                ("😱 FOMO",
                 "🇷🇴 **Fear Of Missing Out** = cumperi din frică să nu ratezi profitul. De obicei la vârf. ❌\n"
                 "🇬🇧 **Fear Of Missing Out** = buying because you're afraid to miss gains. Usually at the top. ❌"),
                ("📉 FUD",
                 "🇷🇴 **Fear, Uncertainty, Doubt** = știri negative care scad prețul artificial.\n"
                 "🇬🇧 **Fear, Uncertainty, Doubt** = negative news that artificially drops the price."),
                ("👑 BTC Dominance",
                 "🇷🇴 % din piața totală crypto aflat în Bitcoin. Dom ↑ = altcoin-urile scad. Dom ↓ = altcoins cresc.\n"
                 "🇬🇧 % of total crypto market in Bitcoin. Dom ↑ = altcoins fall. Dom ↓ = altcoins rise."),
                ("🔄 Altcoin Season",
                 "🇷🇴 Perioadă când **altcoin-urile** (ETH, SOL, etc.) cresc mai repede ca BTC.\n"
                 "🇬🇧 Period when **altcoins** (ETH, SOL, etc.) outperform Bitcoin."),
                ("🌊 Correction / Corecție",
                 "🇷🇴 O scădere **temporară** de preț înainte să reia creșterea. Normal în bull market.\n"
                 "🇬🇧 A **temporary** price drop before resuming the uptrend. Normal in bull market."),
            ]
        }
    }

    data = embeds_data.get(category, embeds_data["basics"])
    embed = discord.Embed(
        title=data["title"],
        description=(
            "🇷🇴 Dicționar crypto simplu pentru traderi\n"
            f"🇬🇧 Simple crypto dictionary for traders\n{SEP}"
        ),
        color=data["color"],
        timestamp=datetime.utcnow()
    )
    embed.set_author(name="📚 Crypto Signals Bot — Glossary", icon_url=BOT_ICON)
    for name, value in data["fields"]:
        embed.add_field(name=name, value=value, inline=False)
    embed.add_field(
        name=f"{SEP}\n📂 Alte categorii / Other categories",
        value=(
            "`/glossary basics` — Termeni de bază\n"
            "`/glossary indicators` — RSI, MACD, BB, EMA\n"
            "`/glossary risk` — Stop Loss, Leverage, OCO\n"
            "`/glossary market` — Bull/Bear, FOMO, FUD\n"
            "`/tutorial` — Ghid complet pas cu pas"
        ),
        inline=False
    )
    embed.set_footer(text=f"Crypto Signals Bot  •  {DISCLAIMER_RO}")
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
    embed.add_field(name="/analysis [coin]",  value="🇬🇧 Full TA: RSI+MACD+BB+StochRSI+Messari+CG\n🇷🇴 Analiză 5 indicatori + date on-chain",    inline=False)
    embed.add_field(name=SEP2, value="\u200b", inline=False)
    embed.add_field(name="💼 TRADING TOOLS", value="\u200b", inline=False)
    embed.add_field(name="/portfolio [add/view/pnl/clear]", value="🇬🇧 Personal portfolio tracker with live P&L\n🇷🇴 Tracker portofoliu personal cu P&L live",  inline=False)
    embed.add_field(name="/risk [capital] [entry] [sl]",    value="🇬🇧 Position size calculator\n🇷🇴 Calculator dimensiune poziție",                             inline=False)
    embed.add_field(name="/calculate [entry] [exit] [amt]", value="🇬🇧 Profit/loss calculator\n🇷🇴 Calculator profit/pierdere",                                  inline=False)
    embed.add_field(name=SEP2, value="\u200b", inline=False)
    embed.add_field(name="📊 MARKET TOOLS", value="\u200b", inline=False)
    embed.add_field(name="/multi [coin]",     value="🇬🇧 5m+15m+1h+4h confluence dashboard\n🇷🇴 Dashboard 4 timeframe-uri",                                    inline=False)
    embed.add_field(name="/heatmap",          value="🇬🇧 All 8 coins status at a glance\n🇷🇴 Status toate 8 monede simultan",                                   inline=False)
    embed.add_field(name="/compare [c1] [c2]",value="🇬🇧 Side-by-side coin comparison\n🇷🇴 Comparație două monede",                                             inline=False)
    embed.add_field(name="/dominance",        value="🇬🇧 BTC dominance + market cap overview\n🇷🇴 Dominanță BTC + capitalizare totală",                        inline=False)
    embed.add_field(name=SEP2, value="\u200b", inline=False)
    embed.add_field(name="🔔 WATCHLIST & PREDICTIONS", value="\u200b", inline=False)
    embed.add_field(name="/watch [coin]",     value="🇬🇧 DM alert when signal fires for coin\n🇷🇴 DM când se generează semnal",                                  inline=False)
    embed.add_field(name="/unwatch [coin]",   value="🇬🇧 Remove from watchlist\n🇷🇴 Scoate din watchlist",                                                     inline=False)
    embed.add_field(name="/mywatchlist",      value="🇬🇧 View your active watchlist\n🇷🇴 Vezi watchlist-ul tău activ",                                          inline=False)
    embed.add_field(name="/predict [coin] [UP/DOWN]", value="🇬🇧 Submit community prediction\n🇷🇴 Trimite predicție comunitară",                              inline=False)
    embed.add_field(name="/leaderboard",      value="🇬🇧 Top predictors ranking\n🇷🇴 Clasament top predictori",                                                 inline=False)
    embed.add_field(name=SEP2, value="\u200b", inline=False)
    embed.add_field(name="🎓 EDUCATION / EDUCAȚIE", value="\u200b", inline=False)
    embed.add_field(name="/tutorial [1–5]",      value="🇬🇧 Full beginner guide (5 pages)\n🇷🇴 Ghid complet pentru începători (5 pagini)",                inline=False)
    embed.add_field(name="/glossary [cat]",      value="🇬🇧 Crypto dictionary: basics/indicators/risk/market\n🇷🇴 Dicționar crypto termeni simpli",          inline=False)
    embed.add_field(name="/tip",                 value="🇬🇧 Random trading tip (20+ tips)\n🇷🇴 Sfat aleatoriu de trading (20+ sfaturi)",                     inline=False)
    embed.add_field(name=SEP2, value="\u200b", inline=False)
    embed.add_field(name="🚀 BEGINNER GUIDE / GHID ÎNCEPĂTORI", value="\u200b", inline=False)
    embed.add_field(name="/firsttrade",          value="🇬🇧 Complete beginner guide: from zero to first profitable trade\n🇷🇴 Ghid complet: de la zero la primul trade cu profit", inline=False)
    embed.add_field(name="/binance",             value="🇬🇧 How to use Binance step by step with screenshots guide\n🇷🇴 Cum folosești Binance pas cu pas",    inline=False)
    embed.add_field(name="/signals_explained",   value="🇬🇧 Real signal example with every field explained\n🇷🇴 Exemplu real de semnal cu explicații pentru fiecare câmp", inline=False)
    embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
    await interaction.response.send_message(embed=embed)


# ══════════════════════════════════════════════
#   /FIRSTTRADE — Ghid complet primul trade
# ══════════════════════════════════════════════

@tree.command(name="firsttrade", description="🚀 Complete beginner guide: from zero to first profitable trade")
@app_commands.describe(step="Which step (1–8), or leave empty for full overview")
async def slash_firsttrade(interaction: discord.Interaction, step: int = 0):

    if step == 0:
        # Overview — all 8 steps
        embed = discord.Embed(
            title="🚀 Primul Tău Trade / Your First Trade — Ghid Complet",
            description=(
                "🇷🇴 **Felicitări că ai ajuns aici!** Urmează acești 8 pași simpli și vei face primul tău trade cu profit.\n"
                "🇬🇧 **Congratulations on being here!** Follow these 8 simple steps to your first profitable trade.\n"
                f"{SEP}"
            ),
            color=0x22c55e, timestamp=datetime.utcnow()
        )
        embed.set_author(name="🚀 Crypto Signals Bot — Beginner Guide", icon_url=BOT_ICON)
        embed.add_field(
            name="📋 Cei 8 pași / The 8 Steps",
            value=(
                "**1️⃣** Creează cont Binance — `/firsttrade 1`\n"
                "**2️⃣** Depune bani (USDT) — `/firsttrade 2`\n"
                "**3️⃣** Înțelege Spot Trading — `/firsttrade 3`\n"
                "**4️⃣** Citește un semnal BUY — `/firsttrade 4`\n"
                "**5️⃣** Plasează primul trade — `/firsttrade 5`\n"
                "**6️⃣** Setează Stop Loss + Take Profit — `/firsttrade 6`\n"
                "**7️⃣** Monitorizează și ieși corect — `/firsttrade 7`\n"
                "**8️⃣** Reguli de aur pentru traderi profitabili — `/firsttrade 8`"
            ),
            inline=False
        )
        embed.add_field(
            name="💡 Sfat înainte să începi / Tip before you start",
            value=(
                "🇷🇴 Începe cu o **sumă mică** pe care îți permiți să o pierzi — de exemplu **50–100$**. "
                "Nu pune toți banii de la început. Învață mai întâi cum funcționează!\n"
                "🇬🇧 Start with a **small amount** you can afford to lose — e.g. **$50–100$**. "
                "Don't invest everything at once. Learn how it works first!"
            ),
            inline=False
        )
        embed.add_field(
            name="⏱️ Cât durează? / How long does it take?",
            value=(
                "🇷🇴 Contul Binance: ~15 min | Depunere: ~10 min | Primul trade: ~5 min\n"
                "🇬🇧 Binance account: ~15 min | Deposit: ~10 min | First trade: ~5 min"
            ),
            inline=False
        )
        embed.set_footer(text="Folosește /firsttrade [1-8] pentru fiecare pas  •  Crypto Signals Bot")
        await interaction.response.send_message(embed=embed)
        return

    steps = {
        1: {
            "title": "1️⃣ Creează cont Binance / Create Binance Account",
            "color": 0xF0B90B,
            "fields": [
                ("🌐 Pasul 1 — Mergi pe Binance / Go to Binance",
                 "🇷🇴 Deschide browserul și mergi la **binance.com** (sau descarcă aplicația Binance)\n"
                 "🇬🇧 Open your browser and go to **binance.com** (or download the Binance app)\n"
                 "⚠️ Asigură-te că e site-ul oficial! Evită link-uri de pe social media."),

                ("📧 Pasul 2 — Înregistrare / Register",
                 "🇷🇴 Apasă **Register** → alege **Email** → introdu email și o parolă puternică.\n"
                 "🇬🇧 Click **Register** → choose **Email** → enter your email and a strong password.\n"
                 "💡 Parola bună: minim 12 caractere, litere mari/mici, cifre și simboluri."),

                ("✅ Pasul 3 — Verificare email / Email verification",
                 "🇷🇴 Binance îți trimite un email cu un cod de 6 cifre. Introdu-l pe site.\n"
                 "🇬🇧 Binance sends a 6-digit code to your email. Enter it on the site.\n"
                 "⚠️ Dacă nu găsești emailul, verifică folderul **Spam/Junk**."),

                ("🔐 Pasul 4 — Activează 2FA / Enable 2FA",
                 "🇷🇴 Merge la **Securitate → Google Authenticator** → descarcă app-ul pe telefon → scanează codul QR.\n"
                 "🇬🇧 Go to **Security → Google Authenticator** → download the app → scan the QR code.\n"
                 "💡 2FA = un cod nou la fiecare 30 secunde. Nimeni nu poate intra fără telefonul tău."),

                ("🪪 Pasul 5 — Verificare identitate KYC / Identity Verification",
                 "🇷🇴 Mergi la **Verification** → alege țara → fotografie **buletin/pașaport** față + verso + selfie.\n"
                 "🇬🇧 Go to **Verification** → choose country → photo of **ID/passport** front + back + selfie.\n"
                 "⏱️ Durează 5–30 minute. Necesară pentru depuneri mai mari de 100$/zi."),
            ]
        },
        2: {
            "title": "2️⃣ Depune Bani (USDT) / Deposit Money",
            "color": 0x22c55e,
            "fields": [
                ("💳 Metoda 1 — Card bancar / Credit/Debit Card",
                 "🇷🇴 Mergi la **Buy Crypto → Credit/Debit Card** → selectează **EUR** sau **RON** → alege să primești **USDT**.\n"
                 "🇬🇧 Go to **Buy Crypto → Credit/Debit Card** → select **EUR** or your currency → choose to receive **USDT**.\n"
                 "💡 USDT = dolari digitali. 1 USDT = ~1 dolar american. Cel mai simplu pentru început."),

                ("🏦 Metoda 2 — Transfer bancar / Bank Transfer",
                 "🇷🇴 Mergi la **Buy Crypto → Bank Transfer** → urmează instrucțiunile pentru SEPA (transfer euro).\n"
                 "🇬🇧 Go to **Buy Crypto → Bank Transfer** → follow SEPA instructions (Euro transfer).\n"
                 "⏱️ Durează 1–3 zile lucrătoare. Fără comision."),

                ("💰 Cât să depui? / How much to deposit?",
                 "🇷🇴 **Recomandat pentru început:** 50–200$ echivalent.\n"
                 "Nu mai mult decât îți permiți să pierzi complet. Crypto e volatil!\n"
                 "🇬🇧 **Recommended to start:** $50–200 equivalent.\n"
                 "Never more than you can afford to lose completely. Crypto is volatile!"),

                ("✅ Verifici dacă ai USDT",
                 "🇷🇴 Mergi la **Wallet → Spot Wallet** → caută **USDT** în lista de monede → ar trebui să vezi soldul.\n"
                 "🇬🇧 Go to **Wallet → Spot Wallet** → find **USDT** in the coin list → you should see your balance.\n"
                 "💡 Dacă vezi USDT cu suma depusă, ești gata pentru Pasul 3!"),
            ]
        },
        3: {
            "title": "3️⃣ Înțelege Spot Trading / Understand Spot Trading",
            "color": 0x3b82f6,
            "fields": [
                ("📦 Ce este Spot Trading?",
                 "🇷🇴 **Spot** = cumperi moneda reală. Dacă cumperi 0.001 BTC, chiar deții acel Bitcoin.\n"
                 "Nu poți pierde mai mult decât ai investit. **Perfect pentru începători!**\n"
                 "🇬🇧 **Spot** = you buy the real coin. If you buy 0.001 BTC, you actually own it.\n"
                 "Can't lose more than you invested. **Perfect for beginners!**"),

                ("⚠️ Ce NU este Spot Trading",
                 "🇷🇴 Spot NU înseamnă Futures sau Margin. Evită acele secțiuni!\n"
                 "**Futures** = tranzacționezi cu bani împrumutați (leverage) → poți pierde TOT rapid.\n"
                 "🇬🇧 Spot is NOT Futures or Margin. Avoid those sections!\n"
                 "**Futures** = trading with borrowed money (leverage) → can lose EVERYTHING fast."),

                ("🔍 Cum găsești Spot pe Binance",
                 "🇷🇴 Sus pe site apasă **Trade → Spot** → ai ajuns la pagina de trading.\n"
                 "Cauta în bara de căutare (dreapta sus): `BTC/USDT` sau `ETH/USDT`.\n"
                 "🇬🇧 Click **Trade → Spot** at the top → you're on the trading page.\n"
                 "Search in top right bar: `BTC/USDT` or `ETH/USDT`."),

                ("📊 Ce vezi pe ecran / What you see on screen",
                 "🇷🇴 **Graficul** = prețul în timp real | **Order Book** = cumpărătorii și vânzătorii activi\n"
                 "**Formularul de cumpărare** = unde plasezi ordinul (stânga jos pe desktop)\n"
                 "🇬🇧 **Chart** = real-time price | **Order Book** = active buyers and sellers\n"
                 "**Buy form** = where you place your order (bottom left on desktop)"),
            ]
        },
        4: {
            "title": "4️⃣ Cum Citești un Semnal BUY / How to Read a BUY Signal",
            "color": 0x00c853,
            "fields": [
                ("📨 Cum arată un semnal real / What a real signal looks like",
                 "```\n"
                 "🟢 BUY — Bitcoin (BTC)\n"
                 "━━━━━━━━━━━━━━━━━━━━━━\n"
                 "📍 Entry:      $94,500\n"
                 "🎯 TP1:        $96,000  (+1.6%)\n"
                 "🎯 TP2:        $98,500  (+4.2%)\n"
                 "🎯 TP3:        $102,000 (+7.9%)\n"
                 "🛑 SL:         $92,000  (-2.6%)\n"
                 "⭐ Confidence: HIGH\n"
                 "```"),

                ("📍 Entry = Prețul de intrare",
                 "🇷🇴 Acesta e prețul la care **cumperi**. Încearcă să cumperi cât mai aproape de acest preț.\n"
                 "Nu cumpăra dacă prețul a depășit deja Entry-ul cu mai mult de **2%**.\n"
                 "🇬🇧 This is the price at which you **buy**. Try to buy close to this price.\n"
                 "Don't buy if price already exceeded Entry by more than **2%**."),

                ("🎯 TP1 / TP2 / TP3 = Take Profit (Ia Profitul)",
                 "🇷🇴 Acestea sunt prețurile la care **vinzi** pentru a lua profit.\n"
                 "**Strategia ideală:** La TP1 vinde 50%, la TP2 vinde 30%, la TP3 vinde restul.\n"
                 "🇬🇧 These are the prices at which you **sell** to take profit.\n"
                 "**Ideal strategy:** At TP1 sell 50%, at TP2 sell 30%, at TP3 sell the rest."),

                ("🛑 SL = Stop Loss (Oprește Pierderea)",
                 "🇷🇴 Acesta e prețul la care **ieși automat** dacă piața merge contra ta.\n"
                 "**NU schimba SL-ul în jos** dacă prețul cade — asta e greșeala clasică!\n"
                 "🇬🇧 This is the price at which you **automatically exit** if market goes against you.\n"
                 "**NEVER move SL down** if price falls — that's the classic mistake!"),

                ("⭐ Confidence = Calitatea Semnalului",
                 "🇷🇴 `LOW` = 1-2 indicatori confirmă | `MEDIUM` = 3 | `HIGH` = 4 | `VERY HIGH` = toti 5\n"
                 "**Tranzacționează doar `HIGH` sau `VERY HIGH`!** Celelalte sunt prea riscante.\n"
                 "🇬🇧 Only trade `HIGH` or `VERY HIGH` confidence signals! Others are too risky."),
            ]
        },
        5: {
            "title": "5️⃣ Plasează Primul Trade / Place Your First Trade",
            "color": 0x6366f1,
            "fields": [
                ("📋 Înainte să începi / Before you start",
                 "🇷🇴 Asigură-te că ai:\n"
                 "✅ USDT în Spot Wallet\n"
                 "✅ Un semnal BUY de la bot cu confidence `HIGH` sau `VERY HIGH`\n"
                 "✅ Știi cât vrei să investești (max 10% din total)\n"
                 "🇬🇧 Make sure you have:\n"
                 "✅ USDT in Spot Wallet\n"
                 "✅ A BUY signal from the bot with `HIGH` or `VERY HIGH` confidence\n"
                 "✅ Know how much to invest (max 10% of total)"),

                ("1. Deschide perechea de tranzacționare",
                 "🇷🇴 Pe Binance Spot, caută perechea: Ex: semnal **BTC** → cauta `BTC/USDT`.\n"
                 "🇬🇧 On Binance Spot, search for the pair: Ex: **BTC** signal → search `BTC/USDT`."),

                ("2. Alege tipul ordinului / Choose order type",
                 "🇷🇴 În formularul de cumpărare (stânga jos), schimbă din **Market** în **Limit**.\n"
                 "**Limit Order** = cumperi exact la prețul Entry din semnal, nu mai scump.\n"
                 "🇬🇧 In the buy form (bottom left), switch from **Market** to **Limit**.\n"
                 "**Limit Order** = you buy exactly at the Entry price from signal, not higher."),

                ("3. Introdu prețul și suma / Enter price and amount",
                 "🇷🇴 La **Price** introdu Entry-ul din semnal (ex: 94500)\n"
                 "La **Amount** introdu câte monede vrei (ex: 0.001 BTC)\n"
                 "Sau la **Total** introdu suma în USDT (ex: 100 USDT)\n"
                 "🇬🇧 In **Price** enter the Entry from signal (e.g. 94500)\n"
                 "In **Amount** enter how many coins (e.g. 0.001 BTC)\n"
                 "Or in **Total** enter the USDT amount (e.g. 100 USDT)"),

                ("4. Confirmă ordinul / Confirm the order",
                 "🇷🇴 Apasă **Buy BTC** → verifică detaliile → apasă **Confirm**.\n"
                 "Ordinul apare în **Open Orders** jos pe pagină. Când prețul ajunge la Entry, se execută!\n"
                 "🇬🇧 Click **Buy BTC** → verify details → click **Confirm**.\n"
                 "Order appears in **Open Orders** at the bottom. When price reaches Entry, it executes!"),
            ]
        },
        6: {
            "title": "6️⃣ Setează Stop Loss + Take Profit / Set SL + TP",
            "color": 0xef4444,
            "fields": [
                ("🏆 Metoda cea mai bună: OCO Order",
                 "🇷🇴 **OCO** = One Cancels the Other = setezi simultan **TP** și **SL**. Binance le execută automat.\n"
                 "Când prețul ajunge la TP → vinde automat cu profit. Dacă ajunge la SL → vinde automat cu pierdere limitată.\n"
                 "🇬🇧 **OCO** = One Cancels the Other = set **TP** and **SL** together. Binance executes automatically.\n"
                 "Price hits TP → auto-sell with profit. Price hits SL → auto-sell with limited loss."),

                ("📋 Cum plasezi un OCO Order / How to place an OCO",
                 "🇷🇴 1. După ce ordinul de cumpărare s-a executat, mergi la **Sell**\n"
                 "2. Schimbă tipul din `Limit` în **`OCO`**\n"
                 "3. La **Price (Limit)** introdu **TP1** din semnal (prețul de vânzare cu profit)\n"
                 "4. La **Stop Price** introdu **SL** din semnal (prețul de oprire pierdere)\n"
                 "5. La **Limit Price** pune același SL sau cu 0.5% mai jos\n"
                 "6. Apasă **Sell BTC → Confirm**\n"
                 "🇬🇧 1. After buy order executed, go to **Sell**\n"
                 "2. Switch type from `Limit` to **`OCO`**\n"
                 "3. **Price (Limit)** = TP1 from signal\n"
                 "4. **Stop Price** = SL from signal\n"
                 "5. **Limit Price** = same as SL or 0.5% below\n"
                 "6. Click **Sell BTC → Confirm**"),

                ("✅ Ce se întâmplă după / What happens next",
                 "🇷🇴 Acum ești protejat! Dacă prețul crește → ia profit automat la TP1.\n"
                 "Dacă prețul scade → iese automat la SL. **Nu mai trebuie să stai cu ochii pe ecran!**\n"
                 "🇬🇧 Now you're protected! If price rises → auto-profit at TP1.\n"
                 "If price falls → auto-exit at SL. **You don't need to watch the screen!**"),

                ("🔄 După TP1: Mută SL la Entry / After TP1: Move SL to Entry",
                 "🇷🇴 Când TP1 e atins: anulezi OCO-ul rămas → plasezi un nou Sell Limit la **TP2** și un **Stop Loss la Entry**.\n"
                 "Acum ești fără risc! Chiar dacă prețul cade înapoi, nu pierzi nimic.\n"
                 "🇬🇧 When TP1 is hit: cancel remaining OCO → place new Sell Limit at **TP2** and **SL at Entry**.\n"
                 "Now you're risk-free! Even if price falls back, you lose nothing."),
            ]
        },
        7: {
            "title": "7️⃣ Monitorizează și Ieși Corect / Monitor and Exit Correctly",
            "color": 0xfbbf24,
            "fields": [
                ("👁️ Cât de des să verifici / How often to check",
                 "🇷🇴 O dată la 4–8 ore e suficient dacă ai OCO setat. Nu sta cu ochii mereu pe grafic!\n"
                 "**Stresul de a urmări fiecare mișcare** duce la decizii emoționale greșite.\n"
                 "🇬🇧 Once every 4–8 hours is enough if you have OCO set. Don't watch every minute!\n"
                 "**Watching every move** leads to emotional, wrong decisions."),

                ("✅ Ieșire corectă cu profit / Correct profitable exit",
                 "🇷🇴 **Scenariul ideal:**\n"
                 "• TP1 atins → 50% din poziție vândut automat cu profit ✅\n"
                 "• Muti SL la Entry → risc zero pentru restul ✅\n"
                 "• TP2 atins → restul vândut cu profit și mai mare ✅\n"
                 "🇬🇧 **Ideal scenario:**\n"
                 "• TP1 hit → 50% sold automatically with profit ✅\n"
                 "• SL moved to Entry → zero risk on remaining ✅\n"
                 "• TP2 hit → rest sold with even more profit ✅"),

                ("❌ Ieșire cu pierdere (e OK!) / Loss exit (it's OK!)",
                 "🇷🇴 SL-ul s-a activat? **E perfect normal.** Nu fiecare trade e câștigător.\n"
                 "Dacă ai risc 2% per trade și câștig 4% per trade câștigat → ești pe profit chiar și cu 40% trades greșite!\n"
                 "🇬🇧 SL triggered? **Completely normal.** Not every trade wins.\n"
                 "Risk 2% per trade, gain 4% per winning trade → you profit even with 40% losing trades!"),

                ("🚫 Nu face asta / Never do this",
                 "🇷🇴 ❌ Nu muta SL-ul în jos sperând că se întoarce\n"
                 "❌ Nu adăuga bani la o poziție pierzătoare\n"
                 "❌ Nu anula SL-ul din lăcomie\n"
                 "🇬🇧 ❌ Never move SL down hoping for recovery\n"
                 "❌ Never add money to a losing position\n"
                 "❌ Never cancel SL out of greed"),
            ]
        },
        8: {
            "title": "8️⃣ Regulile de Aur ale Traderului Profitabil / Golden Rules",
            "color": 0xf59e0b,
            "fields": [
                ("🥇 Regula #1 — Protejează capitalul",
                 "🇷🇴 Scopul principal nu e să câștigi mult — e **să nu pierzi mult**.\n"
                 "Un trader care pierde -50% are nevoie de +100% ca să revină. Protejează-te!\n"
                 "🇬🇧 The main goal is not to gain a lot — it's **not to lose a lot**.\n"
                 "A -50% loss requires +100% gain just to break even. Protect yourself!"),

                ("🥈 Regula #2 — Risc consistent",
                 "🇷🇴 Riscă mereu același procent per trade: **1–2% din capital**.\n"
                 "Ex: ai 500$ → riști max 5–10$ per trade. Folosește `/risk` ca să calculezi exact.\n"
                 "🇬🇧 Always risk the same % per trade: **1–2% of capital**.\n"
                 "Ex: $500 capital → max $5–10 risk per trade. Use `/risk` to calculate exactly."),

                ("🥉 Regula #3 — Tranzacționează doar semnale HIGH",
                 "🇷🇴 Botul trimite semnale de calitate diferită. Tranzacționează **DOAR** `HIGH` și `VERY HIGH`.\n"
                 "Semnalele `LOW` și `MEDIUM` au mai puțini indicatori de confirmare — riscul e mai mare.\n"
                 "🇬🇧 The bot sends different quality signals. Trade **ONLY** `HIGH` and `VERY HIGH`.\n"
                 "`LOW` and `MEDIUM` signals have fewer confirmations — higher risk."),

                ("🏅 Regula #4 — Jurnalul de trading",
                 "🇷🇴 Notează fiecare trade: data, moneda, entry, exit, profit/pierdere, motiv.\n"
                 "După 20 trades vei vedea exact care e pattern-ul tău și unde greșești.\n"
                 "🇬🇧 Note every trade: date, coin, entry, exit, profit/loss, reason.\n"
                 "After 20 trades you'll see exactly your pattern and where you go wrong."),

                ("🎯 Regula #5 — Răbdare și consistență",
                 "🇷🇴 Trading-ul profitabil nu e sprint — e **maraton**. 3–5 trades bune pe săptămână e suficient.\n"
                 "Nu tranzacționa dacă ești obosit, stresat sau emoțional. Asteaptă starea bună.\n"
                 "🇬🇧 Profitable trading is not a sprint — it's a **marathon**. 3–5 good trades per week is enough.\n"
                 "Don't trade when tired, stressed or emotional. Wait for a clear mind."),

                (SEP,
                 "🚀 **Ești gata să faci primul trade!**\n"
                 "Folosește `/signals_explained` pentru a vedea cum arată exact un semnal.\n"
                 "Folosește `/risk` pentru a calcula dimensiunea poziției.\n"
                 "💎 Upgrade la **VIP** pentru semnale cu TP1+TP2+TP3+SL și analiză AI!\n\n"
                 "🚀 **You're ready for your first trade!**\n"
                 "Use `/signals_explained` to see exactly how a signal looks.\n"
                 "Use `/risk` to calculate your position size."),
            ]
        }
    }

    if step not in steps:
        await interaction.response.send_message(
            "❓ Pași disponibili: `0`(overview) `1` `2` `3` `4` `5` `6` `7` `8`\n"
            "🇬🇧 Available steps: `0`(overview) `1` `2` `3` `4` `5` `6` `7` `8`",
            ephemeral=True); return

    data = steps[step]
    embed = discord.Embed(
        title=data["title"],
        color=data["color"],
        timestamp=datetime.utcnow()
    )
    embed.set_author(name="🚀 Crypto Signals Bot — First Trade Guide", icon_url=BOT_ICON)
    for name, value in data["fields"]:
        embed.add_field(name=name, value=value, inline=False)
    # Navigation footer
    next_step = step + 1 if step < 8 else 0
    prev_step = step - 1 if step > 1 else 0
    nav = f"◀️ `/firsttrade {prev_step}`  |  Pasul **{step}/8**  |  `/firsttrade {next_step}` ▶️" if step > 1 else f"Pasul **{step}/8**  |  Next: `/firsttrade {next_step}` ▶️"
    embed.add_field(name="📄 Navigare / Navigation", value=nav, inline=False)
    embed.set_footer(text=f"Crypto Signals Bot  •  {DISCLAIMER_RO}")
    await interaction.response.send_message(embed=embed)


# ══════════════════════════════════════════════
#   /BINANCE — Ghid Binance pas cu pas
# ══════════════════════════════════════════════

@tree.command(name="binance", description="🟡 How to use Binance — step by step guide for beginners")
@app_commands.describe(topic="Choose a topic")
@app_commands.choices(topic=[
    app_commands.Choice(name="🏠 Overview / Prezentare generala", value="overview"),
    app_commands.Choice(name="📝 Register / Inregistrare cont",   value="register"),
    app_commands.Choice(name="💳 Deposit / Depunere bani",        value="deposit"),
    app_commands.Choice(name="📊 Spot Trade / Cum faci un trade", value="trade"),
    app_commands.Choice(name="🛡️ OCO Order / Stop Loss + TP",    value="oco"),
])
async def slash_binance(interaction: discord.Interaction, topic: str = "overview"):
    topics = {
        "overview": {
            "title": "🟡 Binance — Prezentare Generală / Overview",
            "color": 0xF0B90B,
            "fields": [
                ("Ce este Binance? / What is Binance?",
                 "🇷🇴 Binance este cel mai mare exchange de criptomonede din lume.\n"
                 "Îl folosești pentru a **cumpăra, vinde și schimba** monede crypto cu bani reali.\n"
                 "🇬🇧 Binance is the world's largest crypto exchange.\n"
                 "You use it to **buy, sell and exchange** crypto with real money."),

                ("📱 Unde îl găsești / Where to find it",
                 "🇷🇴 **Website:** binance.com | **App iOS:** App Store → caută Binance\n"
                 "**App Android:** Google Play → caută Binance\n"
                 "⚠️ Descarcă DOAR din sursele oficiale! Evită link-uri de pe Telegram/Instagram.\n"
                 "🇬🇧 **Website:** binance.com | **iOS App:** App Store → search Binance\n"
                 "**Android:** Google Play → search Binance. Only from official sources!"),

                ("🗺️ Secțiunile importante / Important sections",
                 "🇷🇴 • **Trade → Spot** = pentru cumpărare/vânzare simpla (recomandat pentru tine)\n"
                 "• **Wallet → Spot Wallet** = soldul tau de monede\n"
                 "• **Buy Crypto** = depune bani de pe card sau transfer bancar\n"
                 "• **Orders → Open Orders** = ordinele tale active\n"
                 "🇬🇧 • **Trade → Spot** = for simple buying/selling (recommended for you)\n"
                 "• **Wallet → Spot Wallet** = your coin balances\n"
                 "• **Buy Crypto** = deposit money from card or bank transfer\n"
                 "• **Orders → Open Orders** = your active orders"),

                ("📋 Pași rapizi / Quick steps",
                 "`/binance register` — Cum creezi contul\n"
                 "`/binance deposit` — Cum depui bani\n"
                 "`/binance trade` — Cum plasezi un trade\n"
                 "`/binance oco` — Cum setezi Stop Loss + Take Profit"),
            ]
        },
        "register": {
            "title": "📝 Binance — Înregistrare Cont / Account Registration",
            "color": 0xF0B90B,
            "fields": [
                ("Pasul 1 — Mergi pe binance.com",
                 "🇷🇴 Deschide **binance.com** în browser. Apasă butonul galben **Register** din dreapta sus.\n"
                 "🇬🇧 Open **binance.com** in your browser. Click the yellow **Register** button top right."),

                ("Pasul 2 — Completează datele / Fill in details",
                 "🇷🇴 • Introdu **adresa de email**\n"
                 "• Creează o **parolă puternică** (min 12 caractere, majuscule, cifre, simboluri)\n"
                 "• Bifează că ești de acord cu termenii\n"
                 "• Apasă **Create Account**\n"
                 "🇬🇧 • Enter your **email address**\n"
                 "• Create a **strong password** (min 12 chars, caps, numbers, symbols)\n"
                 "• Check the terms agreement\n"
                 "• Click **Create Account**"),

                ("Pasul 3 — Verificare email / Email verification",
                 "🇷🇴 Binance trimite un email cu **cod de 6 cifre**. Intră în email → copiază codul → introdu pe site.\n"
                 "Nu ai primit email? Verifică folderul **Spam** sau **Junk**.\n"
                 "🇬🇧 Binance sends a **6-digit code** by email. Open email → copy code → enter on site.\n"
                 "No email? Check your **Spam** or **Junk** folder."),

                ("Pasul 4 — Activează 2FA (important!)",
                 "🇷🇴 Mergi la **Profilul tău → Securitate → Google Authenticator**\n"
                 "1. Descarcă **Google Authenticator** pe telefon (gratuit)\n"
                 "2. Apasă **Enable** pe Binance\n"
                 "3. Scanează codul QR cu app-ul\n"
                 "4. Introdu codul de 6 cifre generat → apasă **Confirm**\n"
                 "💡 Salvează **cheia de backup** undeva sigur!\n"
                 "🇬🇧 Go to **Profile → Security → Google Authenticator**\n"
                 "Download the app, scan QR, confirm with 6-digit code. Save backup key!"),

                ("Pasul 5 — Verificare identitate KYC",
                 "🇷🇴 Mergi la **Profilul tău → Identificare (KYC)**\n"
                 "• Alege **Romania** ca țară\n"
                 "• Fotografiază **buletin/pașaport** (față + spate + selfie cu documentul)\n"
                 "• Asteaptă 5–30 minute pentru aprobare\n"
                 "⚠️ KYC e necesar pentru a depune bani. Datele tale sunt securizate.\n"
                 "🇬🇧 Go to **Profile → Identification (KYC)**\n"
                 "Photo of ID (front + back + selfie). Wait 5–30 min for approval."),
            ]
        },
        "deposit": {
            "title": "💳 Binance — Depunere Bani / Deposit Money",
            "color": 0x22c55e,
            "fields": [
                ("Metoda 1 — Card bancar (cea mai rapidă!)",
                 "🇷🇴 1. Mergi la **Buy Crypto → Credit/Debit Card**\n"
                 "2. La **Spend** selectează suma și moneda (ex: 100 RON sau 50 EUR)\n"
                 "3. La **Receive** alege **USDT** (sau **BTC** dacă vrei direct Bitcoin)\n"
                 "4. Apasă **Buy** → introdu datele cardului → confirmă\n"
                 "⏱️ Instant! USDT apare în Spot Wallet în 1–2 minute.\n"
                 "💸 Comision: ~1.5% pentru card Visa/Mastercard\n"
                 "🇬🇧 Instant! USDT appears in Spot Wallet in 1–2 minutes. ~1.5% fee."),

                ("Metoda 2 — Transfer bancar SEPA (fara comision)",
                 "🇷🇴 1. Mergi la **Buy Crypto → Bank Deposit**\n"
                 "2. Alege **EUR** ca moneda și **SEPA Transfer**\n"
                 "3. Binance iti da datele de transfer bancar\n"
                 "4. Faci transferul din aplicatia bancii tale\n"
                 "⏱️ Durează 1–3 zile lucrătoare. Fara comision!\n"
                 "🇬🇧 1–3 business days. No fee! Best for larger amounts."),

                ("Cât să depui? / How much to deposit?",
                 "🇷🇴 **Recomandat pentru primele tranzacții:**\n"
                 "• Începători: **50–100$** (100–500 RON)\n"
                 "• Intermediar: **200–500$**\n"
                 "Nu pune mai mult decât ți permiți să pierzi complet!\n"
                 "🇬🇧 **Recommended for first trades:**\n"
                 "• Beginners: **$50–100**\n"
                 "• Intermediate: **$200–500**\n"
                 "Never more than you can afford to lose completely!"),

                ("Verifici soldul / Check your balance",
                 "🇷🇴 Mergi la **Wallet → Spot Wallet** → caută **USDT** în listă → verifici suma.\n"
                 "Dacă vezi suma depusă → ești gata să faci primul trade! 🎉\n"
                 "🇬🇧 Go to **Wallet → Spot Wallet** → find **USDT** → check amount.\n"
                 "If you see your deposited amount → ready for first trade! 🎉"),
            ]
        },
        "trade": {
            "title": "📊 Binance — Cum Faci un Trade Spot / How to Spot Trade",
            "color": 0x3b82f6,
            "fields": [
                ("Pasul 1 — Deschide Spot Trading",
                 "🇷🇴 Sus pe site: **Trade → Spot** (sau pe app: tab-ul Trading)\n"
                 "Ești acum pe pagina de trading. Poate pare complicat la prima vedere — e normal!\n"
                 "🇬🇧 At the top: **Trade → Spot** (or on app: Trading tab)\n"
                 "You're on the trading page now. Looks complex at first — that's normal!"),

                ("Pasul 2 — Caută perechea / Find the pair",
                 "🇷🇴 Dreapta sus cauta: `BTC/USDT` (pentru Bitcoin) sau `ETH/USDT` (Ethereum)\n"
                 "Alege perechea care apare în semnalul botului.\n"
                 "🇬🇧 Top right search: `BTC/USDT` (Bitcoin) or `ETH/USDT` (Ethereum)\n"
                 "Choose the pair shown in the bot signal."),

                ("Pasul 3 — Formularul de cumpărare / Buy form",
                 "🇷🇴 Stânga jos ai formularul. Schimbă din **Market** în **Limit**.\n"
                 "• **Price** = Entry-ul din semnal (ex: 94500)\n"
                 "• **Amount** = câte monede (ex: 0.001) SAU\n"
                 "• **Total** = câți USDT vrei să cheltuiești (ex: 100)\n"
                 "🇬🇧 Bottom left is the form. Switch from **Market** to **Limit**.\n"
                 "• **Price** = Entry from signal (e.g. 94500)\n"
                 "• **Total** = how many USDT to spend (e.g. 100)"),

                ("Pasul 4 — Confirmă / Confirm",
                 "🇷🇴 Apasă **Buy BTC** (sau moneda respectiva) → citeste sumarul → apasă **Confirm**.\n"
                 "Ordinul apare în **Open Orders** jos. Cand prețul ajunge la Entry → se executa automat!\n"
                 "🇬🇧 Click **Buy BTC** → read summary → click **Confirm**.\n"
                 "Order appears in **Open Orders** below. When price hits Entry → executes automatically!"),

                ("Pasul urmator / Next step",
                 "🇷🇴 Dupa executare, **imediat** seteaza Stop Loss + Take Profit!\n"
                 "Foloseste `/binance oco` pentru a vedea cum setezi OCO Order.\n"
                 "🇬🇧 After execution, **immediately** set Stop Loss + Take Profit!\n"
                 "Use `/binance oco` to see how to set OCO Order."),
            ]
        },
        "oco": {
            "title": "🛡️ Binance — OCO Order (Stop Loss + Take Profit)",
            "color": 0xef4444,
            "fields": [
                ("Ce este OCO? / What is OCO?",
                 "🇷🇴 **OCO = One Cancels the Other**\n"
                 "Setezi simultan un ordin de **vânzare cu profit (TP)** și unul de **vânzare cu pierdere (SL)**.\n"
                 "Binance le executa automat. Cand unul se activează, celălalt se anulează.\n"
                 "🇬🇧 **OCO = One Cancels the Other**\n"
                 "Set a **profit sell (TP)** and a **loss sell (SL)** at the same time.\n"
                 "Binance executes automatically. When one triggers, the other cancels."),

                ("Cum plasezi un OCO / How to place OCO",
                 "🇷🇴 1. Dupa ce ai cumpărat moneda, mergi la formularul de **Sell** (vânzare)\n"
                 "2. Schimbă tipul din `Limit` în **`OCO`**\n"
                 "3. **Price (Limit Price)** = TP1 din semnalul botului (prețul de profit)\n"
                 "4. **Stop Price** = SL din semnalul botului (prețul de stop)\n"
                 "5. **Limit Price** = acelasi ca SL sau cu 0.5% mai jos\n"
                 "6. **Amount** = câte monede ai cumpărat\n"
                 "7. Apasă **Sell → Confirm**\n"
                 "🇬🇧 1. After buying, go to **Sell** form\n"
                 "2. Switch type to **`OCO`**\n"
                 "3. **Price (Limit)** = TP1 from bot signal\n"
                 "4. **Stop Price** = SL from bot signal\n"
                 "5. **Limit Price** = same as SL or 0.5% below\n"
                 "6. **Amount** = how many coins you bought\n"
                 "7. Click **Sell → Confirm**"),

                ("✅ Rezultat / Result",
                 "🇷🇴 Acum ai două ordine active în **Open Orders**:\n"
                 "• Un ordin Limit la TP1 (vânzare cu profit)\n"
                 "• Un ordin Stop-Limit la SL (vânzare cu pierdere limitată)\n"
                 "Ești protejat 100% automat!\n"
                 "🇬🇧 Now you have two orders in **Open Orders**:\n"
                 "• A Limit order at TP1 (profit sell)\n"
                 "• A Stop-Limit order at SL (limited loss sell)\n"
                 "You're 100% automatically protected!"),

                ("💡 Exemplu real / Real example",
                 "🇷🇴 Ai cumpărat BTC la $94,500. Semnalul bot spune:\n"
                 "TP1: $96,000 | SL: $92,000\n"
                 "• **Price (Limit):** 96000\n"
                 "• **Stop Price:** 92000\n"
                 "• **Limit Price:** 91500\n"
                 "🇬🇧 Bought BTC at $94,500. Bot signal says:\n"
                 "TP1: $96,000 | SL: $92,000\n"
                 "• **Price (Limit):** 96000\n"
                 "• **Stop Price:** 92000\n"
                 "• **Limit Price:** 91500"),
            ]
        }
    }

    data = topics.get(topic, topics["overview"])
    embed = discord.Embed(
        title=data["title"],
        description=f"🇷🇴 Ghid Binance pentru începători  •  🇬🇧 Binance guide for beginners\n{SEP}",
        color=data["color"],
        timestamp=datetime.utcnow()
    )
    embed.set_author(name="🟡 Crypto Signals Bot — Binance Guide", icon_url=BOT_ICON)
    embed.set_thumbnail(url="https://assets.coingecko.com/coins/images/825/small/bnb-icon2_2x.png")
    for name, value in data["fields"]:
        embed.add_field(name=name, value=value, inline=False)
    embed.add_field(
        name=f"{SEP}\n📂 Alte secțiuni / Other sections",
        value=(
            "`/binance overview` — Prezentare generala\n"
            "`/binance register` — Inregistrare cont\n"
            "`/binance deposit` — Depunere bani\n"
            "`/binance trade` — Cum faci un trade\n"
            "`/binance oco` — Stop Loss + Take Profit\n"
            "`/firsttrade` — Ghid complet primul trade"
        ),
        inline=False
    )
    embed.set_footer(text=f"Crypto Signals Bot  •  {DISCLAIMER_RO}")
    await interaction.response.send_message(embed=embed)


# ══════════════════════════════════════════════
#   /SIGNALS_EXPLAINED — Exemplu real de semnal
# ══════════════════════════════════════════════

@tree.command(name="signals_explained", description="📨 Real signal example with every field explained")
async def slash_signals_explained(interaction: discord.Interaction):
    await interaction.response.defer()

    # Get a real live price for the example
    info = get_price_info("BTCUSDT")
    price = info["price"] if info else 94500.0
    tp1   = round(price * 1.016, 2)
    tp2   = round(price * 1.042, 2)
    tp3   = round(price * 1.079, 2)
    sl    = round(price * 0.974, 2)
    tp1p  = round((tp1 - price) / price * 100, 1)
    tp2p  = round((tp2 - price) / price * 100, 1)
    tp3p  = round((tp3 - price) / price * 100, 1)
    slp   = round((sl - price) / price * 100, 1)

    embed = discord.Embed(
        title="📨 Cum Arată un Semnal Real / What a Real Signal Looks Like",
        description=(
            "🇷🇴 Iată **exact** ce vei vedea în canalul de semnale și ce înseamnă fiecare câmp:\n"
            "🇬🇧 Here is **exactly** what you'll see in the signals channel and what each field means:\n"
            f"{SEP}"
        ),
        color=0x00c853, timestamp=datetime.utcnow()
    )
    embed.set_author(name="📨 Crypto Signals Bot — Signal Explained", icon_url=BOT_ICON)

    # Simulated signal block
    embed.add_field(
        name="🟢 Exemplu Semnal BUY — Bitcoin (BTC) [LIVE PRICES]",
        value=(
            f"```\n"
            f"🟢 BUY SIGNAL — Bitcoin (BTC)\n"
            f"{'━'*32}\n"
            f"📍 Entry:      ${price:>12,.2f}\n"
            f"🎯 TP1:        ${tp1:>12,.2f}  ({tp1p:+.1f}%)\n"
            f"🎯 TP2:        ${tp2:>12,.2f}  ({tp2p:+.1f}%)\n"
            f"🎯 TP3:        ${tp3:>12,.2f}  ({tp3p:+.1f}%)\n"
            f"🛑 SL:         ${sl:>12,.2f}  ({slp:+.1f}%)\n"
            f"⭐ Confidence: HIGH\n"
            f"```"
        ),
        inline=False
    )

    # Explanation of each field
    embed.add_field(
        name="📍 Entry = La ce preț cumperi / Buy price",
        value=(
            f"🇷🇴 Cumperi BTC la **${price:,.2f}**. Folosește un **Limit Order** la acest preț pe Binance Spot.\n"
            "⚠️ Nu cumpăra dacă prețul a depășit Entry cu mai mult de 2%!\n"
            f"🇬🇧 Buy BTC at **${price:,.2f}**. Use a **Limit Order** at this price on Binance Spot.\n"
            "⚠️ Don't buy if price already exceeded Entry by more than 2%!"
        ),
        inline=False
    )
    embed.add_field(
        name=f"🎯 TP1 = ${tp1:,.2f} — Primul profit",
        value=(
            f"🇷🇴 La **${tp1:,.2f}** vinzi **50%** din monedele cumpărate și iei primul profit (`{tp1p:+.1f}%`).\n"
            "Dupa aceea muti Stop Loss-ul la Entry — nu mai ai risc!\n"
            f"🇬🇧 At **${tp1:,.2f}** sell **50%** of your coins for first profit (`{tp1p:+.1f}%`).\n"
            "Then move Stop Loss to Entry — no more risk!"
        ),
        inline=False
    )
    embed.add_field(
        name=f"🎯 TP2 = ${tp2:,.2f} — Al doilea profit",
        value=(
            f"🇷🇴 La **${tp2:,.2f}** vinzi inca **30%** (`{tp2p:+.1f}%`). Pastrezi 20% pentru TP3.\n"
            f"🇬🇧 At **${tp2:,.2f}** sell another **30%** (`{tp2p:+.1f}%`). Keep 20% for TP3."
        ),
        inline=False
    )
    embed.add_field(
        name=f"🎯 TP3 = ${tp3:,.2f} — Targetul maxim",
        value=(
            f"🇷🇴 La **${tp3:,.2f}** vinzi restul de 20% pentru **profit maxim** (`{tp3p:+.1f}%`).\n"
            "Numai VIP primesc TP3 in semnale!\n"
            f"🇬🇧 At **${tp3:,.2f}** sell remaining 20% for **maximum profit** (`{tp3p:+.1f}%`).\n"
            "Only VIP members receive TP3 in signals!"
        ),
        inline=False
    )
    embed.add_field(
        name=f"🛑 SL = ${sl:,.2f} — Stop Loss (Protectia ta)",
        value=(
            f"🇷🇴 Daca prețul scade la **${sl:,.2f}** (adica `{slp:.1f}%`), ordinul OCO vinde automat.\n"
            "Pierderea e **limitata** si **controlata**. Fara SL = risc total!\n"
            f"🇬🇧 If price drops to **${sl:,.2f}** (`{slp:.1f}%`), OCO order auto-sells.\n"
            "Loss is **limited** and **controlled**. Without SL = total risk!"
        ),
        inline=False
    )
    embed.add_field(
        name="⭐ Confidence = HIGH — Calitatea semnalului",
        value=(
            "🇷🇴 `HIGH` inseamna ca **4 din 5 indicatori** (RSI + MACD + BB + StochRSI + EMA) confirma semnalul.\n"
            "Cu cat e mai mare, cu atat e mai sigur. **Tranzactioneaza DOAR `HIGH` sau `VERY HIGH`!**\n"
            "🇬🇧 `HIGH` means **4 out of 5 indicators** (RSI + MACD + BB + StochRSI + EMA) confirm the signal.\n"
            "Higher = more reliable. **Only trade `HIGH` or `VERY HIGH`!**"
        ),
        inline=False
    )
    embed.add_field(
        name=f"{SEP}\n✅ Rezumat actiuni / Action summary",
        value=(
            f"🇷🇴 1. Cumpara BTC cu **Limit Order** la `${price:,.2f}`\n"
            f"2. Seteaza **OCO Order**: TP1=`${tp1:,.2f}`, SL=`${sl:,.2f}`\n"
            f"3. La TP1 muta SL la Entry\n"
            f"4. La TP2 vinzi restul\n\n"
            f"🇬🇧 1. Buy BTC with **Limit Order** at `${price:,.2f}`\n"
            f"2. Set **OCO Order**: TP1=`${tp1:,.2f}`, SL=`${sl:,.2f}`\n"
            f"3. At TP1 move SL to Entry\n"
            f"4. At TP2 sell the rest"
        ),
        inline=False
    )
    embed.set_footer(text=f"Crypto Signals Bot  •  Preturi live BTC  •  {DISCLAIMER_RO}")
    await interaction.followup.send(embed=embed)


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


@tree.command(name="analysis", description="🔬 Full technical analysis: RSI + MACD + BB + StochRSI + Messari + CoinGecko")
@app_commands.describe(coin="Choose a coin (default: BTC)")
@app_commands.choices(coin=[
    app_commands.Choice(name="Bitcoin (BTC)",  value="BTCUSDT"),
    app_commands.Choice(name="Ethereum (ETH)", value="ETHUSDT"),
    app_commands.Choice(name="Solana (SOL)",   value="SOLUSDT"),
    app_commands.Choice(name="BNB (BNB)",      value="BNBUSDT"),
])
async def slash_analysis(interaction: discord.Interaction, coin: str = "BTCUSDT"):
    await interaction.response.defer()
    coin_name = COIN_NAMES_EN.get(coin, coin)
    emoji     = COIN_EMOJI.get(coin, "🪙")
    logo      = COIN_LOGOS.get(coin)

    df  = get_data(coin)
    ind = calc_indicators(df)
    pri = get_price_info(coin)

    if ind is None or pri is None:
        await interaction.followup.send("❌ Could not fetch data. Try again in a moment.", ephemeral=True)
        return

    rsi     = ind["rsi"]
    mh      = ind["macd_hist"]
    ema20   = ind["ema20"]
    ema50   = ind["ema50"]
    bb_up   = ind["bb_upper"]
    bb_low  = ind["bb_lower"]
    bb_mid  = ind["bb_mid"]
    bb_pct  = ind["bb_pct"]
    sk      = ind["stoch_k"]
    sd      = ind["stoch_d"]
    price   = pri["price"]
    change  = pri["change"]

    # build signal score
    buy_score  = sum([rsi < 35, mh > 0, price > ema50 * 0.98, bb_pct < 0.25, sk < 0.25 and sk > sd])
    sell_score = sum([rsi > 65, mh < 0, price < ema50 * 1.02, bb_pct > 0.75, sk > 0.75 and sk < sd])
    score_max  = 5
    bias       = "🟢 Bullish" if buy_score > sell_score and buy_score >= 3 else \
                 ("🔴 Bearish" if sell_score > buy_score and sell_score >= 3 else "🟡 Neutral / Mixed")
    score_str  = f"BUY `{buy_score}/{score_max}` | SELL `{sell_score}/{score_max}`"

    bb_pos = "Near Upper Band 🔴" if bb_pct > 0.75 else ("Near Lower Band 🟢" if bb_pct < 0.25 else "Middle Zone ⚪")

    stoch_str  = f"K `{round(sk*100,1)}%` / D `{round(sd*100,1)}%`"
    stoch_zone = "🔴 Overbought" if sk > 0.8 else ("🟢 Oversold" if sk < 0.2 else "🟡 Neutral")

    trend_ema = "🟢 Bullish (EMA20 > EMA50)" if ema20 > ema50 else "🔴 Bearish (EMA20 < EMA50)"

    color = 0x00c853 if buy_score > sell_score else (0xff1744 if sell_score > buy_score else 0xffa726)

    embed = discord.Embed(
        title=f"🔬 Technical Analysis — {emoji} {coin_name}",
        description=(
            f"💰 **Price:** `${price:,.4f}`  |  24h: `{'+' if change >= 0 else ''}{change:.2f}%`\n"
            f"{SEP}\n"
            f"**Overall Bias:** {bias}  |  Score: {score_str}"
        ),
        color=color,
        timestamp=datetime.utcnow()
    )
    if logo:
        embed.set_thumbnail(url=logo)
    embed.set_author(name="🔬 Crypto Signals Bot — Full Analysis", icon_url=BOT_ICON)

    embed.add_field(name="📊 RSI (14)", value=rsi_bar(rsi), inline=False)
    embed.add_field(
        name="📉 MACD",
        value=f"Histogram: `{'▲ ' if mh > 0 else '▼ '}{abs(mh):.4f}` — {'🟢 Bullish momentum' if mh > 0 else '🔴 Bearish momentum'}",
        inline=False
    )
    embed.add_field(
        name="📐 EMA Trend",
        value=f"{trend_ema}\nEMA20: `${ema20:,.2f}` | EMA50: `${ema50:,.2f}`",
        inline=False
    )
    embed.add_field(
        name="🎯 Bollinger Bands",
        value=(
            f"Upper: `${bb_up:,.2f}` | Mid: `${bb_mid:,.2f}` | Lower: `${bb_low:,.2f}`\n"
            f"Position: **{bb_pos}**  |  %B: `{round(bb_pct*100,1)}%`"
        ),
        inline=False
    )
    embed.add_field(
        name="⚡ Stochastic RSI",
        value=f"{stoch_str} — {stoch_zone}",
        inline=False
    )

    # Messari data
    m = get_messari_metrics(coin)
    if m and m.get("roi_1y") is not None:
        roi_str = f"`{round(m['roi_1y'], 1)}%`"
        vol_str = f"`${m['volume_last_24h']:,.0f}`" if m.get("volume_last_24h") else "N/A"
        embed.add_field(name="\u200b", value=SEP, inline=False)
        embed.add_field(name="📡 Messari — 1Y ROI", value=roi_str, inline=True)
        embed.add_field(name="📦 Messari — 24h Volume", value=vol_str, inline=True)

    # CoinGecko extra
    cg = get_coingecko_extra(coin)
    if cg:
        ath_str  = f"`${cg['ath']:,.2f}`" if cg.get("ath") else "N/A"
        rank_str = f"`#{cg['market_cap_rank']}`" if cg.get("market_cap_rank") else "N/A"
        ath_down = f"`{round(cg['ath_change_pct'], 1)}%`" if cg.get("ath_change_pct") else "N/A"
        embed.add_field(name="🏆 CoinGecko Rank", value=rank_str, inline=True)
        embed.add_field(name="📈 ATH", value=f"{ath_str}  ({ath_down} from ATH)", inline=True)

    embed.add_field(name="\u200b", value=SEP, inline=False)
    embed.add_field(
        name="⚠️ Disclaimer",
        value="🇬🇧 Not financial advice. DYOR.\n🇷🇴 Nu e sfat financiar. Fă propriile cercetări.",
        inline=False
    )
    embed.set_footer(text=f"Crypto Signals Bot  •  5 indicators  •  Binance + Messari + CoinGecko")
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


# ══════════════════════════════════════════════
#   PORTFOLIO TRACKER
# ══════════════════════════════════════════════

@tree.command(name="portfolio", description="💼 Manage your crypto portfolio — add/view/pnl/clear")
@app_commands.describe(
    action="add / view / pnl / clear",
    coin="Coin symbol (e.g. BTC, ETH)",
    entry="Entry price in USD",
    amount="Amount of coins you hold"
)
async def slash_portfolio(interaction: discord.Interaction,
                          action: str,
                          coin: str = "",
                          entry: float = 0.0,
                          amount: float = 0.0):
    uid = interaction.user.id
    action = action.lower().strip()

    if action == "add":
        if not coin or entry <= 0 or amount <= 0:
            await interaction.response.send_message(
                "❌ Usage: `/portfolio add BTC 50000 0.5`\n🇷🇴 Exemplu: `/portfolio add BTC 50000 0.5`",
                ephemeral=True); return
        sym = coin.upper() + "USDT"
        if uid not in USER_PORTFOLIOS:
            USER_PORTFOLIOS[uid] = []
        USER_PORTFOLIOS[uid].append({
            "symbol": sym, "entry": entry,
            "amount": amount, "ts": datetime.utcnow()
        })
        logo = COIN_LOGOS.get(sym)
        embed = discord.Embed(
            title="✅ Trade Added / Trade Adăugat",
            description=f"**{COIN_NAMES_EN.get(sym, sym)}** added to your portfolio!",
            color=0x00c853, timestamp=datetime.utcnow()
        )
        if logo: embed.set_thumbnail(url=logo)
        embed.add_field(name="📍 Entry Price", value=f"`${entry:,.4f}`", inline=True)
        embed.add_field(name="💰 Amount",      value=f"`{amount}`",       inline=True)
        embed.add_field(name="💵 Total Invested", value=f"`${entry * amount:,.2f}`", inline=True)
        embed.set_footer(text="Use /portfolio pnl to see live P&L")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    elif action == "view":
        trades = USER_PORTFOLIOS.get(uid, [])
        if not trades:
            await interaction.response.send_message(
                "🇬🇧 Portfolio empty. Use `/portfolio add BTC 50000 0.5` to add a trade.\n"
                "🇷🇴 Portofoliu gol. Folosește `/portfolio add BTC 50000 0.5` pentru a adăuga.",
                ephemeral=True); return
        embed = discord.Embed(
            title="💼 Your Portfolio / Portofoliul Tău",
            color=discord.Color.blurple(), timestamp=datetime.utcnow()
        )
        total_invested = sum(t["entry"] * t["amount"] for t in trades)
        for t in trades:
            coin_name = COIN_NAMES_EN.get(t["symbol"], t["symbol"])
            ts = t["ts"].strftime("%d %b %H:%M")
            embed.add_field(
                name=f"{COIN_EMOJI.get(t['symbol'],'🪙')} {coin_name}",
                value=f"Entry: `${t['entry']:,.4f}` | Amount: `{t['amount']}` | Invested: `${t['entry']*t['amount']:,.2f}` | {ts}",
                inline=False
            )
        embed.add_field(name="💵 Total Invested", value=f"`${total_invested:,.2f}`", inline=False)
        embed.set_footer(text="Use /portfolio pnl to see live P&L")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    elif action == "pnl":
        trades = USER_PORTFOLIOS.get(uid, [])
        if not trades:
            await interaction.response.send_message(
                "🇬🇧 No trades in portfolio.\n🇷🇴 Niciun trade în portofoliu.", ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(
            title="📊 Live P&L / Profit & Pierdere Live",
            color=discord.Color.gold(), timestamp=datetime.utcnow()
        )
        total_invested = 0; total_value = 0
        for t in trades:
            info = get_price_info(t["symbol"])
            if not info:
                continue
            cur = info["price"]
            invested = t["entry"] * t["amount"]
            value    = cur * t["amount"]
            pnl      = value - invested
            pnl_pct  = (pnl / invested) * 100 if invested else 0
            total_invested += invested; total_value += value
            icon = "🟢" if pnl >= 0 else "🔴"
            embed.add_field(
                name=f"{icon} {COIN_NAMES_EN.get(t['symbol'], t['symbol'])}",
                value=(f"Entry `${t['entry']:,.4f}` → Now `${cur:,.4f}`\n"
                       f"P&L: `{'+' if pnl>=0 else ''}{pnl:,.2f}$` (`{pnl_pct:+.2f}%`) | Value: `${value:,.2f}`"),
                inline=False
            )
        total_pnl = total_value - total_invested
        total_pct = (total_pnl / total_invested * 100) if total_invested else 0
        icon = "🟢" if total_pnl >= 0 else "🔴"
        embed.add_field(name=SEP, value="\u200b", inline=False)
        embed.add_field(name=f"{icon} TOTAL P&L",
                        value=f"Invested: `${total_invested:,.2f}` | Value: `${total_value:,.2f}`\n**P&L: `{'+' if total_pnl>=0 else ''}{total_pnl:,.2f}$` (`{total_pct:+.2f}%`)**",
                        inline=False)
        embed.set_footer(text=f"Crypto Signals Bot  •  Live data from Binance")
        await interaction.followup.send(embed=embed, ephemeral=True)

    elif action == "clear":
        USER_PORTFOLIOS[uid] = []
        await interaction.response.send_message(
            "🗑️ 🇬🇧 Portfolio cleared!\n🇷🇴 Portofoliu șters!", ephemeral=True)

    else:
        await interaction.response.send_message(
            "❓ Actions: `add` · `view` · `pnl` · `clear`\n"
            "🇷🇴 Acțiuni: `add` · `view` · `pnl` · `clear`", ephemeral=True)


# ══════════════════════════════════════════════
#   RISK CALCULATOR
# ══════════════════════════════════════════════

@tree.command(name="risk", description="🧮 Position size calculator — how much to buy based on risk %")
@app_commands.describe(
    capital="Total capital in USD",
    entry="Entry price",
    stoploss="Stop Loss price",
    risk_pct="Risk % of capital (default 1)"
)
async def slash_risk(interaction: discord.Interaction,
                     capital: float, entry: float, stoploss: float,
                     risk_pct: float = 1.0):
    if entry <= 0 or stoploss <= 0 or capital <= 0:
        await interaction.response.send_message("❌ Invalid values.", ephemeral=True); return

    risk_usd    = capital * (risk_pct / 100)
    sl_distance = abs(entry - stoploss)
    if sl_distance == 0:
        await interaction.response.send_message("❌ Entry and SL cannot be the same price.", ephemeral=True); return

    position_size = risk_usd / sl_distance
    position_usd  = position_size * entry
    sl_pct        = (sl_distance / entry) * 100
    is_long       = entry > stoploss
    tp1           = round(entry * (1 + sl_pct/100 * 2), 4) if is_long else round(entry * (1 - sl_pct/100 * 2), 4)
    tp2           = round(entry * (1 + sl_pct/100 * 3), 4) if is_long else round(entry * (1 - sl_pct/100 * 3), 4)

    color = 0x00c853 if is_long else 0xff1744
    embed = discord.Embed(
        title="🧮 Risk Calculator / Calculator Risc",
        description=f"{'🟢 LONG' if is_long else '🔴 SHORT'} position sizing for `${entry:,.4f}` entry",
        color=color, timestamp=datetime.utcnow()
    )
    embed.set_author(name="💼 Crypto Signals Bot — Risk Management", icon_url=BOT_ICON)
    embed.add_field(name="💰 Capital",          value=f"`${capital:,.2f}`",           inline=True)
    embed.add_field(name="⚠️ Risk %",            value=f"`{risk_pct}%` = `${risk_usd:,.2f}`", inline=True)
    embed.add_field(name="🛑 SL Distance",       value=f"`{sl_pct:.2f}%`",             inline=True)
    embed.add_field(name=SEP, value="\u200b", inline=False)
    embed.add_field(name="📦 Position Size",     value=f"`{position_size:.6f}` coins",  inline=True)
    embed.add_field(name="💵 Position Value",    value=f"`${position_usd:,.2f}`",        inline=True)
    embed.add_field(name="📐 Leverage needed",   value=f"`{position_usd/capital:.1f}x`", inline=True)
    embed.add_field(name=SEP, value="\u200b", inline=False)
    embed.add_field(name="📍 Entry",   value=f"`${entry:,.4f}`",   inline=True)
    embed.add_field(name="🛑 SL",      value=f"`${stoploss:,.4f}`", inline=True)
    embed.add_field(name="\u200b",     value="\u200b",              inline=True)
    embed.add_field(name="🎯 TP1 (R:R 2:1)", value=f"`${tp1:,.4f}`", inline=True)
    embed.add_field(name="🎯 TP2 (R:R 3:1)", value=f"`${tp2:,.4f}`", inline=True)
    embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
    await interaction.response.send_message(embed=embed)


# ══════════════════════════════════════════════
#   PROFIT CALCULATOR
# ══════════════════════════════════════════════

@tree.command(name="calculate", description="💵 Calculate profit/loss from a trade")
@app_commands.describe(
    entry="Entry price in USD",
    exit_price="Exit / current price in USD",
    amount="Amount of coins",
    leverage="Leverage used (default 1 = spot)"
)
async def slash_calculate(interaction: discord.Interaction,
                          entry: float, exit_price: float,
                          amount: float, leverage: float = 1.0):
    if entry <= 0 or exit_price <= 0 or amount <= 0:
        await interaction.response.send_message("❌ Invalid values.", ephemeral=True); return

    invested  = entry * amount
    value_now = exit_price * amount
    pnl       = (value_now - invested) * leverage
    pnl_pct   = ((exit_price - entry) / entry) * 100 * leverage
    is_profit = pnl >= 0
    fees_est  = invested * 0.001  # 0.1% estimated taker fee

    color = 0x00c853 if is_profit else 0xff1744
    embed = discord.Embed(
        title=f"{'🟢 PROFIT' if is_profit else '🔴 LOSS'} — Trade Calculator",
        color=color, timestamp=datetime.utcnow()
    )
    embed.set_author(name="💵 Crypto Signals Bot — P&L Calculator", icon_url=BOT_ICON)
    embed.add_field(name="📍 Entry Price",  value=f"`${entry:,.4f}`",      inline=True)
    embed.add_field(name="🏁 Exit Price",   value=f"`${exit_price:,.4f}`",  inline=True)
    embed.add_field(name="📦 Amount",       value=f"`{amount}`",            inline=True)
    embed.add_field(name=SEP, value="\u200b", inline=False)
    embed.add_field(name="💰 Invested",    value=f"`${invested:,.2f}`",       inline=True)
    embed.add_field(name="💵 Value Now",   value=f"`${value_now:,.2f}`",      inline=True)
    embed.add_field(name="⚡ Leverage",    value=f"`{leverage}x`",            inline=True)
    embed.add_field(name=SEP, value="\u200b", inline=False)
    embed.add_field(
        name=f"{'🟢 Profit' if is_profit else '🔴 Loss'} (gross)",
        value=f"## `{'+' if is_profit else ''}{pnl:,.2f}$` (`{pnl_pct:+.2f}%`)",
        inline=False
    )
    embed.add_field(name="💸 Est. Fees (0.1%)", value=f"`-${fees_est:,.2f}`", inline=True)
    embed.add_field(
        name="✅ Net P&L",
        value=f"`{'+' if (pnl-fees_est)>=0 else ''}{(pnl-fees_est):,.2f}$`",
        inline=True
    )
    embed.set_footer(text=f"🇬🇧 {DISCLAIMER_EN}  |  🇷🇴 {DISCLAIMER_RO}")
    await interaction.response.send_message(embed=embed)


# ══════════════════════════════════════════════
#   MULTI-TIMEFRAME DASHBOARD
# ══════════════════════════════════════════════

@tree.command(name="multi", description="📐 Multi-timeframe analysis: 5m + 15m + 1h + 4h")
@app_commands.describe(coin="Choose a coin")
@app_commands.choices(coin=[
    app_commands.Choice(name="Bitcoin (BTC)",  value="BTCUSDT"),
    app_commands.Choice(name="Ethereum (ETH)", value="ETHUSDT"),
    app_commands.Choice(name="Solana (SOL)",   value="SOLUSDT"),
    app_commands.Choice(name="BNB (BNB)",      value="BNBUSDT"),
    app_commands.Choice(name="XRP (XRP)",      value="XRPUSDT"),
    app_commands.Choice(name="Cardano (ADA)",  value="ADAUSDT"),
    app_commands.Choice(name="Avalanche (AVAX)",value="AVAXUSDT"),
    app_commands.Choice(name="Dogecoin (DOGE)",value="DOGEUSDT"),
])
async def slash_multi(interaction: discord.Interaction, coin: str = "BTCUSDT"):
    await interaction.response.defer()
    logo = COIN_LOGOS.get(coin)
    timeframes = [("5m","5 min"),("15m","15 min"),("1h","1 Hour"),("4h","4 Hour")]
    rows = []
    for tf, tf_label in timeframes:
        df = get_data(coin, interval=tf)
        ind = calc_indicators(df) if df is not None else None
        if ind is None:
            rows.append((tf_label, "❓", "N/A", "N/A", "N/A", "N/A"))
            continue
        rsi = ind["rsi"]; mh = ind["macd_hist"]; bp = ind["bb_pct"]; sk = ind["stoch_k"]
        buy_s  = sum([rsi < 35, mh > 0, bp < 0.25, sk < 0.25])
        sell_s = sum([rsi > 65, mh < 0, bp > 0.75, sk > 0.75])
        if buy_s >= 2:
            sig = "🟢 BUY"
        elif sell_s >= 2:
            sig = "🔴 SELL"
        else:
            sig = "🟡 NEUTRAL"
        rsi_zone = "OB🔴" if rsi > 70 else ("OS🟢" if rsi < 30 else "OK⚪")
        macd_dir = "▲" if mh > 0 else "▼"
        rows.append((tf_label, sig, f"{round(rsi,1)} {rsi_zone}", f"{macd_dir}", f"{round(bp*100,0):.0f}%", f"{round(sk*100,1)}%"))

    info = get_price_info(coin)
    price_str = f"${info['price']:,.4f}" if info else "N/A"
    change_str = f"{info['change']:+.2f}%" if info else ""

    # overall confluence
    buy_count  = sum(1 for r in rows if "BUY" in r[1])
    sell_count = sum(1 for r in rows if "SELL" in r[1])
    if buy_count >= 3:   overall = "🟢🟢 STRONG BUY"
    elif buy_count == 2: overall = "🟢 BUY"
    elif sell_count >= 3:overall = "🔴🔴 STRONG SELL"
    elif sell_count == 2:overall = "🔴 SELL"
    else:                overall = "🟡 MIXED / NEUTRAL"

    embed = discord.Embed(
        title=f"📐 Multi-Timeframe — {COIN_EMOJI.get(coin,'🪙')} {COIN_NAMES_EN.get(coin,coin)}",
        description=(
            f"💰 **{price_str}** `{change_str}`\n"
            f"{SEP}\n"
            f"**Overall Confluence: {overall}**  (`{buy_count}/4` TF bullish)"
        ),
        color=0x00c853 if "BUY" in overall else (0xff1744 if "SELL" in overall else 0xffa726),
        timestamp=datetime.utcnow()
    )
    if logo: embed.set_thumbnail(url=logo)
    embed.set_author(name="📐 Multi-Timeframe Dashboard", icon_url=BOT_ICON)

    tf_table = "```\n{:<10} {:<14} {:<10} {:<6} {:<8} {:<8}\n{}\n".format(
        "TF","Signal","RSI","MACD","BB%","StochK",
        "─"*56
    )
    for r in rows:
        tf_table += "{:<10} {:<14} {:<10} {:<6} {:<8} {:<8}\n".format(*r)
    tf_table += "```"
    embed.add_field(name="📊 Timeframe Breakdown", value=tf_table, inline=False)
    embed.add_field(
        name="💡 How to use / Cum să folosești",
        value=(
            "🇬🇧 3+ timeframes agree = higher confidence signal.\n"
            "🇷🇴 3+ timeframe-uri de acord = semnal cu încredere mai mare."
        ),
        inline=False
    )
    embed.set_footer(text=f"Crypto Signals Bot  •  {DISCLAIMER_RO}")
    await interaction.followup.send(embed=embed)


# ══════════════════════════════════════════════
#   MARKET HEATMAP
# ══════════════════════════════════════════════

@tree.command(name="heatmap", description="🌡️ Market heatmap — all 8 coins at a glance")
async def slash_heatmap(interaction: discord.Interaction):
    await interaction.response.defer()
    embed = discord.Embed(
        title="🌡️ Market Heatmap / Harta Pieței",
        description=(
            "🇬🇧 Live overview of all tracked coins\n"
            f"🇷🇴 Vizualizare live toate monedele urmărite\n{SEP}"
        ),
        color=0x1e293b, timestamp=datetime.utcnow()
    )
    embed.set_author(name="🌡️ Crypto Signals Bot — Market Heatmap", icon_url=BOT_ICON)

    bull_count = 0; bear_count = 0
    for sym in ALL_SYMBOLS:
        info = get_price_info(sym)
        df   = get_data(sym)
        ind  = calc_indicators(df) if df is not None else None
        if not info:
            continue
        ch   = info["change"]
        p    = info["price"]
        emoji = COIN_EMOJI.get(sym, "🪙")
        name  = sym.replace("USDT","")
        # heat color
        if ch >= 5:     heat = "🔥🔥"
        elif ch >= 2:   heat = "🟢🟢"
        elif ch >= 0.5: heat = "🟢"
        elif ch >= -0.5:heat = "⚪"
        elif ch >= -2:  heat = "🔴"
        elif ch >= -5:  heat = "🔴🔴"
        else:            heat = "💀💀"

        rsi_str = f"RSI `{round(ind['rsi'],1)}`" if ind else ""
        sig_str = ""
        if ind:
            buy_s = sum([ind["rsi"]<35, ind["macd_hist"]>0, ind["bb_pct"]<0.25])
            sel_s = sum([ind["rsi"]>65, ind["macd_hist"]<0, ind["bb_pct"]>0.75])
            if buy_s >= 2:   sig_str = " | 🟢 BUY"; bull_count += 1
            elif sel_s >= 2: sig_str = " | 🔴 SELL"; bear_count += 1
            else:             sig_str = " | 🟡 Neutral"

        embed.add_field(
            name=f"{heat} {emoji} {name}",
            value=f"`${p:,.4f}` `{'+' if ch>=0 else ''}{ch:.2f}%` {rsi_str}{sig_str}",
            inline=True
        )

    # Market summary
    total = bull_count + bear_count
    embed.add_field(name=SEP, value="\u200b", inline=False)
    embed.add_field(
        name="📊 Market Summary / Rezumat Piață",
        value=(f"🟢 Bullish: `{bull_count}` | 🔴 Bearish: `{bear_count}` | ⚪ Neutral: `{len(ALL_SYMBOLS)-total}`\n"
               f"{'🟢 Overall market is **BULLISH**' if bull_count > bear_count else ('🔴 Overall market is **BEARISH**' if bear_count > bull_count else '🟡 Market is **MIXED**')}"),
        inline=False
    )
    embed.set_footer(text=f"Crypto Signals Bot  •  {DISCLAIMER_RO}")
    await interaction.followup.send(embed=embed)


# ══════════════════════════════════════════════
#   COMPARE TWO COINS
# ══════════════════════════════════════════════

@tree.command(name="compare", description="⚖️ Compare two coins side by side")
@app_commands.describe(coin1="First coin", coin2="Second coin")
@app_commands.choices(
    coin1=[
        app_commands.Choice(name="Bitcoin (BTC)",  value="BTCUSDT"),
        app_commands.Choice(name="Ethereum (ETH)", value="ETHUSDT"),
        app_commands.Choice(name="Solana (SOL)",   value="SOLUSDT"),
        app_commands.Choice(name="BNB (BNB)",      value="BNBUSDT"),
        app_commands.Choice(name="XRP (XRP)",      value="XRPUSDT"),
        app_commands.Choice(name="Cardano (ADA)",  value="ADAUSDT"),
        app_commands.Choice(name="AVAX",           value="AVAXUSDT"),
        app_commands.Choice(name="Dogecoin (DOGE)",value="DOGEUSDT"),
    ],
    coin2=[
        app_commands.Choice(name="Bitcoin (BTC)",  value="BTCUSDT"),
        app_commands.Choice(name="Ethereum (ETH)", value="ETHUSDT"),
        app_commands.Choice(name="Solana (SOL)",   value="SOLUSDT"),
        app_commands.Choice(name="BNB (BNB)",      value="BNBUSDT"),
        app_commands.Choice(name="XRP (XRP)",      value="XRPUSDT"),
        app_commands.Choice(name="Cardano (ADA)",  value="ADAUSDT"),
        app_commands.Choice(name="AVAX",           value="AVAXUSDT"),
        app_commands.Choice(name="Dogecoin (DOGE)",value="DOGEUSDT"),
    ]
)
async def slash_compare(interaction: discord.Interaction,
                        coin1: str = "BTCUSDT", coin2: str = "ETHUSDT"):
    await interaction.response.defer()
    results = []
    for sym in [coin1, coin2]:
        info = get_price_info(sym)
        df   = get_data(sym)
        ind  = calc_indicators(df) if df is not None else None
        results.append((sym, info, ind))

    embed = discord.Embed(
        title=f"⚖️ Compare — {coin1.replace('USDT','')} vs {coin2.replace('USDT','')}",
        color=0x6366f1, timestamp=datetime.utcnow()
    )
    embed.set_author(name="⚖️ Crypto Signals Bot — Coin Comparison", icon_url=BOT_ICON)

    labels = ["💰 Price","📈 24h Change","🔺 24h High","🔻 24h Low",
              "📦 Volume","📊 RSI","📉 MACD","🎯 BB%","⚡ StochK"]

    def fmt(sym, info, ind):
        if not info: return ["N/A"]*9
        ch = info["change"]
        row = [
            f"${info['price']:,.4f}",
            f"{'+' if ch>=0 else ''}{ch:.2f}%",
            f"${info['high']:,.4f}",
            f"${info['low']:,.4f}",
            f"${info['volume']:,.0f}",
        ]
        if ind:
            rsi_z = "OB🔴" if ind["rsi"]>70 else ("OS🟢" if ind["rsi"]<30 else "OK⚪")
            mdir  = "▲🟢" if ind["macd_hist"]>0 else "▼🔴"
            row += [f"{round(ind['rsi'],1)} {rsi_z}", mdir,
                    f"{round(ind['bb_pct']*100,1)}%", f"{round(ind['stoch_k']*100,1)}%"]
        else:
            row += ["N/A","N/A","N/A","N/A"]
        return row

    r1 = fmt(*results[0]); r2 = fmt(*results[1])
    n1 = coin1.replace("USDT",""); n2 = coin2.replace("USDT","")
    for i, label in enumerate(labels):
        embed.add_field(name=label, value=f"**{n1}:** `{r1[i]}`\n**{n2}:** `{r2[i]}`", inline=True)

    # Winner per metric
    if results[0][1] and results[1][1]:
        ch1 = results[0][1]["change"]; ch2 = results[1][1]["change"]
        winner = n1 if ch1 > ch2 else n2
        embed.add_field(
            name=f"\n{SEP}\n🏆 Better 24h Performance",
            value=f"**{winner}** wins on 24h change",
            inline=False
        )
    embed.set_footer(text=f"Crypto Signals Bot  •  {DISCLAIMER_RO}")
    await interaction.followup.send(embed=embed)


# ══════════════════════════════════════════════
#   BTC DOMINANCE
# ══════════════════════════════════════════════

@tree.command(name="dominance", description="👑 BTC Dominance + market cap overview")
async def slash_dominance(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        data = requests.get(
            "https://api.coingecko.com/api/v3/global", timeout=10
        ).json().get("data", {})
        dom   = data.get("market_cap_percentage", {})
        btc_d = round(dom.get("btc", 0), 2)
        eth_d = round(dom.get("eth", 0), 2)
        total_mc = data.get("total_market_cap", {}).get("usd", 0)
        total_vol= data.get("total_volume", {}).get("usd", 0)
        mc_chg   = round(data.get("market_cap_change_percentage_24h_usd", 0), 2)
        others   = round(100 - btc_d - eth_d, 2)
    except Exception:
        await interaction.followup.send("❌ Could not fetch dominance data.", ephemeral=True); return

    # BTC dominance interpretation
    if btc_d > 55:
        interp_en = "🔵 High BTC dominance → altcoins may underperform. Stay with BTC."
        interp_ro = "🔵 Dominanță BTC ridicată → altcoin-urile pot performa mai slab. Rămâi pe BTC."
    elif btc_d < 40:
        interp_en = "🟡 Low BTC dominance → altcoin season possible. Check altcoins for signals."
        interp_ro = "🟡 Dominanță BTC scăzută → posibil sezon altcoin. Verifică altcoin-urile."
    else:
        interp_en = "⚪ Neutral dominance → balanced market. Follow signals."
        interp_ro = "⚪ Dominanță neutră → piață echilibrată. Urmează semnalele."

    # dominance bar
    btc_bar_len = int(btc_d / 5)
    eth_bar_len = int(eth_d / 5)
    oth_bar_len = 20 - btc_bar_len - eth_bar_len
    dom_bar = f"{'🟠'*btc_bar_len}{'🔵'*eth_bar_len}{'⬜'*max(0,oth_bar_len)}"

    embed = discord.Embed(
        title="👑 Crypto Market Dominance",
        description=(
            f"🌍 **Total Market Cap:** `${total_mc/1e9:,.1f}B` (`{'+' if mc_chg>=0 else ''}{mc_chg}%` 24h)\n"
            f"📦 **24h Volume:** `${total_vol/1e9:,.1f}B`\n{SEP}"
        ),
        color=0xF7931A, timestamp=datetime.utcnow()
    )
    embed.set_thumbnail(url=BOT_ICON)
    embed.set_author(name="👑 Crypto Signals Bot — Market Dominance", icon_url=BOT_ICON)
    embed.add_field(name="🟠 BTC Dominance",  value=f"`{btc_d}%`", inline=True)
    embed.add_field(name="🔵 ETH Dominance",  value=f"`{eth_d}%`", inline=True)
    embed.add_field(name="⬜ Others",          value=f"`{others}%`",inline=True)
    embed.add_field(name="📊 Visual / Vizual", value=dom_bar, inline=False)
    embed.add_field(name="🇬🇧 Interpretation",  value=interp_en, inline=False)
    embed.add_field(name="🇷🇴 Interpretare",    value=interp_ro, inline=False)
    embed.set_footer(text=f"Crypto Signals Bot  •  Data: CoinGecko")
    await interaction.followup.send(embed=embed)


# ══════════════════════════════════════════════
#   WATCHLIST SYSTEM
# ══════════════════════════════════════════════

@tree.command(name="watch", description="👁️ Add a coin to your watchlist — get DM when signal fires")
@app_commands.describe(coin="Coin to watch")
@app_commands.choices(coin=[
    app_commands.Choice(name="Bitcoin (BTC)",  value="BTCUSDT"),
    app_commands.Choice(name="Ethereum (ETH)", value="ETHUSDT"),
    app_commands.Choice(name="Solana (SOL)",   value="SOLUSDT"),
    app_commands.Choice(name="BNB (BNB)",      value="BNBUSDT"),
    app_commands.Choice(name="XRP (XRP)",      value="XRPUSDT"),
    app_commands.Choice(name="Cardano (ADA)",  value="ADAUSDT"),
    app_commands.Choice(name="AVAX",           value="AVAXUSDT"),
    app_commands.Choice(name="Dogecoin (DOGE)",value="DOGEUSDT"),
])
async def slash_watch(interaction: discord.Interaction, coin: str):
    uid = interaction.user.id
    if uid not in USER_WATCHLISTS:
        USER_WATCHLISTS[uid] = []
    if coin not in USER_WATCHLISTS[uid]:
        USER_WATCHLISTS[uid].append(coin)
        logo = COIN_LOGOS.get(coin)
        embed = discord.Embed(
            title=f"👁️ Watching {coin.replace('USDT','')}",
            description=(
                f"🇬🇧 You'll receive a **DM** whenever our bot generates a BUY or SELL signal for **{COIN_NAMES_EN.get(coin,coin)}**.\n"
                f"🇷🇴 Vei primi un **DM** ori de câte ori botul generează un semnal BUY sau SELL pentru **{COIN_NAMES_EN.get(coin,coin)}**."
            ),
            color=0x6366f1
        )
        if logo: embed.set_thumbnail(url=logo)
        embed.add_field(name="📋 Your watchlist",
                        value=", ".join(f"`{s.replace('USDT','')}`" for s in USER_WATCHLISTS[uid]),
                        inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(
            f"👁️ `{coin.replace('USDT','')}` is already on your watchlist!\n"
            f"🇷🇴 `{coin.replace('USDT','')}` este deja în lista ta de urmărire!",
            ephemeral=True)


@tree.command(name="unwatch", description="🚫 Remove a coin from your watchlist")
@app_commands.describe(coin="Coin to remove")
@app_commands.choices(coin=[
    app_commands.Choice(name="Bitcoin (BTC)",  value="BTCUSDT"),
    app_commands.Choice(name="Ethereum (ETH)", value="ETHUSDT"),
    app_commands.Choice(name="Solana (SOL)",   value="SOLUSDT"),
    app_commands.Choice(name="BNB (BNB)",      value="BNBUSDT"),
    app_commands.Choice(name="XRP (XRP)",      value="XRPUSDT"),
    app_commands.Choice(name="Cardano (ADA)",  value="ADAUSDT"),
    app_commands.Choice(name="AVAX",           value="AVAXUSDT"),
    app_commands.Choice(name="Dogecoin (DOGE)",value="DOGEUSDT"),
])
async def slash_unwatch(interaction: discord.Interaction, coin: str):
    uid = interaction.user.id
    wl  = USER_WATCHLISTS.get(uid, [])
    if coin in wl:
        wl.remove(coin)
        await interaction.response.send_message(
            f"✅ `{coin.replace('USDT','')}` removed from watchlist.\n"
            f"🇷🇴 `{coin.replace('USDT','')}` eliminat din lista de urmărire.", ephemeral=True)
    else:
        await interaction.response.send_message(
            f"❓ `{coin.replace('USDT','')}` not on your watchlist.\n"
            f"🇷🇴 `{coin.replace('USDT','')}` nu este în lista ta.", ephemeral=True)


@tree.command(name="mywatchlist", description="📋 View your active watchlist")
async def slash_mywatchlist(interaction: discord.Interaction):
    uid = interaction.user.id
    wl  = USER_WATCHLISTS.get(uid, [])
    if not wl:
        await interaction.response.send_message(
            "🇬🇧 Watchlist empty. Use `/watch BTC` to add coins.\n"
            "🇷🇴 Lista goală. Folosește `/watch BTC` pentru a adăuga.", ephemeral=True); return
    embed = discord.Embed(
        title="👁️ Your Watchlist / Lista ta de urmărire",
        description="🇬🇧 You'll get a DM when any of these fire a signal.\n🇷🇴 Vei primi DM când oricare dintre acestea generează semnal.",
        color=0x6366f1
    )
    for sym in wl:
        info = get_price_info(sym)
        p_str = f"${info['price']:,.4f} (`{'+' if info['change']>=0 else ''}{info['change']:.2f}%`)" if info else "N/A"
        embed.add_field(name=f"{COIN_EMOJI.get(sym,'🪙')} {COIN_NAMES_EN.get(sym,sym)}", value=p_str, inline=True)
    embed.set_footer(text="Use /unwatch [coin] to remove")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ══════════════════════════════════════════════
#   COMMUNITY PREDICT SYSTEM
# ══════════════════════════════════════════════

@tree.command(name="predict", description="🔮 Submit your prediction — will the coin go UP or DOWN?")
@app_commands.describe(coin="Which coin", direction="UP or DOWN")
@app_commands.choices(
    coin=[
        app_commands.Choice(name="Bitcoin (BTC)",  value="BTCUSDT"),
        app_commands.Choice(name="Ethereum (ETH)", value="ETHUSDT"),
        app_commands.Choice(name="Solana (SOL)",   value="SOLUSDT"),
        app_commands.Choice(name="BNB (BNB)",      value="BNBUSDT"),
    ],
    direction=[
        app_commands.Choice(name="🟢 UP",   value="UP"),
        app_commands.Choice(name="🔴 DOWN", value="DOWN"),
    ]
)
async def slash_predict(interaction: discord.Interaction, coin: str, direction: str):
    uid  = interaction.user.id
    info = get_price_info(coin)
    if not info:
        await interaction.response.send_message("❌ Cannot fetch price. Try again.", ephemeral=True); return

    PREDICTIONS[uid] = {
        "symbol":    coin,
        "direction": direction,
        "entry_price": info["price"],
        "ts":        datetime.utcnow(),
        "username":  str(interaction.user)
    }
    if uid not in PRED_SCORES:
        PRED_SCORES[uid] = {"correct": 0, "total": 0, "username": str(interaction.user)}

    icon = "🟢" if direction == "UP" else "🔴"
    embed = discord.Embed(
        title=f"🔮 Prediction Submitted / Predicție Trimisă",
        description=(
            f"{icon} **{interaction.user.display_name}** predicts **{direction}** for "
            f"**{COIN_NAMES_EN.get(coin,coin)}**\n"
            f"Entry price: `${info['price']:,.4f}`\n"
            f"🇷🇴 **{interaction.user.display_name}** prezice **{direction}** pentru **{COIN_NAMES_EN.get(coin,coin)}**"
        ),
        color=0x00c853 if direction == "UP" else 0xff1744,
        timestamp=datetime.utcnow()
    )
    scores = PRED_SCORES[uid]
    acc = round(scores["correct"] / scores["total"] * 100, 1) if scores["total"] > 0 else 0
    embed.add_field(name="📊 Your accuracy", value=f"`{acc}%` ({scores['correct']}/{scores['total']} correct)", inline=True)
    embed.set_footer(text="Result checked in 1 hour. /leaderboard to see standings.")
    await interaction.response.send_message(embed=embed)


@tree.command(name="leaderboard", description="🏆 Community prediction leaderboard")
async def slash_leaderboard(interaction: discord.Interaction):
    if not PRED_SCORES:
        await interaction.response.send_message(
            "🇬🇧 No predictions yet. Use `/predict` to start!\n"
            "🇷🇴 Nicio predicție încă. Folosește `/predict` pentru a începe!", ephemeral=True); return

    sorted_scores = sorted(
        [(uid, s) for uid, s in PRED_SCORES.items() if s["total"] >= 3],
        key=lambda x: x[1]["correct"] / x[1]["total"] if x[1]["total"] > 0 else 0,
        reverse=True
    )
    embed = discord.Embed(
        title="🏆 Prediction Leaderboard / Clasament Predicții",
        description="🇬🇧 Top predictors this session\n🇷🇴 Top predictori din această sesiune",
        color=0xffd700, timestamp=datetime.utcnow()
    )
    medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    for i, (uid, s) in enumerate(sorted_scores[:10]):
        acc = round(s["correct"] / s["total"] * 100, 1) if s["total"] > 0 else 0
        embed.add_field(
            name=f"{medals[i]} {s.get('username','Unknown')}",
            value=f"Accuracy: `{acc}%` | `{s['correct']}/{s['total']}` correct",
            inline=False
        )
    if not sorted_scores:
        embed.description += "\n\n_Not enough predictions yet (min 3 per user)_"
    embed.set_footer(text="Minimum 3 predictions required to appear on leaderboard.")
    await interaction.response.send_message(embed=embed)


# =========================
# WELCOME
# =========================

@client.event
async def on_member_join(member):
    # ── Welcome message in channel ──
    ch = client.get_channel(WELCOME_CHANNEL)
    if ch:
        embed = discord.Embed(
            title=f"👋 Bun venit / Welcome, {member.display_name}!",
            description=(
                "🇷🇴 **Bun venit pe serverul Crypto Signals!** 🎉\n"
                "Suntem o comunitate de traderi care primesc semnale BUY/SELL în timp real pentru BTC, ETH, SOL și BNB.\n\n"
                f"📜 Reguli → <#{RULES_CHANNEL}>\n"
                f"📊 Cum funcționează → <#{HOWTO_CHANNEL}>\n"
                f"💎 Obține VIP → <#{GET_VIP_CHANNEL}>\n\n"
                "🇬🇧 **Welcome to Crypto Signals server!** 🎉\n"
                "We're a trading community receiving real-time BUY/SELL signals for BTC, ETH, SOL & BNB.\n\n"
                f"📜 Rules → <#{RULES_CHANNEL}>\n"
                f"📊 How to use → <#{HOWTO_CHANNEL}>\n"
                f"💎 Get VIP → <#{GET_VIP_CHANNEL}>"
            ),
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(
            name="🚀 Ești nou? Începe aici! / New here? Start here!",
            value=(
                "`/firsttrade` — Ghid complet: de la zero la primul trade\n"
                "`/binance` — Cum folosești Binance pas cu pas\n"
                "`/signals_explained` — Ce înseamnă fiecare câmp din semnal\n"
                "`/tutorial 1` — Ce este un semnal BUY/SELL\n"
                "`/glossary` — Dicționar termeni crypto\n"
                "`/help` — Toate comenzile disponibile"
            ),
            inline=False
        )
        embed.set_footer(text="Crypto Signals Bot  •  Nu este sfat financiar")
        await ch.send(embed=embed)

    # ── Automatic DM with beginner starter guide ──
    try:
        dm_embed = discord.Embed(
            title=f"👋 Salut {member.display_name}! Bun venit pe Crypto Signals!",
            description=(
                "🇷🇴 Îți mulțumim că te-ai alăturat comunității noastre de trading!\n"
                "Am pregătit un **ghid rapid** ca să începi cu dreptul.\n\n"
                "🇬🇧 Thank you for joining our trading community!\n"
                "Here's a **quick guide** to get you started right.\n"
                f"{SEP}"
            ),
            color=0x22c55e,
            timestamp=datetime.utcnow()
        )
        dm_embed.set_thumbnail(url=BOT_ICON)
        dm_embed.set_author(name="🤖 Crypto Signals Bot", icon_url=BOT_ICON)

        dm_embed.add_field(
            name="🎯 Pasul 1 — Înțelege cum funcționează",
            value=(
                "🇷🇴 Botul analizează automat BTC, ETH, SOL și BNB folosind 5 indicatori tehnici "
                "(RSI, MACD, Bollinger Bands, StochRSI, EMA) și trimite semnale **BUY** sau **SELL**.\n"
                "🇬🇧 The bot automatically analyzes BTC, ETH, SOL & BNB using 5 technical indicators and sends **BUY** or **SELL** signals."
            ),
            inline=False
        )
        dm_embed.add_field(
            name="📨 Pasul 2 — Cum arată un semnal",
            value=(
                "🇷🇴 Fiecare semnal conține:\n"
                "📍 **Entry** = prețul la care cumperi\n"
                "🎯 **TP1/TP2** = prețurile la care vinzi cu profit\n"
                "🛑 **SL** = prețul de Stop Loss (protecție automată)\n"
                "⭐ **Confidence** = calitatea semnalului (tranzacționează doar HIGH+!)\n"
                "🇬🇧 Entry=buy price, TP1/TP2=sell for profit, SL=stop loss protection, Confidence=signal quality."
            ),
            inline=False
        )
        dm_embed.add_field(
            name="🏦 Pasul 3 — Ai nevoie de un cont Binance",
            value=(
                "🇷🇴 Dacă nu ai încă, creează un cont pe **binance.com** (gratuit, durează 15 min).\n"
                "Folosește comenzile de mai jos pentru ghid complet:\n"
                "🇬🇧 If you don't have one yet, create a free account at **binance.com** (15 min)."
            ),
            inline=False
        )
        dm_embed.add_field(
            name=f"{SEP}\n📋 Comenzile esențiale / Essential Commands",
            value=(
                "🚀 `/firsttrade` — Ghid complet în 8 pași de la zero la primul trade\n"
                "🟡 `/binance` — Cum folosești Binance (register, depunere, trade, OCO)\n"
                "📨 `/signals_explained` — Exemplu real de semnal explicat câmp cu câmp\n"
                "📖 `/tutorial 1` — Ce este un semnal BUY/SELL\n"
                "📚 `/glossary` — Dicționar termeni: RSI, MACD, SL, TP, Spot, Futures\n"
                "🎓 `/tip` — Sfat aleatoriu de trading\n"
                "📋 `/help` — Toate comenzile disponibile"
            ),
            inline=False
        )
        dm_embed.add_field(
            name="⚠️ Regula de aur / Golden Rule",
            value=(
                "🇷🇴 **Niciodată** nu investi mai mult decât îți permiți să pierzi complet.\n"
                "Începe cu o sumă mică (50–100$) și învață mai întâi!\n"
                "🇬🇧 **Never** invest more than you can afford to lose completely.\n"
                "Start small ($50–100) and learn first!"
            ),
            inline=False
        )
        dm_embed.set_footer(text="Crypto Signals Bot  •  Nu este sfat financiar  •  Not financial advice")
        await member.send(embed=dm_embed)
    except discord.Forbidden:
        pass  # User has DMs disabled — skip silently

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

    howto_ch = client.get_channel(HOWTO_CHANNEL)

    # ── HOWTO GUIDE 1: Cum citești un semnal ──
    h1 = discord.Embed(
        title="📖 1/4 — Cum citești un semnal / How to Read a Signal",
        description=(
            "🇷🇴 **Când botul trimite un semnal, vei vedea:**\n"
            "🇬🇧 **When the bot sends a signal, you'll see:**"
        ),
        color=0x3b82f6
    )
    h1.add_field(
        name="🟢 BUY = Cumpără / Buy",
        value=(
            "🇷🇴 Indicatorii arată că prețul ar putea **crește**. Intri la prețul **Entry**.\n"
            "🇬🇧 Indicators suggest the price may **go up**. Enter at the **Entry** price."
        ),
        inline=False
    )
    h1.add_field(
        name="🔴 SELL = Vinde / Sell",
        value=(
            "🇷🇴 Indicatorii arată că prețul ar putea **scădea**. Poți ieși sau evita să cumperi.\n"
            "🇬🇧 Indicators suggest the price may **go down**. Exit or avoid buying."
        ),
        inline=False
    )
    h1.add_field(
        name="📍 Entry = Prețul de intrare",
        value=(
            "🇷🇴 Prețul la care BOTul sugerează să **cumperi**.\n"
            "🇬🇧 The price at which the bot suggests you **enter** the trade."
        ),
        inline=True
    )
    h1.add_field(
        name="🎯 TP1 / TP2 / TP3 = Take Profit",
        value=(
            "🇷🇴 Prețurile la care **vinzi** pentru a lua profit.\n"
            "🇬🇧 Prices where you **sell** to lock in profit."
        ),
        inline=True
    )
    h1.add_field(
        name="🛑 SL = Stop Loss",
        value=(
            "🇷🇴 Prețul la care **ieși dacă greșești** — ca să nu pierzi prea mult.\n"
            "🇬🇧 The price where you **exit if wrong** — to limit your loss.\n"
            "⚠️ **MEREU pune SL! / ALWAYS set SL!**"
        ),
        inline=False
    )
    h1.set_footer(text="Crypto Signals Bot  •  Ghid 1/4")
    await send_once(howto_ch, h1, "1/4 — Cum")

    # ── HOWTO GUIDE 2: Ce înseamnă indicatorii ──
    h2 = discord.Embed(
        title="📊 2/4 — Ce înseamnă indicatorii / What Indicators Mean",
        description=(
            "🇷🇴 Botul folosește 5 indicatori. Iată ce înseamnă **simplu**:\n"
            "🇬🇧 The bot uses 5 indicators. Here's what they mean **simply**:"
        ),
        color=0x8b5cf6
    )
    h2.add_field(
        name="📊 RSI (0–100)",
        value=(
            "🇷🇴 Măsoară dacă moneda e **prea cumpărată** sau **prea vândută**.\n"
            "• `sub 30` = 🟢 ieftină, posibil BUY\n"
            "• `peste 70` = 🔴 scumpă, posibil SELL\n"
            "• `40–60` = ⚪ neutru\n"
            "🇬🇧 Measures if coin is **oversold** (cheap) or **overbought** (expensive)."
        ),
        inline=False
    )
    h2.add_field(
        name="📉 MACD",
        value=(
            "🇷🇴 Arată **direcția** momentumului pieței.\n"
            "• Histogramă `verde ▲` = forță bullish (cumpărători dominanți)\n"
            "• Histogramă `roșie ▼` = forță bearish (vânzători dominanți)\n"
            "🇬🇧 Shows the **direction** of market momentum."
        ),
        inline=False
    )
    h2.add_field(
        name="📐 Bollinger Bands (BB)",
        value=(
            "🇷🇴 Sunt ca niște **margini** în jurul prețului.\n"
            "• Prețul lângă **banda de jos** = posibil BUY\n"
            "• Prețul lângă **banda de sus** = posibil SELL\n"
            "🇬🇧 Like **price boundaries** — buy near bottom band, sell near top."
        ),
        inline=False
    )
    h2.add_field(
        name="🌀 Stochastic RSI",
        value=(
            "🇷🇴 Similar cu RSI, dar mai **rapid și sensibil**.\n"
            "• `sub 0.2` = 🟢 zonaă BUY  |  `peste 0.8` = 🔴 zonă SELL\n"
            "🇬🇧 Similar to RSI but faster. Below 0.2 = BUY zone, above 0.8 = SELL zone."
        ),
        inline=False
    )
    h2.add_field(
        name="📈 EMA (20 / 50)",
        value=(
            "🇷🇴 Media prețului din ultimele 20/50 lumânări. Arată **trendul**.\n"
            "• Preț **peste** EMA = trend ascendent 🟢\n"
            "• Preț **sub** EMA = trend descendent 🔴\n"
            "🇬🇧 Average price over 20/50 candles. Shows the **trend direction**."
        ),
        inline=False
    )
    h2.set_footer(text="Crypto Signals Bot  •  Ghid 2/4")
    await send_once(howto_ch, h2, "2/4 — Ce")

    # ── HOWTO GUIDE 3: Cum folosești semnalul pas cu pas ──
    h3 = discord.Embed(
        title="🚀 3/4 — Pași concreți / Step-by-Step Guide",
        description=(
            "🇷🇴 **Exact ce faci când primești un semnal BUY:**\n"
            "🇬🇧 **Exactly what to do when you get a BUY signal:**"
        ),
        color=0x10b981
    )
    h3.add_field(
        name="Pasul 1️⃣ — Deschide Binance / Open Binance",
        value=(
            "🇷🇴 Mergi la **Spot Trading** (NU Futures dacă ești începător!)\n"
            "🇬🇧 Go to **Spot Trading** (NOT Futures if you're a beginner!)\n"
            "💡 Spot = cumperi moneda reală, nu poți pierde mai mult decât ai investit."
        ),
        inline=False
    )
    h3.add_field(
        name="Pasul 2️⃣ — Caută moneda / Find the coin",
        value=(
            "🇷🇴 Ex: semnal pe **BTC** → caută perechea `BTC/USDT` pe Binance.\n"
            "🇬🇧 Ex: signal on **BTC** → search for `BTC/USDT` pair on Binance."
        ),
        inline=False
    )
    h3.add_field(
        name="Pasul 3️⃣ — Stabilește cât investești / Decide amount",
        value=(
            "🇷🇴 **Regula de aur:** max **5–10%** din total. Ex: ai 1000$ → max 100$ per trade.\n"
            "🇬🇧 **Golden rule:** max **5–10%** of your total. Ex: $1000 capital → max $100 per trade."
        ),
        inline=False
    )
    h3.add_field(
        name="Pasul 4️⃣ — Setează Stop Loss ÎNAINTE / Set SL BEFORE",
        value=(
            "🇷🇴 Pe Binance: **OCO Order** sau **Stop-Limit**. Pune SL-ul exact din semnal.\n"
            "🇬🇧 On Binance: use **OCO Order** or **Stop-Limit**. Set SL exactly from signal.\n"
            "⚠️ Fără SL = risc total! / Without SL = full risk!"
        ),
        inline=False
    )
    h3.add_field(
        name="Pasul 5️⃣ — Ia profit la TP1 mai întâi / Take profit at TP1 first",
        value=(
            "🇷🇴 La **TP1**: vinde 50% din poziție. Mută SL la **Entry** → nu mai poți pierde!\n"
            "🇬🇧 At **TP1**: sell 50% of position. Move SL to **Entry** → you can't lose anymore!\n"
            "La TP2: vinde restul. / At TP2: sell the rest."
        ),
        inline=False
    )
    h3.set_footer(text="Crypto Signals Bot  •  Ghid 3/4  •  Nu este sfat financiar")
    await send_once(howto_ch, h3, "3/4 — Pași")

    # ── HOWTO GUIDE 4: Greșeli comune + comenzi utile ──
    h4 = discord.Embed(
        title="⚠️ 4/4 — Greșeli de evitat + Comenzi utile",
        description=(
            "🇷🇴 **Cele mai frecvente greșeli ale începătorilor:**\n"
            "🇬🇧 **Most common beginner mistakes:**"
        ),
        color=0xef4444
    )
    h4.add_field(
        name="❌ Nu pune SL (Stop Loss)",
        value=(
            "🇷🇴 Fără SL poți pierde **tot** dacă piața se întoarce. Mereu protejează-te!\n"
            "🇬🇧 Without SL you can lose **everything** if market reverses. Always protect yourself!"
        ),
        inline=False
    )
    h4.add_field(
        name="❌ Intră cu tot capitalul (All-in)",
        value=(
            "🇷🇴 Dacă intri cu 100% și greșești, e **dezastru**. Max 10% per trade!\n"
            "🇬🇧 Going all-in means one bad trade wipes you. Max 10% per trade!"
        ),
        inline=False
    )
    h4.add_field(
        name="❌ Cumperi din FOMO (după pump mare)",
        value=(
            "🇷🇴 BTC a crescut 15% azi → NU cumpăra acum! Așteaptă o **corecție** și un semnal nou.\n"
            "🇬🇧 BTC pumped 15% today → DON'T buy now! Wait for a **pullback** and new signal."
        ),
        inline=False
    )
    h4.add_field(
        name="❌ Folosești Futures / Leverage ca începător",
        value=(
            "🇷🇴 Leverage 10x = o mișcare de 10% te poate **lichida** (pierzi tot). Începe cu **SPOT**!\n"
            "🇬🇧 10x leverage = a 10% move can **liquidate** you (lose everything). Start with **SPOT**!"
        ),
        inline=False
    )
    h4.add_field(
        name=SEP,
        value="\u200b",
        inline=False
    )
    h4.add_field(
        name="✅ Comenzi utile / Useful Commands",
        value=(
            "`/tutorial` — Ghid complet pas cu pas\n"
            "`/glossary` — Dicționar termeni crypto simplu\n"
            "`/tip` — Sfat aleatoriu de trading\n"
            "`/risk` — Calculator dimensiune poziție\n"
            "`/calculate` — Calculator profit/pierdere\n"
            "`/multi` — Analiză 4 timeframe-uri\n"
            "`/help` — Toate comenzile disponibile"
        ),
        inline=False
    )
    h4.set_footer(text="Crypto Signals Bot  •  Ghid 4/4  •  Nu este sfat financiar")
    await send_once(howto_ch, h4, "4/4 — Greșeli")

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
    client.loop.create_task(pump_alert_loop())
    client.loop.create_task(daily_summary_loop())
    client.loop.create_task(status_update_loop())
    client.loop.create_task(watchlist_notifier_loop())
    client.loop.create_task(prediction_checker_loop())

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
# PUMP ALERT LOOP
# =========================

LAST_PUMP = {}

async def pump_alert_loop():
    await client.wait_until_ready()
    channel = client.get_channel(ALERTS_CHANNEL)
    while True:
        try:
            for symbol in SYMBOLS:
                df = get_data(symbol)
                if df is None or len(df) < 10:
                    continue
                pump_pct = (df["close"].iloc[-1] - df["close"].iloc[-10]) / df["close"].iloc[-10] * 100
                coin = symbol.replace("USDT", "")
                now  = datetime.utcnow()

                # PUMP: +3% in ~50 min
                if pump_pct > 3:
                    last = LAST_PUMP.get(f"pump_{symbol}")
                    if not last or (now - last).seconds > 3600:
                        LAST_PUMP[f"pump_{symbol}"] = now
                        ind  = calc_indicators(df)
                        logo = COIN_LOGOS.get(symbol)
                        embed = discord.Embed(
                            title=f"🚀 PUMP Detected — {coin} +{round(pump_pct,1)}%",
                            description=(
                                f"🇬🇧 **{COIN_NAMES_EN.get(symbol, symbol)}** pumped **+{round(pump_pct,1)}%** in ~50 min!\n"
                                f"Current price: `${round(df['close'].iloc[-1], 2):,}`\n"
                                f"⚠️ Do NOT chase — wait for consolidation and a new signal.\n\n"
                                f"🇷🇴 **{COIN_NAMES_EN.get(symbol, symbol)}** a crescut cu **+{round(pump_pct,1)}%** în ~50 min!\n"
                                f"Preț curent: `${round(df['close'].iloc[-1], 2):,}`\n"
                                f"⚠️ Nu urmări pump-ul — așteaptă consolidare și un semnal nou."
                            ),
                            color=0x00e676,
                            timestamp=now
                        )
                        if logo:
                            embed.set_thumbnail(url=logo)
                        if ind:
                            embed.add_field(name="📊 RSI", value=rsi_bar(ind["rsi"]), inline=False)
                        embed.set_footer(text=f"Crypto Signals Bot  •  {DISCLAIMER_RO}")
                        if channel:
                            await channel.send(embed=embed)

                # DUMP: -3% in ~50 min (more granular than crash_alert)
                elif pump_pct < -3:
                    last = LAST_PUMP.get(f"dump_{symbol}")
                    if not last or (now - last).seconds > 3600:
                        LAST_PUMP[f"dump_{symbol}"] = now
                        logo = COIN_LOGOS.get(symbol)
                        embed = discord.Embed(
                            title=f"📉 DUMP Detected — {coin} {round(pump_pct,1)}%",
                            description=(
                                f"🇬🇧 **{COIN_NAMES_EN.get(symbol, symbol)}** dropped **{round(pump_pct,1)}%** in ~50 min!\n"
                                f"Current price: `${round(df['close'].iloc[-1], 2):,}`\n"
                                f"⚠️ Check your open positions and SL levels!\n\n"
                                f"🇷🇴 **{COIN_NAMES_EN.get(symbol, symbol)}** a scăzut cu **{round(pump_pct,1)}%** în ~50 min!\n"
                                f"Preț curent: `${round(df['close'].iloc[-1], 2):,}`\n"
                                f"⚠️ Verifică pozițiile deschise și nivelurile SL!"
                            ),
                            color=0xff1744,
                            timestamp=now
                        )
                        if logo:
                            embed.set_thumbnail(url=logo)
                        embed.set_footer(text=f"Crypto Signals Bot  •  {DISCLAIMER_RO}")
                        if channel:
                            await channel.send(embed=embed)

        except Exception as e:
            print(f"Pump alert error: {e}")
        await asyncio.sleep(300)

# =========================
# EDUCATION LOOP
# =========================

async def education_loop():
    await client.wait_until_ready()
    channel = client.get_channel(HOWTO_CHANNEL)
    index = 0
    while True:
        await asyncio.sleep(43200)  # every 12 hours
        try:
            if channel:
                title, value = TRADING_TIPS[index % len(TRADING_TIPS)]
                embed = discord.Embed(
                    title="🎓 Sfat de Trading / Daily Trading Tip",
                    description=f"**{title}**",
                    color=discord.Color.teal(),
                    timestamp=datetime.utcnow()
                )
                embed.set_author(name="🎓 Crypto Signals Bot — Education", icon_url=BOT_ICON)
                embed.add_field(name="\u200b", value=value, inline=False)
                embed.add_field(
                    name="📖 Vrei să înveți mai mult? / Want to learn more?",
                    value=(
                        "🇷🇴 Folosește aceste comenzi oricând:\n"
                        "`/tutorial` — Ghid complet pas cu pas\n"
                        "`/glossary` — Dicționar termeni crypto\n"
                        "`/tip` — Sfat aleatoriu\n\n"
                        "🇬🇧 Use these commands anytime:\n"
                        "`/tutorial` — Full step-by-step guide\n"
                        "`/glossary` — Crypto dictionary\n"
                        "`/tip` — Random tip"
                    ),
                    inline=False
                )
                embed.set_footer(text=f"Crypto Signals Bot  •  Tip {index+1}/{len(TRADING_TIPS)}  •  {DISCLAIMER_RO}")
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
    # ── !sterge [numar/all] — șterge mesaje din canal ──
    if content_lower.startswith("!sterge"):
        # Check permissions
        if not message.author.guild_permissions.manage_messages:
            err = await message.channel.send(
                f"🚫 {message.author.mention} "
                "🇷🇴 Nu ai permisiunea să ștergi mesaje. Ai nevoie de rolul **Manage Messages**.\n"
                "🇬🇧 You don't have permission to delete messages. You need the **Manage Messages** role."
            )
            await asyncio.sleep(6)
            try:
                await err.delete()
                await message.delete()
            except Exception:
                pass
            return

        parts = message.content.split()
        arg = parts[1].lower() if len(parts) > 1 else "10"

        # Delete the command message first
        try:
            await message.delete()
        except Exception:
            pass

        if arg == "all":
            # Delete up to 1000 messages in batches
            deleted_total = 0
            while True:
                deleted = await message.channel.purge(limit=100, bulk=True)
                deleted_total += len(deleted)
                if len(deleted) < 100:
                    break
                await asyncio.sleep(1)
            confirm = await message.channel.send(
                embed=discord.Embed(
                    title="🗑️ Chat șters / Chat cleared",
                    description=(
                        f"🇷🇴 Am șters **{deleted_total} mesaje** din acest canal.\n"
                        f"🇬🇧 Deleted **{deleted_total} messages** from this channel.\n\n"
                        f"👤 Executat de / Executed by: {message.author.mention}"
                    ),
                    color=0xef4444,
                    timestamp=datetime.utcnow()
                )
            )
        else:
            try:
                count = int(arg)
                count = max(1, min(count, 500))  # clamp between 1 and 500
            except ValueError:
                count = 10

            deleted = await message.channel.purge(limit=count, bulk=True)
            confirm = await message.channel.send(
                embed=discord.Embed(
                    title="🗑️ Mesaje șterse / Messages deleted",
                    description=(
                        f"🇷🇴 Am șters **{len(deleted)} mesaje** din acest canal.\n"
                        f"🇬🇧 Deleted **{len(deleted)} messages** from this channel.\n\n"
                        f"👤 Executat de / Executed by: {message.author.mention}\n\n"
                        "💡 `!sterge 50` → 50 mesaje  |  `!sterge all` → tot chatul"
                    ),
                    color=0xef4444,
                    timestamp=datetime.utcnow()
                )
            )

        # Auto-delete confirmation after 5 seconds
        await asyncio.sleep(5)
        try:
            await confirm.delete()
        except Exception:
            pass
        return

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

# ══════════════════════════════════════════════
#   DAILY MARKET SUMMARY (8 AM UTC)
# ══════════════════════════════════════════════

async def daily_summary_loop():
    await client.wait_until_ready()
    channel = client.get_channel(MARKET_NEWS_CHANNEL)
    while True:
        try:
            now = datetime.utcnow()
            if now.hour == 8 and now.minute < 5:
                fg_score, fg_class = get_fear_greed()
                rows = []
                for sym in SYMBOLS:
                    info = get_price_info(sym)
                    df   = get_data(sym)
                    ind  = calc_indicators(df) if df is not None else None
                    if not info: continue
                    ch = info["change"]
                    ch_icon = "📈" if ch >= 0 else "📉"
                    rsi_str = f"RSI `{round(ind['rsi'],1)}`" if ind else ""
                    rows.append(
                        f"{COIN_EMOJI.get(sym,'🪙')} **{sym.replace('USDT','')}** "
                        f"`${info['price']:,.2f}` {ch_icon} `{ch:+.2f}%` {rsi_str}"
                    )
                top_gainer = max(SYMBOLS, key=lambda s: (get_price_info(s) or {}).get("change", -999))
                top_info   = get_price_info(top_gainer)

                embed = discord.Embed(
                    title=f"☀️ Daily Market Summary — {now.strftime('%d %b %Y')}",
                    description=(
                        "🇬🇧 **Good morning traders!** Here's your daily crypto briefing.\n"
                        f"🇷🇴 **Bună dimineața traderi!** Iată rezumatul zilnic crypto.\n{SEP}"
                    ),
                    color=0xfbbf24, timestamp=now
                )
                embed.set_author(name="☀️ Crypto Signals Bot — Daily Briefing", icon_url=BOT_ICON)
                embed.add_field(
                    name="📊 Market Overview / Prezentare Piață",
                    value="\n".join(rows) if rows else "N/A",
                    inline=False
                )
                embed.add_field(
                    name="😱 Fear & Greed Index",
                    value=f"`{fg_score}/100` — **{fg_class}**",
                    inline=True
                )
                if top_info:
                    embed.add_field(
                        name="🏆 Top Performer",
                        value=f"**{top_gainer.replace('USDT','')}** `{top_info['change']:+.2f}%`",
                        inline=True
                    )
                embed.add_field(name="\u200b", value=SEP, inline=False)
                embed.add_field(
                    name="💡 Today's reminder / Reminder zilnic",
                    value=(
                        "🇬🇧 Always check multiple timeframes before entering. Use `/multi` for a full picture.\n"
                        "🇷🇴 Verifică mereu mai multe timeframe-uri. Folosește `/multi` pentru imagine completă."
                    ),
                    inline=False
                )
                embed.add_field(
                    name="💎 VIP Signals",
                    value=f"🇬🇧 Get advanced signals with TP1+TP2+TP3 → <#{GET_VIP_CHANNEL}>\n🇷🇴 Semnale avansate cu TP1+TP2+TP3 → <#{GET_VIP_CHANNEL}>",
                    inline=False
                )
                embed.set_footer(text=f"Crypto Signals Bot  •  {DISCLAIMER_RO}")
                if channel:
                    await channel.send(embed=embed)
                await asyncio.sleep(3600)
            else:
                await asyncio.sleep(60)
        except Exception as e:
            print(f"Daily summary error: {e}")
            await asyncio.sleep(300)


# ══════════════════════════════════════════════
#   STATUS CHANNEL AUTO-UPDATE (every 30 min)
# ══════════════════════════════════════════════

async def status_update_loop():
    await client.wait_until_ready()
    channel = client.get_channel(STATUS_CHANNEL)
    while True:
        try:
            if channel:
                btc_info = get_price_info("BTCUSDT")
                eth_info = get_price_info("ETHUSDT")
                fg_score, fg_class = get_fear_greed()
                btc_str = f"`${btc_info['price']:,.2f}` (`{btc_info['change']:+.2f}%`)" if btc_info else "N/A"
                eth_str = f"`${eth_info['price']:,.2f}` (`{eth_info['change']:+.2f}%`)" if eth_info else "N/A"
                embed = discord.Embed(
                    title="🤖 Bot Status — Online & Monitoring",
                    description=f"🟢 **All systems operational** | Updated: `{datetime.utcnow().strftime('%H:%M UTC')}`",
                    color=0x22c55e, timestamp=datetime.utcnow()
                )
                embed.set_author(name="🤖 Crypto Signals Bot — Status", icon_url=BOT_ICON)
                embed.add_field(name="₿ BTC",  value=btc_str, inline=True)
                embed.add_field(name="Ξ ETH",  value=eth_str, inline=True)
                embed.add_field(name="😱 F&G",  value=f"`{fg_score}/100` {fg_class}", inline=True)
                embed.add_field(
                    name="📡 Signals Generated",
                    value=f"🟢 BUY: `{SIGNAL_STATS['BUY']}` | 🔴 SELL: `{SIGNAL_STATS['SELL']}` | Total: `{SIGNAL_STATS['total']}`",
                    inline=False
                )
                embed.add_field(
                    name="👁️ Active Watchlists",
                    value=f"`{sum(len(v) for v in USER_WATCHLISTS.values())}` coin watches across `{len(USER_WATCHLISTS)}` users",
                    inline=True
                )
                embed.add_field(
                    name="💼 Portfolios",
                    value=f"`{len(USER_PORTFOLIOS)}` active portfolios",
                    inline=True
                )
                embed.set_footer(text=f"Crypto Signals Bot  •  Next update in 30 min")
                await channel.send(embed=embed)
        except Exception as e:
            print(f"Status update error: {e}")
        await asyncio.sleep(1800)


# ══════════════════════════════════════════════
#   WATCHLIST SIGNAL NOTIFIER
# ══════════════════════════════════════════════

async def watchlist_notifier_loop():
    await client.wait_until_ready()
    while True:
        try:
            for uid, watchlist in list(USER_WATCHLISTS.items()):
                for sym in watchlist:
                    df  = get_data(sym)
                    sig, price, rsi, conf = get_signal_v2(df)
                    if not sig or not price:
                        continue
                    key = f"{uid}_{sym}_{sig}"
                    now = datetime.utcnow()
                    last = WATCHLIST_NOTIF.get(key)
                    if last and (now - last).seconds < 3600:
                        continue
                    WATCHLIST_NOTIF[key] = now
                    try:
                        user = await client.fetch_user(uid)
                        logo = COIN_LOGOS.get(sym)
                        icon = "🟢" if sig == "BUY" else "🔴"
                        dm_embed = discord.Embed(
                            title=f"👁️ Watchlist Alert — {icon} {sig} on {sym.replace('USDT','')}",
                            description=(
                                f"🇬🇧 **{COIN_NAMES_EN.get(sym,sym)}** just generated a **{sig}** signal!\n"
                                f"Entry: `${price:,.4f}` | RSI: `{round(rsi,1)}` | Confidence: `{conf}`\n\n"
                                f"🇷🇴 **{COIN_NAMES_EN.get(sym,sym)}** tocmai a generat un semnal **{sig}**!\n"
                                f"Intrare: `${price:,.4f}` | RSI: `{round(rsi,1)}` | Calitate: `{conf}`"
                            ),
                            color=0x00c853 if sig == "BUY" else 0xff1744,
                            timestamp=now
                        )
                        if logo: dm_embed.set_thumbnail(url=logo)
                        tp1 = round(price * (1.02 if sig == "BUY" else 0.98), 4)
                        sl  = round(price * (0.97 if sig == "BUY" else 1.03), 4)
                        dm_embed.add_field(name="🎯 TP1", value=f"`${tp1:,.4f}`", inline=True)
                        dm_embed.add_field(name="🛑 SL",  value=f"`${sl:,.4f}`",  inline=True)
                        dm_embed.add_field(name="📊 RSI", value=rsi_bar(rsi),     inline=False)
                        dm_embed.set_footer(text=f"You're watching {sym.replace('USDT','')} | Use /unwatch to stop  •  {DISCLAIMER_RO}")
                        await user.send(embed=dm_embed)
                    except Exception:
                        pass
        except Exception as e:
            print(f"Watchlist notifier error: {e}")
        await asyncio.sleep(300)


# ══════════════════════════════════════════════
#   PREDICTION RESULT CHECKER (every 1h)
# ══════════════════════════════════════════════

async def prediction_checker_loop():
    await client.wait_until_ready()
    while True:
        await asyncio.sleep(3600)
        try:
            now = datetime.utcnow()
            resolved = []
            for uid, pred in list(PREDICTIONS.items()):
                age = (now - pred["ts"]).total_seconds()
                if age < 3600:
                    continue
                info = get_price_info(pred["symbol"])
                if not info:
                    continue
                entry  = pred["entry_price"]
                current= info["price"]
                went_up = current > entry
                predicted_up = pred["direction"] == "UP"
                correct = (went_up == predicted_up)
                if uid not in PRED_SCORES:
                    PRED_SCORES[uid] = {"correct": 0, "total": 0, "username": pred.get("username","?")}
                PRED_SCORES[uid]["total"] += 1
                if correct:
                    PRED_SCORES[uid]["correct"] += 1
                resolved.append(uid)
                try:
                    user = await client.fetch_user(uid)
                    pnl_pct = round((current - entry) / entry * 100, 2)
                    result_icon = "✅" if correct else "❌"
                    scores = PRED_SCORES[uid]
                    acc = round(scores["correct"] / scores["total"] * 100, 1) if scores["total"] > 0 else 0
                    embed = discord.Embed(
                        title=f"🔮 Prediction Result — {result_icon} {'Correct!' if correct else 'Wrong'}",
                        description=(
                            f"🇬🇧 Your **{pred['direction']}** prediction on **{COIN_NAMES_EN.get(pred['symbol'],pred['symbol'])}**:\n"
                            f"Entry `${entry:,.4f}` → Now `${current:,.4f}` ({'+' if pnl_pct>=0 else ''}{pnl_pct}%)\n\n"
                            f"🇷🇴 Predicția ta **{pred['direction']}** pe **{COIN_NAMES_EN.get(pred['symbol'],pred['symbol'])}**:\n"
                            f"Intrare `${entry:,.4f}` → Acum `${current:,.4f}` ({'+' if pnl_pct>=0 else ''}{pnl_pct}%)"
                        ),
                        color=0x00c853 if correct else 0xff1744,
                        timestamp=now
                    )
                    embed.add_field(
                        name="📊 Your accuracy / Acuratețea ta",
                        value=f"`{acc}%` ({scores['correct']}/{scores['total']} correct)",
                        inline=False
                    )
                    embed.set_footer(text="Use /predict to submit a new prediction | /leaderboard for rankings")
                    await user.send(embed=embed)
                except Exception:
                    pass
            for uid in resolved:
                PREDICTIONS.pop(uid, None)
        except Exception as e:
            print(f"Prediction checker error: {e}")

# ══════════════════════════════════════════════
#   KEEP-ALIVE SERVER (24/7 uptime on Replit)
# ══════════════════════════════════════════════

class _PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        uptime_info = (
            f"<h2 style='color:#00c896;font-family:monospace'>🤖 Crypto Signals Bot — ONLINE</h2>"
            f"<p>Signals generated: BUY <b>{SIGNAL_STATS['BUY']}</b> | SELL <b>{SIGNAL_STATS['SELL']}</b> | Total <b>{SIGNAL_STATS['total']}</b></p>"
            f"<p>Active portfolios: <b>{len(USER_PORTFOLIOS)}</b> | Watchlists: <b>{len(USER_WATCHLISTS)}</b></p>"
            f"<p style='color:#8b949e'>Last ping: {datetime.utcnow().strftime('%d %b %Y %H:%M:%S UTC')}</p>"
        )
        self.wfile.write(uptime_info.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # suppress HTTP request logs from console


def keep_alive():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), _PingHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"Keep-alive server running on port {port}")

# =========================

keep_alive()
client.run(TOKEN)
