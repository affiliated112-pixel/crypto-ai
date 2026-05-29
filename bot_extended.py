"""bot_extended.py — Railway entrypoint that wraps bot.py.

Layers added on top of bot.py without modifying it:
  1. Bug fix: client.process_commands AttributeError
  2. New free-API slash commands (11 total)
  3. Beginner-friendly signal explainer
  4. PRO embeds (modern Discord design)
  5. Smart signal filter (Fear&Greed + News + Cross-exchange)
  6. Performance tracker (win rate, history)
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

# ---- 2. Replace embed builders with PRO versions + smart-filter wrap ----
# We monkey-patch bot.build_free_embed / bot.build_vip_embed so the existing
# bot.signal_loop() calls our new pro embeds automatically. We also wrap
# bot.get_signal_v2 to score every signal and suppress weak ones.
_orig_get_signal = bot.get_signal_v2  # type: ignore[attr-defined]
_orig_build_free = getattr(bot, "build_free_embed", None)
_orig_build_vip = getattr(bot, "build_vip_embed", None)

# We need to pass the filter context from get_signal_v2 → build_*_embed.
# Use a tiny per-symbol cache populated in our wrapper.
_LAST_EVAL = {}


def _patched_get_signal_v2(df):
    sig, price, rsi, conf = _orig_get_signal(df)
    if not sig or not price:
        return sig, price, rsi, conf
    # Detect the symbol from the DataFrame attrs or fall back to caller frame
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
    # Record this signal for the tracker (called BEFORE bot.py decides cooldown).
    # Cooldown handling stays in bot.py — we only log when the signal will be sent.
    return sig, price, rsi, conf


def _patched_build_free_embed(symbol, sig, price, rsi, conf, *args, **kwargs):
    ev = _LAST_EVAL.get(symbol, {})
    # Track every signal that reaches build_free_embed (it always does when sent).
    try:
        tracker.record_signal(
            symbol, sig, price,
            score=ev.get("score"), quality=ev.get("quality"),
        )
    except Exception as e:
        print(f"[tracker] record error: {e}", flush=True)
    return pro_embeds.build_free_embed(
        symbol, sig, price, rsi, conf,
        quality=ev.get("quality"),
        score=ev.get("score"),
        filters=ev.get("filters"),
    )


def _patched_build_vip_embed(symbol, sig, price, rsi, conf, ai_text="", confirmed=False, ind=None, *args, **kwargs):
    ev = _LAST_EVAL.get(symbol, {})
    return pro_embeds.build_vip_embed(
        symbol, sig, price, rsi, conf,
        ai_text=ai_text, confirmed=confirmed, ind=ind,
        quality=ev.get("quality"),
        score=ev.get("score"),
        filters=ev.get("filters"),
    )


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

# ---- 5. Start performance tracker background task ----
@bot.client.event
async def on_ready():
    print(f"[bot_extended] Bot ready as {bot.client.user} — starting tracker poll loop", flush=True)
    bot.client.loop.create_task(tracker.poll_loop())


if __name__ == "__main__":
    bot.main()
