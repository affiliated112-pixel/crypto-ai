"""signal_results.py — Automatic signal outcome tracking.

After every signal is sent, this module:
  1. Records entry price, TP1, TP2, TP3, SL
  2. Polls Binance every 30 min to check if TP1/TP2/TP3/SL was hit
  3. Posts the result to RESULTS_CHANNEL (1509524216821579839)
  4. Closes the trade after 48h max (expired = neutral)

Results channel: 1509524216821579839
"""

import asyncio
import json
import requests
import discord
from datetime import datetime, timezone, timedelta
from pathlib import Path

import coins_config
import market_data
import signal_engine

RESULTS_CHANNEL_ID = 1509524216821579839
POLL_INTERVAL      = 1800   # check every 30 min
MAX_TRADE_HOURS    = 48     # close after 48h regardless

TRADES_FILE = Path(__file__).with_name("open_trades.json")

# ─── PERSISTENCE ─────────────────────────────────────────────────────────────
# {trade_id: {symbol, signal, entry, tp1, tp2, tp3, sl, opened_at, tier, score}}
_open_trades: dict[str, dict] = {}

def _load():
    global _open_trades
    if TRADES_FILE.exists():
        try:
            _open_trades = json.loads(TRADES_FILE.read_text())
            print(f"[results] Loaded {len(_open_trades)} open trades", flush=True)
        except Exception as e:
            print(f"[results] load error: {e}", flush=True)

def _save():
    try:
        TRADES_FILE.write_text(json.dumps(_open_trades, indent=2))
    except Exception as e:
        print(f"[results] save error: {e}", flush=True)

_load()

# ─── TRADE REGISTRATION ───────────────────────────────────────────────────────

def register_signal(
    symbol:  str,
    signal:  str,
    price:   float,
    atr:     float,
    score:   int,
    tier:    str = "free",
    levels:  dict | None = None,
    signal_id: str | None = None,
):
    """Call this immediately after sending a signal.

    Uses the same ATR-based levels as the signal embed when provided, so result
    tracking matches what users actually saw in Discord.
    """
    if levels and all(k in levels for k in ("sl", "tp1", "tp2", "tp3")):
        sl  = float(levels["sl"])
        tp1 = float(levels["tp1"])
        tp2 = float(levels["tp2"])
        tp3 = float(levels["tp3"])
    else:
        try:
            levels = signal_engine.compute_levels(price, signal, atr, atr / price if price else None)
            sl, tp1, tp2, tp3 = (float(levels["sl"]), float(levels["tp1"]), float(levels["tp2"]), float(levels["tp3"]))
        except Exception:
            is_buy = signal == "BUY"
            tp1 = round(price + 1.5 * atr, 6) if is_buy else round(price - 1.5 * atr, 6)
            tp2 = round(price + 3.0 * atr, 6) if is_buy else round(price - 3.0 * atr, 6)
            tp3 = round(price + 5.0 * atr, 6) if is_buy else round(price - 5.0 * atr, 6)
            sl  = round(price - 1.2 * atr, 6) if is_buy else round(price + 1.2 * atr, 6)

    trade_id = signal_id or f"{symbol}_{int(datetime.now(timezone.utc).timestamp())}"
    _open_trades[trade_id] = {
        "symbol":     symbol,
        "signal":     signal,
        "entry":      price,
        "tp1":        tp1,
        "tp2":        tp2,
        "tp3":        tp3,
        "sl":         sl,
        "atr":        atr,
        "score":      score,
        "tier":       tier,
        "opened_at":  datetime.now(timezone.utc).isoformat(),
        "tp1_hit":    False,
        "tp2_hit":    False,
        "tp3_hit":    False,
        "sl_hit":     False,
        "closed":     False,
        "result":     None,   # "TP1"/"TP2"/"TP3"/"SL"/"EXPIRED"
        "close_price": None,
        "pnl_pct":    None,
    }
    _save()
    print(f"[results] Registered trade {trade_id}: {signal} {symbol} @ {price:.4f}", flush=True)
    return trade_id

