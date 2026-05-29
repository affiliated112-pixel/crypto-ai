"""bot_extended.py — Railway entrypoint that wraps bot.py and registers new modules.
Keeps the original bot.py untouched. New features go into separate modules.
"""
import bot
import commands_ext
import commands_ext2

# Register new slash commands on the existing CommandTree.
commands_ext.register(bot.tree, bot.client)
commands_ext2.register(bot.tree, bot.client)

if __name__ == "__main__":
    bot.main()
