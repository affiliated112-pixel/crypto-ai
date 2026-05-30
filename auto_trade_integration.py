"""
auto_trade_integration.py — Auto-trader integrat in server-ul Discord

Cum functioneaza:
  1. Semnalul apare in canalul de semnale (FREE sau VIP)
  2. Botul posteaza automat in #auto-trader (canal privat, vizibil doar tu)
     un embed frumos cu butoane: [✅ Executa] [❌ Skip] [⚙️ Modifica]
  3. Dai click pe buton — botul executa trade-ul instant
  4. Update-urile (TP atins, SL atins, PnL live) apar in acelasi canal
  5. Comenzi: /trade_status  /trade_pnl  /trade_close  /trade_stop

ENV variables necesare:
  TRADER_USER_ID          — Discord User ID al tau (admin)
  AUTO_TRADER_CHANNEL_ID  — ID canal #auto-trader (privat) — optional, 
                             botul il creeaza automat daca nu exista
  AUTO_TRADE_TESTNET      — "true" (default) | "false" pentru live
  AUTO_TRADE_RISK         — % risk per trade (default: 2.0)
  AUTO_TRADE_MAX          — max trades simultane (default: 5)
  AUTO_TRADE_TIMEOUT      — secunde pentru confirmare (default: 120)
  AUTO_TRADE_AUTO         — "true" = fara confirmare (default: false)
  BINANCE_API_KEY         — Binance API key
  BINANCE_SECRET          — Binance API secret
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import market_data
import discord
from discord import app_commands
from discord.ext import tasks

log = logging.getLogger("auto_trade")

# ─── CONFIG ───────────────────────────────────────────────────────────────────
def _env(k: str, d: str = "") -> str:
    return os.environ.get(k, d).strip()
def _env_int(k: str, d: int) -> int:
    try: return int(os.environ.get(k, d))
    except: return d
def _env_float(k: str, d: float) -> float:
    try: return float(os.environ.get(k, d))
    except: return d

TRADER_USER_ID    = _env_int("TRADER_USER_ID", 0)
CHANNEL_ID        = _env_int("AUTO_TRADER_CHANNEL_ID", 0)
TESTNET           = _env("AUTO_TRADE_TESTNET", "true").lower() == "true"
RISK_PCT          = _env_float("AUTO_TRADE_RISK", 2.0)
MAX_TRADES        = _env_int("AUTO_TRADE_MAX", 5)
CONFIRM_TIMEOUT   = _env_int("AUTO_TRADE_TIMEOUT", 120)
AUTO_CONFIRM      = _env("AUTO_TRADE_AUTO", "false").lower() == "true"
ALLOW_LIVE_AUTO   = _env("AUTO_TRADE_ALLOW_LIVE_AUTO", "false").lower() == "true"
BIN_KEY           = _env("BINANCE_API_KEY")
BIN_SECRET        = _env("BINANCE_SECRET")

if AUTO_CONFIRM and not TESTNET and not ALLOW_LIVE_AUTO:
    # Safety guard: live trading still works, but manual confirmation is required
    # unless AUTO_TRADE_ALLOW_LIVE_AUTO=true is set explicitly.
    AUTO_CONFIRM = False
    log.warning("AUTO_TRADE_AUTO ignored on LIVE. Set AUTO_TRADE_ALLOW_LIVE_AUTO=true only if you really want live auto-confirm.")

# ─── BINANCE (optional) ───────────────────────────────────────────────────────
try:
    from binance.client import Client as _BClient
    from binance.exceptions import BinanceAPIException as _BErr
    _binance = _BClient(BIN_KEY, BIN_SECRET, testnet=TESTNET) if BIN_KEY else None
    PAPER_MODE = _binance is None
except ImportError:
    _binance  = None
    PAPER_MODE = True

if PAPER_MODE:
    log.warning("Auto-trader: rulează in PAPER MODE (Binance nu e disponibil)")
else:
    mode_str = "TESTNET" if TESTNET else "LIVE"
    log.info(f"Auto-trader: Binance {mode_str} conectat")

# ─── SIMULARE BALANTA PAPER ────────────────────────────────────────────────────
_PAPER_BALANCE = 1000.0   # USDT virtual pentru paper mode

def _get_usdt_balance() -> float:
    if PAPER_MODE or not _binance:
        return _PAPER_BALANCE
    try:
        acc = _binance.get_account()
        return float(next(
            (b["free"] for b in acc["balances"] if b["asset"] == "USDT"), "0"
        ))
    except Exception as e:
        log.error(f"[auto_trade] live balance unavailable: {e}")
        return 0.0

def _get_price(symbol: str) -> float:
    """Real public market price used for PAPER, TESTNET and LIVE monitoring."""
    try:
        px = market_data.get_current_price(symbol)
        return float(px or 0.0)
    except Exception:
        return 0.0

def _execute_binance(symbol: str, side: str, qty: float) -> tuple[bool, str, float]:
    """Returns (ok, message, actual_price)"""
    if PAPER_MODE or not _binance:
        px = _get_price(symbol)
        return True, "📝 PAPER TRADE (preț public live)", px
    try:
        if side == "BUY":
            order = _binance.order_market_buy(symbol=symbol, quantity=qty)
        else:
            order = _binance.order_market_sell(symbol=symbol, quantity=qty)
        fills = order.get("fills", [{}])
        price = float(fills[0].get("price", 0)) if fills else 0.0
        return True, "✅ Ordin executat pe Binance", price
    except Exception as e:
        return False, f"❌ Eroare: {e}", 0.0

# ─── DB ───────────────────────────────────────────────────────────────────────
DB = "auto_trades.db"

def _db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def _init_db():
    with _db() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS at_trades (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol      TEXT,
                side        TEXT,
                entry       REAL,
                qty         REAL,
                tp1         REAL,
                tp2         REAL,
                tp3         REAL,
                sl          REAL,
                risk_pct    REAL,
                exit_price  REAL,
                pnl_usdt    REAL,
                pnl_pct     REAL,
                status      TEXT DEFAULT 'OPEN',
                source      TEXT,
                confidence  TEXT,
                rr          REAL,
                opened_at   TEXT,
                closed_at   TEXT,
                close_reason TEXT,
                msg_id      INTEGER
            );
            CREATE TABLE IF NOT EXISTS at_settings (
                key TEXT PRIMARY KEY, value TEXT
            );
        """)
        c.execute("INSERT OR IGNORE INTO at_settings VALUES('risk_pct',?)", (str(RISK_PCT),))
        c.execute("INSERT OR IGNORE INTO at_settings VALUES('max_trades',?)", (str(MAX_TRADES),))
        c.execute("INSERT OR IGNORE INTO at_settings VALUES('active','true')")

