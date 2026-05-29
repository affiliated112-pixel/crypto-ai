"""Overrides bot.py's /help command. The original built an embed with one
field per slash command and after we added 13 more commands it crossed the
Discord limit of 25 fields, throwing HTTPException 400.

This version groups commands into 6 categories — well under the limit and
much easier to read.
"""
import discord
from discord import app_commands
from datetime import datetime, timezone

OWN_COMMANDS = ["help"]


def register(tree, client):
    removed = []
    for n in OWN_COMMANDS:
        try:
            old = tree.remove_command(n)
            if old is not None: removed.append(n)
        except Exception: pass
    if removed:
        print(f"[help-cmd] Replaced existing: {', '.join(removed)}", flush=True)

    @tree.command(name="help", description="📖 List all commands grouped by category")
    async def slash_help(interaction: discord.Interaction):
        embed = discord.Embed(
            title="🤖 Crypto Signals Bot — All Commands",
            description="All commands are slash commands — type `/` to see them in Discord.",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )

        embed.add_field(
            name="📊 Market Data",
            value=(
                "`/coin <name>` — price for any of 300+ coins\n"
                "`/compare <pair>` — price on 6 exchanges\n"
                "`/arbitrage <pair>` — biggest spread (arbitrage)\n"
                "`/trending` — top 7 trending on CoinGecko\n"
                "`/dominance` — BTC/ETH dominance + global mcap\n"
                "`/tvl` — total DeFi Value Locked"
            ),
            inline=False,
        )

        embed.add_field(
            name="🧠 Sentiment & News",
            value=(
                "`/fear` — Fear & Greed Index 0-100\n"
                "`/news` — latest crypto news with sentiment\n"
                "`/sentiment` — aggregated News + Reddit score\n"
                "`/whales` — top volume movers (whale activity)\n"
                "`/stables` — stablecoin supply flows"
            ),
            inline=False,
        )

        embed.add_field(
            name="📈 Bot Performance",
            value=(
                "`/stats` — win rate, P&L, breakdown by quality\n"
                "`/history` — last 10 signals with results"
            ),
            inline=False,
        )

        embed.add_field(
            name="💼 Portfolio & Paper Trading",
            value=(
                "`/portfolio add/view/pnl/clear` — personal portfolio tracker\n"
                "`/paper buy/sell/balance` — paper trading with virtual money\n"
                "`/predict <coin> <direction>` — predict price movement"
            ),
            inline=False,
        )

        embed.add_field(
            name="🎯 Signals & Analysis",
            value=(
                "`/signal <coin>` — get current signal for a coin\n"
                "`/chart <coin>` — generate technical chart\n"
                "`/explain <coin>` — AI-powered signal explanation\n"
                "`/setalert <coin> <price>` — personal price alert"
            ),
            inline=False,
        )

        embed.add_field(
            name="📚 Learning",
            value=(
                "`/tutorial` — 5-part beginner trading tutorial\n"
                "`/term <word>` — explain a crypto/trading term\n"
                "`/binance` — guide to using Binance.US safely"
            ),
            inline=False,
        )

        embed.add_field(
            name="🔧 Admin (owners only)",
            value=(
                "`/clear <amount>` — delete last N messages\n"
                "`/purge <amount>` — alias for /clear"
            ),
            inline=False,
        )

        embed.set_footer(
            text="📊 Signals every 5 min · ⚠️ Educational only — not financial advice · DYOR",
            icon_url="https://cdn-icons-png.flaticon.com/512/2331/2331970.png",
        )
        await interaction.response.send_message(embed=embed)

    print("[help-cmd] Registered /help (grouped, 7 categories)", flush=True)
