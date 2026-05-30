"""
auto_trader.py — Smart Auto-Trader cu DM interactiv

FILOSOFIE:
  - Citește semnale din botul tău de Discord (FREE + VIP)
  - Îți trimite un DM cu detalii complete ÎNAINTE să execute
  - Tu decizi: ✅ Confirm / ❌ Skip / ⚙️ Modifică parametrii
  - Timeout 60 secunde → sare automat dacă nu răspunzi
  - Rulează pe Binance TESTNET (sigur, fără bani reali)
  - Monitorizează pozițiile și îți trimite update-uri în timp real
  - Acces la toate cele 30 de monede din VIP

COMENZI DM:
  ✅ sau "da"          → confirmă trade-ul
  ❌ sau "nu"          → anulează
  "risk 2"            → schimbă risk% pentru trade-ul curent
  "sl 63000"          → schimbă stop-loss
  "tp 70000"          → schimbă target
  "!status"           → portofoliu + trades deschise
  "!pnl"              → profit/pierdere totală
  "!close #5"         → închide manual trade #5
  "!stop"             → oprește autotraderul (kill switch)
  "!start"            → repornește
  "!risk 3"           → schimbă risk% global
  "!help"             → toate comenzile

ENV VARIABLES:
  DISCORD_BOT_TOKEN   — token Discord (același ca botul tău sau separat)
  BINANCE_API_KEY     — Binance API key cu permisiuni Spot + Futures Testnet
  BINANCE_SECRET      — Binance API secret
  SIGNALS_CHANNEL_ID  — ID canal semnale FREE sau VIP
  TRADER_USER_ID      — Discord User ID al tău (primești DM-urile)
  TESTNET             — "true" (default) sau "false" pentru live
  MAX_TRADES          — trades simultane max (default: 5)
  RISK_PERCENT        — % din balanță per trade (default: 2)
  CONFIRM_TIMEOUT     — secunde așteptare confirmare (default: 60)
  AUTO_CONFIRM        — "true" execută fără să mai ceară confirmare (PERICULOS)
"""

from __future__ import annotations

import os
import re
import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import discord
from discord.ext import commands, tasks
import market_data

# ─── LOGGING ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("auto_trader")

# ─── CONFIG DIN ENV ───────────────────────────────────────────────────────────
def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()

def _env_int(name: str, default: int) -> int:
    try: return int(os.environ.get(name, default))
    except: return default

def _env_float(name: str, default: float) -> float:
    try: return float(os.environ.get(name, default))
    except: return default

DISCORD_TOKEN     = _env("DISCORD_BOT_TOKEN")
BINANCE_KEY       = _env("BINANCE_API_KEY")
BINANCE_SECRET    = _env("BINANCE_SECRET")
SIGNALS_CHANNEL_ID = _env_int("SIGNALS_CHANNEL_ID", 0)
TRADER_USER_ID     = _env_int("TRADER_USER_ID", 0)     # TU — primești DM-uri
TESTNET            = _env("TESTNET", "true").lower() == "true"
MAX_TRADES         = _env_int("MAX_TRADES", 5)
RISK_PERCENT       = _env_float("RISK_PERCENT", 2.0)
CONFIRM_TIMEOUT    = _env_int("CONFIRM_TIMEOUT", 60)   # secunde
AUTO_CONFIRM       = _env("AUTO_CONFIRM", "false").lower() == "true"

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN lipsește din ENV")
if not BINANCE_KEY or not BINANCE_SECRET:
    log.warning("BINANCE_API_KEY / BINANCE_SECRET lipsesc — rulare în PAPER MODE cu prețuri publice live")

# ─── BINANCE CLIENT ───────────────────────────────────────────────────────────
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException
    if BINANCE_KEY and BINANCE_SECRET:
        if TESTNET:
            binance = Client(BINANCE_KEY, BINANCE_SECRET, testnet=True)
            log.info("🧪 Binance TESTNET activ")
        else:
            binance = Client(BINANCE_KEY, BINANCE_SECRET)
            log.info("🚀 Binance LIVE activ — ATENȚIE: bani reali!")
        BINANCE_OK = True
    else:
        binance = None
        BINANCE_OK = False
except ImportError:
    log.warning("python-binance nu este instalat — PAPER MODE cu prețuri publice live")
    binance    = None
    BINANCE_OK = False

# ─── COINS REGISTRY (din proiectul tău) ──────────────────────────────────────
try:
    import coins_config
    ALL_SYMBOLS = coins_config.ALL_VIP_SYMBOLS    # toate 30 monedele VIP
    COIN_META   = coins_config.COIN_META
    log.info(f"Loaded {len(ALL_SYMBOLS)} coins from coins_config")