def _get_setting(k: str, d: str = "") -> str:
    with _db() as c:
        r = c.execute("SELECT value FROM at_settings WHERE key=?", (k,)).fetchone()
        return r["value"] if r else d

def _set_setting(k: str, v: str):
    with _db() as c:
        c.execute("INSERT OR REPLACE INTO at_settings VALUES(?,?)", (k, v))

def _open_trade(symbol, side, entry, qty, tp1, tp2, tp3, sl, risk_pct, source, confidence, rr) -> int:
    with _db() as c:
        cur = c.execute("""
            INSERT INTO at_trades
              (symbol,side,entry,qty,tp1,tp2,tp3,sl,risk_pct,source,confidence,rr,status,opened_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'OPEN',?)
        """, (symbol, side, entry, qty, tp1, tp2, tp3, sl, risk_pct,
              source, confidence, rr, datetime.now(timezone.utc).isoformat()))
        return cur.lastrowid

def _close_trade(trade_id: int, exit_price: float, reason: str):
    with _db() as c:
        row = c.execute("SELECT entry,qty,side FROM at_trades WHERE id=?", (trade_id,)).fetchone()
        if not row:
            return
        e, q, s = row["entry"], row["qty"], row["side"]
        pnl = (exit_price - e) * q if s == "BUY" else (e - exit_price) * q
        pct = pnl / (e * q) * 100 if e * q > 0 else 0
        now = datetime.now(timezone.utc).isoformat()
        c.execute("""
            UPDATE at_trades
            SET exit_price=?,pnl_usdt=?,pnl_pct=?,status='CLOSED',closed_at=?,close_reason=?
            WHERE id=?
        """, (exit_price, round(pnl, 4), round(pct, 2), now, reason, trade_id))

