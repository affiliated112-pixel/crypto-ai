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
                btc_sig, _, _, _ = bot.get_signal_v2(df_btc)
                signal_engine.cache_btc_signal(btc_sig)
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

        # ── Send FREE: top 1 candidate this round (budget permitting) ─────
        # Sort by score desc, pick the best
        free_candidates.sort(key=lambda c: c["score"], reverse=True)

        for c in free_candidates[:1]:   # send at most 1 FREE per scan round
            if signal_engine.approve_and_record(c):
                try:
                    await _send_free(
                        client, free_ch_id,
                        c["symbol"], c["signal"], c["price"],
                        c["rsi"], c["conf"], c["ind"], c["score"],
                    )
                    # Track
                    if _HAS_TRACKER:
                        _record_signal(c["symbol"], c["signal"], float(c["price"]))
                    if _HAS_PAPER:
                        paper_trading.hook_signal(c["symbol"], c["signal"], float(c["price"]))
                except Exception as e:
                    print(f"  [SEND FREE] Error: {e}", flush=True)

        # ── Send VIP: top 1-2 candidates this round ───────────────────────
        vip_candidates.sort(key=lambda c: c["score"], reverse=True)

        sent_vip = 0
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
                    if _HAS_TRACKER:
                        _record_signal(c["symbol"], c["signal"], float(c["price"]))
                    if _HAS_PAPER:
                        paper_trading.hook_signal(c["symbol"], c["signal"], float(c["price"]))
                    sent_vip += 1
                    await asyncio.sleep(3)   # space out sends
                except Exception as e:
                    print(f"  [SEND VIP] Error: {e}", flush=True)

        total_qual = len(free_candidates) + len(vip_candidates)
        print(
            f"[SMART LOOP] Round done. {total_qual} qualified candidates. "
            f"Sent: {min(len(free_candidates),1)} FREE + {sent_vip} VIP. "
            f"Next in {SCAN_INTERVAL//60} min.",
            flush=True
        )

        await asyncio.sleep(SCAN_INTERVAL)
