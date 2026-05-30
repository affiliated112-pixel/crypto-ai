"""smart_loop.py — The main signal loop. Replaces bot_extended's patched loop.

Runs every 15 minutes (not 5). Scans all coins. Scores all candidates.
Sends only the BEST ones, respecting daily budgets.

FREE:  scans 6 coins  | max 3 signals/day | score >= 58 | R:R >= 1.8
VIP:   scans 30 coins | max 5 signals/day | score >= 70 | R:R >= 2.2 | 2/3 TF
"""

import asyncio
import discord
from datetime import datetime, timezone

import bot
import coins_config
import signal_engine
import clean_signals

try:
    import vip_analysis as _vip
    _HAS_VIP = True
except ImportError:
    _HAS_VIP = False

try:
    import coin_ticket
    _HAS_TICKET = True
except ImportError:
    _HAS_TICKET = False

try:
    import paper_trading
    import paper_interactive
    _HAS_PAPER = True
except ImportError:
    _HAS_PAPER = False

try:
    from tracker import record_signal as _record_signal
    _HAS_TRACKER = True
except ImportError:
    _HAS_TRACKER = False

try:
    import signal_results
    _HAS_RESULTS = True
except ImportError:
    _HAS_RESULTS = False

try:
    import auto_trade_integration
    _HAS_AUTO_TRADE = True
except ImportError:
    _HAS_AUTO_TRADE = False

try:
    import demo_app
    _HAS_DEMO_APP = True
except ImportError:
    _HAS_DEMO_APP = False

SCAN_INTERVAL = 900   # 15 minutes — enough time for indicators to develop

async def _get_ch(client, ch_id):
    if not ch_id:
        return None
    ch = client.get_channel(ch_id)
    if ch is None:
        try:
            ch = await client.fetch_channel(ch_id)
        except Exception:
            ch = None
    return ch

def _build_trade_payload(c: dict, tier: str) -> dict:
    """Build a real signal payload for paper/auto-trader modules."""
    price = float(c.get("price") or 0)
    ind = c.get("ind") or {}
    atr = float(ind.get("atr") or price * 0.018)
    atr_pct = atr / price if price > 0 else 0.018
    levels = signal_engine.compute_levels(price, c.get("signal"), atr, atr_pct)
    return {
        "symbol": c.get("symbol"),
        "side": c.get("signal"),
        "entry": price,
        "tp1": levels.get("tp1", 0.0),
        "tp2": levels.get("tp2", 0.0),
        "tp3": levels.get("tp3", 0.0),
        "sl": levels.get("sl", 0.0),
        "source": tier.upper(),
        "confidence": c.get("conf") or "MEDIUM",
        "rr": c.get("rr", 0.0),
    }

async def _post_signal_side_effects(client, c: dict, tier: str):
    """Record only signals that were actually sent, with matching real levels."""
    symbol, sig, price = c["symbol"], c["signal"], float(c["price"])
    score = int(c.get("score") or 0)
    ind = c.get("ind") or {}
    atr = float(ind.get("atr") or price * 0.018)
    atr_pct = atr / price if price > 0 else 0.018
    levels = ind.get("_levels") if isinstance(ind.get("_levels"), dict) else None
    if not levels:
        levels = signal_engine.compute_levels(price, sig, atr, atr_pct)
        ind["_levels"] = levels

    if _HAS_TRACKER:
        _record_signal(symbol, sig, price, score=score, quality=signal_engine.quality_label(score), levels=levels)
    if _HAS_PAPER:
        paper_trading.hook_signal(symbol, sig, price)
    if _HAS_RESULTS:
        signal_results.register_signal(symbol, sig, price, atr=atr, score=score, tier=tier, levels=levels)
    if _HAS_DEMO_APP:
        demo_app.signal_received(symbol, sig, price)
    if _HAS_AUTO_TRADE:
        payload = _build_trade_payload(c, tier)
        await auto_trade_integration.handle_signal(payload, client)

async def _send_free(client, ch_id, symbol, sig, price, rsi, conf, ind, score):
    ch = await _get_ch(client, ch_id)
    if not ch:
        return

    embed = clean_signals.build_free_signal(
        symbol, sig, price, rsi, conf,
        atr=ind.get("atr") if ind else None,
        score=score,
    )
    view = paper_interactive.TryDemoButton(symbol, sig, price) if _HAS_PAPER else None

    if view:
        await ch.send(embed=embed, view=view)
    else:
        await ch.send(embed=embed)

    print(f"  [FREE SENT] {sig} {symbol} score={score}", flush=True)