def _total_stats() -> tuple[float, int, int]:
    with _db() as c:
        r = c.execute("""
            SELECT COALESCE(SUM(pnl_usdt),0) p,
                   SUM(CASE WHEN pnl_usdt>0 THEN 1 ELSE 0 END) w,
                   SUM(CASE WHEN pnl_usdt<=0 THEN 1 ELSE 0 END) l
            FROM at_trades WHERE status='CLOSED'
        """).fetchone()
        return float(r["p"]), int(r["w"]), int(r["l"])

# ─── STATE ────────────────────────────────────────────────────────────────────
_open:    dict[int, dict] = {}    # trade_id -> {symbol,side,entry,qty,tp1,tp2,tp3,sl}
_channel: Optional[discord.TextChannel] = None
_client:  Optional[discord.Client]      = None

# ─── DISCORD VIEWS (Butoane) ──────────────────────────────────────────────────

class ConfirmTradeView(discord.ui.View):
    """
    Embed cu 3 butoane: [✅ Executa] [❌ Skip] [⚙️ Modifica]
    Apare in canalul #auto-trader cand vine un semnal nou.
    """
    def __init__(self, signal: dict, qty: float):
        super().__init__(timeout=CONFIRM_TIMEOUT)
        self.signal  = signal
        self.qty     = qty
        self.result  = None    # "confirm" / "skip" / None (timeout)

    @discord.ui.button(label="✅  Executa", style=discord.ButtonStyle.success)
    async def do_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _is_trader(interaction.user):
            await interaction.response.send_message("❌ Nu ai permisiuni.", ephemeral=True)
            return
        self.result = "confirm"
        self.stop()
        await interaction.response.edit_message(
            content="⏳ **Execut trade-ul...** Te rog asteapta.",
            view=None
        )

    @discord.ui.button(label="❌  Skip", style=discord.ButtonStyle.danger)
    async def do_skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _is_trader(interaction.user):
            await interaction.response.send_message("❌ Nu ai permisiuni.", ephemeral=True)
            return
        self.result = "skip"
        self.stop()
        s = self.signal
        coin = s["symbol"].replace("USDT", "")
        await interaction.response.edit_message(
            content=f"❌ **{s['side']} {coin} sărit.** Aștept semnalul următor.",
            embed=None, view=None
        )

    @discord.ui.button(label="⚙️  Modifica", style=discord.ButtonStyle.secondary)
    async def do_modify(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _is_trader(interaction.user):
            await interaction.response.send_message("❌ Nu ai permisiuni.", ephemeral=True)
            return
        await interaction.response.send_modal(ModifyTradeModal(self))

    async def on_timeout(self):
        if _channel:
            s    = self.signal
            coin = s["symbol"].replace("USDT", "")
            try:
                await _channel.send(
                    f"⏰ **Timeout {CONFIRM_TIMEOUT}s** — {s['side']} `{coin}` sărit automat."
                )
            except Exception:
                pass

class ModifyTradeModal(discord.ui.Modal, title="Modifică parametrii"):
    """Modal (popup) pentru a schimba risk%, SL sau TP înainte de execuție."""
    risk = discord.ui.TextInput(
        label="Risk % (ex: 1.5)",
        placeholder="Lasă gol pentru a păstra valoarea curentă",
        required=False, max_length=6
    )
    new_sl = discord.ui.TextInput(
        label="Stop Loss (preț)",
        placeholder="Lasă gol pentru a păstra valoarea curentă",
        required=False, max_length=12
    )
    new_tp = discord.ui.TextInput(
        label="TP1 (preț)",
        placeholder="Lasă gol pentru a păstra valoarea curentă",
        required=False, max_length=12
    )

    def __init__(self, parent: ConfirmTradeView):
        super().__init__()
        self.parent = parent

    async def on_submit(self, interaction: discord.Interaction):
        p = self.parent
        try:
            risk_pct = float(p.signal.get("_risk_pct", _get_setting("risk_pct", str(RISK_PCT))))
            if self.risk.value:
                risk_pct = float(self.risk.value)
                p.signal["_risk_pct"] = risk_pct
            if self.new_sl.value:
                p.signal["sl"] = float(self.new_sl.value.replace(",", ""))
            if self.new_tp.value:
                p.signal["tp1"] = float(self.new_tp.value.replace(",", ""))
            if self.risk.value or self.new_sl.value:
                p.qty = _calc_qty(p.signal["symbol"], p.signal["entry"], risk_pct, p.signal.get("sl"))
        except ValueError:
            await interaction.response.send_message(
                "❌ Valori invalide — verifică formatul (ex: 1.5, 62000)", ephemeral=True
            )
            return

        updated_embed = _build_confirm_embed(p.signal, p.qty)
        await interaction.response.edit_message(
            content="✏️ **Parametrii actualizați.** Confirmă sau sari:",
            embed=updated_embed, view=p
        )

class TradeStatusView(discord.ui.View):
    """Butoane Quick Action pe mesajul de trade deschis."""
    def __init__(self, trade_id: int):
        super().__init__(timeout=None)
        self.trade_id = trade_id

    @discord.ui.button(label="❌  Inchide manual", style=discord.ButtonStyle.danger, custom_id="close_trade")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _is_trader(interaction.user):
            await interaction.response.send_message("❌ Nu ai permisiuni.", ephemeral=True)
            return
        tid = self.trade_id
        if tid not in _open:
            await interaction.response.edit_message(
                content="ℹ️ Trade-ul este deja închis.", embed=None, view=None
            )
            return
        t   = _open.pop(tid)
        cur = _get_price(t["symbol"]) or t["entry"]
        _close_trade(tid, cur, "MANUAL")
        await interaction.response.edit_message(
            content=_closed_msg(tid, t["symbol"], t["side"], t["entry"], cur, t["qty"], "MANUAL"),
            embed=None, view=None
        )

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _is_trader(user: discord.User | discord.Member) -> bool:
    return not TRADER_USER_ID or user.id == TRADER_USER_ID

def _calc_qty(symbol: str, entry: float, risk_pct: float, sl: float | None = None) -> float:
    """Position size based on real risk to SL, capped by available balance."""
    bal = _get_usdt_balance()
    if entry <= 0 or bal <= 0:
        return 0.0
    risk_usdt = bal * (risk_pct / 100)
    if sl and abs(entry - sl) > 0:
        qty = risk_usdt / abs(entry - sl)
    else:
        qty = risk_usdt / entry
    max_qty = bal / entry
    return round(max(0.0, min(qty, max_qty)), 6)

def _rr(entry: float, tp: float, sl: float) -> float:
    if abs(sl - entry) == 0:
        return 0.0
    return round(abs(tp - entry) / abs(sl - entry), 2)

def _build_confirm_embed(sig: dict, qty: float) -> discord.Embed:
    side    = sig["side"]
    symbol  = sig["symbol"]
    coin    = symbol.replace("USDT", "")
    entry   = sig["entry"]
    tp1     = sig.get("tp1", entry * 1.03)
    tp2     = sig.get("tp2", 0.0)
    tp3     = sig.get("tp3", 0.0)
    sl      = sig.get("sl", entry * 0.97)
    conf    = sig.get("confidence", "MEDIUM")
    source  = sig.get("source", "VIP")
    rr_val  = _rr(entry, tp1, sl)
    risk_pct = sig.get("_risk_pct", float(_get_setting("risk_pct", str(RISK_PCT))))
    usdt_risk = abs(entry - sl) * qty if sl and qty else qty * entry * (risk_pct / 100)

    conf_icons = {"VERY HIGH": "🌟", "HIGH": "🔥", "MEDIUM": "⚡", "LOW": "📊"}
    ci = conf_icons.get(conf, "⚡")
    color = 0x00FF88 if side == "BUY" else 0xFF4444
    mode_str = "📝 PAPER" if PAPER_MODE else ("🧪 TESTNET" if TESTNET else "🚀 LIVE")

    embed = discord.Embed(
        title=f"{'🟢' if side == 'BUY' else '🔴'} SEMNAL NOU — {source} | {mode_str}",
        description=(
            f"**{side}** `{coin}` — {ci} {conf}\n"
            f"R:R `{rr_val:.1f}:1`"
        ),
        color=color
    )
    embed.add_field(
        name="💰 Niveluri",
        value=(
            f"**Entry:**  `${entry:,.4f}`\n"
            f"**TP1:**    `${tp1:,.4f}` (+{abs(tp1-entry)/entry*100:.2f}%)\n"
            + (f"**TP2:**    `${tp2:,.4f}` (+{abs(tp2-entry)/entry*100:.2f}%)\n" if tp2 else "")
            + (f"**TP3:**    `${tp3:,.4f}` (+{abs(tp3-entry)/entry*100:.2f}%)\n" if tp3 else "")
            + f"**SL:**     `${sl:,.4f}` (-{abs(sl-entry)/entry*100:.2f}%)"
        ),
        inline=True
    )
    embed.add_field(
        name="📦 Ordin",
        value=(
            f"**Cantitate:**  `{qty} {coin}`\n"
            f"**Risc:**       `~${usdt_risk:.2f}` ({risk_pct}%)\n"
            f"**Balanta:**    `${_get_usdt_balance():,.2f} USDT`"
        ),
        inline=True
    )
    embed.set_footer(text=f"Timeout: {CONFIRM_TIMEOUT}s — apasă un buton de mai jos")
    return embed

def _build_open_embed(trade_id: int, sig: dict, qty: float) -> discord.Embed:
    side  = sig["side"]
    coin  = sig["symbol"].replace("USDT", "")
    entry = sig["entry"]
    mode  = "📝 PAPER" if PAPER_MODE else ("🧪 TESTNET" if TESTNET else "🚀 LIVE")
    embed = discord.Embed(
        title=f"{'🟢' if side == 'BUY' else '🔴'} TRADE #{trade_id} DESCHIS | {mode}",
        description=(
            f"**{side}** `{qty} {coin}` @ `${entry:,.4f}`\n"
            f"🎯 TP1: `${sig.get('tp1',0):,.4f}` | 🛑 SL: `${sig.get('sl',0):,.4f}`\n"
            f"Monitorizez la fiecare 30s."
        ),
        color=0x00FF88 if side == "BUY" else 0xFF4444
    )
    embed.set_footer(text=f"Trade ID: #{trade_id} | Apasă butonul de mai jos pentru a închide manual")
    return embed

def _closed_msg(trade_id: int, symbol: str, side: str,
                entry: float, exit_p: float, qty: float, reason: str) -> str:
    pnl     = (exit_p - entry) * qty if side == "BUY" else (entry - exit_p) * qty
    pnl_pct = pnl / (entry * qty) * 100 if entry * qty > 0 else 0
    coin    = symbol.replace("USDT", "")
    labels  = {
        "TARGET": "✅ TP1 atins",
        "TARGET2": "✅ TP2 atins",
        "TARGET3": "✅ TP3 atins",
        "STOP": "🛑 Stop-Loss atins",
        "MANUAL": "👋 Închis manual",
    }
    label = labels.get(reason, reason)
    emoji = "💰" if pnl >= 0 else "💸"
    return (
        f"{emoji} **TRADE #{trade_id} ÎNCHIS — {label}**\n"
        f"`{coin}` | Entry `${entry:,.4f}` → Exit `${exit_p:,.4f}`\n"
        f"**PnL: `{pnl:+.2f} USDT` ({pnl_pct:+.1f}%)**"
    )

# ─── CANAL AUTO-TRADER ────────────────────────────────────────────────────────

async def _get_or_create_channel(client: discord.Client) -> Optional[discord.TextChannel]:
    """
    Găsește sau creează canalul #auto-trader vizibil doar pentru TRADER_USER_ID.
    """
    global _channel

    if _channel:
        return _channel

    # Caută mai întâi după ID din ENV
    if CHANNEL_ID:
        ch = client.get_channel(CHANNEL_ID)
        if ch:
            _channel = ch
            return _channel

    # Caută după nume
    for guild in client.guilds:
        for ch in guild.text_channels:
            if ch.name in ("auto-trader", "auto-trade", "trading-desk", "auto_trader"):
                _channel = ch
                log.info(f"[auto_trade] canal găsit: #{ch.name} ({ch.id})")
                return _channel

    # Creează canal nou dacă nu există
    for guild in client.guilds:
        trader_member = guild.get_member(TRADER_USER_ID) if TRADER_USER_ID else None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
        }
        if trader_member:
            overwrites[trader_member] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            )
        # Adaugă și botul
        bot_member = guild.get_member(client.user.id)
        if bot_member:
            overwrites[bot_member] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_messages=True,
                embed_links=True,
                attach_files=True,
            )
        try:
            ch = await guild.create_text_channel(
                "auto-trader",
                topic="🤖 Canal privat auto-trading | Comenzi: /trade_status /trade_pnl /trade_stop",
                overwrites=overwrites,
            )
            _channel = ch
            log.info(f"[auto_trade] canal creat: #{ch.name} ({ch.id})")
            await ch.send(
                "🤖 **Auto-Trader activat!**\n\n"
                f"Mod: **{'📝 PAPER' if PAPER_MODE else ('🧪 TESTNET' if TESTNET else '🚀 LIVE')}**\n"
                f"Risk per trade: **{_get_setting('risk_pct', str(RISK_PCT))}%**\n"
                f"Max trades simultane: **{_get_setting('max_trades', str(MAX_TRADES))}**\n"
                f"Confirmare: **{'AUTO ⚡' if AUTO_CONFIRM else f'Manual ({CONFIRM_TIMEOUT}s)'}**\n\n"
                "Când vine un semnal, apare aici cu butoane de confirmare.\n"
                "Folosește `/trade_status` `/trade_pnl` `/trade_stop` pentru control."
            )
            return _channel
        except discord.Forbidden:
            log.error("[auto_trade] Nu am permisiunea să creez canal — adaugă-mă ca admin sau setează AUTO_TRADER_CHANNEL_ID")
        except Exception as e:
            log.error(f"[auto_trade] Eroare creare canal: {e}")

    return None