except ImportError:
    # Fallback dacă modulul nu e în path
    ALL_SYMBOLS = [
        "BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT",
        "ADAUSDT","AVAXUSDT","DOTUSDT","LINKUSDT","LTCUSDT","MATICUSDT",
        "UNIUSDT","ATOMUSDT","XLMUSDT","NEARUSDT","FTMUSDT","ALGOUSDT",
        "SANDUSDT","MANAUSDT","FILUSDT","TRXUSDT","ETCUSDT","AAVEUSDT",
        "GRTUSDT","SHIBUSDT","OPUSDT","ARBUSDT","INJUSDT","SUIUSDT",
    ]
    COIN_META = {}
    log.warning("coins_config.py nu a fost găsit — folosind lista hardcodată")

# ─── DATABASE ─────────────────────────────────────────────────────────────────
DB_PATH = "auto_trades.db"

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with _db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol       TEXT    NOT NULL,
                side         TEXT    NOT NULL,         -- BUY / SELL
                entry_price  REAL    NOT NULL,
                qty          REAL    NOT NULL,
                target       REAL    NOT NULL,         -- TP1
                target2      REAL,                     -- TP2
                target3      REAL,                     -- TP3
                stop_loss    REAL    NOT NULL,
                current_price REAL,
                exit_price   REAL,
                pnl_usdt     REAL,
                pnl_pct      REAL,
                status       TEXT    DEFAULT 'PENDING', -- PENDING/OPEN/CLOSED/CANCELLED
                source       TEXT,                     -- "FREE" / "VIP" / "MANUAL"
                confidence   TEXT,
                rr           REAL,
                opened_at    TEXT,
                closed_at    TEXT,
                close_reason TEXT                      -- TARGET/STOP/MANUAL/TIMEOUT
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS daily_pnl (
                date       TEXT PRIMARY KEY,
                pnl_usdt   REAL DEFAULT 0,
                trades_won INTEGER DEFAULT 0,
                trades_lost INTEGER DEFAULT 0
            );
        """)
        # Setări default
        conn.execute("INSERT OR IGNORE INTO settings VALUES ('risk_pct', ?)", (str(RISK_PERCENT),))
        conn.execute("INSERT OR IGNORE INTO settings VALUES ('trading_active', 'true')")
        conn.execute("INSERT OR IGNORE INTO settings VALUES ('max_trades', ?)", (str(MAX_TRADES),))

def get_setting(key: str, default: str = "") -> str:
    with _db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

def set_setting(key: str, value: str):
    with _db() as conn:
        conn.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, value))

def save_trade(
    symbol: str, side: str, entry: float, qty: float,
    target: float, stop_loss: float, source: str = "VIP",
    confidence: str = "", rr: float = 0.0,
    target2: float = 0.0, target3: float = 0.0,
) -> int:
    with _db() as conn:
        cur = conn.execute("""
            INSERT INTO trades
              (symbol,side,entry_price,qty,target,target2,target3,stop_loss,
               status,source,confidence,rr,opened_at)
            VALUES (?,?,?,?,?,?,?,?,'OPEN',?,?,?,?)
        """, (symbol, side, entry, qty, target, target2 or 0, target3 or 0,
              stop_loss, source, confidence, rr,
              datetime.now(timezone.utc).isoformat()))
        return cur.lastrowid

def close_trade_db(trade_id: int, exit_price: float, reason: str = "MANUAL"):
    with _db() as conn:
        row = conn.execute(
            "SELECT entry_price, qty, side FROM trades WHERE id=?", (trade_id,)
        ).fetchone()
        if not row:
            return
        entry, qty, side = row["entry_price"], row["qty"], row["side"]
        pnl_usdt = (exit_price - entry) * qty if side == "BUY" else (entry - exit_price) * qty
        pnl_pct  = (pnl_usdt / (entry * qty)) * 100 if entry * qty > 0 else 0
        now      = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            UPDATE trades
            SET exit_price=?, pnl_usdt=?, pnl_pct=?, status='CLOSED',
                closed_at=?, close_reason=?
            WHERE id=?
        """, (exit_price, round(pnl_usdt, 4), round(pnl_pct, 2), now, reason, trade_id))
        # Actualizează daily_pnl
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        conn.execute("""
            INSERT INTO daily_pnl (date, pnl_usdt, trades_won, trades_lost)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
              pnl_usdt = pnl_usdt + excluded.pnl_usdt,
              trades_won  = trades_won  + excluded.trades_won,
              trades_lost = trades_lost + excluded.trades_lost
        """, (
            today, round(pnl_usdt, 4),
            1 if pnl_usdt > 0 else 0,
            1 if pnl_usdt <= 0 else 0,
        ))

def get_open_trades() -> list[sqlite3.Row]:
    with _db() as conn:
        return conn.execute("SELECT * FROM trades WHERE status='OPEN'").fetchall()

def total_pnl() -> tuple[float, int, int]:
    """Returns (pnl_usdt, wins, losses)"""
    with _db() as conn:
        row = conn.execute("""
            SELECT COALESCE(SUM(pnl_usdt),0) as p,
                   SUM(CASE WHEN pnl_usdt>0 THEN 1 ELSE 0 END) as w,
                   SUM(CASE WHEN pnl_usdt<=0 THEN 1 ELSE 0 END) as l
            FROM trades WHERE status='CLOSED'
        """).fetchone()
        return float(row["p"]), int(row["w"]), int(row["l"])

