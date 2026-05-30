"""on_demand.py — /signal command: real-time deep analysis for any coin.

User picks a coin → bot runs FULL analysis RIGHT NOW and returns:
  - The signal (BUY / SELL / NO CLEAR SETUP)
  - Why (which indicators say what)
  - Entry, SL, TP levels (ATR-based, real numbers)
  - Quality score with honest explanation
  - Chart (VIP only)

FREE: 6 coins, basic analysis, 1-TF
VIP:  30 coins, 3-TF, Smart Score, Fibonacci, Ichimoku, chart

Honesty rule: if no clear setup → say so. Never force a signal.
"""

import asyncio
import discord
from discord import app_commands
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

# ─── COIN AUTOCOMPLETE ────────────────────────────────────────────────────────

async def coin_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    """Autocomplete: type 'BT' → shows BTCUSDT, etc."""
    is_vip = any(r.name.upper() == "VIP" for r in getattr(interaction.user, "roles", []))
    pool   = coins_config.ALL_VIP_SYMBOLS if is_vip else coins_config.FREE_SYMBOLS

    results = []
    cur = current.upper().replace("USDT", "")
    for sym in pool:
        coin = sym.replace("USDT", "")
        meta = coins_config.COIN_META.get(sym, {})
        name = meta.get("name", coin)
        if cur in coin or cur in name.upper():
            label = f"{meta.get('emoji','')} {name}"
            results.append(app_commands.Choice(name=label, value=sym))
        if len(results) >= 25:
            break
    return results

# ─── INDICATOR BREAKDOWN (honest, clear) ─────────────────────────────────────

def _indicator_breakdown(ind: dict, signal: str) -> str:
    """
    Shows EXACTLY which indicators say BUY and which say SELL.
    No hiding. No spin. Just facts.
    """
    if not ind:
        return "_No data_"

    is_buy = signal == "BUY"
    rsi    = ind.get("rsi", 50)
    macd_h = ind.get("macd_hist", 0)
    adx    = ind.get("adx", 20)
    adx_p  = ind.get("adx_pos", 10)
    adx_n  = ind.get("adx_neg", 10)
    cmf    = ind.get("cmf", 0)
    willr  = ind.get("willr", -50)
    bb_pct = ind.get("bb_pct", 0.5)
    stoch  = ind.get("stoch_k", 0.5)
    obv_up = ind.get("obv_up", False)
    vwap   = ind.get("vwap", 0)
    ema200 = ind.get("ema200", 0)
    price  = ind.get("price", ind.get("vwap", 0))
    vol_surge = ind.get("vol_surge", False)
    struct_bull = ind.get("struct_bull", False)
    struct_bear = ind.get("struct_bear", False)
    bull_div = ind.get("bull_div", False)
    bear_div = ind.get("bear_div", False)

    def check(ok: bool) -> str:
        return "🟢" if ok else "🔴"

    lines = [
        f"{check(rsi < 40 if is_buy else rsi > 60)} **RSI** `{rsi:.1f}` — {'oversold ✓' if rsi < 40 else ('overbought ✓' if rsi > 60 else 'neutral ✗')}",
        f"{check((macd_h > 0) == is_buy)} **MACD** `{macd_h:+.4f}` — {'bullish ✓' if macd_h > 0 else 'bearish ✓' if not is_buy else 'bearish ✗'}",
        f"{check(adx > 20 and ((adx_p > adx_n) == is_buy))} **ADX** `{adx:.1f}` — trend {'strong ✓' if adx > 25 else 'weak ✗'}, DI {'+ dominant ✓' if adx_p > adx_n else '- dominant ✓' if not is_buy else '- dominant ✗'}",
        f"{check((cmf > 0.05) == is_buy)} **CMF** `{cmf:+.3f}` — {'buying pressure ✓' if cmf > 0.05 else ('selling pressure ✓' if not is_buy else 'selling ✗')}",
        f"{check(willr < -70 if is_buy else willr > -30)} **Williams %R** `{willr:.0f}` — {'oversold ✓' if willr < -70 else ('overbought ✓' if willr > -30 else 'neutral ✗')}",
        f"{check(bb_pct < 0.25 if is_buy else bb_pct > 0.75)} **Bollinger** `{bb_pct:.2f}` — {'lower band ✓' if bb_pct < 0.25 else ('upper band ✓' if bb_pct > 0.75 else 'middle ✗')}",
        f"{check(stoch < 0.25 if is_buy else stoch > 0.75)} **StochRSI** `{stoch:.2f}` — {'oversold ✓' if stoch < 0.25 else ('overbought ✓' if stoch > 0.75 else 'neutral ✗')}",
        f"{check(obv_up == is_buy)} **OBV** — {'accumulation ✓' if obv_up else 'distribution ✓' if not is_buy else 'distribution ✗'}",
        f"{check((price < vwap) == is_buy)} **VWAP** — price {'below (value zone) ✓' if price < vwap else 'above (premium) ✓' if not is_buy else 'above ✗'}",
        f"{check((price > ema200) == is_buy)} **EMA200** — price {'above (bull trend) ✓' if price > ema200 else 'below (bear trend) ✓' if not is_buy else 'below ✗'}",
    ]

    # Bonus lines
    if bull_div and is_buy:
        lines.append("🟢 **Bullish Divergence** detected ✓")
    if bear_div and not is_buy:
        lines.append("🟢 **Bearish Divergence** detected ✓")
    if vol_surge:
        lines.append("🟢 **Volume Surge** 2.5x above average ✓")
    if (struct_bull and is_buy) or (struct_bear and not is_buy):
        lines.append("🟢 **Market Structure** confirms direction ✓")

    green = sum(1 for l in lines if l.startswith("🟢"))
    red   = sum(1 for l in lines if l.startswith("🔴"))
    lines.append(f"\n**{green} confirm** · **{red} against** out of {green+red} indicators")

    return "\n".join(lines)