# ─── PROCESARE SEMNAL ─────────────────────────────────────────────────────────

async def handle_signal(signal: dict, client: discord.Client):
    """
    Apelat din smart_loop sau signal_loop când apare un semnal nou.
    Postează în #auto-trader cu butoane de confirmare.
    """
    global _client
    _client = client
    try:
        _init_db()
        if not position_monitor.is_running():
            position_monitor.start()
    except Exception as e:
        log.warning(f"[auto_trade] monitor/db init skipped: {e}")

    if _get_setting("active", "true") != "true":
        return
    if len(_open) >= int(_get_setting("max_trades", str(MAX_TRADES))):
        log.info(f"[auto_trade] MAX_TRADES atins — {signal['symbol']} ignorat")
        return

    ch = await _get_or_create_channel(client)
    if not ch:
        log.error("[auto_trade] Nu am canal disponibil")
        return

    risk_pct = float(_get_setting("risk_pct", str(RISK_PCT)))
    qty      = _calc_qty(signal["symbol"], signal["entry"], risk_pct, signal.get("sl"))
    signal["_risk_pct"] = risk_pct

    if AUTO_CONFIRM:
        # Executa direct fara confirmare
        await _execute_signal(signal, qty, ch)
        return

    # Postează embed cu butoane
    embed = _build_confirm_embed(signal, qty)
    view  = ConfirmTradeView(signal, qty)
    msg   = await ch.send(
        content=f"📨 **Semnal nou detectat!** {'<@' + str(TRADER_USER_ID) + '>' if TRADER_USER_ID else ''}",
        embed=embed,
        view=view
    )

    # Asteapta raspunsul
    await view.wait()

    if view.result == "confirm":
        await _execute_signal(view.signal, view.qty, ch)
    elif view.result == "skip":
        pass   # Mesajul e deja actualizat de buton
    else:
        # Timeout — deja tratat in on_timeout
        pass

