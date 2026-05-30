"""Admin / owner-only commands.
/clear deletes the last N messages in the current channel.
Owner IDs are read from OWNER_IDS env, with the original list as fallback.
"""
import os
import discord
from discord import app_commands

_DEFAULT_OWNER_IDS = {
    1426677891269267618,
    1463583046962909410,
}

def _load_owner_ids() -> set[int]:
    raw = os.environ.get("OWNER_IDS", "").replace(";", ",")
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            print(f"[admin-cmd] Ignored invalid OWNER_IDS entry: {part}", flush=True)
    return ids or set(_DEFAULT_OWNER_IDS)

OWNER_IDS = _load_owner_ids()

OWN_COMMANDS = ["clear", "purge"]


def _is_owner(user):
    return user.id in OWNER_IDS


def register(tree, client):
    removed = []
    for n in OWN_COMMANDS:
        try:
            old = tree.remove_command(n)
            if old is not None: removed.append(n)
        except Exception: pass
    if removed:
        print(f"[admin-cmd] Replaced existing: {', '.join(removed)}", flush=True)

    @tree.command(name="clear", description="🧹 Delete the last N messages in this channel (owners only)")
    @app_commands.describe(
        amount="How many messages to delete (1-100, default 10)",
        user="Optional: only delete messages from this user",
    )
    async def slash_clear(
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100] = 10,
        user: discord.User = None,
    ):
        # Owner gate
        if not _is_owner(interaction.user):
            await interaction.response.send_message(
                "❌ Doar **owner-ii botului** pot folosi această comandă.",
                ephemeral=True,
            )
            return

        # Must be in a text channel where we can manage messages
        ch = interaction.channel
        if not isinstance(ch, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                "❌ Această comandă merge doar în canale text.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Permission check on bot
        me = ch.guild.me if ch.guild else None
        perms = ch.permissions_for(me) if me else None
        if perms and not perms.manage_messages:
            await interaction.followup.send(
                "❌ Botul nu are permisiunea **`Manage Messages`** pe acest canal.\n"
                "📝 Mergi la Channel Settings → Permissions → adaugă botul cu drept `Manage Messages`.",
                ephemeral=True,
            )
            return

        def _check(msg):
            if user is not None and msg.author.id != user.id:
                return False
            return True

        try:
            # purge handles 14-day rule + bulk delete automatically
            deleted = await ch.purge(limit=amount, check=_check, bulk=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ Permisiune insuficientă pentru a șterge mesaje.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Eroare Discord: `{e}`", ephemeral=True)
            return

        target = f" de la {user.mention}" if user else ""
        await interaction.followup.send(
            f"✅ Șterse **{len(deleted)}** mesaje{target} din {ch.mention}.",
            ephemeral=True,
        )

    # Alias /purge with the same handler
    @tree.command(name="purge", description="🧹 Alias for /clear — delete last N messages (owners only)")
    @app_commands.describe(
        amount="How many messages to delete (1-100, default 10)",
        user="Optional: only delete messages from this user",
    )
    async def slash_purge(
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100] = 10,
        user: discord.User = None,
    ):
        await slash_clear.callback(interaction, amount=amount, user=user)

    print(f"[admin-cmd] Registered /clear and /purge (owners: {len(OWNER_IDS)})", flush=True)
