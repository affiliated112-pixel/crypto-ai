"""Grouped /help command for the real-data Discord crypto bot.

This replaces the large legacy help embed with compact, accurate command groups.
It only lists commands that exist in bot.py or in the optional modules loaded by
bot_extended.py / _register_optional_command_modules().
"""
from __future__ import annotations

from datetime import datetime, timezone

import discord

OWN_COMMANDS = ["help"]


def register(tree, client):
    removed = []
    for name in OWN_COMMANDS:
        try:
            old = tree.remove_command(name)
            if old is not None:
                removed.append(name)
        except Exception:
            pass
    if removed:
        print(f"[help-cmd] Replaced existing: {', '.join(removed)}", flush=True)

    @tree.command(name="help", description="📖 List all commands grouped by category")
    async def slash_help(interaction: discord.Interaction):
        embed = discord.Embed(
            title="🤖 Crypto Signals Bot — Commands",
            description="Type `/` in Discord to run a command. Stats and signals use tracked/live public data only.",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )

        embed.add_field(
            name="📊 Market Data",
            value=(
                "`/price` · `/coin` · `/chart` · `/rsi`\n"
                "`/compare` · `/arbitrage` · `/dominance` · `/tvl`\n"
                "`/trending` · `/heatmap` · `/fear`"
            ),
            inline=False,
        )

        embed.add_field(
            name="🎯 Signals & Analysis",
            value=(
                "`/signal` · `/analysis` · `/multi` · `/advanced`\n"
                "`/fibonacci` · `/smartmoney` · `/ichimoku` · `/vwap` · `/atr`\n"
                "`/signals_explained` · `/backtest`"
            ),
            inline=False,
        )

        embed.add_field(
            name="🔔 Alerts, Watchlist & Community",
            value=(
                "`/alert` · `/myalerts` · `/removealert`\n"
                "`/watch` · `/unwatch` · `/mywatchlist`\n"
                "`/predict` · `/leaderboard`"
            ),
            inline=False,
        )

        embed.add_field(
            name="📈 Real Performance Tracking",
            value=(
                "`/stats` — win rate/P&L from tracked TP/SL outcomes\n"
                "`/history` — last tracked signals and results"
            ),
            inline=False,
        )

        embed.add_field(
            name="💼 Portfolio & Paper/Demo",
            value=(
                "`/portfolio` · `/journal` · `/risk` · `/calculate`\n"
                "`/paper` · `/paper_reset` · `/paper_trades`"
            ),
            inline=False,
        )

        embed.add_field(
            name="🧠 News, Sentiment & Flows",
            value=(
                "`/news` · `/sentiment` · `/whales` · `/stables`"
            ),
            inline=False,
        )

        embed.add_field(
            name="📚 Learning",
            value=(
                "`/tutorial` · `/glossary` · `/tip` · `/firsttrade` · `/binance`"
            ),
            inline=False,
        )

        embed.add_field(
            name="🪙 Coin Subscriptions",
            value="`/subscribe` · `/mysignals` · `/unsubscribe`",
            inline=False,
        )

        embed.add_field(
            name="🔧 Admin / Auto-Trade",
            value=(
                "`/clear` · `/purge`\n"
                "`/trade_status` · `/trade_pnl` · `/trade_close` · `/trade_start` · `/trade_stop` · `/trade_risk`"
            ),
            inline=False,
        )

        embed.set_footer(
            text="Educational only — not financial advice. No guaranteed profit. DYOR.",
            icon_url="https://cdn-icons-png.flaticon.com/512/2331/2331970.png",
        )
        await interaction.response.send_message(embed=embed)

    print("[help-cmd] Registered /help (accurate grouped list)", flush=True)