async def _execute_signal(signal: dict, qty: float, ch: discord.TextChannel):
    """Executa ordinul si posteaza confirmarea in canal."""
    symbol = signal["symbol"]
    side   = signal["side"]
    entry  = signal["entry"]
    tp1    = signal.get("tp1", entry * 1.03)
    tp2    = signal.get("tp2", 0.0)
    tp3    = signal.get("tp3", 0.0)
    sl     = signal.get("sl", entry * 0.97)
    risk_pct = signal.get("_risk_pct", float(_get_setting("risk_pct", str(RISK_PCT))))

    # Executa pe Binance / paper
    ok, exec_msg, actual_price = _execute_binance(symbol, side, qty)
    if not ok:
        await ch.send(f"⚠️ **Execuție eșuată:** {exec_msg}")
        return
    if actual_price > 0:
        entry = actual_price   # prețul real de fill / preț public live în PAPER
        signal["entry"] = entry

    # Salvează în DB
    trade_id = _open_trade(
        symbol, side, entry, qty, tp1, tp2, tp3, sl, risk_pct,
        signal.get("source", "VIP"), signal.get("confidence", ""), signal.get("rr", 0.0)
    )
    _open[trade_id] = {
        "symbol": symbol, "side": side, "entry": entry, "qty": qty,
        "tp1": tp1, "tp2": tp2, "tp3": tp3, "sl": sl,
    }

    # Postează confirmarea cu butonul de close
    embed = _build_open_embed(trade_id, signal, qty)
    view  = TradeStatusView(trade_id)
    await ch.send(embed=embed, view=view)
    log.info(f"[auto_trade] Trade #{trade_id} deschis: {side} {qty} {symbol} @ {entry}")