async def _send_vip(client, vip_ch_id, symbol, sig, price, rsi, conf, ind, score, mtf):
    vip_ch = await _get_ch(client, vip_ch_id)

    # Build AI text
    ai_text = bot.ai_analysis(sig, price, rsi, symbol)

    # MTF summary
    mtf_badge, mtf_aligned = ("", 0)
    if _HAS_VIP and mtf:
        mtf_badge, mtf_aligned = _vip._mtf_summary(mtf, sig)

    sector = _vip.COIN_SECTORS.get(symbol, "Crypto") if _HAS_VIP else "Crypto"

    embed = clean_signals.build_vip_signal(
        symbol, sig, price, rsi, conf,
        ai_text=ai_text, ind=ind or {},
        mtf=mtf, smart_score=score,
        sector=sector,
    )

    # Chart
    chart_file = None
    try:
        chart_path = bot.generate_chart(
            bot.get_data(symbol, interval="5m"), symbol, sig
        )
        chart_file = discord.File(chart_path)
    except Exception:
        pass

    view = paper_interactive.TryDemoButton(symbol, sig, price) if _HAS_PAPER else None

    if vip_ch:
        kwargs = {}
        if chart_file: kwargs["file"] = chart_file
        if view:       kwargs["view"] = view
        await vip_ch.send(embed=embed, **kwargs)

    # Personal subscription channels
    if _HAS_TICKET:
        await coin_ticket.deliver_to_subscribers(client, symbol, embed)

    print(f"  [VIP SENT] {sig} {symbol} score={score} MTF={mtf_aligned}/3", flush=True)

