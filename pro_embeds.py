"""Professional, modern Discord embeds for trading signals.
Replaces bot.build_free_embed and bot.build_vip_embed with cleaner layouts.
"""
import discord
from datetime import datetime, timezone

COIN_ICONS = {
    "BTC":  "https://assets.coingecko.com/coins/images/1/large/bitcoin.png",
    "ETH":  "https://assets.coingecko.com/coins/images/279/large/ethereum.png",
    "SOL":  "https://assets.coingecko.com/coins/images/4128/large/solana.png",
    "BNB":  "https://assets.coingecko.com/coins/images/825/large/bnb-icon2_2x.png",
    "XRP":  "https://assets.coingecko.com/coins/images/44/large/xrp-symbol-white-128.png",
    "ADA":  "https://assets.coingecko.com/coins/images/975/large/cardano.png",
    "DOGE": "https://assets.coingecko.com/coins/images/5/large/dogecoin.png",
    "AVAX": "https://assets.coingecko.com/coins/images/12559/large/Avalanche_Circle_RedWhite_Trans.png",
    "LINK": "https://assets.coingecko.com/coins/images/877/large/chainlink-new-logo.png",
    "MATIC":"https://assets.coingecko.com/coins/images/4713/large/polygon.png",
}

COLOR_BUY = 0x00D26A   # vivid green
COLOR_SELL = 0xED4245  # discord red
COLOR_PREMIUM = 0xF1C40F  # gold

QUALITY_BADGES = {
    "PREMIUM":  ("🌟 PREMIUM", 0xF1C40F),
    "STRONG":   ("🔥 STRONG",  0xE67E22),
    "STANDARD": ("⚡ STANDARD", 0x3498DB),
}


def _fmt_price(p):
    if p is None: return "—"
    if p >= 1000: return f"${p:,.2f}"
    if p >= 1:    return f"${p:,.4f}"
    return f"${p:,.8f}".rstrip("0").rstrip(".")


def _coin_from_symbol(symbol):
    s = symbol.upper()
    if s.endswith("USDT"): return s[:-4]
    if s.endswith("USD"):  return s[:-3]
    return s


def _calc_levels(direction, price):
    """Return SL, TP1, TP2, TP3."""
    if direction == "BUY":
        return price * 0.98, price * 1.02, price * 1.04, price * 1.07
    return price * 1.02, price * 0.98, price * 0.96, price * 0.93


