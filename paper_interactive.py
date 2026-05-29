"""paper_interactive.py — Interactive Demo Trading System.

When the bot posts a signal, it includes a button:
  [💰 Try with Demo Money]

Clicking it opens a modal:
  "How much demo money do you want to invest? (e.g. 5, 10, 50)"

The bot then opens a PERSONAL virtual trade for that user and posts
a live embed (updated every 30s) showing exactly what their money is doing.

ALL virtual. Zero real money. Each user has their own portfolio.
"""
import asyncio
import json
import os
import time
import requests
import discord
from discord import ui
from datetime import datetime, timezone

DEMO_FILE = os.environ.get("DEMO_TRADING_FILE", "demo_portfolios.json")
UA = {"User-Agent": "crypto-ai-bot/2026"}

# ─── Storage ──────────────────────────────────────────────────────────────────

def _load_all() -> dict:
    if not os.path.isfile(DEMO_FILE):
        return {}
    try:
        with open(DEMO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_all(data: dict):
    try:
        with open(DEMO_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[demo] save error: {e}", flush=True)

def get_user_portfolio(user_id: int) -> dict:
    all_data = _load_all()
    uid = str(user_id)
    if uid not in all_data:
        all_data[uid] = {
            "balance": 0.0,
            "total_invested": 0.0,
            "total_pnl": 0.0,
            "wins": 0,
            "losses": 0,
            "open_trades": [],
            "closed_trades": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_all(all_data)
    return all_data[uid]

def save_user_portfolio(user_id: int, portfolio: dict):
    all_data = _load_all()
    all_data[str(user_id)] = portfolio
    _save_all(all_data)

def _get_price(symbol: str) -> float | None:
    try:
        r = requests.get(
            f"https://api.binance.us/api/v3/ticker/price?symbol={symbol}",
            headers=UA, timeout=6,
        )
        return float(r.json()["price"])
    except Exception:
        return None

# ─── Trade Logic ──────────────────────────────────────────────────────────────

def open_user_trade(user_id: int, symbol: str, direction: str,
                    entry_price: float, invest_usd: float) -> dict | None:
    portfolio = get_user_portfolio(user_id)

    # Max 3 open trades per user
    if len(portfolio["open_trades"]) >= 3:
        return None

    qty = invest_usd / entry_price
    if direction == "BUY":
        sl  = entry_price * 0.98
        tp1 = entry_price * 1.02
        tp2 = entry_price * 1.04
        tp3 = entry_price * 1.07
    else:
        sl  = entry_price * 1.02
        tp1 = entry_price * 0.98
        tp2 = entry_price * 0.96
        tp3 = entry_price * 0.93

    trade = {
        "id":        int(time.time() * 1000),
        "symbol":    symbol,
        "direction": direction,
        "entry":     entry_price,
        "qty":       qty,
        "invest":    invest_usd,
        "sl":        sl,
        "tp1":       tp1, "tp2": tp2, "tp3": tp3,
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "status":    "OPEN",
        "hit_tp1":   False,
        "hit_tp2":   False,
    }

    portfolio["total_invested"] += invest_usd
    portfolio["open_trades"].append(trade)
    save_user_portfolio(user_id, portfolio)
    print(f"[demo] user {user_id} opened {direction} {symbol} @ ${entry_price:.2f} invest=${invest_usd:.2f}", flush=True)
    return trade

def close_user_trade(user_id: int, trade_id: int, reason: str, close_price: float) -> dict | None:
    portfolio = get_user_portfolio(user_id)
    trade = next((t for t in portfolio["open_trades"] if t["id"] == trade_id), None)
    if not trade:
        return None

    entry = trade["entry"]
    qty   = trade["qty"]
    invest = trade["invest"]

    if trade["direction"] == "BUY":
        pnl = (close_price - entry) * qty
    else:
        pnl = (entry - close_price) * qty

    pnl_pct = (pnl / invest) * 100
    portfolio["total_pnl"] += pnl
    portfolio["balance"]   += invest + pnl

    if pnl >= 0:
        portfolio["wins"] += 1
    else:
        portfolio["losses"] += 1

    closed = {**trade,
        "close_price":  close_price,
        "pnl":          round(pnl, 4),
        "pnl_pct":      round(pnl_pct, 2),
        "close_reason": reason,
        "closed_at":    datetime.now(timezone.utc).isoformat(),
    }
    portfolio["open_trades"]   = [t for t in portfolio["open_trades"] if t["id"] != trade_id]
    portfolio["closed_trades"].append(closed)
    if len(portfolio["closed_trades"]) > 100:
        portfolio["closed_trades"] = portfolio["closed_trades"][-100:]
    save_user_portfolio(user_id, portfolio)
    return closed

# ─── Embed Builder ────────────────────────────────────────────────────────────

def build_user_embed(user_id: int, username: str) -> discord.Embed:
    portfolio = get_user_portfolio(user_id)
    open_trades = portfolio["open_trades"]

    # Update live prices
    total_unrealized = 0.0
    live_trades = []
    for t in open_trades:
        price = _get_price(t["symbol"]) or t["entry"]
        if t["direction"] == "BUY":
            unreal = (price - t["entry"]) * t["qty"]
        else:
            unreal = (t["entry"] - price) * t["qty"]
        unreal_pct = (unreal / t["invest"]) * 100
        total_unrealized += unreal
        live_trades.append({**t, "live_price": price, "unrealized": unreal, "unrealized_pct": unreal_pct})

    total_pnl = portfolio["total_pnl"] + total_unrealized
    total_invested = portfolio["total_invested"]
    total_return_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0

    color = 0x00C896 if total_return_pct >= 0 else 0xE74C3C
    arrow = "📈" if total_return_pct >= 0 else "📉"
    sign  = "+" if total_return_pct >= 0 else ""

    total_trades = portfolio["wins"] + portfolio["losses"]
    win_rate = (portfolio["wins"] / total_trades * 100) if total_trades > 0 else 0.0

    embed = discord.Embed(
        title=f"💼 DEMO PORTFOLIO — {username}",
        description=(
            f"**Bani virtuali • Zero risc real • 100% prețuri Binance live**\n"
            f"{'━' * 35}"
        ),
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name=f"{arrow} Rezultat Total",
        value=(
            f"```\n"
            f"Investit total:  ${total_invested:.2f}\n"
            f"P&L realizat:    {'+' if portfolio['total_pnl']>=0 else ''}${portfolio['total_pnl']:.4f}\n"
            f"P&L nerealizat:  {'+' if total_unrealized>=0 else ''}${total_unrealized:.4f}\n"
            f"P&L TOTAL:       {sign}${total_pnl:.4f} ({sign}{total_return_pct:.2f}%)\n"
            f"```"
        ),
        inline=False,
    )

    if total_trades > 0:
        embed.add_field(
            name="📊 Statistici",
            value=(
                f"✅ Câștigate: `{portfolio['wins']}`  "
                f"❌ Pierdute: `{portfolio['losses']}`  "
                f"🎯 Win Rate: `{win_rate:.1f}%`"
            ),
            inline=False,
        )

    if live_trades:
        lines = []
        for t in live_trades:
            emoji = "🟢" if t["direction"] == "BUY" else "🔴"
            s = "+" if t["unrealized_pct"] >= 0 else ""
            lines.append(
                f"{emoji} **{t['symbol']}** {t['direction']}\n"
                f"　Entry: `${t['entry']:.2f}` → Live: `${t['live_price']:.2f}`\n"
                f"　Investit: `${t['invest']:.2f}` | P&L: `{s}${t['unrealized']:.4f}` (`{s}{t['unrealized_pct']:.2f}%`)\n"
                f"　SL: `${t['sl']:.2f}` | TP1: `${t['tp1']:.2f}` | TP3: `${t['tp3']:.2f}`"
            )
        embed.add_field(
            name=f"🔄 Poziții deschise ({len(live_trades)}/3)",
            value="\n".join(lines),
            inline=False,
        )
    else:
        embed.add_field(
            name="🔄 Poziții deschise",
            value="Nicio poziție deschisă. Apasă **💰 Try with Demo Money** pe un semnal!",
            inline=False,
        )

    closed = list(reversed(portfolio["closed_trades"]))[:3]
    if closed:
        lines = []
        for t in closed:
            s = "+" if t["pnl_pct"] >= 0 else ""
            e = "✅" if t["pnl_pct"] >= 0 else "❌"
            lines.append(f"{e} {t['symbol']} {t['direction']} | `{s}{t['pnl_pct']:.2f}%` | {t['close_reason']}")
        embed.add_field(name="🕒 Ultimele trades", value="\n".join(lines), inline=False)

    embed.set_footer(text="🎮 Demo Trading • Bani virtuali • Prețuri reale Binance • Nu e sfat financiar")
    return embed

# ─── Discord UI ───────────────────────────────────────────────────────────────

class InvestModal(ui.Modal, title="💰 Demo Trading — Cât vrei să investești?"):
    amount = ui.TextInput(
        label="Sumă demo (USD virtual)",
        placeholder="Ex: 5  sau  10  sau  50",
        min_length=1,
        max_length=10,
        required=True,
    )

    def __init__(self, symbol: str, direction: str, entry_price: float):
        super().__init__()
        self.symbol      = symbol
        self.direction   = direction
        self.entry_price = entry_price

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.amount.value.strip().replace("$", "").replace(",", ".")
        try:
            invest_usd = float(raw)
        except ValueError:
            await interaction.response.send_message(
                "❌ Sumă invalidă. Introdu un număr, ex: `5` sau `10`.", ephemeral=True
            )
            return

        if invest_usd < 1:
            await interaction.response.send_message("❌ Suma minimă este $1 demo.", ephemeral=True)
            return
        if invest_usd > 10000:
            await interaction.response.send_message("❌ Suma maximă demo este $10,000.", ephemeral=True)
            return

        trade = open_user_trade(
            interaction.user.id, self.symbol, self.direction,
            self.entry_price, invest_usd,
        )

        if trade is None:
            await interaction.response.send_message(
                "⚠️ Ai deja 3 poziții deschise. Închide una înainte să deschizi alta.",
                ephemeral=True,
            )
            return

        embed = build_user_embed(interaction.user.id, interaction.user.display_name)
        view  = PortfolioView(interaction.user.id)

        await interaction.response.send_message(
            f"✅ **Trade demo deschis!**\n"
            f"{'🟢' if self.direction=='BUY' else '🔴'} {self.direction} **{self.symbol}** "
            f"— `${invest_usd:.2f}` virtuali la `${self.entry_price:.2f}`\n\n"
            f"Urmărește mai jos ce fac banii tăi în timp real 👇",
            embed=embed,
            view=view,
            ephemeral=True,
        )

class TryDemoButton(ui.View):
    """Button attached to every signal embed."""
    def __init__(self, symbol: str, direction: str, entry_price: float):
        super().__init__(timeout=3600)
        self.symbol      = symbol
        self.direction   = direction
        self.entry_price = entry_price

    @ui.button(label="💰 Try with Demo Money", style=discord.ButtonStyle.success, emoji="🎮")
    async def try_demo(self, interaction: discord.Interaction, button: ui.Button):
        modal = InvestModal(self.symbol, self.direction, self.entry_price)
        await interaction.response.send_modal(modal)

    @ui.button(label="📊 My Portfolio", style=discord.ButtonStyle.secondary, emoji="💼")
    async def my_portfolio(self, interaction: discord.Interaction, button: ui.Button):
        embed = build_user_embed(interaction.user.id, interaction.user.display_name)
        view  = PortfolioView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class PortfolioView(ui.View):
    """Buttons on the personal portfolio embed."""
    def __init__(self, user_id: int):
        super().__init__(timeout=600)
        self.user_id = user_id

    @ui.button(label="🔄 Refresh", style=discord.ButtonStyle.primary)
    async def refresh(self, interaction: discord.Interaction, button: ui.Button):
        embed = build_user_embed(self.user_id, interaction.user.display_name)
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="📋 Close All Trades", style=discord.ButtonStyle.danger)
    async def close_all(self, interaction: discord.Interaction, button: ui.Button):
        portfolio = get_user_portfolio(self.user_id)
        if not portfolio["open_trades"]:
            await interaction.response.send_message("📭 Nu ai poziții deschise.", ephemeral=True)
            return
        closed_count = 0
        for t in list(portfolio["open_trades"]):
            price = _get_price(t["symbol"]) or t["entry"]
            close_user_trade(self.user_id, t["id"], "MANUAL", price)
            closed_count += 1
        embed = build_user_embed(self.user_id, interaction.user.display_name)
        await interaction.response.edit_message(
            content=f"✅ {closed_count} poziție(i) închisă(e) manual.",
            embed=embed, view=self,
        )

# ─── Background SL/TP Poller ─────────────────────────────────────────────────

async def demo_poll_loop():
    """Poll all open user trades every 30s, auto-close at SL/TP."""
    await asyncio.sleep(45)
    print("[demo] SL/TP poll loop started", flush=True)
    while True:
        try:
            all_data = _load_all()
            for uid_str, portfolio in all_data.items():
                uid = int(uid_str)
                for trade in list(portfolio["open_trades"]):
                    price = _get_price(trade["symbol"])
                    if not price:
                        continue
                    tid = trade["id"]
                    direction = trade["direction"]
                    reason = None

                    if direction == "BUY":
                        if price <= trade["sl"]:
                            close_user_trade(uid, tid, "SL 🛑", price); reason = "SL"
                        elif price >= trade["tp3"]:
                            close_user_trade(uid, tid, "TP3 🎯", price); reason = "TP3"
                        elif price >= trade["tp2"] and not trade.get("hit_tp2"):
                            # Mark TP2 hit
                            p2 = get_user_portfolio(uid)
                            for t in p2["open_trades"]:
                                if t["id"] == tid: t["hit_tp2"] = True
                            save_user_portfolio(uid, p2)
                            reason = "TP2"
                        elif price >= trade["tp1"] and not trade.get("hit_tp1"):
                            p2 = get_user_portfolio(uid)
                            for t in p2["open_trades"]:
                                if t["id"] == tid: t["hit_tp1"] = True
                            save_user_portfolio(uid, p2)
                            reason = "TP1"
                    else:
                        if price >= trade["sl"]:
                            close_user_trade(uid, tid, "SL 🛑", price); reason = "SL"
                        elif price <= trade["tp3"]:
                            close_user_trade(uid, tid, "TP3 🎯", price); reason = "TP3"
                        elif price <= trade["tp2"] and not trade.get("hit_tp2"):
                            p2 = get_user_portfolio(uid)
                            for t in p2["open_trades"]:
                                if t["id"] == tid: t["hit_tp2"] = True
                            save_user_portfolio(uid, p2)
                            reason = "TP2"
                        elif price <= trade["tp1"] and not trade.get("hit_tp1"):
                            p2 = get_user_portfolio(uid)
                            for t in p2["open_trades"]:
                                if t["id"] == tid: t["hit_tp1"] = True
                            save_user_portfolio(uid, p2)
                            reason = "TP1"

                    if reason:
                        print(f"[demo] user {uid} trade {trade['symbol']} hit {reason} @ ${price:.2f}", flush=True)
        except Exception as e:
            print(f"[demo] poll error: {e}", flush=True)
        await asyncio.sleep(30)
