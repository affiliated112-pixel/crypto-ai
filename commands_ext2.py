"""Second batch of extended commands: news, sentiment, multi-exchange, whales.
All free APIs, no keys.
"""
import discord
from discord import app_commands
import news
import exchanges
import whales


def register(tree, client):

    @tree.command(name="news", description="📰 Latest crypto news + sentiment (CryptoPanic free)")
    async def slash_news(interaction: discord.Interaction):
        await interaction.response.defer()
        items = news.cryptopanic_news(limit=10)
        if items and "error" in items[0]:
            await interaction.followup.send(f"❌ News API error: {items[0]['error']}")
            return
        lines = []
        for it in items[:8]:
            title = it["title"][:120]
            lines.append(f"{it['mood']} [{title}]({it['link']})")
        embed = discord.Embed(
            title="📰 Latest Crypto News",
            description="\n\n".join(lines) if lines else "No news right now.",
            color=0x3498DB,
        )
        embed.set_footer(text="🟢 Bullish · 🔴 Bearish · ⚪ Neutral · Source: CryptoPanic")
        await interaction.followup.send(embed=embed)

    @tree.command(name="sentiment", description="🧠 Aggregated market sentiment (News + Reddit)")
    async def slash_sentiment(interaction: discord.Interaction):
        await interaction.response.defer()
        s = news.aggregate_sentiment()
        embed = discord.Embed(
            title=f"{s['emoji']} Market Sentiment: {s['label']}",
            description=f"Combined score: **{s['total']:+d}** from {s['news_count']} news + {s['reddit_count']} Reddit posts",
            color=0x00C896 if s["total"] >= 0 else 0xE74C3C,
        )
        embed.add_field(name="📰 News Score", value=f"{s['news_score']:+d}", inline=True)
        embed.add_field(name="👽 Reddit Score", value=f"{s['reddit_score']:+d}", inline=True)
        embed.set_footer(text="Free sources: CryptoPanic + r/CryptoCurrency")
        await interaction.followup.send(embed=embed)

    @tree.command(name="compare", description="📊 Compare price across 6 exchanges (Binance/Bybit/OKX/KuCoin/Coinbase/Kraken)")
    @app_commands.describe(symbol="Trading pair, e.g. BTCUSDT, ETHUSDT, SOLUSDT")
    async def slash_compare(interaction: discord.Interaction, symbol: str = "BTCUSDT"):
        await interaction.response.defer()
        symbol = symbol.upper().strip()
        prices = exchanges.all_prices(symbol)
        ok = {k: v for k, v in prices.items() if v is not None}
        if not ok:
            await interaction.followup.send(f"❌ No exchange returned a price for `{symbol}`.")
            return
        lines = []
        for ex, p in sorted(ok.items(), key=lambda x: x[1]):
            lines.append(f"**{ex}:** `${p:,.4f}`".rstrip("0").rstrip("."))
        low = min(ok.values()); high = max(ok.values())
        spread = ((high - low) / low * 100) if low else 0
        embed = discord.Embed(
            title=f"📊 {symbol} — Cross-Exchange Prices",
            description="\n".join(lines),
            color=0x9B59B6,
        )
        embed.add_field(name="📉 Lowest", value=f"${low:,.4f}", inline=True)
        embed.add_field(name="📈 Highest", value=f"${high:,.4f}", inline=True)
        embed.add_field(name="🔀 Spread", value=f"{spread:.3f}%", inline=True)
        await interaction.followup.send(embed=embed)

    @tree.command(name="arbitrage", description="💱 Find biggest price spread across exchanges (arbitrage opportunity)")
    @app_commands.describe(symbol="Trading pair, e.g. BTCUSDT, ETHUSDT")
    async def slash_arbitrage(interaction: discord.Interaction, symbol: str = "BTCUSDT"):
        await interaction.response.defer()
        symbol = symbol.upper().strip()
        arb = exchanges.arbitrage(symbol)
        if not arb:
            await interaction.followup.send(f"❌ Not enough exchange data for `{symbol}`.")
            return
        embed = discord.Embed(
            title=f"💱 Arbitrage Opportunity — {symbol}",
            description=f"Spread: **{arb['spread_pct']:.3f}%**",
            color=0x00C896 if arb["spread_pct"] > 0.2 else 0xF39C12,
        )
        embed.add_field(name="📉 BUY on", value=f"**{arb['low_exchange']}**\n`${arb['low_price']:,.4f}`", inline=True)
        embed.add_field(name="📈 SELL on", value=f"**{arb['high_exchange']}**\n`${arb['high_price']:,.4f}`", inline=True)
        embed.set_footer(text="⚠️ Educational only — real arbitrage has fees, slippage, transfer time")
        await interaction.followup.send(embed=embed)

    @tree.command(name="whales", description="🐋 Top whale-driven volume movers (24h)")
    async def slash_whales(interaction: discord.Interaction):
        await interaction.response.defer()
        movers = whales.top_volume_movers(limit=8)
        if movers and "error" in movers[0]:
            await interaction.followup.send(f"❌ Error: {movers[0]['error']}")
            return
        if not movers:
            await interaction.followup.send("No whale activity detected right now.")
            return
        lines = []
        for m in movers:
            arrow = "📈" if m["change_pct"] >= 0 else "📉"
            vol_m = m["quote_volume"] / 1e6
            lines.append(
                f"{arrow} **{m['symbol']}** · `${m['price']:,.4f}` · `{m['change_pct']:+.2f}%` · Vol: `${vol_m:,.0f}M`"
            )
        embed = discord.Embed(
            title="🐋 Whale Activity — Top Volume Movers",
            description="\n".join(lines),
            color=0x1ABC9C,
        )
        embed.set_footer(text="Source: Binance.US 24h ticker · min $50M volume")
        await interaction.followup.send(embed=embed)

    @tree.command(name="stables", description="💵 Stablecoin flows (USDT, USDC, DAI...) — liquidity signal")
    async def slash_stables(interaction: discord.Interaction):
        await interaction.response.defer()
        flows = whales.stablecoin_flows()
        if flows and "error" in flows[0]:
            await interaction.followup.send(f"❌ Error: {flows[0]['error']}")
            return
        lines = []
        for s in flows[:8]:
            circ_b = s["circulating_usd"] / 1e9
            delta_m = s["change_24h_usd"] / 1e6
            arrow = "🟢" if delta_m >= 0 else "🔴"
            lines.append(
                f"{arrow} **{s['symbol']}** · `${circ_b:,.2f}B` · 24h: `{delta_m:+,.1f}M` (`{s['change_pct']:+.2f}%`)"
            )
        embed = discord.Embed(
            title="💵 Stablecoin Supply Flows (24h)",
            description="\n".join(lines),
            color=0x16A085,
        )
        embed.set_footer(text="Source: DefiLlama · Net inflows = more buying power")
        await interaction.followup.send(embed=embed)

    print("[ext2] Registered 6 extended commands: /news /sentiment /compare /arbitrage /whales /stables", flush=True)
