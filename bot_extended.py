"""bot_extended.py — optional safe wrapper for bot.py.

The old wrapper monkey-patched loops and could create duplicate signals. This
version keeps every module, but does not replace bot.py's real-data loops unless
you explicitly enable optional extras through environment variables.

Default behaviour:
  * run the same stable Discord bot from bot.py
  * register optional slash-command modules idempotently
  * no unsupported performance claims
  * no duplicate smart/signal loops

Optional env flags:
  DEMO_APP_ENABLED=1       start the Discord demo trading app
  PAPER_TRADING_ENABLED=1  start admin paper-trading loops
  AUTO_TRADE_ENABLED=1     start private auto-trader confirmation channel
"""
from __future__ import annotations

import asyncio
import os

import bot


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


async def _find_paper_channel() -> int | None:
    category_id = int(os.environ.get("PAPER_CATEGORY_ID", "1509818706509955172"))
    explicit = os.environ.get("PAPER_CHANNEL_ID")
    if explicit and explicit.isdigit():
        return int(explicit)
    for guild in bot.client.guilds:
        for ch in guild.text_channels:
            if ch.category_id == category_id and any(k in (ch.name or "").lower() for k in ("paper", "demo", "virtual", "admin", "test")):
                print(f"[paper] auto-discovered channel: {ch.name} ({ch.id})", flush=True)
                return ch.id
    return None


async def _optional_extras_once():
    await bot.client.wait_until_ready()
    bot._register_optional_command_modules()

    if _flag("DEMO_APP_ENABLED"):
        try:
            import paper_interactive
            import demo_app
            bot.client.loop.create_task(paper_interactive.demo_poll_loop())
            bot.client.loop.create_task(demo_app.demo_app_loop(bot.client))
            print("[demo] optional demo app started", flush=True)
        except Exception as e:
            print(f"[demo] optional demo app not started: {e}", flush=True)

    if _flag("PAPER_TRADING_ENABLED"):
        try:
            import paper_trading
            paper_ch = await _find_paper_channel()
            if paper_ch:
                bot.client.loop.create_task(paper_trading.paper_portfolio_loop(bot, paper_ch, interval=300))
                bot.client.loop.create_task(paper_trading.paper_poll_loop(bot, paper_ch))
                print(f"[paper] optional loops started in channel {paper_ch}", flush=True)
            else:
                print("[paper] no channel found; set PAPER_CHANNEL_ID to enable", flush=True)
        except Exception as e:
            print(f"[paper] optional loops not started: {e}", flush=True)

    if _flag("AUTO_TRADE_ENABLED"):
        try:
            import auto_trade_integration
            bot.client.loop.create_task(auto_trade_integration.setup(bot.client))
            print("[auto_trade] optional auto-trader setup started", flush=True)
        except Exception as e:
            print(f"[auto_trade] optional setup not started: {e}", flush=True)


_orig_setup_hook = bot.client.setup_hook


async def _patched_setup_hook():
    if _orig_setup_hook:
        try:
            await _orig_setup_hook()
        except Exception as e:
            print(f"[bot_extended] original setup_hook error: {e}", flush=True)
    bot.client.loop.create_task(_optional_extras_once())


bot.client.setup_hook = _patched_setup_hook  # type: ignore[assignment]
print("[bot_extended] safe wrapper installed", flush=True)

if __name__ == "__main__":
    bot.main()