# ─── STATE GLOBAL ─────────────────────────────────────────────────────────────
_open_trades:    dict[int, dict] = {}     # trade_id -> info dict
_pending_confirms: dict[int, asyncio.Future] = {}  # msg_id -> future (pentru confirm DM)
_current_risk = RISK_PERCENT

# ─── PARSARE SEMNAL ───────────────────────────────────────────────────────────
def parse_signal(text: str) -> Optional[dict]:
    """
    Suportă semnalele generate de botul tău (embed + text).
    Extrage: symbol, side, entry, TP1/TP2/TP3, SL, confidence, source (FREE/VIP).
    """
    t = text.upper()

    # Direcție
    side = None
    if re.search(r"\b(BUY|LONG|🟢|📈)\b", t):    side = "BUY"
    elif re.search(r"\b(SELL|SHORT|🔴|📉)\b", t): side = "SELL"
    if not side:
        return None

    # Symbol
    m = re.search(r"\b([A-Z]{2,10})[/\-]?(USDT|BTC|ETH|BNB)\b", t)
    if not m:
        return None
    symbol = m.group(1) + m.group(2)

    # Verifică că moneda e în lista noastră
    if symbol not in ALL_SYMBOLS:
        return None

    # Entry price
    em = re.search(r"(?:ENTRY|ENTRY PRICE|INTRARE)[:\s\|]+\$?([0-9,]+\.?[0-9]*)", t)
    if not em:
        return None
    entry = float(em.group(1).replace(",", ""))

    # TP1
    t1m = re.search(r"(?:TP1?|TARGET\s*1?|TAKE PROFIT)[:\s\|]+\$?([0-9,]+\.?[0-9]*)", t)
    tp1 = float(t1m.group(1).replace(",", "")) if t1m else (entry * 1.03 if side == "BUY" else entry * 0.97)

    # TP2
    t2m = re.search(r"(?:TP2|TARGET\s*2)[:\s\|]+\$?([0-9,]+\.?[0-9]*)", t)
    tp2 = float(t2m.group(1).replace(",", "")) if t2m else 0.0

    # TP3
    t3m = re.search(r"(?:TP3|TARGET\s*3)[:\s\|]+\$?([0-9,]+\.?[0-9]*)", t)
    tp3 = float(t3m.group(1).replace(",", "")) if t3m else 0.0

    # Stop Loss
    slm = re.search(r"(?:STOP|SL|STOP.?LOSS|STOPLOSS)[:\s\|]+\$?([0-9,]+\.?[0-9]*)", t)
    stop_loss = float(slm.group(1).replace(",", "")) if slm else (
        entry * 0.97 if side == "BUY" else entry * 1.03
    )

    # Confidence (din botul tău)
    conf = "MEDIUM"
    if re.search(r"(VERY HIGH|🌟)", t): conf = "VERY HIGH"
    elif re.search(r"(HIGH|🔥)",  t):  conf = "HIGH"
    elif re.search(r"(LOW|📊)",   t):  conf = "LOW"

    # Source
    source = "VIP" if re.search(r"\bVIP\b", t) else "FREE"

    # R:R
    rr = round(abs(tp1 - entry) / abs(stop_loss - entry), 2) if abs(stop_loss - entry) > 0 else 1.5

    return {
        "symbol":    symbol,
        "side":      side,
        "entry":     entry,
        "tp1":       tp1,
        "tp2":       tp2,
        "tp3":       tp3,
        "stop_loss": stop_loss,
        "confidence": conf,
        "source":    source,
        "rr":        rr,
    }

# ─── CALCUL CANTITATE ─────────────────────────────────────────────────────────
def calc_qty(symbol: str, entry: float, risk_pct: float) -> float:
    """
    Calculează cantitatea pe baza risk% din balanță.
    Paper trade: simulează o balanță de 1000 USDT.
    """
    if not BINANCE_OK or not binance:
        # Paper trade: simulăm 1000 USDT
        balance   = 1000.0
        to_use    = balance * (risk_pct / 100)
        return round(to_use / entry, 6)

    try:
        balance_data = binance.get_account()
        usdt_balance = next(
            (float(b["free"]) for b in balance_data["balances"] if b["asset"] == "USDT"),
            100.0
        )
        to_use = usdt_balance * (risk_pct / 100)
        return round(to_use / entry, 6)
    except Exception as e:
        log.error(f"Eroare calcul balanță: {e}")
        return round((100.0 * risk_pct / 100) / entry, 6)

# ─── OBȚINE PREȚUL CURENT ─────────────────────────────────────────────────────
def get_price(symbol: str) -> float:
    try:
        px = market_data.get_current_price(symbol)
        return float(px or 0.0)
    except Exception:
        return 0.0

