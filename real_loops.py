"""REAL DATA loops — replace bot.py's fake performance/announcement/news loops.
All content is built from real tracker data + real free APIs. No hardcoded
fake stats. Required for legal safety (no false advertising).
"""
import asyncio
import discord
from datetime import datetime, timezone, timedelta
import tracker
import feeds
import news as news_mod

# Channels are read live from the bot module at runtime.


def _fmt_pnl(pct):
    if pct > 0: return f"+{pct:.2f}%"
    return f"{pct:.2f}%"


async def _get_channel(bot, attr):
    cid = getattr(bot, attr, None)
    if not cid: return None
    ch = bot.client.get_channel(cid)
    if ch is None:
        try:
            ch = await bot.client.fetch_channel(cid)
        except Exception:
            ch = None
    return ch


async def real_performance_loop(bot, interval=86400):
    """Posts REAL daily performance from tracker.py data — NOT hardcoded."""
    await bot.client.wait_until_ready()
    # Wait 30 sec so other startup is done
    await asyncio.sleep(30)
    while True:
        try:
            ch = await _get_channel(bot, "PERFORMANCE_CHANNEL")
            if ch:
                s = tracker.compute_stats(days=1)  # last 24h
                s7 = tracker.compute_stats(days=7)  # last 7d

                if s.get("total", 0) == 0 and s7.get("total", 0) == 0:
                    # No signals yet — honest, no fake
                    embed = discord.Embed(
                        title="📊 Daily Performance — No signals yet",
                        description=(
                            "⏳ Bot is still gathering signals. Real stats will appear here "
                            "once we have closed trades.\n\n"
                            "🔍 All data is real — no fake numbers, no marketing fluff."
                        ),
                        color=0x95A5A6,
                        timestamp=datetime.now(timezone.utc),
                    )
                else:
                    color = 0x00C896 if s7.get("win_rate", 0) >= 50 else 0xE74C3C
                    embed = discord.Embed(
                        title="📊 Daily Performance — REAL DATA",
                        description=(
                            "🔍 **All stats below come from actual signals the bot sent**, "
                            "tracked in real-time against live Binance prices."
                        ),
                        color=color,
                        timestamp=datetime.now(timezone.utc),
                    )
                    embed.add_field(
                        name="📅 Last 24 hours",
                        value=(
                            f"✅ Wins: `{s.get('wins', 0)}`  ❌ Losses: `{s.get('losses', 0)}`\n"
                            f"🎯 TP hits: `{s.get('tp1', 0)}` / `{s.get('tp2', 0)}` / `{s.get('tp3', 0)}`\n"
                            f"⚖️ Win rate: `{s.get('win_rate', 0):.1f}%`\n"
                            f"📊 Avg P&L: `{_fmt_pnl(s.get('avg_pnl', 0))}`"
                        ),
                        inline=False,
                    )
                    embed.add_field(
                        name="📆 Last 7 days",
                        value=(
                            f"✅ Wins: `{s7.get('wins', 0)}`  ❌ Losses: `{s7.get('losses', 0)}`\n"
                            f"⚖️ Win rate: `{s7.get('win_rate', 0):.1f}%`\n"
                            f"📊 Avg P&L: `{_fmt_pnl(s7.get('avg_pnl', 0))}`\n"
                            f"⏳ Open: `{s7.get('open', 0)}`  🕒 Expired: `{s7.get('expired', 0)}`"
                        ),
                        inline=False,
                    )
                    bq = s7.get("by_quality", {})
                    if bq:
                        lines = []
                        for q, d in sorted(bq.items()):
                            total = d["w"] + d["l"]
                            wr = (d["w"] / total * 100) if total else 0
                            lines.append(f"• **{q}**: `{d['w']}W / {d['l']}L` — `{wr:.0f}%` win rate")
                        embed.add_field(name="⭐ By Quality", value="\n".join(lines), inline=False)

                embed.set_footer(
                    text="🔍 100% real tracker data • Use /stats and /history for live numbers"
                )
                await ch.send(embed=embed)
        except Exception as e:
            print(f"[real_performance] error: {e}", flush=True)
        await asyncio.sleep(interval)


