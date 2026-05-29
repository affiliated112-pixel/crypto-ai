"""paper_trading.py — Admin-only Paper Trading Engine.
Simulates real trades based on bot signals using virtual money.
100% real-time prices from Binance. Zero real money involved.
Only the admin can see the results (private channel).

Category ID: 1509818706509955172
"""
import asyncio
import json
import os
import requests
from datetime import datetime, timezone

PAPER_FILE = os.environ.get("PAPER_TRADING_FILE", "paper_trading.json")
STARTING_BALANCE = float(os.environ.get("PAPER_STARTING_BALANCE", "5.0"))
TRADE_PCT = 0.20  # 20% of portfolio per trade
POLL_SECONDS = 30
UA = {"User-Agent": "crypto-ai-bot/2026"}

CATEGORY_ID = 1509818706509955172

def _load():
    if not os.path.isfile(PAPER_FILE):
        return _default()
    try:
        with open(PAPER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return _default()

def _default():
    return {
        "balance": STARTING_BALANCE,
        "starting_balance": STARTING_BALANCE,
        "open_trades": [],
        "closed_trades": [],
        "total_pnl": 0.0,
        "wins": 0,
        "losses": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

def _save(data):
    try:
        with open(PAPER_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[paper] save error: {e}", flush=True)

def _get_price(symbol):
    try:
        r = requests.get(
            f"https://api.binance.us/api/v3/ticker/price?symbol={symbol}",
            headers=UA, timeout=6,
        )
        return float(r.json()["price"])
    except Exception:
        return None

def open_trade(symbol, direction, entry_price):
    """Open a new paper trade based on a bot signal."""
    data = _load()
    available = data["balance"]
    if available < 0.10:
        print(f"[paper] not enough balance (${available:.2f}) to open trade", flush=True)
        return None

    # Check if already have open trade for this symbol
    for t in data["open_trades"]:
        if t["symbol"] == symbol:
            print(f"[paper] already have open trade for {symbol} — skipping", flush=True)
            return None

    size_usd = round(available * TRADE_PCT, 4)
    qty = size_usd / entry_price

    if direction == "BUY":
        sl = entry_price * 0.98
        tp1 = entry_price * 1.02
        tp2 = entry_price * 1.04
        tp3 = entry_price * 1.07
    else:
        sl = entry_price * 1.02
        tp1 = entry_price * 0.98
        tp2 = entry_price * 0.96
        tp3 = entry_price * 0.93

    trade = {
        "id": int(datetime.now(timezone.utc).timestamp() * 1000),
        "symbol": symbol,
        "direction": direction,
        "entry": entry_price,
        "qty": qty,
        "size_usd": size_usd,
        "sl": sl,
        "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "hit_tp1": False, "hit_tp2": False,
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "current_price": entry_price,
        "unrealized_pnl": 0.0,
    }

    data["balance"] -= size_usd
    data["open_trades"].append(trade)
    _save(data)
    print(f"[paper] OPENED {direction} {symbol} @ ${entry_price:.4f} size=${size_usd:.2f}", flush=True)
    return trade

def close_trade(trade_id, reason, close_price):
    """Close a paper trade and record P&L."""
    data = _load()
    trade = next((t for t in data["open_trades"] if t["id"] == trade_id), None)
    if not trade:
        return None

    qty = trade["qty"]
    entry = trade["entry"]
    direction = trade["direction"]

    if direction == "BUY":
        pnl = (close_price - entry) * qty
    else:
        pnl = (entry - close_price) * qty

    pnl_pct = (pnl / trade["size_usd"]) * 100
    close_usd = trade["size_usd"] + pnl
    data["balance"] += close_usd
    data["total_pnl"] += pnl

    if pnl > 0:
        data["wins"] += 1
    else:
        data["losses"] += 1

    closed = {**trade,
        "closed_at": datetime.now(timezone.utc).isoformat(),
        "close_price": close_price,
        "pnl": round(pnl, 4),
        "pnl_pct": round(pnl_pct, 2),
        "close_reason": reason,
    }
    data["open_trades"] = [t for t in data["open_trades"] if t["id"] != trade_id]
    data["closed_trades"].append(closed)
    if len(data["closed_trades"]) > 200:
        data["closed_trades"] = data["closed_trades"][-200:]
    _save(data)
    print(f"[paper] CLOSED {trade['symbol']} {reason} pnl={pnl:+.4f} ({pnl_pct:+.2f}%)", flush=True)
    return closed

def get_stats():
    """Return current paper trading stats."""
    data = _load()
    total = data["wins"] + data["losses"]
    win_rate = (data["wins"] / total * 100) if total > 0 else 0.0

    # Calculate unrealized P&L from open trades
    unrealized = 0.0
    for t in data["open_trades"]:
        price = _get_price(t["symbol"])
        if price:
            qty = t["qty"]
            if t["direction"] == "BUY":
                unrealized += (price - t["entry"]) * qty
            else:
                unrealized += (t["entry"] - price) * qty
            t["current_price"] = price
            t["unrealized_pnl"] = round((price - t["entry"]) / t["entry"] * 100, 2)

    equity = data["balance"] + sum(t["size_usd"] for t in data["open_trades"]) + unrealized
    total_return = ((equity - data["starting_balance"]) / data["starting_balance"]) * 100

    return {
        "balance": round(data["balance"], 4),
        "equity": round(equity, 4),
        "starting": data["starting_balance"],
        "total_pnl": round(data["total_pnl"] + unrealized, 4),
        "total_return_pct": round(total_return, 2),
        "wins": data["wins"],
        "losses": data["losses"],
        "win_rate": round(win_rate, 1),
        "open_trades": data["open_trades"],
        "closed_trades": data["closed_trades"][-5:],
        "started_at": data["started_at"],
    }

def reset(starting_balance=None):
    """Reset paper trading to fresh state."""
    bal = starting_balance or STARTING_BALANCE
    data = _default()
    data["balance"] = bal
    data["starting_balance"] = bal
    _save(data)
    print(f"[paper] RESET — starting balance ${bal:.2f}", flush=True)
    return data

# ─── Discord Integration ──────────────────────────────────────────────────────

import discord

def _pnl_color(pnl):
    if pnl > 0: return 0x00C896
    if pnl < 0: return 0xE74C3C
    return 0x95A5A6

def _bar(value, max_val, length=10, fill="█", empty="░"):
    filled = int(round((value / max_val) * length)) if max_val else 0
    filled = max(0, min(length, filled))
    return fill * filled + empty * (length - filled)

def build_portfolio_embed(stats):
    """Build the Discord embed for portfolio status."""
    equity = stats["equity"]
    starting = stats["starting"]
    ret_pct = stats["total_return_pct"]
    color = _pnl_color(ret_pct)

    arrow = "📈" if ret_pct >= 0 else "📉"
    sign = "+" if ret_pct >= 0 else ""

    embed = discord.Embed(
        title="💼 PAPER TRADING — LIVE PORTFOLIO",
        description=(
            f"**Admin-only demo** — 100% real prices, zero real money\n"
            f"Started: <t:{int(datetime.fromisoformat(stats['started_at'].replace('Z','+00:00')).timestamp())}:R>"
        ),
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="💰 Capital",
        value=(
            f"```\n"
            f"Start:    ${starting:.2f}\n"
            f"Equity:   ${equity:.4f}\n"
            f"Free:     ${stats['balance']:.4f}\n"
            f"P&L:      {sign}${stats['total_pnl']:.4f}\n"
            f"Return:   {sign}{ret_pct:.2f}% {arrow}\n"
            f"```"
        ),
        inline=False,
    )

    total = stats["wins"] + stats["losses"]
    wr = stats["win_rate"]
    bar = _bar(wr, 100)
    embed.add_field(
        name="📊 Track Record",
        value=(
            f"```\n"
            f"Trades:   {total}\n"
            f"Wins:     {stats['wins']}  Losses: {stats['losses']}\n"
            f"Win Rate: {wr:.1f}%\n"
            f"{bar} {wr:.0f}%\n"
            f"```"
        ),
        inline=False,
    )

    if stats["open_trades"]:
        lines = []
        for t in stats["open_trades"]:
            cur = t.get("current_price", t["entry"])
            upnl = t.get("unrealized_pnl", 0.0)
            sign2 = "+" if upnl >= 0 else ""
            emoji = "🟢" if t["direction"] == "BUY" else "🔴"
            lines.append(
                f"{emoji} **{t['symbol']}** {t['direction']} @ `${t['entry']:.2f}`\n"
                f"   Curent: `${cur:.2f}` | P&L: `{sign2}{upnl:.2f}%`\n"
                f"   SL: `${t['sl']:.2f}` | TP1: `${t['tp1']:.2f}` | TP3: `${t['tp3']:.2f}`"
            )
        embed.add_field(
            name=f"🔄 Poziții deschise ({len(stats['open_trades'])})",
            value="\n".join(lines) or "—",
            inline=False,
        )
    else:
        embed.add_field(name="🔄 Poziții deschise", value="Nicio poziție deschisă momentan.", inline=False)

    if stats["closed_trades"]:
        lines = []
        for t in reversed(stats["closed_trades"]):
            p = t["pnl_pct"]
            s = "+" if p >= 0 else ""
            e = "✅" if p >= 0 else "❌"
            lines.append(f"{e} {t['symbol']} {t['direction']} → `{s}{p:.2f}%` ({t['close_reason']})")
        embed.add_field(
            name="🕒 Ultimele 5 trades",
            value="\n".join(lines),
            inline=False,
        )

    embed.set_footer(text="📊 100% real Binance prices • Paper money only • Not financial advice")
    return embed

async def paper_portfolio_loop(bot, channel_id, interval=300):
    """Post live portfolio update every 5 minutes to admin channel."""
    await bot.client.wait_until_ready()
    await asyncio.sleep(20)
    print(f"[paper] portfolio loop started — channel {channel_id}", flush=True)
    last_msg = None
    while True:
        try:
            ch = bot.client.get_channel(channel_id)
            if ch is None:
                try:
                    ch = await bot.client.fetch_channel(channel_id)
                except Exception as e:
                    print(f"[paper] cannot fetch channel {channel_id}: {e}", flush=True)
                    await asyncio.sleep(interval)
                    continue

            stats = get_stats()
            embed = build_portfolio_embed(stats)

            # Edit last message if possible, else send new
            if last_msg:
                try:
                    await last_msg.edit(embed=embed)
                    print("[paper] portfolio embed updated", flush=True)
                except Exception:
                    last_msg = await ch.send(embed=embed)
            else:
                last_msg = await ch.send(embed=embed)

        except Exception as e:
            print(f"[paper] loop error: {e}", flush=True)
        await asyncio.sleep(interval)

async def paper_poll_loop(bot, admin_channel_id):
    """Poll open trades every 30s, close at SL/TP, notify admin."""
    await bot.client.wait_until_ready()
    await asyncio.sleep(30)
    print("[paper] SL/TP poll loop started", flush=True)
    while True:
        try:
            data = _load()
            for trade in list(data["open_trades"]):
                price = _get_price(trade["symbol"])
                if not price:
                    continue
                tid = trade["id"]
                direction = trade["direction"]

                closed = None
                reason = None

                if direction == "BUY":
                    if price <= trade["sl"]:
                        closed = close_trade(tid, "SL", price)
                        reason = "🛑 STOP LOSS HIT"
                    elif price >= trade["tp3"]:
                        closed = close_trade(tid, "TP3", price)
                        reason = "🎯 TAKE PROFIT 3 HIT"
                    elif price >= trade["tp2"] and not trade.get("hit_tp2"):
                        # Partial close — just notify, keep position
                        data2 = _load()
                        for t in data2["open_trades"]:
                            if t["id"] == tid:
                                t["hit_tp2"] = True
                        _save(data2)
                        reason = "🎯 TP2 reached"
                    elif price >= trade["tp1"] and not trade.get("hit_tp1"):
                        data2 = _load()
                        for t in data2["open_trades"]:
                            if t["id"] == tid:
                                t["hit_tp1"] = True
                        _save(data2)
                        reason = "🎯 TP1 reached"
                else:  # SELL
                    if price >= trade["sl"]:
                        closed = close_trade(tid, "SL", price)
                        reason = "🛑 STOP LOSS HIT"
                    elif price <= trade["tp3"]:
                        closed = close_trade(tid, "TP3", price)
                        reason = "🎯 TAKE PROFIT 3 HIT"
                    elif price <= trade["tp2"] and not trade.get("hit_tp2"):
                        data2 = _load()
                        for t in data2["open_trades"]:
                            if t["id"] == tid:
                                t["hit_tp2"] = True
                        _save(data2)
                        reason = "🎯 TP2 reached"
                    elif price <= trade["tp1"] and not trade.get("hit_tp1"):
                        data2 = _load()
                        for t in data2["open_trades"]:
                            if t["id"] == tid:
                                t["hit_tp1"] = True
                        _save(data2)
                        reason = "🎯 TP1 reached"

                if reason:
                    try:
                        ch = bot.client.get_channel(admin_channel_id)
                        if ch is None:
                            ch = await bot.client.fetch_channel(admin_channel_id)
                        pnl = closed["pnl_pct"] if closed else 0
                        sign = "+" if pnl >= 0 else ""
                        color = 0x00C896 if pnl >= 0 else 0xE74C3C
                        embed = discord.Embed(
                            title=f"📊 PAPER TRADE UPDATE — {trade['symbol']}",
                            description=(
                                f"**{reason}**\n\n"
                                f"{'Closed' if closed else 'Milestone'}: `{trade['direction']}` {trade['symbol']}\n"
                                f"Entry: `${trade['entry']:.4f}` → Price: `${price:.4f}`\n"
                                f"P&L: `{sign}{pnl:.2f}%`"
                            ),
                            color=color,
                            timestamp=datetime.now(timezone.utc),
                        )
                        if closed:
                            stats = get_stats()
                            embed.add_field(
                                name="💼 Portfolio acum",
                                value=f"Equity: `${stats['equity']:.4f}` | Return: `{'+' if stats['total_return_pct']>=0 else ''}{stats['total_return_pct']:.2f}%`",
                                inline=False,
                            )
                        embed.set_footer(text="Paper Trading • Admin only • Not financial advice")
                        await ch.send(embed=embed)
                    except Exception as e:
                        print(f"[paper] notify error: {e}", flush=True)

        except Exception as e:
            print(f"[paper] poll error: {e}", flush=True)
        await asyncio.sleep(POLL_SECONDS)

def hook_signal(symbol, direction, price):
    """Call this from bot_extended when a signal is emitted to auto-open paper trade."""
    trade = open_trade(symbol, direction, price)
    if trade:
        print(f"[paper] auto-opened from signal: {direction} {symbol} @ ${price}", flush=True)
    return trade
