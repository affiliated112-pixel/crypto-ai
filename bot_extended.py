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
import coins_config
import coin_ticket
import clean_signals
import signal_engine
import on_demand
import paper_trading
import commands_paper
import paper_interactive
import demo_app

# ---- Patch signal loop to add Demo Button on every signal ----
_orig_signal_loop_fn = getattr(bot, 'signal_loop', None)

async def _patched_signal_loop():
    """Wraps bot.signal_loop to inject Demo Trading button on every signal."""
    import discord as _discord
    await bot.client.wait_until_ready()

    # Monkey-patch the channel.send calls inside bot to add view=TryDemoButton
    _orig_free_send = None

    async def _run_with_demo_buttons():
        """Intercept free_ch.send and vip_ch.send to attach demo button."""
        # We patch at the signal-send level in bot.py's signal_loop
        # by wrapping the two embed objects after the fact.
        # Since bot.signal_loop is a coroutine we let it run and
        # hook into the channel objects dynamically.
        pass  # actual patching done via _patch_channel_send below

    if _orig_signal_loop_fn:
        await _orig_signal_loop_fn()
    else:
        print('[demo-button] signal_loop not found on bot', flush=True)

def _make_send_with_demo(original_send, symbol, direction, price):
    """Return a wrapped send() that appends TryDemoButton to signal embeds."""
    async def _wrapped_send(*args, **kwargs):
        # Only attach button if this send has an embed and no view yet
        if 'embed' in kwargs and 'view' not in kwargs:
            kwargs['view'] = paper_interactive.TryDemoButton(symbol, direction, price)
        return await original_send(*args, **kwargs)
    return _wrapped_send

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

# ---- Demo button: patch bot.signal_loop channel sends ----
_LAST_SIGNAL = {}  # symbol -> (direction, price)