# ─── PRICE FETCH ──────────────────────────────────────────────────────────────

def _get_current_price(symbol: str) -> float | None:
    return market_data.get_current_price(symbol)

# ─── OUTCOME CHECK ────────────────────────────────────────────────────────────

def _check_trade(trade: dict, current_price: float) -> str | None:
    """
    Returns the outcome string if trade should close, else None.
    Priority: SL first (most important), then TP3, TP2, TP1.
    """
    sig    = trade["signal"]
    is_buy = sig == "BUY"
    entry  = trade["entry"]
    sl     = trade["sl"]
    tp1    = trade["tp1"]
    tp2    = trade["tp2"]
    tp3    = trade["tp3"]

    if is_buy:
        if current_price <= sl:   return "SL"
        if current_price >= tp3:  return "TP3"
        if current_price >= tp2:  return "TP2"
        if current_price >= tp1:  return "TP1"
    else:
        if current_price >= sl:   return "SL"
        if current_price <= tp3:  return "TP3"
        if current_price <= tp2:  return "TP2"
        if current_price <= tp1:  return "TP1"
    return None

# ─── RESULT EMBED ─────────────────────────────────────────────────────────────

def _result_embed(trade: dict, result: str, close_price: float) -> discord.Embed:
    symbol   = trade["symbol"]
    sig      = trade["signal"]
    entry    = trade["entry"]
    score    = trade["score"]
    tier     = trade["tier"]
    is_buy   = sig == "BUY"
    emoji    = coins_config.COIN_EMOJI.get(symbol, "🪙")
    coin     = symbol.replace("USDT", "")
    opened   = datetime.fromisoformat(trade["opened_at"])
    duration = datetime.now(timezone.utc) - opened
    hrs      = int(duration.total_seconds() / 3600)
    mins     = int((duration.total_seconds() % 3600) / 60)

    # P&L calculation
    pnl_pct  = ((close_price - entry) / entry * 100) * (1 if is_buy else -1)

    # Color and icon per result
    if result == "SL":
        color = 0xFF4757
        icon  = "🔴"
        headline = "STOP LOSS HIT"
        verdict  = "Trade closed at stop. Capital protected."
    elif result == "TP1":
        color = 0x2ECC71
        icon  = "🟢"
        headline = "TP1 HIT ✓"
        verdict  = "First target reached based on tracked levels. Manage the remaining position by plan."
    elif result == "TP2":
        color = 0x00B894
        icon  = "🟢🟢"
        headline = "TP2 HIT ✓✓"
        verdict  = "Second target reached. Strong move."
    elif result == "TP3":
        color = 0x00CEC9
        icon  = "🏆"
        headline = "TP3 HIT — FULL TARGET ✓✓✓"
        verdict  = "Full target reached based on tracked levels."
    else:  # EXPIRED
        color = 0x636E72
        icon  = "⏳"
        headline = "EXPIRED (48h)"
        verdict  = "Trade did not hit any target within 48h. No result."
        pnl_pct  = ((close_price - entry) / entry * 100) * (1 if is_buy else -1)

    tier_badge = "💎 VIP" if tier == "vip" else "🆓 FREE"
    dir_badge  = "📈 BUY" if is_buy else "📉 SELL"

    embed = discord.Embed(
        title=f"{icon}  {emoji} {coin}  —  {headline}",
        description=f"`{tier_badge}`  ·  `{dir_badge}`  ·  Signal Score: `{score}/100`",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(name="📊 Signal Result — Automatic Tracking")

    embed.add_field(
        name="📌 Trade Summary",
        value=(
            f"```\n"
            f"Direction  {'BUY  (LONG)' if is_buy else 'SELL (SHORT)'}\n"
            f"Entry      {entry:>14,.4f}\n"
            f"Close      {close_price:>14,.4f}\n"
            f"P&L        {pnl_pct:>+13.2f}%\n"
            f"Duration   {hrs}h {mins}m\n"
            f"Result     {result}\n"
            f"```"
        ),
        inline=False,
    )

    # Targets hit overview
    tp1_icon = "✅" if result in ("TP1","TP2","TP3") else "⬜"
    tp2_icon = "✅" if result in ("TP2","TP3") else "⬜"
    tp3_icon = "✅" if result == "TP3" else "⬜"
    sl_icon  = "🛑" if result == "SL" else "✅"

    embed.add_field(
        name="🎯 Targets",
        value=(
            f"{sl_icon} SL    `{trade['sl']:,.4f}`\n"
            f"{tp1_icon} TP1   `{trade['tp1']:,.4f}`\n"
            f"{tp2_icon} TP2   `{trade['tp2']:,.4f}`\n"
            f"{tp3_icon} TP3   `{trade['tp3']:,.4f}`"
        ),
        inline=True,
    )

    embed.add_field(
        name="📝 Verdict",
        value=verdict,
        inline=True,
    )

    # Running stats
    total  = sum(1 for t in _open_trades.values() if t.get("closed"))
    wins   = sum(1 for t in _open_trades.values() if t.get("result") in ("TP1","TP2","TP3"))
    losses = sum(1 for t in _open_trades.values() if t.get("result") == "SL")
    wr     = (wins / total * 100) if total > 0 else 0.0

    embed.add_field(
        name="📈 All-time Results",
        value=(
            f"**{total}** trades closed\n"
            f"✅ **{wins}** wins · 🔴 **{losses}** losses\n"
            f"**Win rate: {wr:.1f}%** (tracked signals only)"
        ),
        inline=False,
    )

    embed.set_footer(text="Tracked results · Past performance is not a guarantee · Not financial advice")
    return embed

# ─── POLLING LOOP ─────────────────────────────────────────────────────────────

async def results_loop(client: discord.Client):
    """Polls all open trades every 30 min and posts results."""
    await client.wait_until_ready()
    await asyncio.sleep(60)   # Let bot fully start

    print(f"[results] Loop started — polling every {POLL_INTERVAL//60} min", flush=True)

    while True:
        now = datetime.now(timezone.utc)
        to_close = []

        for trade_id, trade in list(_open_trades.items()):
            if trade.get("closed"):
                continue

            symbol  = trade["symbol"]
            opened  = datetime.fromisoformat(trade["opened_at"])
            age_h   = (now - opened).total_seconds() / 3600

            # Expired
            if age_h >= MAX_TRADE_HOURS:
                price = _get_current_price(symbol)
                to_close.append((trade_id, "EXPIRED", price or trade["entry"]))
                continue

            # Check price
            price = _get_current_price(symbol)
            if price is None:
                continue

            result = _check_trade(trade, price)
            if result:
                to_close.append((trade_id, result, price))

        # Send results
        for trade_id, result, close_price in to_close:
            trade = _open_trades[trade_id]
            try:
                ch = client.get_channel(RESULTS_CHANNEL_ID)
                if ch is None:
                    ch = await client.fetch_channel(RESULTS_CHANNEL_ID)

                embed = _result_embed(trade, result, close_price)
                await ch.send(embed=embed)

                # Mark closed
                _open_trades[trade_id]["closed"]     = True
                _open_trades[trade_id]["result"]     = result
                _open_trades[trade_id]["close_price"] = close_price
                pnl = ((close_price - trade["entry"]) / trade["entry"] * 100)
                _open_trades[trade_id]["pnl_pct"]   = pnl * (1 if trade["signal"]=="BUY" else -1)
                _save()

                print(f"[results] CLOSED {trade_id}: {result} @ {close_price:.4f}", flush=True)
                await asyncio.sleep(2)

            except Exception as e:
                print(f"[results] error closing {trade_id}: {e}", flush=True)

        await asyncio.sleep(POLL_INTERVAL)