# ─── EXECUȚIE ORDIN ───────────────────────────────────────────────────────────
async def execute_order(signal: dict, qty: float) -> tuple[bool, str]:
    """
    Execută ordinul pe Binance.
    Returnează (success, message).
    """
    symbol    = signal["symbol"]
    side      = signal["side"]
    stop_loss = signal["stop_loss"]
    entry     = signal["entry"]

    if not BINANCE_OK or not binance:
        # PAPER TRADE — virtual execution, priced from public live market data when available.
        live_entry = get_price(symbol) or entry
        signal["entry"] = live_entry
        log.info(f"[PAPER] {side} {qty} {symbol} @ {live_entry}")
        return True, f"📝 PAPER TRADE (preț public live): {side} {qty} {symbol} @ ${live_entry:,.4f}"

    try:
        if side == "BUY":
            order = binance.order_market_buy(symbol=symbol, quantity=qty)
        else:
            order = binance.order_market_sell(symbol=symbol, quantity=qty)

        actual_price = float(order.get("fills", [{}])[0].get("price", entry))
        log.info(f"Ordin executat: {side} {qty} {symbol} @ {actual_price}")
        return True, f"✅ Ordin executat pe Binance: {side} {qty} {symbol} @ ${actual_price:,.4f}"

    except BinanceAPIException as e:
        log.error(f"BinanceAPIException {symbol}: {e.message}")
        return False, f"❌ Eroare Binance: {e.message}"
    except Exception as e:
        log.error(f"Eroare execuție {symbol}: {e}")
        return False, f"❌ Eroare: {e}"

# ─── FORMARE MESAJ DM (confirm request) ──────────────────────────────────────
def _dm_confirm_message(signal: dict, qty: float, risk_pct: float) -> str:
    s    = signal
    sym  = s["symbol"]
    side = s["side"]
    coin = sym.replace("USDT", "")
    emoji = "🟢" if side == "BUY" else "🔴"
    mode  = "🧪 TESTNET" if TESTNET else "🚀 LIVE"
    usdt_risk = qty * s["entry"] * (risk_pct / 100)
    rr   = s.get("rr", 1.5)

    # Iconiță confidence
    conf_icons = {"VERY HIGH": "🌟", "HIGH": "🔥", "MEDIUM": "⚡", "LOW": "📊"}
    conf_icon  = conf_icons.get(s.get("confidence", "MEDIUM"), "⚡")

    msg = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{emoji} **SEMNAL NOU — {s['source']} TIER** | {mode}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"**{side}** `{coin}` — {conf_icon} {s.get('confidence','MEDIUM')}\n\n"
        f"💰 **Entry:**   `${s['entry']:,.4f}`\n"
        f"🎯 **TP1:**     `${s['tp1']:,.4f}` (+{abs(s['tp1']-s['entry'])/s['entry']*100:.2f}%)\n"
    )
    if s.get("tp2"):
        msg += f"🎯 **TP2:**     `${s['tp2']:,.4f}` (+{abs(s['tp2']-s['entry'])/s['entry']*100:.2f}%)\n"
    if s.get("tp3"):
        msg += f"🎯 **TP3:**     `${s['tp3']:,.4f}` (+{abs(s['tp3']-s['entry'])/s['entry']*100:.2f}%)\n"
    msg += (
        f"🛑 **Stop Loss:** `${s['stop_loss']:,.4f}` (-{abs(s['stop_loss']-s['entry'])/s['entry']*100:.2f}%)\n"
        f"📊 **R:R:**    `{rr:.1f}:1`\n\n"
        f"📦 **Cantitate:** `{qty} {coin}`\n"
        f"💵 **Risc USDT:** ~`${usdt_risk:.2f}` ({risk_pct}% din balanță)\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"**Răspunde în {CONFIRM_TIMEOUT}s:**\n"
        f"✅  `da` / `yes`  →  Execută\n"
        f"❌  `nu` / `no`   →  Sari\n"
        f"⚙️  `risk 1.5`    →  Schimbă risk%\n"
        f"⚙️  `sl 62000`    →  Schimbă Stop Loss\n"
        f"⚙️  `tp 70000`    →  Schimbă TP1\n"
    )
    return msg

