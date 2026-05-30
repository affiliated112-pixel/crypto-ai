"""REAL DATA loops — replace bot.py's unsupported performance/announcement/news loops.
All content is built from real tracker data + real free APIs. No hardcoded
unsupported stats. Required for legal safety (no false advertising).
"""
import asyncio
import discord
from datetime import datetime, timezone, timedelta
import tracker
try:
    import news as news_mod
except ImportError:
    news_mod = None
try:
    import feeds
except ImportError:
    feeds = None

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

async def post_legal_disclaimer(bot):
    """One-shot LEGAL DISCLAIMER posted in #announcements on bot start.
    Idempotent: checks last 50 messages of the channel and skips if a
    disclaimer with the same marker is already pinned/posted.
    """
    await bot.client.wait_until_ready()
    await asyncio.sleep(15)
    MARKER = "[CRYPTO-SIGNALS-LEGAL-DISCLAIMER-v1]"
    try:
        ch = await _get_channel(bot, "ANNOUNCEMENTS_CHANNEL")
        if ch is None:
            print("[disclaimer] ANNOUNCEMENTS_CHANNEL not set — skipping", flush=True)
            return
        # Check last 50 messages for the marker
        try:
            async for msg in ch.history(limit=50):
                if msg.author == bot.client.user and MARKER in (msg.content or ""):
                    print("[disclaimer] already posted — skipping", flush=True)
                    return
        except Exception as e:
            print(f"[disclaimer] history check failed: {e}", flush=True)

        embed_en = discord.Embed(
            title="⚖️ LEGAL DISCLAIMER — Please Read Before Using Signals",
            description=(
                "**🇬🇧 ENGLISH**\n\n"
                "This Discord server and the Crypto Signals Bot are an **educational and "
                "informational tool only**. Nothing posted here is financial advice, "
                "investment advice, or a recommendation to buy or sell any asset.\n\n"
                "**Key points you must understand:**\n"
                "• 📊 Signals are **algorithmic opinions** based on technical indicators "
                "(RSI, MACD, Bollinger Bands, EMA, ADX, Stochastic) calculated from "
                "live Binance market data.\n"
                "• ⚠️ **No signal guarantees profit.** Past performance does not predict "
                "future results.\n"
                "• 💸 Cryptocurrency trading is **highly volatile and risky** — you can "
                "lose all the money you invest.\n"
                "• 📋 Always **do your own research (Review risk before acting)** before making any trade.\n"
                "• 🛑 **Use Stop Loss** on every trade. Risk only what you can afford "
                "to lose (1–2% of portfolio per trade is a common rule).\n"
                "• 🚫 The bot operator(s) are **not licensed financial advisors** and "
                "are not responsible for any losses you incur.\n"
                "• 📈 All performance numbers shown in `#performance` are **calculated "
                "from real signals the bot sent**, tracked against real Binance prices. "
                "No marketing or hypothetical numbers are posted."
            ),
            color=0xE67E22,
            timestamp=datetime.now(timezone.utc),
        )
        embed_en.set_footer(text=f"Educational only • Not financial advice • {MARKER}")

        embed_ro = discord.Embed(
            title="⚖️ DISCLAIMER LEGAL — Citește înainte de a folosi semnalele",
            description=(
                "**🇷🇴 ROMÂNĂ**\n\n"
                "Acest server Discord și Crypto Signals Bot sunt un **instrument educațional "
                "și informațional**. Nimic din ce e postat aici nu reprezintă sfat "
                "financiar, sfat de investiție sau recomandare de a cumpăra sau vinde "
                "vreun activ.\n\n"
                "**Puncte esențiale pe care trebuie să le înțelegi:**\n"
                "• 📊 Semnalele sunt **opinii algoritmice** bazate pe indicatori "
                "tehnici (RSI, MACD, Bollinger Bands, EMA, ADX, Stochastic) calculate "
                "din date Binance live.\n"
                "• ⚠️ **Niciun semnal nu garantează profit.** Performanța trecută NU "
                "prezice rezultate viitoare.\n"
                "• 💸 Tranzacționarea cripto este **extrem de volatilă și riscantă** — "
                "poți pierde toți banii investiți.\n"
                "• 📋 Fă-ți **întotdeauna propria cercetare (Review risk before acting)** înainte de a face "
                "vreun trade.\n"
                "• 🛑 **Folosește Stop Loss** la fiecare tranzacție. Riscă doar bani "
                "pe care îți poți permite să-i pierzi (1–2% din portofoliu per trade).\n"
                "• 🚫 Operatorul botului **NU este consilier financiar autorizat** și "
                "nu este responsabil pentru pierderile tale.\n"
                "• 📈 Toate cifrele din `#performance` sunt **calculate din semnale "
                "reale trimise de bot**, urmărite pe prețuri Binance reale. Nu se "
                "postează niciun număr de marketing sau ipotetic."
            ),
            color=0xE67E22,
            timestamp=datetime.now(timezone.utc),
        )
        embed_ro.set_footer(text=f"Doar educațional • Nu e sfat financiar • {MARKER}")

        msg1 = await ch.send(content=MARKER, embed=embed_en)
        await ch.send(embed=embed_ro)
        # Try to pin it (requires Manage Messages permission)
        try:
            await msg1.pin(reason="Legal disclaimer for crypto signals bot")
            print("[disclaimer] posted + pinned in #announcements", flush=True)
        except Exception as e:
            print(f"[disclaimer] posted (pin skipped: {e})", flush=True)
    except Exception as e:
        print(f"[disclaimer] error: {e}", flush=True)

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
                    # No signals yet — honest, no unsupported
                    embed = discord.Embed(
                        title="📊 Daily Performance — No signals yet",
                        description=(
                            "⏳ Bot is still gathering signals. Real stats will appear here "
                            "once we have closed trades.\n\n"
                            "🔍 All data is real — tracked data only, no marketing fluff."
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
                    text="🔍 Live tracker data • Use /stats and /history for live numbers • Not financial advice"
                )
                await ch.send(embed=embed)
        except Exception as e:
            print(f"[real_performance] error: {e}", flush=True)
        await asyncio.sleep(interval)

async def real_market_news_loop(bot, interval=1800):
    """Posts REAL crypto news from public RSS/CoinGecko sources — NOT random hardcoded text."""
    await bot.client.wait_until_ready()
    await asyncio.sleep(60)
    last_posted = set()
    while True:
        try:
            ch = await _get_channel(bot, "MARKET_NEWS_CHANNEL")
            if ch:
                if news_mod:
                    items = await asyncio.to_thread(news_mod.fetch_news, 5)
                else:
                    items = []
                fresh = [it for it in items if it.get("link") and it["link"] not in last_posted]
                if fresh:
                    item = fresh[0]
                    last_posted.add(item["link"])
                    if len(last_posted) > 100:
                        last_posted = set(list(last_posted)[-50:])
                    mood  = item.get("mood", "⚪")
                    emoji = item.get("emoji", "📰")
                    src   = item.get("source", "Multi-source RSS")
                    mood_color = {
                        "🟢": 0x00C896, "🔴": 0xE74C3C, "⚪": 0x95A5A6,
                    }.get(mood, 0x3498DB)
                    summary = item.get("summary", "")
                    embed = discord.Embed(
                        title=f"{emoji} {item['title'][:200]}",
                        url=item["link"],
                        description=(
                            f"{mood} Sentiment | Source: **{src}**\n"
                            + (f"\n{summary}\n" if summary else "")
                            + f"\n🔗 [Read full article]({item['link']})"
                        ),
                        color=mood_color,
                        timestamp=datetime.now(timezone.utc),
                    )
                    embed.set_footer(
                        text="📡 CoinDesk · Decrypt · Bitcoin Magazine · CryptoSlate · CoinGecko — public news feeds"
                    )
                    await ch.send(embed=embed)
        except Exception as e:
            print(f"[real_news] error: {e}", flush=True)
        await asyncio.sleep(interval)

async def real_announcement_loop(bot, interval=86400):
    """Honest announcements — NO unsupported 87% win rate claims.
    First item is always the LEGAL DISCLAIMER so it cycles into view daily.
    """
    await bot.client.wait_until_ready()
    await asyncio.sleep(120)
    items = [
        (
            "⚖️ Disclaimer — Not Financial Advice / Nu e sfat financiar",
            "🇬🇧 This bot is an **educational tool only**. Signals are algorithmic "
            "opinions based on technical indicators — **NOT financial advice**. "
            "Past performance does not predict future results. Crypto is volatile — "
            "you can lose money. Always Review risk before acting and use Stop Loss.\n\n"
            "🇷🇴 Acest bot este un **instrument educațional**. Semnalele sunt opinii "
            "algoritmice bazate pe indicatori tehnici — **NU e sfat financiar**. "
            "Performanța trecută nu garantează rezultate viitoare. Crypto e volatil — "
            "poți pierde bani. Fă-ți Review risk before acting și folosește Stop Loss."
        ),
        (
            "💡 How to use signals safely / Cum să folosești semnalele în siguranță",
            "🇬🇧 Every signal includes Entry, Stop Loss, TP1/TP2/TP3. "
            "ALWAYS set Stop Loss before entering. Max 1–2% of portfolio per trade.\n\n"
            "🇷🇴 Fiecare semnal include Entry, Stop Loss, TP1/TP2/TP3. "
            "ÎNTOTDEAUNA pune Stop Loss înainte de intrare. Maxim 1–2% portofoliu per trade."
        ),
        (
            "🔍 Live public data — no unsupported stats / Date live publice, fără statistici inventate",
            "🇬🇧 All signals are calculated from live Binance candles using RSI, MACD, "
            "Bollinger Bands, EMA, VWAP, ADX, Stochastic. Smart filter uses Fear & Greed, "
            "real news sentiment, cross-exchange validation. Use `/stats` to see real win rate.\n\n"
            "🇷🇴 Toate semnalele sunt calculate din lumânări Binance live. Folosește `/stats` "
            "pentru a vedea win rate-ul real."
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
                embed.set_footer(text="📚 Educational only • Live public data • Review risk before acting • Not financial advice")
                await ch.send(embed=embed)
            i += 1
        except Exception as e:
            print(f"[real_announcement] error: {e}", flush=True)
        await asyncio.sleep(interval)