async def smart_signal_loop(client, bot_module):
    """Main loop: scan → score → send best → sleep 15 min."""
    await client.wait_until_ready()
    await asyncio.sleep(20)

    print(f"[SMART LOOP] Started — FREE max {signal_engine.FREE_MAX_PER_DAY}/day | VIP max {signal_engine.VIP_MAX_PER_DAY}/day", flush=True)

    while True:
        now = datetime.now(timezone.utc)
        budget = signal_engine.budget_status()

        print(
            f"\n[SMART LOOP] {now.strftime('%H:%M UTC')} | "
            f"FREE {budget['free_sent']}/{budget['free_max']} | "
            f"VIP {budget['vip_sent']}/{budget['vip_max']}",
            flush=True
        )

        # Nothing to send today — skip until next interval
        if not budget["free_ok"] and not budget["vip_ok"]:
            print("[SMART LOOP] Daily budget exhausted — sleeping.", flush=True)
            await asyncio.sleep(SCAN_INTERVAL)
            continue

        # Outside active hours
        if not signal_engine.is_active_hour():
            print(f"[SMART LOOP] Outside active hours (08–22 UTC) — sleeping.", flush=True)
            await asyncio.sleep(SCAN_INTERVAL)
            continue

        free_ch_id = getattr(bot_module, "FREE_SIGNALS_CHANNEL", None)
        vip_ch_id  = getattr(bot_module, "VIP_SIGNALS_CHANNEL",  None)

        # ── Refresh BTC context ───────────────────────────────────────────
        try:
            df_btc = bot.get_data("BTCUSDT", interval="5m")
            if df_btc is not None:
                btc_sig, btc_px, _, _ = bot.get_signal_v2(df_btc)
                signal_engine.cache_btc_signal(btc_sig, price=btc_px)
        except Exception as e:
            print(f"[SMART LOOP] BTC fetch error: {e}", flush=True)

        # ── Scan FREE coins ───────────────────────────────────────────────
        free_candidates = []

        if budget["free_ok"]:
            for symbol in coins_config.FREE_SYMBOLS:
                try:
                    df  = bot.get_data(symbol, interval="5m")
                    if df is None or len(df) < 52:
                        continue
                    sig, price, rsi, conf = bot.get_signal_v2(df)
                    ind = bot.calc_indicators(df)
                    if ind and price:
                        ind["price"] = price
                        try:
                            _atr = float(ind.get("atr") or price * 0.018)
                            ind["_levels"] = signal_engine.compute_levels(price, sig, _atr, _atr / price if price else 0.018) if sig else None
                        except Exception:
                            pass

                    candidate = signal_engine.evaluate_candidate(
                        symbol, sig, price, ind or {}, tier="free"
                    )
                    if candidate:
                        candidate.update({"rsi": rsi, "conf": conf, "df": df})
                        free_candidates.append(candidate)
                        print(f"  [SCAN FREE] {symbol}: {sig} score={candidate['score']}", flush=True)
                    else:
                        print(f"  [SCAN FREE] {symbol}: {sig or 'NO SIG'} — not qualifying", flush=True)

                    await asyncio.sleep(0.5)   # rate limit
                except Exception as e:
                    print(f"  [SCAN FREE] {symbol} error: {e}", flush=True)

        # ── Scan VIP coins ────────────────────────────────────────────────
        vip_candidates = []

        if budget["vip_ok"]:
            for symbol in coins_config.ALL_VIP_SYMBOLS:
                try:
                    df  = bot.get_data(symbol, interval="5m")
                    if df is None or len(df) < 52:
                        continue
                    sig, price, rsi, conf = bot.get_signal_v2(df)
                    ind = bot.calc_indicators(df)
                    if ind and price:
                        ind["price"] = price
                        try:
                            _atr = float(ind.get("atr") or price * 0.018)
                            ind["_levels"] = signal_engine.compute_levels(price, sig, _atr, _atr / price if price else 0.018) if sig else None
                        except Exception:
                            pass

                    # MTF for VIP
                    mtf = None
                    if _HAS_VIP and sig:
                        try:
                            mtf = _vip.get_3tf_analysis(symbol)
                        except Exception:
                            mtf = None

                    candidate = signal_engine.evaluate_candidate(
                        symbol, sig, price, ind or {}, mtf=mtf, tier="vip"
                    )
                    if candidate:
                        candidate.update({"rsi": rsi, "conf": conf})
                        vip_candidates.append(candidate)
                        print(f"  [SCAN VIP]  {symbol}: {sig} score={candidate['score']} MTF={candidate['mtf_aligned']}/3", flush=True)
                    else:
                        print(f"  [SCAN VIP]  {symbol}: {sig or 'NO SIG'} — not qualifying", flush=True)

                    await asyncio.sleep(0.3)
                except Exception as e:
                    print(f"  [SCAN VIP] {symbol} error: {e}", flush=True)

        # ── Send VIP first, then FREE, so VIP does not get blocked by a
        # same-symbol free signal recorded moments earlier.
        vip_candidates.sort(key=lambda c: c["score"], reverse=True)
        sent_vip = 0
        sent_symbols: set[str] = set()

        for c in vip_candidates:
            if sent_vip >= 2:
                break   # max 2 VIP sends per scan round
            if signal_engine.approve_and_record(c):
                try:
                    await _send_vip(
                        client, vip_ch_id,
                        c["symbol"], c["signal"], c["price"],
                        c["rsi"], c["conf"], c["ind"], c["score"], c["mtf"],
                    )
                    await _post_signal_side_effects(client, c, "vip")
                    sent_symbols.add(c["symbol"])
                    sent_vip += 1
                    await asyncio.sleep(3)   # space out sends
                except Exception as e:
                    print(f"  [SEND VIP] Error: {e}", flush=True)

        # ── Send FREE: top 1 candidate this round, avoiding exact duplicates.
        free_candidates.sort(key=lambda c: c["score"], reverse=True)
        sent_free = 0

        for c in free_candidates:
            if sent_free >= 1:
                break
            if c["symbol"] in sent_symbols:
                continue
            if signal_engine.approve_and_record(c):
                try:
                    await _send_free(
                        client, free_ch_id,
                        c["symbol"], c["signal"], c["price"],
                        c["rsi"], c["conf"], c["ind"], c["score"],
                    )
                    await _post_signal_side_effects(client, c, "free")
                    sent_free += 1
                except Exception as e:
                    print(f"  [SEND FREE] Error: {e}", flush=True)

        total_qual = len(free_candidates) + len(vip_candidates)
        print(
            f"[SMART LOOP] Round done. {total_qual} qualified candidates. "
            f"Sent: {sent_free} FREE + {sent_vip} VIP. "
            f"Next in {SCAN_INTERVAL//60} min.",
            flush=True
        )

        await asyncio.sleep(SCAN_INTERVAL)