def _patch_signal_loop_for_demo():
    """Monkey-patch bot.signal_loop so every channel.send with a signal embed
    gets a TryDemoButton view automatically."""
    import bot as _bot
    _orig_loop = getattr(_bot, 'signal_loop', None)
    if not _orig_loop:
        print('[demo-button] signal_loop not found — button not attached', flush=True)
        return

    async def _new_signal_loop():
        await _bot.client.wait_until_ready()
        while True:
            try:
                free_ch_id  = getattr(_bot, 'FREE_SIGNALS_CHANNEL', None)
                vip_ch_id   = getattr(_bot, 'VIP_SIGNALS_CHANNEL', None)
                alerts_ch_id = getattr(_bot, 'ALERTS_CHANNEL', None)

                free_ch  = _bot.client.get_channel(free_ch_id)  if free_ch_id  else None
                vip_ch   = _bot.client.get_channel(vip_ch_id)   if vip_ch_id   else None
                alerts_ch = _bot.client.get_channel(alerts_ch_id) if alerts_ch_id else None

                import discord as _disc
                # FREE loop: use coins_config.FREE_SYMBOLS (6 major coins only)
                # Cache BTC signal for context checks on altcoins
                btc_df  = _bot.get_data('BTCUSDT')
                btc_sig, _, _, _ = _bot.get_signal_v2(btc_df) if btc_df is not None else (None, None, None, None)
                signal_engine.cache_btc_signal(btc_sig)

                for symbol in coins_config.FREE_SYMBOLS:
                    df  = _bot.get_data(symbol)
                    sig, price, rsi, conf = _bot.get_signal_v2(df)
                    ind = _bot.calc_indicators(df)

                    if ind:
                        bb_pct  = ind.get('bb_pct', 0)
                        stoch_k = ind.get('stoch_k', 0)
                        print(f'  {symbol}: price={price:.2f} RSI={rsi:.1f} BB%={bb_pct:.2f} SK={stoch_k:.2f} => {sig or "NO SIGNAL"} {conf or ""}')

                    if ind and _bot.check_volume_spike(ind) and alerts_ch:
                        await alerts_ch.send(embed=_disc.Embed(
                            description=f'📊 **Volume Spike — {symbol.replace("USDT","")}**\n\n'
                                        f'🇬🇧 Volume is 2.5x above average! Watch for a big move.\n'
                                        f'🇷🇴 Volumul este de 2.5x mai mare decât media!',
                            color=_disc.Color.yellow()
                        ))

                    if df is not None and _bot.check_volatility(df) and alerts_ch:
                        await alerts_ch.send(embed=_disc.Embed(
                            description=f'⚠️ **High Volatility — {symbol.replace("USDT","")}**\n\n'
                                        f'🇬🇧 Large candle detected. Check open positions.\n'
                                        f'🇷🇴 Lumânare mare detectată.',
                            color=_disc.Color.orange()
                        ))

                    if sig and price and _bot.can_send_signal(symbol, sig):
                        print(f'  >>> SENDING {sig} signal for {symbol} (conf={conf})')
                        _bot.SIGNAL_STATS[sig]     += 1
                        _bot.SIGNAL_STATS['total'] += 1
                        _bot.SIGNAL_HISTORY.append({'symbol': symbol, 'signal': sig,
                            'price': price, 'rsi': round(rsi, 2), 'confidence': conf,
                            'timestamp': _bot.utcnow()})
                        if len(_bot.SIGNAL_HISTORY) > 500:
                            _bot.SIGNAL_HISTORY.pop(0)

                        ai_text   = _bot.ai_analysis(sig, price, rsi, symbol)
                        tf15      = _bot.get_signal_15m(symbol)
                        confirmed = tf15 == sig
                        chart     = _bot.generate_chart(df, symbol, sig)
                        f_embed   = _bot.build_free_embed(symbol, sig, price, rsi, conf)
                        v_embed   = _bot.build_vip_embed(symbol, sig, price, rsi, conf, ai_text, confirmed, ind=ind)

                        # Tracker + admin paper trade
                        try:
                            from tracker import record_signal as _rec
                            _rec(symbol, sig, float(price))
                            paper_trading.hook_signal(symbol, sig, float(price))
                        except Exception as _te:
                            print(f'[tracker] {_te}', flush=True)

                        # Demo button on both channels
                        demo_view = paper_interactive.TryDemoButton(symbol, sig, price)

                        # Build clean professional embeds
                        f_embed_clean = clean_signals.build_free_signal(
                            symbol, sig, price, rsi, conf,
                            atr=ind.get('atr') if ind else None
                        )
                        v_embed_clean = clean_signals.build_vip_signal(
                            symbol, sig, price, rsi, conf,
                            ai_text=ai_text, ind=ind,
                            sector=getattr(vip_analysis, 'COIN_SECTORS', {}).get(symbol, 'Crypto'),
                        )
                        # ── Quality gate ──────────────────────────────
                        btc_ctx = signal_engine.get_cached_btc_signal()
                        free_ok, free_score, free_reason = signal_engine.should_send_free(
                            symbol, sig, price, ind or {}, btc_ctx
                        )
                        vip_ok, vip_score, vip_reason = signal_engine.should_send_vip(
                            symbol, sig, price, ind or {}, btc_signal=btc_ctx
                        )

                        print(f'  [GATE] {symbol}: FREE={free_ok}(score={free_score}) VIP={vip_ok}(score={vip_score})', flush=True)

                        if not free_ok and not vip_ok:
                            print(f'  [GATE] BLOCKED {symbol}: {free_reason or vip_reason}', flush=True)
                            continue

                        quality = signal_engine.quality_label(vip_score)
                        f_embed_clean = clean_signals.build_free_signal(
                            symbol, sig, price, rsi, conf,
                            atr=ind.get('atr') if ind else None
                        )
                        v_embed_clean = clean_signals.build_vip_signal(
                            symbol, sig, price, rsi, conf,
                            ai_text=ai_text, ind=ind or {},
                            smart_score=vip_score,
                            sector=getattr(vip_analysis, 'COIN_SECTORS', {}).get(symbol, 'Crypto'),
                        )

                        if free_ok and free_ch:
                            await free_ch.send(embed=f_embed_clean, view=demo_view)
                        if vip_ok and vip_ch:
                            await vip_ch.send(embed=v_embed_clean,
                                             file=_disc.File(chart),
                                             view=paper_interactive.TryDemoButton(symbol, sig, price))
                        # Deliver to personal subscription channels (VIP quality)
                        if vip_ok:
                            bot.client.loop.create_task(
                                coin_ticket.deliver_to_subscribers(bot.client, symbol, v_embed_clean)
                            )

                print(f'[SIGNAL LOOP] Done. Next check in {getattr(_bot,"SIGNAL_LOOP_SECONDS",900)//60} min.')
                await asyncio.sleep(getattr(_bot, 'SIGNAL_LOOP_SECONDS', 900))

            except _disc.HTTPException as e:
                print(f'[SIGNAL LOOP ERROR] HTTP {e.status}: {e}', flush=True)
                await asyncio.sleep(120)
            except Exception as e:
                print(f'[SIGNAL LOOP ERROR] {e}', flush=True)
                await asyncio.sleep(60)

    # Disable original loop, replace with ours
    _bot.signal_loop = _new_signal_loop
    # Also patch the task creation
    print('[demo-button] signal_loop patched — TryDemoButton will appear on every signal', flush=True)

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
                # Auto-open admin paper trade
                paper_trading.hook_signal(symbol, sig, float(price))
                # Auto-trade for ALL demo users
                demo_app.signal_received(symbol, sig, float(price))
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
    # Demo trading: patch bot.py signal_loop to inject TryDemoButton on every signal
    _patch_signal_loop_for_demo()
    # Demo trading poll loop (per-user virtual portfolios)
    bot.client.loop.create_task(paper_interactive.demo_poll_loop())
    # LIVE DEMO APP — auto-creates channel + live portfolio in admin category
    bot.client.loop.create_task(demo_app.demo_app_loop(bot.client))
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
    # VIP DEEP ANALYSIS — 30 coins, 3-TF, Fibonacci, Ichimoku, Smart Score
    bot.client.loop.create_task(vip_analysis.vip_analysis_loop(bot, interval=300))
    # COIN TICKET — register /subscribe /mysignals /unsubscribe
    try:
        coin_ticket.register_commands(bot.tree)
        print('[ticket] slash commands registered: /subscribe /mysignals /unsubscribe', flush=True)
    except Exception as e:
        print(f'[ticket] command register error: {e}', flush=True)
    try:
        on_demand.register_commands(bot.tree)
        print('[on_demand] slash commands registered: /signal /scan', flush=True)
    except Exception as e:
        print(f'[on_demand] command register error: {e}', flush=True)
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
