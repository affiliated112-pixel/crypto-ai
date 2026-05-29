"""demo_app.py — Auto-creates a LIVE DEMO TRADING APP inside Discord category.

On startup:
  1. Finds or creates a channel named "🎮・demo-trading" in category 1509818706509955172
  2. Clears old messages and posts the LIVE APP embed (pinned)
  3. Updates the embed every 30 seconds with real Binance prices
  4. Users click "🚀 Start Demo cu $5" → bot auto-trades for them
  5. Bot opens/closes trades automatically based on real signals
  6. Each user sees their own live P&L in real-time

ZERO real money. 100% Binance live prices.
"""
import asyncio
import json
import os
import time
import requests
import discord
from discord import ui
from datetime import datetime, timezone

CATEGORY_ID   = 1509818706509955172
CHANNEL_NAME  = "🎮・demo-trading"
DEMO_FILE     = os.environ.get("DEMO_FILE", "demo_app_portfolios.json")
STARTING_USD  = 5.0
TRADE_PCT     = 0.40        # 40% of balance per trade (max 2 open at once)
MAX_OPEN      = 2
POLL_SECONDS  = 30
UA            = {"User-Agent": "crypto-ai-bot/2026"}
SYMBOLS       = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

# ─── Storage ──────────────────────────────────────────────────────────────────

def _load() -> dict:
    if not os.path.isfile(DEMO_FILE):
        return {"users": {}, "app_message_id": None, "leaderboard_message_id": None}
    try:
        with open(DEMO_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"users": {}, "app_message_id": None, "leaderboard_message_id": None}

