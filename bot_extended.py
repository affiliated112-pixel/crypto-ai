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
  * Posts a one-time LEGAL DISCLAIMER (EN+RO) in #announcements on startup
    and pins it (idempotent — won't repost if already there).
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
import paper_trading
import commands_paper

# ---- Paper Trading Config ----
PAPER_CATEGORY_ID = 1509818706509955172
PAPER_CHANNEL_ID = int(os.environ.get("PAPER_CHANNEL_ID", "0")) or None

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
                symbol = f.frame.f_locals.get("coin") or f.frame.f_locals.get("symbol")
                break
    if not symbol:
        return sig, price, rsi, conf
    try:
        verdict = smart_filter.evaluate_signal_sync(symbol, sig, price)
        _LAST_EVAL[symbol] = verdict
        if not verdict.get("allow", True):
            print(f"[smart_filter] BLOCKED {symbol} {sig} -> {verdict.get('reasons')}", flush=True)
            return None, None, None, None
        print(f"[smart_filter] ALLOWED {symbol} {sig} score={verdict.get('score'):.2f} quality={verdict.get('quality')}", flush=True)
    except Exception as e:
        print(f"[smart_filter] error on {symbol}: {e}", flush=True)
    return sig, price, rsi, conf

bot.get_signal_v2 = _patched_get_signal_v2  # type: ignore[attr-defined]

# ---- Record signals into tracker for live SL/TP polling ----
_orig_signal_loop = None
if hasattr(bot, "signal_loop"):
    _orig_signal_loop = bot.signal_loop

# Wrap signal_loop to record each emitted signal + open paper trade
import functools
if hasattr(bot, "send_signal_embed"):
    _orig_send_signal_embed = bot.send_signal_embed

    @functools.wraps(_orig_send_signal_embed)
    async def _patched_send_signal_embed(*args, **kwargs):
        result = await _orig_send_signal_embed(*args, **kwargs)
        try:
            symbol = kwargs.get("symbol") or (args[1] if len(args) > 1 else None)
            sig = kwargs.get("sig") or kwargs.get("direction") or (args[2] if len(args) > 2 else None)
            price = kwargs.get("price") or (args[3] if len(args) > 3 else None)
            quality = None
            score = None
            if symbol and symbol in _LAST_EVAL:
                quality = _LAST_EVAL[symbol].get("quality")
                score = _LAST_EVAL[symbol].get("score")
            if symbol and sig and price:
                tracker.record_signal(symbol, sig, float(price), score=score, quality=quality)
                print(f"[tracker] recorded {sig} {symbol} @ {price}", flush=True)
                # Auto-open paper trade on every signal
                paper_trading.hook_signal(symbol, sig, float(price))
        except Exception as e:
            print(f"[tracker] record skipped: {e}", flush=True)
        return result

    bot.send_signal_embed = _patched_send_signal_embed  # type: ignore[attr-defined]

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

async def _find_paper_channel():
    """Auto-discover paper trading channel inside admin category."""
    for guild in bot.client.guilds:
        for ch in guild.text_channels:
            if ch.category_id == PAPER_CATEGORY_ID:
                n = (ch.name or "").lower()
                if any(k in n for k in ["paper", "demo", "virtual", "admin", "test"]):
                    print(f"[paper] auto-discovered channel: {ch.name} ({ch.id})", flush=True)
                    return ch.id
        for ch in guild.text_channels:
            if ch.category_id == PAPER_CATEGORY_ID:
                print(f"[paper] fallback channel: {ch.name} ({ch.id})", flush=True)
                return ch.id
    return None

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
    # Post the legal disclaimer once (idempotent)
    bot.client.loop.create_task(real_loops.post_legal_disclaimer(bot))
    # Paper trading (admin only)
    paper_ch = PAPER_CHANNEL_ID or await _find_paper_channel()
    if paper_ch:
        bot.client.loop.create_task(paper_trading.paper_portfolio_loop(bot, paper_ch, interval=300))
        bot.client.loop.create_task(paper_trading.paper_poll_loop(bot, paper_ch))
        print(f"[paper] loops started — channel {paper_ch}", flush=True)
    else:
        print("[paper] WARNING: no channel found in category. Set PAPER_CHANNEL_ID env var.", flush=True)
    # Background loops
    bot.client.loop.create_task(tracker.poll_loop())
    bot.client.loop.create_task(smart_filter.background_refresh_loop(symbols, interval=120))
    # REAL data loops (replace bot.py's fake ones)
    bot.client.loop.create_task(real_loops.real_performance_loop(bot, interval=86400))
    bot.client.loop.create_task(real_loops.real_market_news_loop(bot, interval=1800))
    bot.client.loop.create_task(real_loops.real_announcement_loop(bot, interval=86400))
    # VIP DEEP ANALYSIS
    bot.client.loop.create_task(vip_analysis.vip_analysis_loop(bot, interval=1800))
    # Paper trading slash commands
    try:
        commands_paper.register(bot.tree)
        print("[paper] slash commands registered: /paper /paper_reset /paper_trades", flush=True)
    except Exception as e:
        print(f"[paper] command register error: {e}", flush=True)
    print("[bot_extended] all loops started including paper trading", flush=True)

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