async def real_market_news_loop(bot, interval=1800):
    """Posts REAL crypto news from CryptoPanic — NOT random hardcoded text."""
    await bot.client.wait_until_ready()
    await asyncio.sleep(60)
    last_posted = set()
    while True:
        try:
            ch = await _get_channel(bot, "MARKET_NEWS_CHANNEL")
            if ch:
                items = await asyncio.to_thread(news_mod.cryptopanic_news, limit=5)
                if items and "error" in items[0]:
                    print(f"[real_news] api error: {items[0]['error']}", flush=True)
                else:
                    # Pick first item we haven't posted recently
                    fresh = [it for it in items if it.get("link") and it["link"] not in last_posted]
                    if fresh:
                        item = fresh[0]
                        last_posted.add(item["link"])
                        if len(last_posted) > 100:
                            last_posted = set(list(last_posted)[-50:])
                        mood_color = {
                            "🟢": 0x00C896, "🔴": 0xE74C3C, "⚪": 0x95A5A6,
                        }.get(item.get("mood", "⚪"), 0x3498DB)
                        embed = discord.Embed(
                            title=f"{item.get('mood', '📰')} {item['title'][:200]}",
                            url=item["link"],
                            description=(
                                f"🔗 [Read full article]({item['link']})\n\n"
                                f"🔍 **Source:** CryptoPanic API (free, real-time)"
                            ),
                            color=mood_color,
                            timestamp=datetime.now(timezone.utc),
                        )
                        embed.set_footer(
                            text="🟢 Bullish • 🔴 Bearish • ⚪ Neutral • 100% real news, no fake content"
                        )
                        await ch.send(embed=embed)
        except Exception as e:
            print(f"[real_news] error: {e}", flush=True)
        await asyncio.sleep(interval)


async def real_announcement_loop(bot, interval=86400):
    """Honest announcements — NO fake 87% win rate claims."""
    await bot.client.wait_until_ready()
    await asyncio.sleep(120)
    items = [
        (
            "💡 How to use signals safely",
            "🇬🇧 Every signal includes Entry, Stop Loss, TP1/TP2/TP3. "
            "ALWAYS set Stop Loss before entering. Max 5% portfolio per trade.\n\n"
            "🇷🇴 Fiecare semnal include Entry, Stop Loss, TP1/TP2/TP3. "
            "ÎNTOTDEAUNA pune Stop Loss înainte de intrare. Maxim 5% portofoliu per trade."
        ),
        (
            "🔍 100% real data — no fake stats",
            "🇬🇧 All signals are calculated from live Binance candles using RSI, MACD, "
            "Bollinger Bands, EMA, VWAP, ADX, Stochastic. Smart filter uses Fear & Greed, "
            "real news sentiment, cross-exchange validation. Use `/stats` to see real win rate.\n\n"
            "🇷🇴 Toate semnalele sunt calculate din lumânări Binance live. Folosește `/stats` "
            "pentru a vedea win rate-ul real."
        ),
        (
            "⚠️ Educational tool — not financial advice",
            "🇬🇧 This bot is an educational tool. It does NOT guarantee profit. "
            "Crypto is volatile — you can lose money. Do your own research. Past performance "
            "does not predict future results.\n\n"
            "🇷🇴 Acest bot este un instrument educațional. NU garantează profit. "
            "Crypto e volatil — poți pierde bani. Fă-ți propria cercetare."
        ),
        (
            "📊 Useful commands to explore the bot",
            "`/stats` real win rate • `/history` last 10 signals • `/fear` Fear & Greed Index • "
            "`/news` latest news • `/coin <name>` price for any coin • `/compare` 6-exchange prices • "
            "`/sentiment` aggregated News + Reddit • `/help` full command list"
        ),
    ]
    i = 0
    while True:
        try:
            ch = await _get_channel(bot, "ANNOUNCEMENTS_CHANNEL")
            if ch:
                title, desc = items[i % len(items)]
                embed = discord.Embed(
                    title=title, description=desc,
                    color=0x3498DB,
                    timestamp=datetime.now(timezone.utc),
                )
                embed.set_footer(text="📚 Educational only • 100% real data • DYOR")
                await ch.send(embed=embed)
            i += 1
        except Exception as e:
            print(f"[real_announcement] error: {e}", flush=True)
        await asyncio.sleep(interval)