def _dm_trade_opened(trade_id: int, signal: dict, qty: float) -> str:
    s   = signal
    sym = s["symbol"]
    coin = sym.replace("USDT", "")
    emoji = "🟢" if s["side"] == "BUY" else "🔴"
    mode = "🧪 PAPER" if (not BINANCE_OK) else ("🧪 TESTNET" if TESTNET else "🚀 LIVE")
    return (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{emoji} **TRADE #{trade_id} DESCHIS** | {mode}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"**{s['side']}** `{qty} {coin}` @ `${s['entry']:,.4f}`\n"
        f"🎯 Target: `${s['tp1']:,.4f}` | 🛑 SL: `${s['stop_loss']:,.4f}`\n"
        f"📊 R:R: `{s.get('rr',1.5):.1f}:1`\n\n"
        f"Monitorizez prețul la fiecare 30s.\n"
        f"Poți închide manual cu: `!close #{trade_id}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

def _dm_trade_closed(trade_id: int, symbol: str, side: str,
                      entry: float, exit_price: float,
                      qty: float, reason: str) -> str:
    pnl      = (exit_price - entry) * qty if side == "BUY" else (entry - exit_price) * qty
    pnl_pct  = (pnl / (entry * qty)) * 100 if entry * qty > 0 else 0
    won      = pnl > 0
    emoji    = "💰" if won else "💸"
    coin     = symbol.replace("USDT", "")
    reason_labels = {
        "TARGET": "✅ TARGET atins",
        "TARGET2": "✅ TP2 atins",
        "TARGET3": "✅ TP3 atins",
        "STOP":  "🛑 Stop-Loss atins",
        "MANUAL": "👋 Închis manual",
    }
    label = reason_labels.get(reason, reason)
    return (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{emoji} **TRADE #{trade_id} ÎNCHIS**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"`{coin}` | {label}\n"
        f"Entry: `${entry:,.4f}` → Exit: `${exit_price:,.4f}`\n"
        f"**PnL: `{'+'if pnl>=0 else ''}{pnl:.2f} USDT` ({'+' if pnl_pct>=0 else ''}{pnl_pct:.1f}%)**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

# ─── DISCORD BOT ──────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages     = True
intents.members         = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

async def _get_trader_dm() -> Optional[discord.DMChannel]:
    """Obține DM channel cu userul tău (TRADER_USER_ID)."""
    if not TRADER_USER_ID:
        return None
    try:
        user = await bot.fetch_user(TRADER_USER_ID)
        return await user.create_dm()
    except Exception as e:
        log.error(f"Nu pot deschide DM cu {TRADER_USER_ID}: {e}")
        return None

async def _ask_confirm(dm: discord.DMChannel, signal: dict, qty: float) -> dict | None:
    """
    Trimite mesajul de confirmare și așteaptă răspunsul.
    Returnează dict-ul de semnal (posibil modificat) sau None dacă e anulat.
    """
    msg = _dm_confirm_message(signal, qty, _current_risk)
    sent = await dm.send(msg)

    # Adaugă reacții quick-confirm
    try:
        await sent.add_reaction("✅")
        await sent.add_reaction("❌")
    except Exception:
        pass

    if AUTO_CONFIRM:
        await asyncio.sleep(1)
        await dm.send("⚡ **Auto-confirm activat** — execut automat.")
        return signal

    def check_msg(m: discord.Message):
        return m.channel == dm and m.author.id == TRADER_USER_ID

    def check_react(reaction: discord.Reaction, user: discord.User):
        return (user.id == TRADER_USER_ID
                and reaction.message.id == sent.id
                and str(reaction.emoji) in ("✅", "❌"))

    deadline  = asyncio.get_event_loop().time() + CONFIRM_TIMEOUT
    modified  = dict(signal)

    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            await dm.send(
                f"⏰ **Timeout** — {CONFIRM_TIMEOUT}s fără răspuns. Semnalul a fost sărit."
            )
            return None

        try:
            done, _ = await asyncio.wait(
                [
                    asyncio.ensure_future(
                        bot.wait_for("message", check=check_msg, timeout=remaining)
                    ),
                    asyncio.ensure_future(
                        bot.wait_for("reaction_add", check=check_react, timeout=remaining)
                    ),
                ],
                return_when=asyncio.FIRST_COMPLETED,
                timeout=remaining
            )
        except Exception:
            await dm.send(f"⏰ **Timeout** — semnalul a fost sărit.")
            return None

        if not done:
            await dm.send(f"⏰ **Timeout** — semnalul a fost sărit.")
            return None

        result = done.pop().result()
        # Anulează celelalte task-uri
        for task in done:
            task.cancel()

        # Reacție ✅ / ❌
        if isinstance(result, tuple):   # reaction_add
            reaction, user = result
            if str(reaction.emoji) == "✅":
                await dm.send("✅ Confirmat — execut acum!")
                return modified
            elif str(reaction.emoji) == "❌":
                await dm.send("❌ Anulat — sărim semnalul.")
                return None

        # Mesaj text
        text = result.content.strip().lower()

        if text in ("da", "yes", "✅", "1", "confirm", "ok"):
            await dm.send("✅ Confirmat — execut acum!")
            return modified

        if text in ("nu", "no", "❌", "0", "skip", "nope"):
            await dm.send("❌ Anulat — sărim semnalul.")
            return None

        # Modificare risk
        m = re.match(r"risk\s+([0-9]+\.?[0-9]*)", text)
        if m:
            new_risk = float(m.group(1))
            new_qty  = calc_qty(modified["symbol"], modified["entry"], new_risk)
            modified["_risk_pct"] = new_risk
            await dm.send(
                f"⚙️ Risk schimbat la **{new_risk}%** — cantitate nouă: `{new_qty}`\n"
                f"Răspunde `da` pentru a confirma sau `nu` pentru a anula."
            )
            continue

        # Modificare SL
        m = re.match(r"sl\s+([0-9,]+\.?[0-9]*)", text)
        if m:
            new_sl = float(m.group(1).replace(",", ""))
            modified["stop_loss"] = new_sl
            rr = round(abs(modified["tp1"] - modified["entry"]) / abs(new_sl - modified["entry"]), 2)
            await dm.send(
                f"⚙️ Stop Loss schimbat la **${new_sl:,.4f}** — R:R nou: `{rr}:1`\n"
                f"Răspunde `da` pentru a confirma sau `nu` pentru a anula."
            )
            continue

        # Modificare TP
        m = re.match(r"tp\s+([0-9,]+\.?[0-9]*)", text)
        if m:
            new_tp = float(m.group(1).replace(",", ""))
            modified["tp1"] = new_tp
            rr = round(abs(new_tp - modified["entry"]) / abs(modified["stop_loss"] - modified["entry"]), 2)
            await dm.send(
                f"⚙️ Target schimbat la **${new_tp:,.4f}** — R:R nou: `{rr}:1`\n"
                f"Răspunde `da` pentru a confirma sau `nu` pentru a anula."
            )
            continue

        # Mesaj necunoscut
        await dm.send(
            f"❓ Nu am înțeles. Răspunde:\n"
            f"`da` / `nu` / `risk 2.5` / `sl 62000` / `tp 70000`"
        )

# ─── PROCESARE SEMNAL (apelat la fiecare mesaj din canalul de semnale) ────────
async def process_signal(signal: dict):
    global _current_risk, _open_trades

    trading_on = get_setting("trading_active", "true") == "true"
    if not trading_on:
        log.info("Trading oprit — semnal ignorat")
        return

    max_t = int(get_setting("max_trades", str(MAX_TRADES)))
    if len(_open_trades) >= max_t:
        log.warning(f"MAX_TRADES ({max_t}) atins — semnal ignorat")
        return

    dm = await _get_trader_dm()
    if not dm:
        log.error("Nu pot trimite DM — TRADER_USER_ID invalid sau lipsă")
        return

    risk_pct = float(get_setting("risk_pct", str(RISK_PERCENT)))
    qty      = calc_qty(signal["symbol"], signal["entry"], risk_pct)

    # Cere confirmare (sau auto-confirm)
    confirmed = await _ask_confirm(dm, signal, qty)
    if not confirmed:
        return

    # Recalculează qty dacă risk-ul a fost modificat în DM
    if "_risk_pct" in confirmed:
        risk_pct = confirmed["_risk_pct"]
        qty      = calc_qty(confirmed["symbol"], confirmed["entry"], risk_pct)

    # Execută ordinul
    ok, exec_msg = await execute_order(confirmed, qty)
    if not ok:
        await dm.send(f"⚠️ Execuția a eșuat: {exec_msg}")
        return

    # Salvează în DB
    trade_id = save_trade(
        symbol      = confirmed["symbol"],
        side        = confirmed["side"],
        entry       = confirmed["entry"],
        qty         = qty,
        target      = confirmed["tp1"],
        target2     = confirmed.get("tp2", 0),
        target3     = confirmed.get("tp3", 0),
        stop_loss   = confirmed["stop_loss"],
        source      = confirmed.get("source", "VIP"),
        confidence  = confirmed.get("confidence", ""),
        rr          = confirmed.get("rr", 0),
    )

    _open_trades[trade_id] = {
        "symbol":    confirmed["symbol"],
        "side":      confirmed["side"],
        "entry":     confirmed["entry"],
        "qty":       qty,
        "tp1":       confirmed["tp1"],
        "tp2":       confirmed.get("tp2", 0),
        "tp3":       confirmed.get("tp3", 0),
        "stop_loss": confirmed["stop_loss"],
    }

    await dm.send(_dm_trade_opened(trade_id, confirmed, qty))
    log.info(f"Trade #{trade_id} deschis: {confirmed['side']} {qty} {confirmed['symbol']}")

# ─── MONITOR POZITII ──────────────────────────────────────────────────────────
@tasks.loop(seconds=30)
async def monitor_loop():
    """Verifică fiecare poziție deschisă la fiecare 30 secunde."""
    if not _open_trades:
        return

    dm = await _get_trader_dm()
    to_close: list[int] = []

    for trade_id, t in list(_open_trades.items()):
        symbol     = t["symbol"]
        side       = t["side"]
        current    = get_price(symbol)
        if current <= 0:
            continue

        hit_tp1 = (side == "BUY"  and current >= t["tp1"]) or \
                  (side == "SELL" and current <= t["tp1"])
        hit_tp2 = t.get("tp2") and (
            (side == "BUY"  and current >= t["tp2"]) or
            (side == "SELL" and current <= t["tp2"])
        )
        hit_tp3 = t.get("tp3") and (
            (side == "BUY"  and current >= t["tp3"]) or
            (side == "SELL" and current <= t["tp3"])
        )
        hit_sl  = (side == "BUY"  and current <= t["stop_loss"]) or \
                  (side == "SELL" and current >= t["stop_loss"])

        reason = None
        if hit_tp3:  reason = "TARGET3"
        elif hit_tp2: reason = "TARGET2"
        elif hit_tp1: reason = "TARGET"
        elif hit_sl:  reason = "STOP"

        if reason:
            close_trade_db(trade_id, current, reason)
            to_close.append(trade_id)
            if dm:
                await dm.send(
                    _dm_trade_closed(
                        trade_id, symbol, side,
                        t["entry"], current, t["qty"], reason
                    )
                )
            log.info(f"Trade #{trade_id} închis @ {current} — {reason}")

    for tid in to_close:
        _open_trades.pop(tid, None)

@monitor_loop.before_loop
async def before_monitor():
    await bot.wait_until_ready()

# ─── EVENT: ON_READY ──────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    init_db()
    monitor_loop.start()
    log.info(f"✅ Auto-trader pornit ca {bot.user}")

    dm = await _get_trader_dm()
    if dm:
        mode  = "PAPER 📝" if not BINANCE_OK else ("TESTNET 🧪" if TESTNET else "LIVE 🚀")
        coins = len(ALL_SYMBOLS)
        await dm.send(
            f"⚙️ **Auto-Trader pornit!**\n\n"
            f"Mod: **{mode}**\n"
            f"Monede scanate: **{coins}** (toate VIP)\n"
            f"Risk per trade: **{RISK_PERCENT}%**\n"
            f"Max trades simultane: **{MAX_TRADES}**\n"
            f"Confirmare: **{'AUTO ⚡' if AUTO_CONFIRM else f'Manual ({CONFIRM_TIMEOUT}s)'}\n\n**"
            f"Ascult semnale din canalul de semnale.\n"
            f"Trimite `!help` pentru toate comenzile.\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

# ─── EVENT: ON_MESSAGE (citește semnale din canal) ────────────────────────────
@bot.event
async def on_message(message: discord.Message):
    # Procesează comenzile !start, !stop etc.
    await bot.process_commands(message)

    # Ignoră mesajele proprii
    if message.author.id == bot.user.id:
        return

    # DM-uri de la trader → tratate de comenzi
    if isinstance(message.channel, discord.DMChannel):
        return

    # Canalul de semnale
    if message.channel.id != SIGNALS_CHANNEL_ID:
        return

    # Extrage textul (embed + text normal)
    text = message.content or ""
    if message.embeds:
        for emb in message.embeds:
            parts = []
            if emb.title:       parts.append(emb.title)
            if emb.description: parts.append(emb.description)
            for f in emb.fields:
                parts.append(f"{f.name}: {f.value}")
            text += "\n" + "\n".join(parts)

    if not text.strip():
        return

    signal = parse_signal(text)
    if not signal:
        return

    log.info(f"Semnal detectat: {signal['side']} {signal['symbol']} entry={signal['entry']}")
    asyncio.create_task(process_signal(signal))

# ─── COMENZI DM ───────────────────────────────────────────────────────────────

def _only_trader():
    """Check: doar TRADER_USER_ID poate folosi comenzile."""
    async def predicate(ctx):
        return ctx.author.id == TRADER_USER_ID or not TRADER_USER_ID
    return commands.check(predicate)

@bot.command(name="help")
@_only_trader()
async def cmd_help(ctx):
    await ctx.send(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚙️ **Auto-Trader — Comenzi DM**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "**`!status`**      — portofoliu + trades deschise\n"
        "**`!pnl`**         — profit/pierdere total\n"
        "**`!trades`**      — lista trades deschise\n"
        "**`!close #ID`**   — închide manual un trade\n"
        "**`!stop`**        — oprește autotraderul\n"
        "**`!start`**       — repornește autotraderul\n"
        "**`!risk 2.5`**    — schimbă risk% global\n"
        "**`!maxtr 5`**     — schimbă max trades\n"
        "**`!autoconfirm`** — activează execuție fără confirmare\n"
        "**`!manualconfirm`** — reactivează confirmare manuală\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "**La confirmare semnal:**\n"
        "`da` / `nu` — confirmă / anulează\n"
        "`risk 1.5` — schimbă risk%\n"
        "`sl 62000` — schimbă stop-loss\n"
        "`tp 70000` — schimbă target\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

@bot.command(name="status")
@_only_trader()
async def cmd_status(ctx):
    active    = get_setting("trading_active", "true") == "true"
    risk      = get_setting("risk_pct", str(RISK_PERCENT))
    max_t     = get_setting("max_trades", str(MAX_TRADES))
    open_n    = len(_open_trades)
    state_ico = "✅" if active else "🛑"
    mode      = "PAPER" if not BINANCE_OK else ("TESTNET 🧪" if TESTNET else "LIVE 🚀")

    lines = [
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 **Status Auto-Trader**",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Stare: {state_ico} {'ACTIV' if active else 'OPRIT'}",
        f"Mod: `{mode}`",
        f"Risk: `{risk}%` | Max trades: `{max_t}`",
        f"Trades deschise: `{open_n}/{max_t}`",
        f"Monede urmărite: `{len(ALL_SYMBOLS)}`",
    ]
    if _open_trades:
        lines.append("\n**Trades deschise:**")
        for tid, t in _open_trades.items():
            cur   = get_price(t["symbol"])
            pnl   = (cur - t["entry"]) * t["qty"] if t["side"] == "BUY" else (t["entry"] - cur) * t["qty"]
            emoji = "🟢" if pnl >= 0 else "🔴"
            lines.append(
                f"{emoji} `#{tid}` {t['side']} {t['symbol'].replace('USDT','')} "
                f"@ ${t['entry']:,.4f} → ${cur:,.4f} | PnL: `{pnl:+.2f}$`"
            )
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    await ctx.send("\n".join(lines))

@bot.command(name="pnl")
@_only_trader()
async def cmd_pnl(ctx):
    total, wins, losses = total_pnl()
    win_rate = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
    pnl_ico  = "💰" if total >= 0 else "💸"
    await ctx.send(
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{pnl_ico} **PnL Total (closed trades)**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"PnL: **`{total:+.2f} USDT`**\n"
        f"Win/Loss: `{wins}W / {losses}L` — Win Rate: `{win_rate:.1f}%`\n"
        f"Trades totale: `{wins + losses}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

@bot.command(name="trades")
@_only_trader()
async def cmd_trades(ctx):
    if not _open_trades:
        await ctx.send("Nu ai niciun trade deschis momentan.")
        return
    lines = ["**Trades deschise:**"]
    for tid, t in _open_trades.items():
        cur  = get_price(t["symbol"])
        pnl  = (cur - t["entry"]) * t["qty"] if t["side"] == "BUY" else (t["entry"] - cur) * t["qty"]
        ico  = "🟢" if pnl >= 0 else "🔴"
        lines.append(
            f"{ico} `#{tid}` **{t['side']} {t['symbol'].replace('USDT','')}** | "
            f"Entry `${t['entry']:,.4f}` | Now `${cur:,.4f}` | "
            f"TP `${t['tp1']:,.4f}` | SL `${t['stop_loss']:,.4f}` | "
            f"PnL `{pnl:+.2f}$`"
        )
    await ctx.send("\n".join(lines))

@bot.command(name="close")
@_only_trader()
async def cmd_close(ctx, trade_ref: str = ""):
    """!close #5 sau !close 5"""
    try:
        trade_id = int(trade_ref.lstrip("#"))
    except ValueError:
        await ctx.send("❌ Sintaxă: `!close #ID` (ex: `!close #5`)")
        return

    if trade_id not in _open_trades:
        await ctx.send(f"❌ Trade `#{trade_id}` nu există sau este deja închis.")
        return

    t   = _open_trades.pop(trade_id)
    cur = get_price(t["symbol"])
    if cur <= 0:
        cur = t["entry"]
    close_trade_db(trade_id, cur, "MANUAL")
    await ctx.send(
        _dm_trade_closed(trade_id, t["symbol"], t["side"], t["entry"], cur, t["qty"], "MANUAL")
    )

@bot.command(name="stop")
@_only_trader()
async def cmd_stop(ctx):
    set_setting("trading_active", "false")
    await ctx.send("🛑 **Trading OPRIT.** Niciun semnal nu va fi executat.\nFolosește `!start` pentru a relua.")

@bot.command(name="start")
@_only_trader()
async def cmd_start(ctx):
    set_setting("trading_active", "true")
    await ctx.send("✅ **Trading PORNIT.** Ascult semnale din nou.")

@bot.command(name="risk")
@_only_trader()
async def cmd_risk(ctx, value: str = ""):
    try:
        new_risk = float(value)
        if not 0.1 <= new_risk <= 20:
            raise ValueError()
    except ValueError:
        await ctx.send("❌ Risk trebuie să fie între 0.1 și 20 (ex: `!risk 2.5`)")
        return
    set_setting("risk_pct", str(new_risk))
    global _current_risk
    _current_risk = new_risk
    await ctx.send(f"⚙️ Risk global schimbat la **{new_risk}%** per trade.")

@bot.command(name="maxtr")
@_only_trader()
async def cmd_maxtr(ctx, value: str = ""):
    try:
        new_max = int(value)
        if not 1 <= new_max <= 20:
            raise ValueError()
    except ValueError:
        await ctx.send("❌ Valoare invalidă (ex: `!maxtr 5`)")
        return
    set_setting("max_trades", str(new_max))
    await ctx.send(f"⚙️ Max trades schimbat la **{new_max}**.")

@bot.command(name="autoconfirm")
@_only_trader()
async def cmd_autoconfirm(ctx):
    global AUTO_CONFIRM
    AUTO_CONFIRM = True
    await ctx.send(
        "⚡ **Auto-confirm ACTIVAT** — toate semnalele vor fi executate AUTOMAT!\n"
        "⚠️ Folosește `!manualconfirm` pentru a reveni la confirmare manuală."
    )

@bot.command(name="manualconfirm")
@_only_trader()
async def cmd_manualconfirm(ctx):
    global AUTO_CONFIRM
    AUTO_CONFIRM = False
    await ctx.send(f"✋ **Confirmare manuală ACTIVATĂ** — vei fi întrebat pentru fiecare semnal ({CONFIRM_TIMEOUT}s timeout).")

# ─── START ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN lipsește din ENV")
        exit(1)
    log.info("Pornire auto_trader.py...")
    bot.run(DISCORD_TOKEN)
