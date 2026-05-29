"""bot_extended.py — Railway entrypoint that wraps bot.py.

100% REAL DATA mode:
  * Disables bot.py's fake performance/announcement/market_news loops
    (those posted hardcoded '+12% +8% 87% Win Rate' and random text —
    REMOVED for legal safety, no false advertising).
  * Replaces them with real_loops that read live data from tracker.py +
    CryptoPanic + Fear&Greed.
  * Adds VIP DEEP ANALYSIS — multi-timeframe (15m/1h/4h) analysis with
    RSI/MACD/BB/EMA/ADX + macro inputs + trade plan, posted to vip-analysis
    every 30 min.
"""
import asyncio
import os
import discord
import bot
import commands_ext
import commands_ext2
import commands_stats
import commands_admin
import commands_help
import pro_embeds
import smart_filter
import tracker
import alert_messages
import real_loops
import vip_analysis

async def _noop_process_commands(*args, **kwargs):
    return None
bot.client.process_commands = _noop_process_commands  # type: ignore[attr-defined]

# ---- Disable bot.py's FAKE marketing loops ----
async def _disabled_loop_performance():
    print("[real-data] bot.performance_loop DISABLED (used fake +12%/87%). Real one will run.", flush=True)

async def _disabled_loop_market_news():
    print("[real-data] bot.market_news_loop DISABLED (used random hardcoded text). Real one will run.", flush=True)

async def _disabled_loop_announcement():
    print("[real-data] bot.announcement_loop DISABLED (used fake '87% Win Rate'). Real one will run.", flush=True)

bot.performance_loop = _disabled_loop_performance       # type: ignore[attr-defined]
bot.market_news_loop = _disabled_loop_market_news       # type: ignore[attr-defined]
bot.announcement_loop = _disabled_loop_announcement     # type: ignore[attr-defined]

# ---- Configure VIP_ANALYSIS_CHANNEL (env var or fallback) ----
VIP_ANALYSIS_CHANNEL = None
_raw = os.environ.get("VIP_ANALYSIS_CHANNEL")
if _raw:
    try:
        VIP_ANALYSIS_CHANNEL = int(_raw)
    except ValueError:
        VIP_ANALYSIS_CHANNEL = None
if VIP_ANALYSIS_CHANNEL:
    bot.VIP_ANALYSIS_CHANNEL = VIP_ANALYSIS_CHANNEL  # type: ignore[attr-defined]
    print(f"[vip_analysis] using VIP_ANALYSIS_CHANNEL={VIP_ANALYSIS_CHANNEL}", flush=True)
else:
    print("[vip_analysis] VIP_ANALYSIS_CHANNEL not set — will auto-discover by name", flush=True)

# ---- Smart-filter wrap on signals ----
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

commands_ext.register(bot.tree, bot.client)
commands_ext2.register(bot.tree, bot.client)
commands_stats.register(bot.tree, bot.client)
commands_admin.register(bot.tree, bot.client)
commands_help.register(bot.tree, bot.client)

print("[explainer] DISABLED (user request)", flush=True)


# ---- SL/TP alert pipeline ----
async def _send_alert(event, record, extra):
    try:
        embed = alert_messages.build_alert_embed(event, record, extra)
    except Exception as e:
        print(f"[alert] embed build error: {e}", flush=True)
        return
    alerts_id = getattr(bot, "ALERTS_CHANNEL", None)
    free_id = getattr(bot, "FREE_SIGNALS_CHANNEL", None)
    if alerts_id:
        ch = bot.client.get_channel(alerts_id)
        if ch is None:
            try: ch = await bot.client.fetch_channel(alerts_id)
            except Exception: ch = None
        if ch:
            try: await ch.send(embed=embed)
            except Exception as e: print(f"[alert] send to alerts error: {e}", flush=True)
    if event in ("TP1", "TP2", "TP3") and free_id:
        ch = bot.client.get_channel(free_id)
        if ch is None:
            try: ch = await bot.client.fetch_channel(free_id)
            except Exception: ch = None
        if ch:
            try: await ch.send(embed=embed)
            except Exception as e: print(f"[alert] send to free error: {e}", flush=True)
    print(f"[alert] {event} {record['symbol']} dispatched (P&L {extra.get('pnl_pct', 0):+.2f}%)", flush=True)


tracker.set_alert_callback(_send_alert)


async def _autodiscover_vip_analysis():
    """If VIP_ANALYSIS_CHANNEL was not set via env, find a channel named 'vip-analysis'."""
    if getattr(bot, "VIP_ANALYSIS_CHANNEL", None):
        return
    for guild in bot.client.guilds:
        for ch in guild.text_channels:
            n = (ch.name or "").lower()
            if "vip-analysis" in n or n.endswith("vip-analysis") or "vip_analysis" in n:
                bot.VIP_ANALYSIS_CHANNEL = ch.id
                print(f"[vip_analysis] auto-discovered channel: {ch.name} (id={ch.id})", flush=True)
                return
    print("[vip_analysis] could not find vip-analysis channel; falling back to vip-signals", flush=True)
    bot.VIP_ANALYSIS_CHANNEL = getattr(bot, "VIP_SIGNALS_CHANNEL", None)


async def _startup_extras():
    await bot.client.wait_until_ready()
    print(f"[bot_extended] Extras starting", flush=True)
    await _autodiscover_vip_analysis()
    symbols = getattr(bot, "SYMBOLS", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"])
    try:
        tasks = [smart_filter._cached_fear_greed(), smart_filter._cached_sentiment()]
        for s in symbols:
            tasks.append(smart_filter._cached_arbitrage(s))
        await asyncio.gather(*tasks, return_exceptions=True)
        print("[smart_filter] cache warmed up", flush=True)
    except Exception as e:
        print(f"[smart_filter] warm error: {e}", flush=True)
    # Background loops
    bot.client.loop.create_task(tracker.poll_loop())
    bot.client.loop.create_task(smart_filter.background_refresh_loop(symbols, interval=120))
    # REAL data loops (replace bot.py's fake ones)
    bot.client.loop.create_task(real_loops.real_performance_loop(bot, interval=86400))
    bot.client.loop.create_task(real_loops.real_market_news_loop(bot, interval=1800))
    bot.client.loop.create_task(real_loops.real_announcement_loop(bot, interval=86400))
    # VIP DEEP ANALYSIS
    bot.client.loop.create_task(vip_analysis.vip_analysis_loop(bot, interval=1800))
    print("[bot_extended] tracker + smart_filter + real_loops + vip_analysis loops started", flush=True)


_orig_setup_hook = bot.client.setup_hook

async def _patched_setup_hook():
    if _orig_setup_hook:
        try:
            await _orig_setup_hook()
        except Exception as e:
            print(f"[bot_extended] original setup_hook error: {e}", flush=True)
    bot.client.loop.create_task(_startup_extras())

bot.client.setup_hook = _patched_setup_hook  # type: ignore[assignment]
print("[bot_extended] setup_hook installed", flush=True)


if __name__ == "__main__":
    bot.main()
