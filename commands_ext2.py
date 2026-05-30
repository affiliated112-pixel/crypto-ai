"""Second batch of real-data slash commands: news, sentiment, exchange prices,
volume movers and stablecoin flows.

The safe default keeps existing commands unless replace_existing=True is passed.
"""
from __future__ import annotations

import discord
from discord import app_commands

import news
import exchanges
import whales

OWN_COMMANDS = ["news", "sentiment", "compare", "arbitrage", "whales", "stables"]


def _existing_names(tree) -> set[str]:
    try:
        return {cmd.name for cmd in tree.get_commands()}
    except Exception:
        return set()


def _remove_existing(tree, names: list[str]) -> list[str]:
    removed: list[str] = []
    for name in names:
        try:
            old = tree.remove_command(name)
            if old is not None:
                removed.append(name)
        except Exception:
            pass
    return removed


def register(tree, client, replace_existing: bool = False):
    if replace_existing:
        removed = _remove_existing(tree, OWN_COMMANDS)
        if removed:
            print(f"[ext2] Replaced existing commands: {', '.join(removed)}", flush=True)

    existing = _existing_names(tree)
    registered: list[str] = []
    skipped: list[str] = []

    def enabled(name: str) -> bool:
        if name in existing:
            skipped.append(name)
            return False
        registered.append(name)
        return True

    if enabled("news"):
        @tree.command(name="news", description="📰 Latest crypto news from public RSS/CoinGecko sources")
        async def slash_news(interaction: discord.Interaction):
            await interaction.response.defer()
            items = news.fetch_news(limit=10)
            if items and "error" in items[0]:
                await interaction.followup.send(f"❌ News error: {items[0]['error']}")
                return
            lines = []
            for it in items[:8]:
                title = str(it.get("title", "Untitled"))[:120]
                mood = it.get("mood", "⚪")
                source = it.get("source", "source")
                link = it.get("link", "")
                if link:
                    lines.append(f"{mood} [{title}]({link}) — `{source}`")
                else:
                    lines.append(f"{mood} **{title}** — `{source}`")
            embed = discord.Embed(
                title="📰 Latest Crypto News",
                description="\n\n".join(lines) if lines else "No fresh news returned right now.",
                color=0x3498DB,
            )
            embed.set_footer(text="Mood is keyword-based: 🟢 bullish · 🔴 bearish · ⚪ neutral · Sources: public RSS/CoinGecko")
            await interaction.followup.send(embed=embed)

    if enabled("sentiment"):
        @tree.command(name="sentiment", description="📋 Real market sentiment from news + public Reddit when available")
        async def slash_sentiment(interaction: discord.Interaction):
            await interaction.response.defer()
            s = news.aggregate_sentiment()
            total = int(s.get("total", 0))
            embed = discord.Embed(
                title=f"{s.get('emoji','⚪')} Market Sentiment: {s.get('label','Neutral')}",
                description=(
                    f"Combined score: **{total:+d}** from **{s.get('news_count', 0)}** fetched headlines "
                    f"+ **{s.get('reddit_count', 0)}** Reddit posts.\n"
                    "This is a transparent keyword snapshot, not a prediction."
                ),
                color=0x00C896 if total >= 0 else 0xE74C3C,
            )
            embed.add_field(name="📰 News Score", value=f"{int(s.get('news_score', 0)):+d}", inline=True)
            embed.add_field(name="👽 Reddit Score", value=f"{int(s.get('reddit_score', 0)):+d}", inline=True)
            embed.add_field(name="⚪ Neutral Headlines", value=str(s.get("neutral", 0)), inline=True)
            embed.set_footer(text=f"Sources: {s.get('source', 'public feeds')} · best-effort live snapshot")
            await interaction.followup.send(embed=embed)

    if enabled("compare"):
        @tree.command(name="compare", description="📊 Compare live price across public exchange APIs")
        @app_commands.describe(symbol="Trading pair, e.g. BTCUSDT, ETHUSDT, SOLUSDT")
        async def slash_compare(interaction: discord.Interaction, symbol: str = "BTCUSDT"):
            await interaction.response.defer()
            symbol = symbol.upper().strip()
            prices = exchanges.all_prices(symbol)
            ok = {k: v for k, v in prices.items() if v is not None}
            if not ok:
                await interaction.followup.send(f"❌ No exchange returned a price for `{symbol}`.")
                return
            lines = [f"**{ex}:** `${p:,.4f}`".rstrip("0").rstrip(".") for ex, p in sorted(ok.items(), key=lambda x: x[1])]
            low = min(ok.values())
            high = max(ok.values())
            spread = ((high - low) / low * 100) if low else 0
            embed = discord.Embed(
                title=f"📊 {symbol} — Cross-Exchange Prices",
                description="\n".join(lines),
                color=0x9B59B6,
            )
            embed.add_field(name="📉 Lowest", value=f"${low:,.4f}".rstrip("0").rstrip("."), inline=True)
            embed.add_field(name="📈 Highest", value=f"${high:,.4f}".rstrip("0").rstrip("."), inline=True)
            embed.add_field(name="🔀 Spread", value=f"{spread:.3f}%", inline=True)
            embed.set_footer(text="Public exchange APIs; prices can differ by fees, liquidity and quote currency")
            await interaction.followup.send(embed=embed)

    if enabled("arbitrage"):
        @tree.command(name="arbitrage", description="💱 Show biggest exchange spread for a pair (educational)")
        @app_commands.describe(symbol="Trading pair, e.g. BTCUSDT, ETHUSDT")
        async def slash_arbitrage(interaction: discord.Interaction, symbol: str = "BTCUSDT"):
            await interaction.response.defer()
            symbol = symbol.upper().strip()
            arb = exchanges.arbitrage(symbol)
            if not arb:
                await interaction.followup.send(f"❌ Not enough exchange data for `{symbol}`.")
                return
            embed = discord.Embed(
                title=f"💱 Exchange Spread — {symbol}",
                description=f"Spread: **{arb['spread_pct']:.3f}%**",
                color=0x00C896 if arb["spread_pct"] > 0.2 else 0xF39C12,
            )
            embed.add_field(name="📉 Lowest price", value=f"**{arb['low_exchange']}**\n`${arb['low_price']:,.4f}`", inline=True)
            embed.add_field(name="📈 Highest price", value=f"**{arb['high_exchange']}**\n`${arb['high_price']:,.4f}`", inline=True)
            embed.set_footer(text="Educational only — real arbitrage includes fees, slippage, liquidity and transfer time")
            await interaction.followup.send(embed=embed)

    if enabled("whales"):
        @tree.command(name="whales", description="🐋 Top high-volume crypto movers from public market data")
        async def slash_whales(interaction: discord.Interaction):
            await interaction.response.defer()
            movers = whales.top_volume_movers(limit=8)
            if movers and "error" in movers[0]:
                await interaction.followup.send(f"❌ Error: {movers[0]['error']}")
                return
            if not movers:
                await interaction.followup.send("No high-volume movers detected right now.")
                return
            lines = []
            for m in movers:
                arrow = "📈" if m["change_pct"] >= 0 else "📉"
                vol_m = m["quote_volume"] / 1e6
                lines.append(f"{arrow} **{m['symbol']}** · `${m['price']:,.4f}` · `{m['change_pct']:+.2f}%` · Vol: `${vol_m:,.0f}M`")
            embed = discord.Embed(
                title="🐋 High-Volume Movers",
                description="\n".join(lines),
                color=0x1ABC9C,
            )
            embed.set_footer(text="Source: public Binance 24h ticker endpoint · volume is a proxy, not proof of one whale")
            await interaction.followup.send(embed=embed)

    if enabled("stables"):
        @tree.command(name="stables", description="💵 Stablecoin supply flows from DeFiLlama")
        async def slash_stables(interaction: discord.Interaction):
            await interaction.response.defer()
            flows = whales.stablecoin_flows()
            if flows and "error" in flows[0]:
                await interaction.followup.send(f"❌ Error: {flows[0]['error']}")
                return
            lines = []
            for s in flows[:8]:
                circ_b = float(s["circulating_usd"]) / 1e9
                delta_m = float(s["change_24h_usd"]) / 1e6
                arrow = "🟢" if delta_m >= 0 else "🔴"
                lines.append(f"{arrow} **{s['symbol']}** · `${circ_b:,.2f}B` · 24h: `{delta_m:+,.1f}M` (`{s['change_pct']:+.2f}%`)")
            embed = discord.Embed(
                title="💵 Stablecoin Supply Flows",
                description="\n".join(lines) if lines else "No stablecoin flow data returned right now.",
                color=0x16A085,
            )
            embed.set_footer(text="Source: DeFiLlama stablecoins endpoint · Educational only")
            await interaction.followup.send(embed=embed)

    if skipped:
        print(f"[ext2] Kept existing commands: {', '.join(sorted(set(skipped)))}", flush=True)
    if registered:
        print(f"[ext2] Registered commands: {', '.join(registered)}", flush=True)
