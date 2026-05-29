"""bot_extended.py — Railway entrypoint that wraps bot.py and registers new modules.
Keeps the original bot.py untouched. New features go into separate modules.
"""
import asyncio
import bot
import commands_ext
import commands_ext2
import signal_explainer

# ---- Fix bot.py bug: discord.Client has no process_commands() ----
# bot.py's on_message calls client.process_commands() which only exists on
# commands.Bot, not discord.Client. That raised AttributeError on every
# message. We monkey-patch it to a harmless no-op so old code stops crashing.
async def _noop_process_commands(*args, **kwargs):
    return None
bot.client.process_commands = _noop_process_commands  # type: ignore[attr-defined]

# Register new slash commands on the existing CommandTree.
commands_ext.register(bot.tree, bot.client)
commands_ext2.register(bot.tree, bot.client)

# Install the beginner-friendly signal explainer.
# This REPLACES on_message with a clean version that:
#   1) does not call the broken process_commands
#   2) posts a step-by-step trading guide under every signal
signal_explainer.install(bot.client)

if __name__ == "__main__":
    bot.main()
