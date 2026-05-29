"""Builds Discord embeds for SL/TP alerts and sends them to the alerts
or signals channel via the bot client.
"""
import discord
from datetime import datetime, timezone

COIN_ICONS = {
    "BTC":  "https://assets.coingecko.com/coins/images/1/large/bitcoin.png",
    "ETH":  "https://assets.coingecko.com/coins/images/279/large/ethereum.png",
    "SOL":  "https://assets.coingecko.com/coins/images/4128/large/solana.png",
    "BNB":  "https://assets.coingecko.com/coins/images/825/large/bnb-icon2_2x.png",
}

EVENT_STYLE = {
    "TP1":     ("🎯 TP1 HIT",      "+2%",  0x2ECC71),
    "TP2":     ("🎯🎯 TP2 HIT",   "+4%",  0x27AE60),
    "TP3":     ("🎯🎯🎯 TP3 HIT", "+7%",  0xF1C40F),
    "SL":      ("🛑 STOP LOSS",    "−2%", 0xE74C3C),
    "EXPIRED": ("🕒 SIGNAL EXPIRED", "—",   0x7F8C8D),
}


def _coin(symbol):
    return symbol.replace("USDT", "").replace("USD", "") if symbol else "COIN"


def _fmt(p):
    if p is None: return "—"
    if p >= 1000: return f"${p:,.2f}"
    if p >= 1:    return f"${p:,.4f}"
    return f"${p:,.8f}".rstrip("0").rstrip(".")


def build_alert_embed(event, record, extra):
    title_prefix, target_pct, color = EVENT_STYLE.get(event, (event, "—", 0x95A5A6))
    coin = _coin(record["symbol"])
    is_buy = record["direction"] == "BUY"
    side = "🟢 BUY" if is_buy else "🔴 SELL"
    pnl = extra.get("pnl_pct", 0)
    current = extra.get("current_price")
    pnl_str = f"{pnl:+.2f}%"

    if event.startswith("TP"):
        desc = (
            f"```diff\n+ {title_prefix} — {coin}/USDT\n"
            f"+ Result: {pnl_str} from entry\n```"
            f"✨ **Felicitări** dacă ai luat acest semnal!"
        )
    elif event == "SL":
        desc = (
            f"```diff\n- {title_prefix} — {coin}/USDT\n"
            f"- Result: {pnl_str} from entry\n```"
            f"🛡️ Stop Loss te-a protejat — așa funcționează risk management!"
        )
    else:  # EXPIRED
        desc = (
            f"```{title_prefix} — {coin}/USDT\n"
            f"Result: {pnl_str} from entry\n```"
            f"⏰ Semnalul a expirat după 48h fără să atingă TP sau SL."
        )

    embed = discord.Embed(
        title=f"{title_prefix} • {coin}",
        description=desc,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    if coin in COIN_ICONS:
        embed.set_thumbnail(url=COIN_ICONS[coin])

    embed.add_field(name="📊 Side",       value=f"`{side}`",            inline=True)
    embed.add_field(name="💰 Entry",      value=f"`{_fmt(record['entry'])}`", inline=True)
    embed.add_field(name="💵 Now",        value=f"`{_fmt(current)}`",   inline=True)

    if event == "SL":
        embed.add_field(name="🛑 SL Level", value=f"`{_fmt(record['sl'])}`", inline=True)
    elif event == "TP1":
        embed.add_field(name="🎯 TP1 Target", value=f"`{_fmt(record['tp1'])}`", inline=True)
    elif event == "TP2":
        embed.add_field(name="🎯 TP2 Target", value=f"`{_fmt(record['tp2'])}`", inline=True)
    elif event == "TP3":
        embed.add_field(name="🎯 TP3 Target", value=f"`{_fmt(record['tp3'])}`", inline=True)

    embed.add_field(name="⚖️ P&L", value=f"`{pnl_str}`", inline=True)

    if record.get("quality"):
        embed.add_field(name="⭐ Quality", value=f"`{record['quality']}`", inline=True)

    embed.set_footer(text=f"Signal tracker • entry was at {record['opened_at'][:16].replace('T',' ')} UTC")
    return embed
