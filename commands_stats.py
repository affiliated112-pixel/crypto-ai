"""/stats and /history commands powered by tracker.py."""
import discord
from discord import app_commands
from datetime import datetime, timezone
import tracker

OWN_COMMANDS = ["stats", "history"]


def register(tree, client):
    removed = []
    for n in OWN_COMMANDS:
        try:
            old = tree.remove_command(n)
            if old is not None: removed.append(n)
        except Exception: pass
    if removed:
        print(f"[stats-cmd] Replaced existing: {', '.join(removed)}", flush=True)

    @tree.command(name="stats", description="📈 Bot performance — real win rate from tracked signals")
    @app_commands.describe(symbol="Filter by coin (optional, e.g. BTCUSDT)", days="Filter by last N days (optional)")
    async def slash_stats(interaction: discord.Interaction, symbol: str = None, days: int = None):
        await interaction.response.defer()
        s = tracker.compute_stats(symbol=symbol, days=days)
        if s["total"] == 0:
            await interaction.followup.send("📍 No signals tracked yet. Wait for the bot to send a few signals.")
            return
        if s.get("closed", 0) == 0:
            await interaction.followup.send(
                f"⏳ Tracking **{s['open']}** open signal(s). No closed signals yet — stats available once TP/SL is hit."
            )
            return
        title = "📈 Bot Performance"
        if symbol: title += f" — {symbol.upper()}"
        if days: title += f" (last {days}d)"
        win_rate = s["win_rate"]
        color = 0x00D26A if win_rate >= 55 else (0xF1C40F if win_rate >= 45 else 0xED4245)
        bar_len = int(win_rate / 5)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        embed = discord.Embed(
            title=title,
            description=f"**Win Rate:** `{win_rate:.1f}%`\n`{bar}`",
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="✅ Wins (TP1+)", value=f"`{s['wins']}`", inline=True)
        embed.add_field(name="❌ Losses (SL)", value=f"`{s['losses']}`", inline=True)
        embed.add_field(name="⚖️ Avg P&L", value=f"`{s['avg_pnl']:+.2f}%`", inline=True)
        embed.add_field(name="🎯 TP1 hit", value=f"`{s['tp1']}`", inline=True)
        embed.add_field(name="🎯 TP2 hit", value=f"`{s['tp2']}`", inline=True)
        embed.add_field(name="🎯 TP3 hit", value=f"`{s['tp3']}`", inline=True)
        embed.add_field(name="⏳ Open", value=f"`{s['open']}`", inline=True)
        embed.add_field(name="🕒 Expired", value=f"`{s['expired']}`", inline=True)
        embed.add_field(name="📊 Total signals", value=f"`{s['total']}`", inline=True)
        bq = s.get("by_quality", {})
        if bq:
            lines = []
            for q, d in sorted(bq.items()):
                total = d["w"] + d["l"]
                wr = (d["w"] / total * 100) if total else 0
                lines.append(f"**{q}** — `{d['w']}W / {d['l']}L` · win rate `{wr:.0f}%`")
            embed.add_field(name="⭐ By Quality", value="\n".join(lines), inline=False)
        embed.set_footer(text="Auto-tracked every 2 minutes against live Binance prices")
        await interaction.followup.send(embed=embed)

    @tree.command(name="history", description="📜 Last 10 tracked signals + their results")
    async def slash_history(interaction: discord.Interaction):
        await interaction.response.defer()
        recs = tracker.recent(limit=10)
        if not recs:
            await interaction.followup.send("📍 No signal history yet.")
            return
        lines = []
        for r in recs:
            status = r.get("status", "OPEN")
            if status == "OPEN":
                emoji = "⏳"
            elif status == "SL":
                emoji = "❌"
            elif status == "EXPIRED":
                emoji = "🕒"
            else:
                emoji = "✅"
            hit_str = ",".join(r.get("hit", [])).upper() or "—"
            dir_emoji = "🟢" if r["direction"] == "BUY" else "🔴"
            lines.append(
                f"{emoji} {dir_emoji} **{r['symbol']}** @ `${r['entry']:,.2f}`".rstrip("0").rstrip(".")
                + f" — {status}"
                + (f" ({hit_str})" if r.get("hit") else "")
            )
        embed = discord.Embed(
            title="📜 Recent Signal History",
            description="\n".join(lines),
            color=0x3498DB,
        )
        embed.set_footer(text="✅ TP hit · ❌ SL · ⏳ Open · 🕒 Expired (>48h)")
        await interaction.followup.send(embed=embed)

    print("[stats-cmd] Registered /stats and /history", flush=True)