def build_free_embed(symbol, sig, price, rsi, conf, quality=None, score=None, filters=None):
    """Clean, lightweight embed for the free channel."""
    coin = _coin_from_symbol(symbol)
    is_buy = sig == "BUY"
    color = COLOR_BUY if is_buy else COLOR_SELL
    arrow = "🟢 BUY" if is_buy else "🔴 SELL"
    sl, tp1, tp2, tp3 = _calc_levels(sig, price)

    badge = ""
    if quality and quality in QUALITY_BADGES:
        b, c = QUALITY_BADGES[quality]
        badge = f" • {b}"
        color = c

    embed = discord.Embed(
        title=f"{arrow}  •  {coin}/USDT{badge}",
        description=f"```diff\n{'+ ' if is_buy else '- '}Entry zone: {_fmt_price(price)}\n```",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    icon = COIN_ICONS.get(coin)
    if icon:
        embed.set_thumbnail(url=icon)

    embed.add_field(name="💰 Entry",      value=f"`{_fmt_price(price)}`", inline=True)
    embed.add_field(name="🛑 Stop Loss",  value=f"`{_fmt_price(sl)}`",    inline=True)
    embed.add_field(name="⚖️ R:R",         value="`1 : 2`",                inline=True)

    embed.add_field(name="🎯 TP1 (+2%)", value=f"`{_fmt_price(tp1)}`", inline=True)
    embed.add_field(name="🎯 TP2 (+4%)", value=f"`{_fmt_price(tp2)}`", inline=True)
    embed.add_field(name="🎯 TP3 (+7%)", value=f"`{_fmt_price(tp3)}`", inline=True)

    meta = f"RSI `{rsi:.1f}` • Confidence `{conf}`"
    if score is not None:
        meta += f" • Quality `{score}/100`"
    embed.add_field(name="📊 Indicators", value=meta, inline=False)

    embed.set_footer(
        text="⚠️ Educational only — always use Stop Loss • Risk small, usually 1–2% per trade",
        icon_url="https://cdn-icons-png.flaticon.com/512/2331/2331970.png",
    )
    return embed


def build_vip_embed(symbol, sig, price, rsi, conf, ai_text="", confirmed=False, ind=None,
                    quality=None, score=None, filters=None):
    """Rich VIP embed with full analysis, MTF confirmation, rationale text, indicators."""
    coin = _coin_from_symbol(symbol)
    is_buy = sig == "BUY"
    color = COLOR_BUY if is_buy else COLOR_SELL
    arrow = "🟢 BUY" if is_buy else "🔴 SELL"
    sl, tp1, tp2, tp3 = _calc_levels(sig, price)

    badge = ""
    if quality and quality in QUALITY_BADGES:
        b, c = QUALITY_BADGES[quality]
        badge = f"  •  {b}"
        color = c

    confirm_emoji = "✅" if confirmed else "⚠️"
    embed = discord.Embed(
        title=f"💎 VIP SIGNAL  •  {arrow}  {coin}/USDT{badge}",
        description=(
            f"```diff\n{'+ ' if is_buy else '- '}Action: {sig} {coin}\n"
            f"{'+ ' if is_buy else '- '}Entry:  {_fmt_price(price)}\n```"
            f"{confirm_emoji}  **15m Timeframe:** {'confirmed' if confirmed else 'not confirmed'}"
        ),
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    icon = COIN_ICONS.get(coin)
    if icon:
        embed.set_thumbnail(url=icon)

    embed.add_field(name="💰 Entry",     value=f"```{_fmt_price(price)}```", inline=True)
    embed.add_field(name="🛑 Stop Loss", value=f"```{_fmt_price(sl)}```",    inline=True)
    embed.add_field(name="⚖️ R:R",        value="```1 : 2.0```",              inline=True)

    embed.add_field(name="🎯 TP1 · +2%", value=f"```{_fmt_price(tp1)}```", inline=True)
    embed.add_field(name="🎯 TP2 · +4%", value=f"```{_fmt_price(tp2)}```", inline=True)
    embed.add_field(name="🎯 TP3 · +7%", value=f"```{_fmt_price(tp3)}```", inline=True)

    # Indicators block
    if ind:
        macd_h  = ind.get("macd_hist", 0)
        bb_pct  = ind.get("bb_pct", 0)
        adx     = ind.get("adx", 0)
        ema50   = ind.get("ema50", 0)
        vwap    = ind.get("vwap", 0)
        ind_txt = (
            f"• RSI: `{rsi:.1f}`        • MACD hist: `{macd_h:+.4f}`\n"
            f"• BB %B: `{bb_pct:.2f}`   • ADX: `{adx:.1f}`\n"
            f"• EMA50: `{_fmt_price(ema50)}`  • VWAP: `{_fmt_price(vwap)}`"
        )
        embed.add_field(name="📊 Technical Indicators", value=ind_txt, inline=False)

    # Smart filters
    if filters:
        lines = []
        for name, status, detail in filters:
            mark = "✅" if status else "⚠️"
            lines.append(f"{mark} **{name}** — {detail}")
        if lines:
            embed.add_field(name="📋 Smart Filters", value="\n".join(lines), inline=False)

    if score is not None:
        bar_len = score // 5
        bar = "█" * bar_len + "░" * (20 - bar_len)
        embed.add_field(
            name=f"⭐ Quality Score — {score}/100",
            value=f"`{bar}`",
            inline=False,
        )

    if ai_text:
        embed.add_field(name="Trade Rationale", value=ai_text[:1000], inline=False)

    embed.set_footer(
        text=f"💎 VIP Signal • {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')} • Review risk before acting",
        icon_url="https://cdn-icons-png.flaticon.com/512/2331/2331970.png",
    )
    return embed
