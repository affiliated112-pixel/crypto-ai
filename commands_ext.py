"""Extended market slash commands.

All commands use public/free data sources. The module keeps existing bot.py
commands unless ``replace_existing=True`` is explicitly requested, so loading
extra modules cannot accidentally break the original command list.
"""
from __future__ import annotations

import discord
from discord import app_commands

import feeds

OWN_COMMANDS = ["fear", "trending", "tvl", "dominance", "coin"]


def _emoji_for_fg(v: int) -> str:
    if v <= 25:
        return "😱"
    if v <= 45:
        return "😟"
    if v <= 55:
        return "😐"
    if v <= 75:
        return "😊"
    return "🤑"


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
    """Register extended commands.

    ``replace_existing=False`` is the safe default: if bot.py already registered
    a command name, we keep it and only add missing commands.
    """
    if replace_existing:
        removed = _remove_existing(tree, OWN_COMMANDS)
        if removed:
            print(f"[ext] Replaced existing commands: {', '.join(removed)}", flush=True)

    existing = _existing_names(tree)
    registered: list[str] = []
    skipped: list[str] = []

    def enabled(name: str) -> bool:
        if name in existing:
            skipped.append(name)
            return False
        registered.append(name)
        return True

    if enabled("fear"):
        @tree.command(name="fear", description="📊 Crypto Fear & Greed Index — real market sentiment 0-100")
        async def slash_fear(interaction: discord.Interaction):
            await interaction.response.defer()
            d = feeds.fear_greed_index()
            if d.get("error"):
                await interaction.followup.send(f"❌ Fear & Greed API error: {d['error']}")
                return
            v = int(d.get("value", 0))
            emoji = _emoji_for_fg(v)
            bar = "█" * (v // 5) + "░" * (20 - v // 5)
            embed = discord.Embed(
                title=f"{emoji} Fear & Greed Index — {v}/100",
                description=f"**{d.get('classification', 'Unknown')}**\n`{bar}`",
                color=0x00C896 if v >= 50 else 0xE74C3C,
            )
            embed.set_footer(text="Source: alternative.me · 0 = Extreme Fear · 100 = Extreme Greed · Educational only")
            await interaction.followup.send(embed=embed)

    if enabled("trending"):
        @tree.command(name="trending", description="🔥 Top trending coins on CoinGecko")
        async def slash_trending(interaction: discord.Interaction):
            await interaction.response.defer()
            items = feeds.coingecko_trending()
            if not items:
                await interaction.followup.send("❌ Could not fetch trending coins right now.")
                return
            lines = []
            for i, c in enumerate(items, 1):
                rank = f"#{c['rank']}" if c.get("rank") else "—"
                lines.append(f"`{i}.` **{c['name']}** ({c['symbol']}) · Market cap rank: `{rank}`")
            embed = discord.Embed(
                title="🔥 Trending Coins (CoinGecko)",
                description="\n".join(lines),
                color=0xFFA500,
            )
            embed.set_footer(text="Source: CoinGecko trending search data")
            await interaction.followup.send(embed=embed)

    if enabled("tvl"):
        @tree.command(name="tvl", description="💰 Total Value Locked in DeFi (DeFiLlama)")
        async def slash_tvl(interaction: discord.Interaction):
            await interaction.response.defer()
            d = feeds.defillama_tvl()
            if not d or d.get("error"):
                err = d.get("error", "no data") if d else "no data"
                await interaction.followup.send(f"❌ DeFiLlama error: {err}")
                return
            tvl_b = float(d["tvl_usd"]) / 1e9
            change = float(d.get("change_24h_pct") or 0)
            arrow = "📈" if change >= 0 else "📉"
            embed = discord.Embed(
                title="💰 Total DeFi TVL",
                description=f"**${tvl_b:,.2f}B** {arrow} `{change:+.2f}%` (last data point)",
                color=0x00C896 if change >= 0 else 0xE74C3C,
            )
            embed.set_footer(text="Source: DeFiLlama — all chains aggregated")
            await interaction.followup.send(embed=embed)

    if enabled("dominance"):
        @tree.command(name="dominance", description="👑 BTC & ETH market dominance + global market cap")
        async def slash_dominance(interaction: discord.Interaction):
            await interaction.response.defer()
            d = feeds.global_market()
            if d.get("error"):
                await interaction.followup.send(f"❌ Error: {d['error']}")
                return
            mcap_t = float(d["total_mcap_usd"]) / 1e12
            vol_b = float(d["total_volume_usd"]) / 1e9
            embed = discord.Embed(title="👑 Global Crypto Market", color=0xF1C40F)
            embed.add_field(name="💎 Total Market Cap", value=f"${mcap_t:,.2f}T", inline=True)
            embed.add_field(name="📊 24h Volume", value=f"${vol_b:,.2f}B", inline=True)
            embed.add_field(name="🪙 Active Cryptos", value=f"{int(d.get('active_cryptos') or 0):,}", inline=True)
            embed.add_field(name="🟠 BTC Dominance", value=f"{float(d.get('btc_dominance') or 0):.2f}%", inline=True)
            embed.add_field(name="🔷 ETH Dominance", value=f"{float(d.get('eth_dominance') or 0):.2f}%", inline=True)
            embed.set_footer(text="Source: CoinGecko global market data")
            await interaction.followup.send(embed=embed)

    if enabled("coin"):
        @tree.command(name="coin", description="💎 Price, 24h change, market cap and volume from CoinGecko")
        @app_commands.describe(symbol="Coin name or symbol, e.g. bitcoin, BTC, ETH, solana")
        async def slash_coin(interaction: discord.Interaction, symbol: str):
            await interaction.response.defer()
            query = symbol.strip().lower()
            coin_id = feeds.coingecko_search(query) or query
            d = feeds.coingecko_price(coin_id)
            if not d or d.get("error"):
                await interaction.followup.send(f"❌ Price lookup failed for `{symbol}`")
                return
            price = float(d.get("usd") or 0)
            change = float(d.get("usd_24h_change") or 0)
            mcap = float(d.get("usd_market_cap") or 0) / 1e9
            vol = float(d.get("usd_24h_vol") or 0) / 1e9
            arrow = "📈" if change >= 0 else "📉"
            price_str = f"${price:,.8f}".rstrip("0").rstrip(".")
            embed = discord.Embed(
                title=f"💎 {coin_id.upper()} — {price_str}",
                description=f"{arrow} `{change:+.2f}%` (24h)",
                color=0x00C896 if change >= 0 else 0xE74C3C,
            )
            embed.add_field(name="💰 Market Cap", value=f"${mcap:,.2f}B", inline=True)
            embed.add_field(name="📊 24h Volume", value=f"${vol:,.2f}B", inline=True)
            embed.set_footer(text="Source: CoinGecko free API")
            await interaction.followup.send(embed=embed)

    if skipped:
        print(f"[ext] Kept existing commands: {', '.join(sorted(set(skipped)))}", flush=True)
    if registered:
        print(f"[ext] Registered commands: {', '.join(registered)}", flush=True)
