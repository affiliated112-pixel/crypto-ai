"""bot_extended.py — Railway entrypoint that wraps bot.py.
Optimized + does NOT clobber bot.py's on_ready.
"""
import asyncio
import discord
import bot
import commands_ext
import commands_ext2
import commands_stats
import signal_explainer
import pro_embeds
import smart_filter
import tracker

# ---- 1. Fix bot.py's broken on_message ----
async def _noop_process_commands(*args, **kwargs):
    return None
bot.client.process_commands = _noop_process_commands  # type: ignore[attr-defined]

# ---- 2. Wrap signal generator + embed builders ----
_orig_get_signal = bot.get_signal_v2  # type: ignore[attr-defined]
_LAST_EVAL = {}


def _patched_get_signal_v2(df):
    sig, price, rsi, conf = _orig_get_signal(df)
    if not sig or not price:
        return sig, price, rsi, conf
    symbol = getattr(df, "_symbol_hint", None)
    if symbol is None:
        import inspect
        for f in inspect.stack():
            if f.function == "signal_loop":
                symbol = f.frame.f_locals.get("symbol")
                break
    if symbol is None:
        return sig, price, rsi, conf
    try:
        score, quality, filters, suppressed = smart_filter.evaluate(symbol, sig, price, conf)
    except Exception as e:
        print(f"[smart_filter] error: {e}", flush=True)
        return sig, price, rsi, conf
    _LAST_EVAL[symbol] = {"score": score, "quality": quality, "filters": filters}
    if suppressed:
        print(f"  [SMART_FILTER] {sig} {symbol} suppressed (score={score})", flush=True)
        return None, price, rsi, conf
    return sig, price, rsi, conf


def _patched_build_free_embed(symbol, sig, price, rsi, conf, *args, **kwargs):
    ev = _LAST_EVAL.get(symbol, {})
    try:
        tracker.record_signal(symbol, sig, price, score=ev.get("score"), quality=ev.get("quality"))
    except Exception as e:
        print(f"[tracker] record error: {e}", flush=True)
    return pro_embeds.build_free_embed(symbol, sig, price, rsi, conf,
        quality=ev.get("quality"), score=ev.get("score"), filters=ev.get("filters"))


def _patched_build_vip_embed(symbol, sig, price, rsi, conf, ai_text="", confirmed=False, ind=None, *args, **kwargs):
    ev = _LAST_EVAL.get(symbol, {})
    return pro_embeds.build_vip_embed(symbol, sig, price, rsi, conf,
        ai_text=ai_text, confirmed=confirmed, ind=ind,
        quality=ev.get("quality"), score=ev.get("score"), filters=ev.get("filters"))


bot.get_signal_v2 = _patched_get_signal_v2  # type: ignore[attr-defined]
bot.build_free_embed = _patched_build_free_embed  # type: ignore[attr-defined]
bot.build_vip_embed = _patched_build_vip_embed  # type: ignore[attr-defined]
print("[pro] Patched get_signal_v2 + build_free_embed + build_vip_embed", flush=True)

# ---- 3. Register extended slash commands ----
commands_ext.register(bot.tree, bot.client)
commands_ext2.register(bot.tree, bot.client)
commands_stats.register(bot.tree, bot.client)

# ---- 4. Install beginner-friendly signal explainer ----
signal_explainer.install(bot.client)

# ---- 5. Start background tasks WITHOUT clobbering bot.py's on_ready ----
# CRITICAL: @bot.client.event on_ready would REPLACE the original on_ready
# in bot.py that starts signal_loop, syncs slash commands, and fetches
# channels. Instead we add a one-shot startup task that waits for the bot
# to be ready, then kicks off OUR background loops alongside bot.py's.
async def _startup_extras():
    await bot.client.wait_until_ready()
    print(f"[bot_extended] Extras starting (alongside bot.py loops)", flush=True)
    # Warm caches so first signal has data
    symbols = getattr(bot, "SYMBOLS", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"])
    try:
        tasks = [smart_filter._cached_fear_greed(), smart_filter._cached_sentiment()]
        for s in symbols:
            tasks.append(smart_filter._cached_arbitrage(s))
        await asyncio.gather(*tasks, return_exceptions=True)
        print("[smart_filter] cache warmed up", flush=True)
    except Exception as e:
        print(f"[smart_filter] warm error: {e}", flush=True)
    # Now schedule the ongoing background loops
    bot.client.loop.create_task(tracker.poll_loop())
    bot.client.loop.create_task(smart_filter.background_refresh_loop(symbols, interval=120))
    print("[bot_extended] tracker + smart_filter refresh loops started", flush=True)


# Hook into bot.main() by scheduling _startup_extras as a setup_hook.
# discord.Client supports `setup_hook` which fires BEFORE on_ready and is
# the correct place to schedule background tasks without overriding events.
_orig_setup_hook = bot.client.setup_hook

async def _patched_setup_hook():
    if _orig_setup_hook:
        try:
            await _orig_setup_hook()
        except Exception as e:
            print(f"[bot_extended] original setup_hook error: {e}", flush=True)
    bot.client.loop.create_task(_startup_extras())

bot.client.setup_hook = _patched_setup_hook  # type: ignore[assignment]
print("[bot_extended] setup_hook installed (extras will run after bot.py on_ready)", flush=True)


if __name__ == "__main__":
    bot.main()
