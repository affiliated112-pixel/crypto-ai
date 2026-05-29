"""commands_paper.py — Admin-only slash commands for Paper Trading.
/paper        — show live portfolio
/paper_reset  — reset paper trading (admin only)
/paper_trades — show last 10 closed trades
"""
import os
import discord
from discord import app_commands
import paper_trading

ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()]

def is_admin(interaction: discord.Interaction) -> bool:
    if ADMIN_IDS and interaction.user.id in ADMIN_IDS:
        return True
    if interaction.user.guild_permissions.administrator:
        return True
    return False

def register(tree: app_commands.CommandTree):

    @tree.command(name="paper", description="📊 Admin: Live paper trading portfolio")
    async def paper_cmd(interaction: discord.Interaction):
        if not is_admin(interaction):
            await interaction.response.send_message(
                "🔒 This command is for admins only.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        stats = paper_trading.get_stats()
        embed = paper_trading.build_portfolio_embed(stats)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @tree.command(name="paper_reset", description="🔄 Admin: Reset paper trading portfolio")
    @app_commands.describe(balance="Starting balance in USD (default 5.0)")
    async def paper_reset_cmd(interaction: discord.Interaction, balance: float = 5.0):
        if not is_admin(interaction):
            await interaction.response.send_message(
                "🔒 This command is for admins only.", ephemeral=True
            )
            return
        paper_trading.reset(starting_balance=balance)
        await interaction.response.send_message(
            f"✅ Paper trading reset! Starting with **${balance:.2f}** virtual.", ephemeral=True
        )

    @tree.command(name="paper_trades", description="📋 Admin: Last 10 closed paper trades")
    async def paper_trades_cmd(interaction: discord.Interaction):
        if not is_admin(interaction):
            await interaction.response.send_message(
                "🔒 This command is for admins only.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        data = paper_trading._load()
        closed = list(reversed(data.get("closed_trades", [])))[:10]
        if not closed:
            await interaction.followup.send("📭 No closed trades yet.", ephemeral=True)
            return

        lines = []
        for t in closed:
            p = t["pnl_pct"]
            s = "+" if p >= 0 else ""
            e = "✅" if p >= 0 else "❌"
            lines.append(
                f"{e} **{t['symbol']}** {t['direction']} "
                f"@ `${t['entry']:.2f}` → `${t['close_price']:.2f}` "
                f"| `{s}{p:.2f}%` | {t['close_reason']}"
            )

        embed = discord.Embed(
            title="📋 Last 10 Closed Paper Trades",
            description="\n".join(lines),
            color=0x3498DB,
        )
        embed.set_footer(text="Paper Trading • Admin only • Not financial advice")
        await interaction.followup.send(embed=embed, ephemeral=True)