def _no_signal_embed(symbol: str, price: float, rsi: float, ind: dict | None) -> discord.Embed:
    """Honest 'no clear setup' response."""
    coin  = symbol.replace("USDT", "")
    emoji = coins_config.COIN_EMOJI.get(symbol, "🪙")
    logo  = coins_config.COIN_LOGOS.get(symbol)

    embed = discord.Embed(
        title=f"{emoji} {coin} — ⏳ No Clear Setup Right Now",
        description=(
            "The indicators are **mixed or neutral** at this moment.\n"
            "Sending a signal here would be gambling, not trading.\n"
            "**Wait for a clear setup — patience is edge.**"
        ),
        color=0x636E72,  # Grey
        timestamp=datetime.now(timezone.utc),
    )
    if logo:
        embed.set_thumbnail(url=logo)

    if ind:
        rsi_v = ind.get("rsi", rsi)
        macd_h = ind.get("macd_hist", 0)
        adx = ind.get("adx", 20)
        embed.add_field(
            name="Current State",
            value=(
                f"**RSI:** `{rsi_v:.1f}` — {'Overbought 🔴' if rsi_v > 65 else 'Oversold 🟢' if rsi_v < 35 else 'Neutral ⚪'}\n"
                f"**MACD:** `{macd_h:+.4f}` — {'Bullish 🟢' if macd_h > 0 else 'Bearish 🔴'}\n"
                f"**ADX:** `{adx:.1f}` — {'Trending 📈' if adx > 25 else 'Ranging ↔️'}"
            ),
            inline=False,
        )
    embed.add_field(
        name="What to do",
        value="Check again in 15–30 min or wait for the bot's automatic signal.",
        inline=False,
    )
    embed.set_footer(text="⚠️ Not financial advice — only trade clear setups")
    return embed

# ─── MAIN COMMAND BUILDER ─────────────────────────────────────────────────────