# ─── MONITOR POZITII ──────────────────────────────────────────────────────────

@tasks.loop(seconds=30)
async def position_monitor():
    if not _open or not _channel or not _client:
        return

    to_close: list[int] = []
    for tid, t in list(_open.items()):
        cur = _get_price(t["symbol"])
        if cur <= 0:
            continue

        side = t["side"]
        hit_tp3 = t.get("tp3") and (
            (side == "BUY" and cur >= t["tp3"]) or (side == "SELL" and cur <= t["tp3"]))
        hit_tp2 = t.get("tp2") and (
            (side == "BUY" and cur >= t["tp2"]) or (side == "SELL" and cur <= t["tp2"]))
        hit_tp1 = (side == "BUY" and cur >= t["tp1"]) or (side == "SELL" and cur <= t["tp1"])
        hit_sl  = (side == "BUY" and cur <= t["sl"])  or (side == "SELL" and cur >= t["sl"])

        reason = None
        if hit_tp3:  reason = "TARGET3"
        elif hit_tp2: reason = "TARGET2"
        elif hit_tp1: reason = "TARGET"
        elif hit_sl:  reason = "STOP"

        if reason:
            _close_trade(tid, cur, reason)
            to_close.append(tid)
            try:
                await _channel.send(
                    _closed_msg(tid, t["symbol"], t["side"], t["entry"], cur, t["qty"], reason)
                )
            except Exception as e:
                log.error(f"[auto_trade] send close error: {e}")

    for tid in to_close:
        _open.pop(tid, None)