def _save(data: dict):
    try:
        with open(DEMO_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[demo_app] save error: {e}", flush=True)

def _get_user(data: dict, user_id: int) -> dict:
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {
            "name":          "Unknown",
            "balance":       STARTING_USD,
            "starting":      STARTING_USD,
            "open_trades":   [],
            "closed_trades": [],
            "wins":          0,
            "losses":        0,
            "total_pnl":     0.0,
            "started_at":    datetime.now(timezone.utc).isoformat(),
            "active":        True,
        }
    return data["users"][uid]

# ─── Price Feed ───────────────────────────────────────────────────────────────

_price_cache: dict[str, float] = {}
_price_ts: dict[str, float]    = {}

def get_price(symbol: str) -> float | None:
    now = time.time()
    if symbol in _price_cache and now - _price_ts.get(symbol, 0) < 15:
        return _price_cache[symbol]
    try:
        r = requests.get(
            f"https://api.binance.us/api/v3/ticker/price?symbol={symbol}",
            headers=UA, timeout=5,
        )
        price = float(r.json()["price"])
        _price_cache[symbol] = price
        _price_ts[symbol]    = now
        return price
    except Exception:
        return _price_cache.get(symbol)

def get_24h_change(symbol: str) -> float:
    try:
        r = requests.get(
            f"https://api.binance.us/api/v3/ticker/24hr?symbol={symbol}",
            headers=UA, timeout=5,
        )
        return float(r.json()["priceChangePercent"])
    except Exception:
        return 0.0

# ─── Trade Logic ──────────────────────────────────────────────────────────────

def auto_open_trade(user: dict, symbol: str, direction: str, price: float) -> dict | None:
    """Bot automatically opens a trade for user when a signal fires."""
    open_t = user["open_trades"]
    # Already have trade on this symbol?
    if any(t["symbol"] == symbol for t in open_t):
        return None
    # Max open trades reached?
    if len(open_t) >= MAX_OPEN:
        return None
    # Need enough balance
    invest = round(user["balance"] * TRADE_PCT, 4)
    if invest < 0.10:
        return None

    qty = invest / price
    if direction == "BUY":
        sl  = price * 0.978
        tp1 = price * 1.02
        tp2 = price * 1.04
        tp3 = price * 1.07
    else:
        sl  = price * 1.022
        tp1 = price * 0.98
        tp2 = price * 0.96
        tp3 = price * 0.93

    trade = {
        "id":        int(time.time() * 1000),
        "symbol":    symbol,
        "direction": direction,
        "entry":     price,
        "qty":       qty,
        "invest":    invest,
        "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "hit_tp1":   False, "hit_tp2":   False,
        "opened_at": datetime.now(timezone.utc).isoformat(),
    }
    user["balance"]  -= invest
    user["open_trades"].append(trade)
    print(f"[demo_app] auto-opened {direction} {symbol} @ ${price:.2f} invest=${invest:.2f}", flush=True)
    return trade

def auto_close_trade(user: dict, trade: dict, reason: str, price: float) -> dict:
    """Close a trade and update user balance."""
    invest = trade["invest"]
    qty    = trade["qty"]
    if trade["direction"] == "BUY":
        pnl = (price - trade["entry"]) * qty
    else:
        pnl = (trade["entry"] - price) * qty

    pnl_pct = (pnl / invest) * 100
    user["balance"]   += invest + pnl
    user["total_pnl"] += pnl
    if pnl >= 0:
        user["wins"]   += 1
    else:
        user["losses"] += 1

    closed = {**trade,
        "close_price": price,
        "pnl":         round(pnl, 4),
        "pnl_pct":     round(pnl_pct, 2),
        "reason":      reason,
        "closed_at":   datetime.now(timezone.utc).isoformat(),
    }
    user["open_trades"]   = [t for t in user["open_trades"] if t["id"] != trade["id"]]
    user["closed_trades"].append(closed)
    if len(user["closed_trades"]) > 50:
        user["closed_trades"] = user["closed_trades"][-50:]
    print(f"[demo_app] closed {trade['symbol']} {reason} pnl={pnl:+.4f} ({pnl_pct:+.2f}%)", flush=True)
    return closed

# ─── Embed Builders ───────────────────────────────────────────────────────────

def _bar(pct: float, length: int = 10) -> str:
    filled = max(0, min(length, int(pct / 100 * length)))
    return "█" * filled + "░" * (length - filled)

def build_main_embed(data: dict) -> discord.Embed:
    """The main pinned LIVE APP embed — shows market + top 3 portfolios."""
    # Live market snapshot
    market_lines = []
    for sym in SYMBOLS:
        price  = get_price(sym)
        change = get_24h_change(sym)
        arrow  = "🟢" if change >= 0 else "🔴"
        name   = sym.replace("USDT", "")
        if price:
            market_lines.append(
                f"{arrow} **{name}**: `${price:,.2f}` ({'+' if change>=0 else ''}{change:.2f}%)"
            )

    # Active users stats
    users    = data.get("users", {})
    active   = [u for u in users.values() if u.get("active")]
    n_active = len(active)
    n_trades = sum(len(u["open_trades"]) for u in active)

    embed = discord.Embed(
        title="🎮 DEMO TRADING — LIVE APP",
        description=(
            "**Investește virtual și urmărește ce fac banii tăi în timp real!**\n"
            "✅ Bani demo • ✅ Prețuri reale Binance • ✅ Bot tranzacționează automat\n"
            f"{'━' * 38}"
        ),
        color=0x00C896,
        timestamp=datetime.now(timezone.utc),
    )

    # Market
    embed.add_field(
        name="📊 Piața Live — Binance",
        value="\n".join(market_lines) if market_lines else "Se încarcă...",
        inline=False,
    )

    # Stats
    embed.add_field(
        name="👥 Statistici Demo",
        value=(
            f"🎮 Traderi activi: `{n_active}`\n"
            f"🔄 Poziții deschise: `{n_trades}`\n"
            f"💰 Fiecare trader începe cu: `$5.00 demo`"
        ),
        inline=False,
    )

    # Leaderboard top 3
    if active:
        ranked = sorted(active, key=lambda u: u["total_pnl"] + sum(
            ((get_price(t["symbol"]) or t["entry"]) - t["entry"]) * t["qty"]
            if t["direction"] == "BUY"
            else (t["entry"] - (get_price(t["symbol"]) or t["entry"])) * t["qty"]
            for t in u["open_trades"]
        ), reverse=True)[:3]

        medals = ["🥇", "🥈", "🥉"]
        lb_lines = []
        for i, u in enumerate(ranked):
            eq = u["balance"] + sum(
                ((get_price(t["symbol"]) or t["entry"]) - t["entry"]) * t["qty"]
                if t["direction"] == "BUY"
                else (t["entry"] - (get_price(t["symbol"]) or t["entry"])) * t["qty"]
                for t in u["open_trades"]
            )
            ret = ((eq - u["starting"]) / u["starting"]) * 100
            s   = "+" if ret >= 0 else ""
            lb_lines.append(f"{medals[i]} **{u['name']}** — `{s}{ret:.2f}%` (`${eq:.2f}`)")
        embed.add_field(
            name="🏆 Leaderboard",
            value="\n".join(lb_lines),
            inline=False,
        )

    embed.add_field(
        name="🚀 Cum funcționează?",
        value=(
            "1️⃣ Apasă **[🚀 Start Demo cu $5]** de mai jos\n"
            "2️⃣ Primești `$5.00` virtuali instant\n"
            "3️⃣ La fiecare semnal BUY/SELL → **botul tranzacționează automat** pentru tine\n"
            "4️⃣ Apasă **[💼 Portofelul Meu]** să vezi P&L live\n"
            "5️⃣ SL și TP se execută automat la prețuri reale Binance"
        ),
        inline=False,
    )

    embed.set_footer(text="🔄 Se actualizează la 30s • 100% prețuri reale • Bani virtuali • Nu e sfat financiar")
    return embed

def build_user_embed(user: dict) -> discord.Embed:
    """Personal portfolio embed for a single user."""
    open_trades = user["open_trades"]

    # Calculate live unrealized P&L
    total_unrealized = 0.0
    live_trades      = []
    for t in open_trades:
        price = get_price(t["symbol"]) or t["entry"]
        if t["direction"] == "BUY":
            unreal = (price - t["entry"]) * t["qty"]
        else:
            unreal = (t["entry"] - price) * t["qty"]
        unreal_pct = (unreal / t["invest"]) * 100
        total_unrealized += unreal
        live_trades.append({**t, "live_price": price, "unreal": unreal, "unreal_pct": unreal_pct})

    equity     = user["balance"] + sum(t["invest"] for t in open_trades) + total_unrealized
    total_pnl  = user["total_pnl"] + total_unrealized
    ret_pct    = ((equity - user["starting"]) / user["starting"]) * 100
    color      = 0x00C896 if ret_pct >= 0 else 0xE74C3C
    arrow      = "📈" if ret_pct >= 0 else "📉"
    sign       = "+" if ret_pct >= 0 else ""

    total_t  = user["wins"] + user["losses"]
    win_rate = (user["wins"] / total_t * 100) if total_t > 0 else 0.0

    embed = discord.Embed(
        title=f"💼 Portofelul tău Demo — {user['name']}",
        description=f"**Bani virtuali • Prețuri reale Binance • Bot tranzacționează automat**",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    # Summary card
    embed.add_field(
        name=f"{arrow} Situație Financiară",
        value=(
            f"```\n"
            f"Start:          $5.00\n"
            f"Sold liber:     ${user['balance']:.4f}\n"
            f"Equity totală:  ${equity:.4f}\n"
            f"P&L realizat:   {'+' if user['total_pnl']>=0 else ''}${user['total_pnl']:.4f}\n"
            f"P&L nerealizat: {'+' if total_unrealized>=0 else ''}${total_unrealized:.4f}\n"
            f"RETURN TOTAL:   {sign}{ret_pct:.2f}% {arrow}\n"
            f"```"
        ),
        inline=False,
    )

    # Win rate bar
    if total_t > 0:
        bar = _bar(win_rate)
        embed.add_field(
            name="📊 Performance",
            value=(
                f"✅ Câștigate: `{user['wins']}`  ❌ Pierdute: `{user['losses']}`\n"
                f"`{bar}` **{win_rate:.1f}%** win rate"
            ),
            inline=False,
        )

    # Open positions
    if live_trades:
        lines = []
        for t in live_trades:
            emoji = "🟢" if t["direction"] == "BUY" else "🔴"
            s     = "+" if t["unreal_pct"] >= 0 else ""
            lines.append(
                f"{emoji} **{t['symbol'].replace('USDT','')}** {t['direction']}\n"
                f"　Entry `${t['entry']:.2f}` → Live `${t['live_price']:.2f}`\n"
                f"　Invest `${t['invest']:.2f}` | P&L `{s}${t['unreal']:.4f}` (`{s}{t['unreal_pct']:.2f}%`)\n"
                f"　🛑 SL `${t['sl']:.2f}` | 🎯 TP3 `${t['tp3']:.2f}`"
            )
        embed.add_field(
            name=f"🔄 Poziții deschise ({len(live_trades)}/{MAX_OPEN})",
            value="\n".join(lines),
            inline=False,
        )
    else:
        embed.add_field(
            name="🔄 Poziții deschise",
            value=(
                "Nicio poziție deschisă momentan.\n"
                "Botul deschide automat la următorul semnal BUY/SELL! ⏳"
            ),
            inline=False,
        )

    # Last 3 closed
    closed = list(reversed(user["closed_trades"]))[:3]
    if closed:
        lines = []
        for t in closed:
            e = "✅" if t["pnl_pct"] >= 0 else "❌"
            s = "+" if t["pnl_pct"] >= 0 else ""
            lines.append(
                f"{e} **{t['symbol'].replace('USDT','')}** {t['direction']} "
                f"→ `{s}{t['pnl_pct']:.2f}%` | {t['reason']}"
            )
        embed.add_field(name="🕒 Ultimele trades", value="\n".join(lines), inline=False)

    embed.set_footer(text="🔄 Apasă Refresh pentru prețuri live • Bot tranzacționează automat • Nu e sfat financiar")
    return embed

# ─── Discord Views ────────────────────────────────────────────────────────────

class MainAppView(ui.View):
    """Buttons on the main pinned embed."""
    def __init__(self):
        super().__init__(timeout=None)  # Persistent

    @ui.button(label="🚀 Start Demo cu $5", style=discord.ButtonStyle.success, custom_id="demo_start")
    async def start_demo(self, interaction: discord.Interaction, button: ui.Button):
        data = _load()
        uid  = str(interaction.user.id)

        if uid in data["users"] and data["users"][uid].get("active"):
            # Already has portfolio — show it
            user = data["users"][uid]
            user["name"] = interaction.user.display_name
            _save(data)
            embed = build_user_embed(user)
            await interaction.response.send_message(
                embed=embed,
                view=UserPortfolioView(interaction.user.id),
                ephemeral=True,
            )
            return

        # Create new portfolio
        user         = _get_user(data, interaction.user.id)
        user["name"] = interaction.user.display_name
        _save(data)

        embed = build_user_embed(user)
        await interaction.response.send_message(
            content=(
                f"🎉 **Bine ai venit la Demo Trading, {interaction.user.display_name}!**\n"
                f"Ai primit `$5.00` virtuali. Botul începe să tranzacționeze automat "
                f"la următorul semnal BUY/SELL! 🤖\n"
                f"Urmărește portofelul tău mai jos 👇"
            ),
            embed=embed,
            view=UserPortfolioView(interaction.user.id),
            ephemeral=True,
        )

    @ui.button(label="💼 Portofelul Meu", style=discord.ButtonStyle.primary, custom_id="demo_portfolio")
    async def my_portfolio(self, interaction: discord.Interaction, button: ui.Button):
        data = _load()
        uid  = str(interaction.user.id)
        if uid not in data["users"]:
            await interaction.response.send_message(
                "❌ Nu ai un portofoliu demo. Apasă **🚀 Start Demo cu $5** mai întâi!",
                ephemeral=True,
            )
            return
        user         = data["users"][uid]
        user["name"] = interaction.user.display_name
        _save(data)
        embed = build_user_embed(user)
        await interaction.response.send_message(
            embed=embed, view=UserPortfolioView(interaction.user.id), ephemeral=True
        )

    @ui.button(label="🏆 Leaderboard", style=discord.ButtonStyle.secondary, custom_id="demo_leaderboard")
    async def leaderboard(self, interaction: discord.Interaction, button: ui.Button):
        data  = _load()
        users = [u for u in data["users"].values() if u.get("active")]
        if not users:
            await interaction.response.send_message("📭 Niciun trader activ încă.", ephemeral=True)
            return

        ranked = sorted(users, key=lambda u: u["total_pnl"] + sum(
            ((get_price(t["symbol"]) or t["entry"]) - t["entry"]) * t["qty"]
            if t["direction"] == "BUY"
            else (t["entry"] - (get_price(t["symbol"]) or t["entry"])) * t["qty"]
            for t in u["open_trades"]
        ), reverse=True)

        medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 20
        lines  = []
        for i, u in enumerate(ranked[:10]):
            eq  = u["balance"] + sum(t["invest"] for t in u["open_trades"]) + sum(
                ((get_price(t["symbol"]) or t["entry"]) - t["entry"]) * t["qty"]
                if t["direction"] == "BUY"
                else (t["entry"] - (get_price(t["symbol"]) or t["entry"])) * t["qty"]
                for t in u["open_trades"]
            )
            ret = ((eq - u["starting"]) / u["starting"]) * 100
            s   = "+" if ret >= 0 else ""
            total_t = u["wins"] + u["losses"]
            wr  = f"{u['wins']}/{total_t}"
            lines.append(f"{medals[i]} **{u['name']}** — `{s}{ret:.2f}%` | W/L: `{wr}` | `${eq:.2f}`")

        embed = discord.Embed(
            title="🏆 Demo Trading Leaderboard",
            description="\n".join(lines),
            color=0xF39C12,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Demo Trading • Bani virtuali • Prețuri reale Binance")
        await interaction.response.send_message(embed=embed, ephemeral=True)

class UserPortfolioView(ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=600)
        self.user_id = user_id

    @ui.button(label="🔄 Refresh Live", style=discord.ButtonStyle.primary)
    async def refresh(self, interaction: discord.Interaction, button: ui.Button):
        data         = _load()
        user         = _get_user(data, self.user_id)
        user["name"] = interaction.user.display_name
        _save(data)
        embed = build_user_embed(user)
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="❌ Închide toate pozițiile", style=discord.ButtonStyle.danger)
    async def close_all(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Nu poți modifica alt portofoliu.", ephemeral=True)
            return
        data = _load()
        user = _get_user(data, self.user_id)
        n    = 0
        for t in list(user["open_trades"]):
            price = get_price(t["symbol"]) or t["entry"]
            auto_close_trade(user, t, "MANUAL ✋", price)
            n += 1
        _save(data)
        embed = build_user_embed(user)
        await interaction.response.edit_message(
            content=f"✅ {n} poziție(i) închisă(e) manual.",
            embed=embed, view=self,
        )

    @ui.button(label="🔄 Reset ($5 nou)", style=discord.ButtonStyle.secondary)
    async def reset_portfolio(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Nu poți modifica alt portofoliu.", ephemeral=True)
            return
        data         = _load()
        uid          = str(self.user_id)
        name         = data["users"].get(uid, {}).get("name", interaction.user.display_name)
        data["users"][uid] = {
            "name":          name,
            "balance":       STARTING_USD,
            "starting":      STARTING_USD,
            "open_trades":   [],
            "closed_trades": [],
            "wins":          0,
            "losses":        0,
            "total_pnl":     0.0,
            "started_at":    datetime.now(timezone.utc).isoformat(),
            "active":        True,
        }
        _save(data)
        embed = build_user_embed(data["users"][uid])
        await interaction.response.edit_message(
            content="✅ Portofoliu resetat cu **$5.00** demo fresh!",
            embed=embed, view=self,
        )

# ─── Channel Setup ────────────────────────────────────────────────────────────

async def setup_demo_channel(client: discord.Client) -> discord.TextChannel | None:
    """Find or create the demo-trading channel inside the admin category."""
    for guild in client.guilds:
        category = guild.get_channel(CATEGORY_ID)
        if category is None:
            continue
        # Find existing channel
        for ch in category.channels:
            if isinstance(ch, discord.TextChannel) and "demo" in ch.name.lower():
                print(f"[demo_app] found existing channel: {ch.name} ({ch.id})", flush=True)
                return ch
        # Create new channel
        try:
            ch = await guild.create_text_channel(
                name=CHANNEL_NAME,
                category=category,
                topic="🎮 Demo Trading Live — Investește virtual, prețuri reale Binance, zero risc",
            )
            print(f"[demo_app] created channel: {ch.name} ({ch.id})", flush=True)
            return ch
        except Exception as e:
            print(f"[demo_app] could not create channel: {e}", flush=True)
    print(f"[demo_app] category {CATEGORY_ID} not found in any guild", flush=True)
    return None

async def post_or_update_main_embed(ch: discord.TextChannel, client: discord.Client) -> discord.Message | None:
    """Post (or edit) the main pinned app embed."""
    data       = _load()
    msg_id     = data.get("app_message_id")
    embed      = build_main_embed(data)
    view       = MainAppView()

    if msg_id:
        try:
            msg = await ch.fetch_message(int(msg_id))
            await msg.edit(embed=embed, view=view)
            return msg
        except Exception:
            pass  # Message deleted — repost

    # Clear channel and post fresh
    try:
        await ch.purge(limit=10)
    except Exception:
        pass

    # Header message
    await ch.send(
        "# 🎮 DEMO TRADING LIVE\n"
        "> Investește **virtual** și urmărește în **timp real** ce fac banii tăi!\n"
        "> ✅ Bani demo • ✅ Prețuri reale Binance • ✅ Bot tranzacționează automat • ✅ Zero risc real\n"
        f"> 🔄 *Se actualizează la fiecare 30 secunde*"
    )

    msg = await ch.send(embed=embed, view=view)
    data["app_message_id"] = str(msg.id)
    _save(data)
    try:
        await msg.pin()
    except Exception:
        pass
    print(f"[demo_app] main embed posted (id={msg.id})", flush=True)
    return msg

# ─── Auto-Trade on Signal ─────────────────────────────────────────────────────

def signal_received(symbol: str, direction: str, price: float):
    """Call this from bot_extended when a real signal fires.
    Opens trades automatically for ALL active demo users.
    """
    data    = _load()
    opened  = 0
    for uid_str, user in data["users"].items():
        if not user.get("active"):
            continue
        trade = auto_open_trade(user, symbol, direction, price)
        if trade:
            opened += 1
    _save(data)
    print(f"[demo_app] signal {direction} {symbol} @ ${price:.2f} → opened {opened} trades", flush=True)

# ─── Main Loop ────────────────────────────────────────────────────────────────

async def demo_app_loop(client: discord.Client):
    """Main loop: setup channel, post embed, poll SL/TP, update every 30s."""
    await client.wait_until_ready()
    await asyncio.sleep(10)

    ch = await setup_demo_channel(client)
    if ch is None:
        print("[demo_app] no channel found — loop exiting", flush=True)
        return

    main_msg = await post_or_update_main_embed(ch, client)
    print("[demo_app] live loop running", flush=True)

    while True:
        try:
            # 1. Poll all open trades for SL/TP hits
            data    = _load()
            changed = False
            for uid_str, user in data["users"].items():
                if not user.get("active"):
                    continue
                for trade in list(user["open_trades"]):
                    price = get_price(trade["symbol"])
                    if not price:
                        continue
                    d = trade["direction"]
                    reason = None

                    if d == "BUY":
                        if price <= trade["sl"]:
                            auto_close_trade(user, trade, "SL 🛑", price); reason = "SL"; changed = True
                        elif price >= trade["tp3"]:
                            auto_close_trade(user, trade, "TP3 🎯🎯🎯", price); reason = "TP3"; changed = True
                        elif price >= trade["tp2"] and not trade.get("hit_tp2"):
                            trade["hit_tp2"] = True; reason = "TP2"; changed = True
                        elif price >= trade["tp1"] and not trade.get("hit_tp1"):
                            trade["hit_tp1"] = True; reason = "TP1"; changed = True
                    else:
                        if price >= trade["sl"]:
                            auto_close_trade(user, trade, "SL 🛑", price); reason = "SL"; changed = True
                        elif price <= trade["tp3"]:
                            auto_close_trade(user, trade, "TP3 🎯🎯🎯", price); reason = "TP3"; changed = True
                        elif price <= trade["tp2"] and not trade.get("hit_tp2"):
                            trade["hit_tp2"] = True; reason = "TP2"; changed = True
                        elif price <= trade["tp1"] and not trade.get("hit_tp1"):
                            trade["hit_tp1"] = True; reason = "TP1"; changed = True

                    if reason:
                        print(f"[demo_app] {uid_str} {trade['symbol']} hit {reason} @ ${price:.2f}", flush=True)

            if changed:
                _save(data)

            # 2. Update main embed
            embed = build_main_embed(data)
            view  = MainAppView()
            if main_msg:
                try:
                    await main_msg.edit(embed=embed, view=view)
                except discord.NotFound:
                    main_msg = await post_or_update_main_embed(ch, client)
                except Exception as e:
                    print(f"[demo_app] edit error: {e}", flush=True)

        except Exception as e:
            print(f"[demo_app] loop error: {e}", flush=True)

        await asyncio.sleep(POLL_SECONDS)
