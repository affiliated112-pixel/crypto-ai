"""Extended slash commands added on top of bot.py — all use free APIs.
Safely removes any existing same-name commands first so we never crash on
CommandAlreadyRegistered when bot.py defines the same name.
"""
import discord
from discord import app_commands
import feeds

OWN_COMMANDS = ["fear", "trending", "tvl", "dominance", "coin"]


def _emoji_for_fg(v):
    if v <= 25: return "😱"
    if v <= 45: return "😟"
    if v <= 55: return "😐"
    if v <= 75: return "😊"
    return "🤑"


def register(tree, client):
    """Register all extended slash commands on the given CommandTree.
    Removes any existing same-name commands so our richer versions win."""

    removed = []
    for name in OWN_COMMANDS:
        try:
            old = tree.remove_command(name)
            if old is not None:
                removed.append(name)
        except Exception:
            pass
    if removed:
        print(f"[ext] Replaced existing commands: {', '.join(removed)}", flush=True)

    @tree.command(name="fear", description="📊 Crypto Fear & Greed Index — market sentiment 0-100")
    async def slash_fear(interaction: discord.Interaction):
        await interaction.response.defer()
        d = feeds.fear_greed_index()
        if d.get("error"):
            await interaction.followup.send(f"❌ Fear & Greed API error: {d['error']}")
            return
        v = d["value"]
        emoji = _emoji_for_fg(v)
        bar = "█" * (v // 5) + "░" * (20 - v // 5)
        embed = discord.Embed(
            title=f"{emoji} Fear & Greed Index — {v}/100",
            description=f"**{d['classification']}**\n`{bar}`",
            color=0x00C896 if v >= 50 else 0xE74C3C,
        )
        embed.set_footer(text="Source: alternative.me · 0 = Extreme Fear · 100 = Extreme Greed")
        await interaction.followup.send(embed=embed)

    @tree.command(name="trending", description="🔥 Top 7 trending coins on CoinGecko (last 24h)")
    async def slash_trending(interaction: discord.Interaction):
        await interaction.response.defer()
        items = feeds.coingecko_trending()
        if not items:
            await interaction.followup.send("❌ Could not fetch trending coins.")
            return
        lines = []
        for i, c in enumerate(items, 1):
            rank = f"#{c['rank']}" if c['rank'] else "—"
            lines.append(f"`{i}.` **{c['name']}** ({c['symbol']}) · Rank: `{rank}`")
        embed = discord.Embed(
            title="🔥 Trending Coins (CoinGecko 24h)",
            description="\n".join(lines),
            color=0xFFA500,
        )
        await interaction.followup.send(embed=embed)

    @tree.command(name="tvl", description="💰 Total Value Locked in DeFi (DeFiLlama)")
    async def slash_tvl(interaction: discord.Interaction):
        await interaction.response.defer()
        d = feeds.defillama_tvl()
        if not d or d.get("error"):
            err = d.get("error", "no data") if d else "no data"
            await interaction.followup.send(f"❌ DeFiLlama error: {err}")
            return
        tvl_b = d["tvl_usd"] / 1e9
        change = d["change_24h_pct"]
        arrow = "📈" if change >= 0 else "📉"
        embed = discord.Embed(
            title="💰 Total DeFi TVL",
            description=f"**${tvl_b:,.2f}B** {arrow} `{change:+.2f}%` (24h)",
            color=0x00C896 if change >= 0 else 0xE74C3C,
        )
        embed.set_footer(text="Source: DeFiLlama — all chains aggregated")
        await interaction.followup.send(embed=embed)

    @tree.command(name="dominance", description="👑 BTC & ETH market dominance + global mcap")
    async def slash_dominance(interaction: discord.Interaction):
        await interaction.response.defer()
        d = feeds.global_market()
        if d.get("error"):
            await interaction.followup.send(f"❌ Error: {d['error']}")
            return
        mcap_t = d["total_mcap_usd"] / 1e12
        vol_b = d["total_volume_usd"] / 1e9
        embed = discord.Embed(title="👑 Global Crypto Market", color=0xF1C40F)
        embed.add_field(name="💎 Total Market Cap", value=f"${mcap_t:,.2f}T", inline=True)
        embed.add_field(name="📊 24h Volume", value=f"${vol_b:,.2f}B", inline=True)
        embed.add_field(name="🪙 Active Cryptos", value=f"{d['active_cryptos']:,}", inline=True)
        embed.add_field(name="🟠 BTC Dominance", value=f"{d['btc_dominance']:.2f}%", inline=True)
        embed.add_field(name="🔷 ETH Dominance", value=f"{d['eth_dominance']:.2f}%", inline=True)
        await interaction.followup.send(embed=embed)

    @tree.command(name="coin", description="💎 Live price + 24h change for ANY coin (300+ supported)")
    @app_commands.describe(symbol="Coin name or symbol (e.g. doge, shib, pepe, link, arb)")
    async def slash_coin(interaction: discord.Interaction, symbol: str):
        await interaction.response.defer()
        coin_id = feeds.coingecko_search(symbol)
        if not coin_id:
            await interaction.followup.send(f"❌ Coin not found: `{symbol}`")
            return
        d = feeds.coingecko_price(coin_id)
        if not d or d.get("error"):
            await interaction.followup.send(f"❌ Price lookup failed for `{symbol}`")
            return
        price = d.get("usd", 0)
        change = d.get("usd_24h_change", 0) or 0
        mcap = (d.get("usd_market_cap", 0) or 0) / 1e9
        vol = (d.get("usd_24h_vol", 0) or 0) / 1e9
        arrow = "📈" if change >= 0 else "📉"
        price_str = f"${price:,.8f}".rstrip("0").rstrip(".")
        embed = discord.Embed(
            title=f"💎 {coin_id.upper()} — {price_str}",
            description=f"{arrow} `{change:+.2f}%` (24h)",
            color=0x00C896 if change >= 0 else 0xE74C3C,
        )
        embed.add_field(name="💰 Market Cap", value=f"${mcap:,.2f}B", inline=True)
        embed.add_field(name="📊 24h Volume", value=f"${vol:,.2f}B", inline=True)
        embed.set_footer(text="Source: CoinGecko (free API)")
        await interaction.followup.send(embed=embed)

    print("[ext] Registered 5 extended commands: /fear /trending /tvl /dominance /coin", flush=True)
