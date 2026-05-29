"""coin_ticket.py — Personal coin subscription system.

Flow:
  1. User clicks 🎫 in #get-signals (or uses /subscribe)
  2. A Discord Select menu appears (ephemeral) — user picks 1-5 coins
  3. Bot creates a PRIVATE text channel  #signals-@username  visible only to that user
  4. Every time a signal fires for a subscribed coin, bot DMs it to that private channel
  5. User can update subscriptions anytime via /subscribe again (channel is reused)

Storage: subscriptions are kept in-memory dict + persisted to subscriptions.json
"""

import asyncio
import json
import os
import discord
from discord import app_commands
from pathlib import Path
from datetime import datetime, timezone

import coins_config

SUBS_FILE = Path(__file__).with_name("subscriptions.json")

# user_id -> {"coins": [...], "channel_id": int}
_SUBS: dict[int, dict] = {}

TICKET_CATEGORY_NAME = "📡 My Signals"   # Category where private channels live
MAX_COINS_PER_USER   = 8                  # Max coins a user can subscribe to

# ─── PERSISTENCE ─────────────────────────────────────────────────────────────

def _load():
    global _SUBS
    if SUBS_FILE.exists():
        try:
            raw = json.loads(SUBS_FILE.read_text())
            _SUBS = {int(k): v for k, v in raw.items()}
            print(f"[ticket] Loaded {len(_SUBS)} subscriptions", flush=True)
        except Exception as e:
            print(f"[ticket] load error: {e}", flush=True)

def _save():
    try:
        SUBS_FILE.write_text(json.dumps(_SUBS, indent=2))
    except Exception as e:
        print(f"[ticket] save error: {e}", flush=True)

_load()

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def get_subscription(user_id: int) -> list[str]:
    """Returns list of subscribed symbols for a user."""
    return _SUBS.get(user_id, {}).get("coins", [])

def get_private_channel_id(user_id: int) -> int | None:
    return _SUBS.get(user_id, {}).get("channel_id")

def set_subscription(user_id: int, coins: list[str], channel_id: int):
    _SUBS[user_id] = {"coins": coins, "channel_id": channel_id}
    _save()

def get_all_subscribers_for_coin(symbol: str) -> list[int]:
    """Returns all user_ids subscribed to this symbol."""
    return [uid for uid, data in _SUBS.items() if symbol in data.get("coins", [])]

async def _get_or_create_category(guild: discord.Guild) -> discord.CategoryChannel:
    """Get or create the 'My Signals' category."""
    for cat in guild.categories:
        if cat.name == TICKET_CATEGORY_NAME:
            return cat
    cat = await guild.create_category(
        TICKET_CATEGORY_NAME,
        reason="Crypto Bot: personal signal channels",
    )
    return cat

async def _get_or_create_private_channel(
    guild: discord.Guild,
    member: discord.Member,
    coins: list[str],
) -> discord.TextChannel:
    """Create or update a private text channel for this user."""
    existing_id = get_private_channel_id(member.id)
    existing_ch = guild.get_channel(existing_id) if existing_id else None

    coin_str = "-".join(c.replace("USDT", "") for c in coins[:3])
    if len(coins) > 3:
        coin_str += f"+{len(coins)-3}"

    if existing_ch and isinstance(existing_ch, discord.TextChannel):
        # Update topic
        try:
            await existing_ch.edit(
                topic=f"📡 {member.display_name}'s signals: {', '.join(c.replace('USDT','') for c in coins)}"
            )
        except Exception:
            pass
        return existing_ch

    # Create new private channel
    category = await _get_or_create_category(guild)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        member:             discord.PermissionOverwrite(read_messages=True, send_messages=False),
        guild.me:           discord.PermissionOverwrite(read_messages=True, send_messages=True),
    }

    ch = await guild.create_text_channel(
        name=f"signals-{member.name[:16]}",
        category=category,
        topic=f"📡 {member.display_name}'s signals: {', '.join(c.replace('USDT','') for c in coins)}",
        overwrites=overwrites,
        reason="Crypto Bot: personal coin subscription",
    )

    # Welcome message
    coins_list = " ".join(f"`{c.replace('USDT','')}`" for c in coins)
    embed = discord.Embed(
        title=f"📡 Your Personal Signal Channel",
        description=(
            f"Hey {member.mention}! This is your **private signal feed**.\n\n"
            f"You'll receive signals exclusively for:\n"
            f"{coins_list}\n\n"
            f"**Only you can see this channel.**\n"
            f"Update your coins anytime with `/subscribe`"
        ),
        color=0x00c896,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="Not financial advice — trade at your own risk")
    await ch.send(embed=embed)

    return ch

# ─── COIN SELECT MENU ─────────────────────────────────────────────────────────