def register_commands(tree: app_commands.CommandTree):
    # Replace bot.py's older /signal command with the richer on-demand version.
    for _name in ("signal", "scan"):
        try:
            tree.remove_command(_name)
        except Exception:
            pass

    @tree.command(
        name="signal",
        description="📊 Get a real-time signal for any coin right now"
    )
    @app_commands.describe(coin="Which coin? (type to search)")
    @app_commands.autocomplete(coin=coin_autocomplete)
    async def slash_signal(interaction: discord.Interaction, coin: str):
        await interaction.response.defer(ephemeral=False)

        symbol = coin.upper()
        if not symbol.endswith("USDT"):
            symbol += "USDT"

        is_vip = any(r.name.upper() == "VIP" for r in getattr(interaction.user, "roles", []))

        # ── VIP-only coins check ──────────────────────────────────────
        coin_meta = coins_config.COIN_META.get(symbol)
        if coin_meta is None:
            await interaction.followup.send(
                f"❌ `{symbol}` is not in our supported list.\n"
                f"Free coins: {', '.join(s.replace('USDT','') for s in coins_config.FREE_SYMBOLS)}\n"
                f"💎 VIP coins: {', '.join(s.replace('USDT','') for s in coins_config.VIP_ONLY_SYMBOLS[:10])}…",
                ephemeral=True,
            )
            return

        if coin_meta["tier"] == "vip" and not is_vip:
            await interaction.followup.send(
                f"⚠️ **{symbol.replace('USDT','')}** is a VIP-only coin.\n"
                f"Upgrade to 💎 **VIP** to access 30 coins + deep analysis.",
                ephemeral=True,
            )
            return

        # ── Thinking message ─────────────────────────────────────────
        coin_name = coin_meta.get("name", symbol)
        await interaction.followup.send(
            f"🔍 Analyzing **{coin_name}** — running {('3-TF + 15 indicators' if is_vip else '10 indicators')}…",
            ephemeral=False,
        )

        try:
            # ── Fetch data ────────────────────────────────────────────
            df5m = bot.get_data(symbol, interval="5m")
            if df5m is None or len(df5m) < 52:
                await interaction.channel.send(
                    f"❌ Could not fetch data for `{symbol}`. Try again in a moment."
                )
                return

            sig, price, rsi, conf = bot.get_signal_v2(df5m)
            ind = bot.calc_indicators(df5m)

            # Inject price into ind for indicator breakdown
            if ind:
                ind["price"] = price

            # ── BTC context ───────────────────────────────────────────
            btc_signal = signal_engine.get_cached_btc_signal()
            if symbol != "BTCUSDT" and btc_signal is None:
                df_btc = bot.get_data("BTCUSDT", interval="5m")
                if df_btc is not None:
                    btc_sig_raw, btc_price_raw, _, _ = bot.get_signal_v2(df_btc)
                    signal_engine.cache_btc_signal(btc_sig_raw, price=btc_price_raw)
                    btc_signal = btc_sig_raw

            # ── No signal case ────────────────────────────────────────
            if not sig:
                embed = _no_signal_embed(symbol, price or 0, rsi or 50, ind)
                await interaction.channel.send(embed=embed)
                return

            # ── Quality gate ──────────────────────────────────────────
            # On-demand checks must NOT consume the auto-signal daily budget.
            if is_vip:
                mtf = _vip.get_3tf_analysis(symbol) if _HAS_VIP else None
                allow, score, reason, _candidate = signal_engine.check_signal_quality(
                    symbol, sig, price, ind or {}, mtf=mtf, tier="vip", consume=False
                )
            else:
                mtf = None
                allow, score, reason, _candidate = signal_engine.check_signal_quality(
                    symbol, sig, price, ind or {}, mtf=None, tier="free", consume=False
                )

            # ── Not enough quality ────────────────────────────────────
            if not allow:
                embed = discord.Embed(
                    title=f"{coins_config.COIN_EMOJI.get(symbol,'🪙')} {symbol.replace('USDT','')} — ⚠️ Signal Exists but Quality is Low",
                    description=(
                        f"There is a **{sig}** signal forming, but it doesn't meet our quality threshold.\n"
                        f"**Reason:** `{reason}`\n"
                        f"**Quality Score:** `{score}/100` (min {signal_engine.VIP_MIN_SCORE if is_vip else signal_engine.FREE_MIN_SCORE} required)\n\n"
                        f"Trading a low-quality setup means lower probability of profit.\n"
                        f"**Recommendation: Wait.**"
                    ),
                    color=0xFFA502,  # Orange = caution
                    timestamp=datetime.now(timezone.utc),
                )
                if ind:
                    embed.add_field(
                        name="Indicators",
                        value=_indicator_breakdown(ind, sig),
                        inline=False,
                    )
                embed.set_footer(text="⚠️ Not financial advice")
                await interaction.channel.send(embed=embed)
                return

            # ── HIGH QUALITY SIGNAL — send full analysis ──────────────
            atr = ind.get("atr", price * 0.018) if ind else price * 0.018

            if is_vip and _HAS_VIP:
                # Full VIP deep embed
                ai_text = bot.ai_analysis(sig, price, rsi, symbol)

                # MTF summary
                mtf_badge = ""
                mtf_aligned = 0
                if mtf:
                    mtf_badge, mtf_aligned = _vip._mtf_summary(mtf, sig)

                smart_score = _vip._smart_score(ind, sig, mtf_aligned)
                sector      = _vip.COIN_SECTORS.get(symbol, "Crypto")

                embed = clean_signals.build_vip_signal(
                    symbol, sig, price, rsi, conf,
                    ai_text=ai_text, ind=ind,
                    mtf=mtf, smart_score=smart_score,
                    sector=sector,
                )

                # Add full indicator breakdown
                embed.add_field(
                    name="🔍 Full Indicator Breakdown",
                    value=_indicator_breakdown(ind, sig),
                    inline=False,
                )

                # Chart
                chart_file = None
                try:
                    chart_path = bot.generate_chart(df5m, symbol, sig)
                    chart_file = discord.File(chart_path)
                except Exception:
                    pass

                embed.set_author(name=f"💎 VIP On-Demand — {coin_name}")
                if chart_file:
                    await interaction.channel.send(embed=embed, file=chart_file)
                else:
                    await interaction.channel.send(embed=embed)

            else:
                # FREE embed — clean, clear, no clutter
                embed = clean_signals.build_free_signal(
                    symbol, sig, price, rsi, conf, atr=atr
                )
                # Add indicator summary (fewer details for FREE)
                is_buy = sig == "BUY"
                ind_summary = (
                    f"🟢 RSI: `{rsi:.1f}` ({'oversold' if rsi < 40 else 'neutral'})\n"
                    f"{'🟢' if (ind.get('macd_hist',0)>0)==is_buy else '🔴'} MACD: `{ind.get('macd_hist',0):+.4f}`\n"
                    f"{'🟢' if ind.get('adx',20)>20 else '🔴'} ADX: `{ind.get('adx',20):.1f}` ({'trending' if ind.get('adx',20)>20 else 'ranging'})\n"
                    f"{'🟢' if (ind.get('cmf',0)>0)==is_buy else '🔴'} CMF: `{ind.get('cmf',0):+.3f}`\n"
                    f"**Quality Score:** `{score}/100`"
                ) if ind else f"**Quality Score:** `{score}/100`"

                embed.add_field(name="📊 Key Indicators", value=ind_summary, inline=False)
                embed.set_author(name=f"📊 On-Demand Signal — {coin_name}")
                await interaction.channel.send(embed=embed)

        except Exception as e:
            print(f"[on_demand] error for {symbol}: {e}", flush=True)
            await interaction.channel.send(
                f"❌ Error analyzing `{symbol}`: `{e}`\nTry again in a moment."
            )

    @tree.command(
        name="scan",
        description="🔍 Scan all your coins and show current market status"
    )
    async def slash_scan(interaction: discord.Interaction):
        """Quick scan of all FREE (or VIP) coins — shows RSI + direction for each."""
        await interaction.response.defer(ephemeral=True)

        is_vip = any(r.name.upper() == "VIP" for r in getattr(interaction.user, "roles", []))
        coins  = coins_config.ALL_VIP_SYMBOLS if is_vip else coins_config.FREE_SYMBOLS

        embed = discord.Embed(
            title=f"🔍 Market Scan — {'VIP (30 coins)' if is_vip else 'Free (6 coins)'}",
            description="Current indicator state for all monitored coins.",
            color=0x2F3542,
            timestamp=datetime.now(timezone.utc),
        )

        lines = []
        for symbol in coins:
            try:
                df = bot.get_data(symbol, interval="5m")
                if df is None:
                    continue
                sig, price, rsi, conf = bot.get_signal_v2(df)
                ind = bot.calc_indicators(df)
                coin    = symbol.replace("USDT","")
                emoji   = coins_config.COIN_EMOJI.get(symbol, "🪙")
                sig_icon = "🟢" if sig == "BUY" else ("🔴" if sig == "SELL" else "⚪")
                rsi_s   = f"RSI {rsi:.0f}" if rsi else "—"
                adx_s   = f"ADX {ind.get('adx',0):.0f}" if ind else ""
                lines.append(
                    f"{sig_icon} **{emoji}{coin}** `${price:,.2f}` | {rsi_s} | {adx_s} | {sig or 'No signal'}"
                )
            except Exception:
                continue

        if lines:
            # Split into chunks (Discord field limit)
            chunk = "\n".join(lines[:10])
            embed.add_field(name="Coins", value=chunk, inline=False)
            if len(lines) > 10:
                embed.add_field(name="More", value="\n".join(lines[10:20]), inline=False)
            if len(lines) > 20:
                embed.add_field(name="More", value="\n".join(lines[20:]), inline=False)
        else:
            embed.add_field(name="Status", value="Could not fetch data. Try again.", inline=False)

        embed.set_footer(text="Use /signal [coin] for full analysis on any coin | Not financial advice")
        await interaction.followup.send(embed=embed, ephemeral=True)