@position_monitor.before_loop
async def _before_monitor():
    if _client:
        await _client.wait_until_ready()

# ─── SLASH COMMANDS ───────────────────────────────────────────────────────────

def register_commands(tree: app_commands.CommandTree):
    """Apelat din bot_extended.py pentru a inregistra comenzile slash."""

    @tree.command(name="trade_status", description="Status auto-trader + trades deschise")
    async def trade_status(interaction: discord.Interaction):
        if not _is_trader(interaction.user):
            await interaction.response.send_message("❌ Fără permisiuni.", ephemeral=True)
            return
        active  = _get_setting("active", "true") == "true"
        risk    = _get_setting("risk_pct", str(RISK_PCT))
        max_t   = _get_setting("max_trades", str(MAX_TRADES))
        mode    = "📝 PAPER" if PAPER_MODE else ("🧪 TESTNET" if TESTNET else "🚀 LIVE")
        state   = "✅ ACTIV" if active else "🛑 OPRIT"

        embed = discord.Embed(
            title="📊 Auto-Trader Status",
            color=0x00FF88 if active else 0xFF4444
        )
        embed.add_field(name="Stare", value=f"{state} | {mode}", inline=False)
        embed.add_field(name="Risk", value=f"{risk}% per trade", inline=True)
        embed.add_field(name="Max trades", value=max_t, inline=True)
        embed.add_field(name="Deschise", value=f"{len(_open)}/{max_t}", inline=True)
        embed.add_field(name="Balanță USDT", value=f"${_get_usdt_balance():,.2f}", inline=True)

        if _open:
            lines = []
            for tid, t in _open.items():
                cur  = _get_price(t["symbol"]) or t["entry"]
                pnl  = (cur - t["entry"]) * t["qty"] if t["side"] == "BUY" \
                       else (t["entry"] - cur) * t["qty"]
                ico  = "🟢" if pnl >= 0 else "🔴"
                coin = t["symbol"].replace("USDT", "")
                lines.append(
                    f"{ico} `#{tid}` **{t['side']} {coin}** | "
                    f"Entry `${t['entry']:,.4f}` | Now `${cur:,.4f}` | "
                    f"PnL `{pnl:+.2f}$`"
                )
            embed.add_field(name="Trades deschise", value="\n".join(lines), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tree.command(name="trade_pnl", description="Profit/pierdere total closed trades")
    async def trade_pnl(interaction: discord.Interaction):
        if not _is_trader(interaction.user):
            await interaction.response.send_message("❌ Fără permisiuni.", ephemeral=True)
            return
        pnl, wins, losses = _total_stats()
        total  = wins + losses
        wr     = wins / total * 100 if total > 0 else 0
        emoji  = "💰" if pnl >= 0 else "💸"
        embed  = discord.Embed(
            title=f"{emoji} PnL Total (Closed Trades)",
            description=(
                f"**PnL: `{pnl:+.2f} USDT`**\n"
                f"Win/Loss: `{wins}W / {losses}L` — Win Rate: `{wr:.1f}%`\n"
                f"Trades totale: `{total}`"
            ),
            color=0x00FF88 if pnl >= 0 else 0xFF4444
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tree.command(name="trade_close", description="Inchide manual un trade (ex: /trade_close 5)")
    @app_commands.describe(trade_id="ID-ul trade-ului de inchis")
    async def trade_close(interaction: discord.Interaction, trade_id: int):
        if not _is_trader(interaction.user):
            await interaction.response.send_message("❌ Fără permisiuni.", ephemeral=True)
            return
        if trade_id not in _open:
            await interaction.response.send_message(
                f"❌ Trade `#{trade_id}` nu există sau e deja închis.", ephemeral=True
            )
            return
        t   = _open.pop(trade_id)
        cur = _get_price(t["symbol"]) or t["entry"]
        _close_trade(trade_id, cur, "MANUAL")
        msg = _closed_msg(trade_id, t["symbol"], t["side"], t["entry"], cur, t["qty"], "MANUAL")
        await interaction.response.send_message(msg)
        if _channel:
            await _channel.send(msg)

    @tree.command(name="trade_stop", description="Opreste auto-traderul (kill switch)")
    async def trade_stop(interaction: discord.Interaction):
        if not _is_trader(interaction.user):
            await interaction.response.send_message("❌ Fără permisiuni.", ephemeral=True)
            return
        _set_setting("active", "false")
        await interaction.response.send_message(
            "🛑 **Auto-trader OPRIT.** Folosește `/trade_start` pentru a relua."
        )

    @tree.command(name="trade_start", description="Reporneste auto-traderul")
    async def trade_start(interaction: discord.Interaction):
        if not _is_trader(interaction.user):
            await interaction.response.send_message("❌ Fără permisiuni.", ephemeral=True)
            return
        _set_setting("active", "true")
        await interaction.response.send_message("✅ **Auto-trader PORNIT.** Aștept semnale.")

    @tree.command(name="trade_risk", description="Schimba risk% per trade (ex: /trade_risk 2.5)")
    @app_commands.describe(procent="Procentul de risc per trade (0.1 - 20)")
    async def trade_risk(interaction: discord.Interaction, procent: float):
        if not _is_trader(interaction.user):
            await interaction.response.send_message("❌ Fără permisiuni.", ephemeral=True)
            return
        if not 0.1 <= procent <= 20:
            await interaction.response.send_message(
                "❌ Risk trebuie între 0.1 și 20.", ephemeral=True
            )
            return
        _set_setting("risk_pct", str(procent))
        await interaction.response.send_message(
            f"⚙️ Risk global schimbat la **{procent}%** per trade."
        )

    log.info("[auto_trade] Slash commands înregistrate: /trade_status /trade_pnl /trade_close /trade_stop /trade_start /trade_risk")

# ─── SETUP — apelat din bot_extended.py ──────────────────────────────────────

async def setup(client: discord.Client):
    """
    Initializeaza auto-traderul.
    Apelat din _startup_extras() in bot_extended.py.
    """
    global _client
    _client = client
    _init_db()
    await _get_or_create_channel(client)
    position_monitor.start()
    log.info(f"[auto_trade] pornit | PAPER={PAPER_MODE} | TESTNET={TESTNET} | risk={RISK_PCT}%")