class CoinSelect(discord.ui.Select):
    def __init__(self):
        # Build options — FREE first, then VIP-only (marked)
        options = []
        for sym, meta in coins_config.COIN_META.items():
            tier_label = "" if meta["tier"] == "free" else " 💎VIP"
            options.append(discord.SelectOption(
                label=f"{meta['emoji']} {meta['name']}{tier_label}",
                value=sym,
                description=f"Get {sym.replace('USDT','')} signals in your private channel",
                emoji=None,
            ))
        super().__init__(
            placeholder="🔍 Choose up to 8 coins…",
            min_values=1,
            max_values=MAX_COINS_PER_USER,
            options=options[:25],  # Discord limit 25
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        selected = self.values
        member   = interaction.user
        guild    = interaction.guild

        if guild is None:
            await interaction.followup.send("❌ This must be used in a server.", ephemeral=True)
            return

        # Check VIP-only coins
        is_vip = any(r.name in ("VIP", "vip", "Vip") for r in getattr(member, "roles", []))
        vip_only_selected = [s for s in selected if coins_config.COIN_META.get(s, {}).get("tier") == "vip"]

        if vip_only_selected and not is_vip:
            coin_names = ", ".join(s.replace("USDT", "") for s in vip_only_selected)
            await interaction.followup.send(
                f"⚠️ **{coin_names}** are VIP-only coins.\n"
                f"Upgrade to 💎 **VIP** to unlock these coins in your private feed.\n"
                f"Free coins: {', '.join(s.replace('USDT','') for s in coins_config.FREE_SYMBOLS)}",
                ephemeral=True,
            )
            # Filter to only free coins
            selected = [s for s in selected if coins_config.COIN_META.get(s, {}).get("tier") == "free"]
            if not selected:
                return

        # Create/update private channel
        try:
            ch = await _get_or_create_private_channel(guild, member, selected)
            set_subscription(member.id, selected, ch.id)

            coins_display = " ".join(
                f"`{coins_config.COIN_META[s]['emoji']}{s.replace('USDT','')}`"
                for s in selected
            )

            await interaction.followup.send(
                f"✅ **Done!** Your private channel: {ch.mention}\n"
                f"Tracking: {coins_display}\n\n"
                f"Signals will be delivered there exclusively for you.",
                ephemeral=True,
            )
            print(f"[ticket] {member.name} subscribed to {selected}", flush=True)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Bot doesn't have permission to create channels. "
                "Ask an admin to give the bot `Manage Channels` permission.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            print(f"[ticket] error for {member.name}: {e}", flush=True)

class CoinSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(CoinSelect())

class SubscribeButton(discord.ui.View):
    """Button posted in #get-vip or #signals to open the coin picker."""
    @discord.ui.button(label="📡 Choose My Coins", style=discord.ButtonStyle.primary, custom_id="subscribe_open")
    async def open_picker(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = CoinSelectView()
        await interaction.response.send_message(
            "**Select the coins you want to track:**\n"
            "You'll get a private channel with signals only for your picks.\n"
            "💎 VIP coins require the VIP role.",
            view=view,
            ephemeral=True,
        )

# ─── SLASH COMMAND /subscribe ─────────────────────────────────────────────────

def register_commands(tree: app_commands.CommandTree):
    @tree.command(name="subscribe", description="📡 Choose which coins to get signals for (private channel)")
    async def slash_subscribe(interaction: discord.Interaction):
        view = CoinSelectView()
        await interaction.response.send_message(
            "**Select up to 8 coins** to track in your private signal channel:\n"
            "💎 VIP-only coins require the VIP role.",
            view=view,
            ephemeral=True,
        )

    @tree.command(name="mysignals", description="📡 View your current coin subscriptions")
    async def slash_mysignals(interaction: discord.Interaction):
        uid  = interaction.user.id
        subs = get_subscription(uid)
        ch_id = get_private_channel_id(uid)

        if not subs:
            await interaction.response.send_message(
                "You have no subscriptions yet.\nUse `/subscribe` to pick your coins!",
                ephemeral=True,
            )
            return

        ch_mention = f"<#{ch_id}>" if ch_id else "*(channel not found)*"
        coins_list = "\n".join(
            f"{coins_config.COIN_META.get(s, {}).get('emoji','🪙')} **{s.replace('USDT','')}** — {coins_config.COIN_NAMES_EN.get(s, s)}"
            for s in subs
        )
        embed = discord.Embed(
            title="📡 Your Signal Subscriptions",
            description=f"**Private channel:** {ch_mention}\n\n{coins_list}",
            color=0x00c896,
        )
        embed.set_footer(text="Update anytime with /subscribe")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tree.command(name="unsubscribe", description="❌ Cancel your coin subscriptions")
    async def slash_unsubscribe(interaction: discord.Interaction):
        uid = interaction.user.id
        if uid not in _SUBS:
            await interaction.response.send_message("You have no active subscriptions.", ephemeral=True)
            return
        _SUBS.pop(uid)
        _save()
        await interaction.response.send_message(
            "✅ Subscriptions cancelled. Use `/subscribe` to start again.",
            ephemeral=True,
        )

# ─── SIGNAL DELIVERY TO PRIVATE CHANNELS ─────────────────────────────────────

async def deliver_to_subscribers(client: discord.Client, symbol: str, embed: discord.Embed, file=None):
    """Called after every signal — sends to every user subscribed to this coin."""
    subscribers = get_all_subscribers_for_coin(symbol)
    if not subscribers:
        return

    print(f"[ticket] delivering {symbol} signal to {len(subscribers)} subscribers", flush=True)
    for uid in subscribers:
        ch_id = get_private_channel_id(uid)
        if not ch_id:
            continue
        try:
            ch = client.get_channel(ch_id)
            if ch is None:
                ch = await client.fetch_channel(ch_id)
            if ch:
                if file:
                    # Re-open file for each send (file can only be sent once)
                    import discord as _d
                    try:
                        await ch.send(embed=embed, file=_d.File(file.fp.name))
                    except Exception:
                        await ch.send(embed=embed)
                else:
                    await ch.send(embed=embed)
        except Exception as e:
            print(f"[ticket] delivery error uid={uid} ch={ch_id}: {e}", flush=True)
