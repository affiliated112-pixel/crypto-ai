"""Reliability/admin slash commands.

Registered from bot.py through _register_optional_command_modules().
"""
from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord import app_commands

import db
import market_data
import signal_engine
import runtime_state

try:
    import pandas as pd
    from ta.momentum import RSIIndicator, StochRSIIndicator, WilliamsRIndicator, ROCIndicator
    from ta.trend import MACD, EMAIndicator, ADXIndicator
    from ta.volatility import BollingerBands, AverageTrueRange
    from ta.volume import OnBalanceVolumeIndicator, ChaikinMoneyFlowIndicator
except Exception:  # pragma: no cover
    pd = None


CHANNEL_ENV_NAMES = [
    "FREE_SIGNALS_CHANNEL", "VIP_SIGNALS_CHANNEL", "ALERTS_CHANNEL", "STATUS_CHANNEL",
    "WELCOME_CHANNEL", "RULES_CHANNEL", "HOWTO_CHANNEL", "ANNOUNCEMENTS_CHANNEL",
    "MARKET_NEWS_CHANNEL", "GET_VIP_CHANNEL", "PERFORMANCE_CHANNEL",
]


def _is_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(getattr(interaction, "user", None), "guild_permissions", None)
    return bool(perms and (perms.administrator or perms.manage_guild))


async def _guard(interaction: discord.Interaction) -> bool:
    if not _is_admin(interaction):
        await interaction.response.send_message("Necesită Administrator sau Manage Server.", ephemeral=True)
        return False
    return True


def _fmt_ts(ts) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%d %b %H:%M UTC")
    except Exception:
        return str(ts)


def _norm_symbol(value: str) -> str:
    s = (value or "BTC").upper().replace("/", "").strip()
    if not s.endswith("USDT"):
        s += "USDT"
    return s


def _calc_indicators(df):
    if pd is None or df is None or len(df) < 60:
        return None
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"] if "volume" in df.columns else pd.Series([1.0] * len(df))
    try:
        rsi_s = RSIIndicator(close=close, window=14).rsi()
        rsi = float(rsi_s.iloc[-1])
        rsi_prev = float(rsi_s.iloc[-5])
        macd_obj = MACD(close=close)
        macd_hist_s = macd_obj.macd_diff()
        macd_hist = float(macd_hist_s.iloc[-1])
        macd_prev = float(macd_hist_s.iloc[-5])
        macd_line = float(macd_obj.macd().iloc[-1])
        macd_sig = float(macd_obj.macd_signal().iloc[-1])
        ema9 = float(EMAIndicator(close=close, window=9).ema_indicator().iloc[-1])
        ema20 = float(EMAIndicator(close=close, window=20).ema_indicator().iloc[-1])
        ema50 = float(EMAIndicator(close=close, window=50).ema_indicator().iloc[-1])
        ema200 = float(EMAIndicator(close=close, window=min(200, len(close)-1)).ema_indicator().iloc[-1])
        bb = BollingerBands(close=close, window=20, window_dev=2)
        bb_upper = float(bb.bollinger_hband().iloc[-1])
        bb_lower = float(bb.bollinger_lband().iloc[-1])
        bb_mid = float(bb.bollinger_mavg().iloc[-1])
        bb_pct = float(bb.bollinger_pband().iloc[-1])
        stoch = StochRSIIndicator(close=close, window=14, smooth1=3, smooth2=3)
        stoch_k = float(stoch.stochrsi_k().iloc[-1])
        stoch_d = float(stoch.stochrsi_d().iloc[-1])
        willr = float(WilliamsRIndicator(high=high, low=low, close=close, lbp=14).williams_r().iloc[-1])
        atr = float(AverageTrueRange(high=high, low=low, close=close, window=14).average_true_range().iloc[-1])
        adx_obj = ADXIndicator(high=high, low=low, close=close, window=14)
        adx = float(adx_obj.adx().iloc[-1])
        adx_pos = float(adx_obj.adx_pos().iloc[-1])
        adx_neg = float(adx_obj.adx_neg().iloc[-1])
        obv_s = OnBalanceVolumeIndicator(close=close, volume=volume).on_balance_volume()
        obv_up = bool(obv_s.iloc[-1] > obv_s.iloc[-20:].mean())
        cmf = float(ChaikinMoneyFlowIndicator(high=high, low=low, close=close, volume=volume, window=20).chaikin_money_flow().iloc[-1])
        typical = (high + low + close) / 3
        vwap = float((typical * volume).sum() / volume.sum()) if float(volume.sum()) > 0 else float(close.mean())
        roc = float(ROCIndicator(close=close, window=12).roc().iloc[-1])
        price_now = float(close.iloc[-1])
        price_prev = float(close.iloc[-5])
        bull_div = bool(price_now < price_prev and rsi > rsi_prev)
        bear_div = bool(price_now > price_prev and rsi < rsi_prev)
        vol_avg = float(volume.iloc[-20:].mean())
        vol_now = float(volume.iloc[-1])
        vol_surge = bool(vol_now > vol_avg * 1.5)
        highs20 = high.iloc[-20:]
        lows20 = low.iloc[-20:]
        struct_bull = bool(highs20.iloc[-1] > highs20.iloc[-10] and lows20.iloc[-1] > lows20.iloc[-10])
        struct_bear = bool(highs20.iloc[-1] < highs20.iloc[-10] and lows20.iloc[-1] < lows20.iloc[-10])
        struct_score = 1 if (struct_bull or struct_bear) else 0
        swing_high = float(high.iloc[-50:].max())
        swing_low = float(low.iloc[-50:].min())
        poc = price_now
        return {
            "rsi": rsi, "rsi_prev": rsi_prev,
            "macd_hist": macd_hist, "macd_line": macd_line, "macd_sig": macd_sig, "macd_prev": macd_prev,
            "ema9": ema9, "ema20": ema20, "ema50": ema50, "ema200": ema200,
            "bb_upper": bb_upper, "bb_lower": bb_lower, "bb_mid": bb_mid,
            "bb_pct": bb_pct, "bb_width": (bb_upper - bb_lower) / bb_mid if bb_mid else 0,
            "stoch_k": stoch_k, "stoch_d": stoch_d,
            "willr": willr, "atr": atr,
            "adx": adx, "adx_pos": adx_pos, "adx_neg": adx_neg,
            "obv_up": obv_up, "cmf": cmf, "vwap": vwap, "roc": roc,
            "bull_div": bull_div, "bear_div": bear_div,
            "struct_bull": struct_bull, "struct_bear": struct_bear, "struct_score": struct_score,
            "vol_surge": vol_surge, "vol_avg": vol_avg, "vol_now": vol_now,
            "price": price_now, "swing_high": swing_high, "swing_low": swing_low, "poc": poc,
        }
    except Exception:
        return None


def _signal_from_ind(ind):
    if not ind:
        return None, None, None, None
    rsi = ind["rsi"]
    price = ind["price"]
    buy = [
        rsi < 42, ind["macd_hist"] > 0, price > ind["ema50"] * 0.985,
        ind["bb_pct"] < 0.35, ind["stoch_k"] < 0.35 and ind["stoch_k"] >= ind["stoch_d"],
        ind["willr"] < -65, ind["obv_up"] or ind["cmf"] > 0.05,
        price < ind["vwap"] * 1.005, ind["adx"] > 18 and ind["adx_pos"] > ind["adx_neg"],
        ind["bull_div"] or (ind["ema9"] > ind["ema20"] and ind["struct_bull"]),
    ]
    sell = [
        rsi > 58, ind["macd_hist"] < 0, price < ind["ema50"] * 1.015,
        ind["bb_pct"] > 0.65, ind["stoch_k"] > 0.65 and ind["stoch_k"] <= ind["stoch_d"],
        ind["willr"] > -35, (not ind["obv_up"]) or ind["cmf"] < -0.05,
        price > ind["vwap"] * 0.995, ind["adx"] > 18 and ind["adx_neg"] > ind["adx_pos"],
        ind["bear_div"] or (ind["ema9"] < ind["ema20"] and ind["struct_bear"]),
    ]
    b, s = sum(buy), sum(sell)
    conf = "VERY HIGH" if max(b, s) >= 8 else "HIGH" if max(b, s) >= 6 else "MEDIUM" if max(b, s) >= 4 else "LOW"
    if b >= 3 and b > s:
        return "BUY", price, rsi, conf
    if s >= 3 and s > b:
        return "SELL", price, rsi, conf
    return None, price, rsi, None


def register(tree: app_commands.CommandTree, client: discord.Client):
    @tree.command(name="admin_status", description="Admin: bot health, DB, budgets and last events")
    async def admin_status(interaction: discord.Interaction):
        if not await _guard(interaction):
            return
        health = runtime_state.health_payload()
        settings = signal_engine.settings_summary()
        budget = signal_engine.budget_status()
        dbh = health.get("database", {})
        embed = discord.Embed(title="Admin Status", color=0x2ecc71, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="Discord", value=f"ready: `{client.is_ready()}`\nuser: `{client.user}`", inline=True)
        embed.add_field(name="Loop", value=f"alive: `{health.get('loop_alive')}`\nlast scan: `{health.get('last_scan_at') or '—'}`", inline=True)
        embed.add_field(name="Budget today", value=f"FREE `{budget['free_sent']}/{budget['free_max']}`\nVIP `{budget['vip_sent']}/{budget['vip_max']}`", inline=True)
        embed.add_field(name="Signal settings", value=f"mode `{settings['mode']}`\nFREE score `{settings['free_min_score']}` · VIP score `{settings['vip_min_score']}`", inline=True)
        embed.add_field(name="Database", value=f"backend `{dbh.get('backend')}`\nopen results `{dbh.get('results_30d',{}).get('open',0)}`", inline=True)
        embed.add_field(name="Last error", value=f"`{health.get('last_error') or 'none'}`", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tree.command(name="admin_last_blocked", description="Admin: last blocked signal decisions")
    @app_commands.describe(symbol="Optional coin, e.g. BTC or BTCUSDT", limit="How many rows")
    async def admin_last_blocked(interaction: discord.Interaction, symbol: str = "", limit: int = 10):
        if not await _guard(interaction):
            return
        rows = db.last_blocked(max(1, min(int(limit), 20)), _norm_symbol(symbol) if symbol else None)
        if not rows:
            await interaction.response.send_message("No blocked signals logged yet.", ephemeral=True)
            return
        lines = []
        for r in rows:
            lines.append(f"`{_fmt_ts(r.get('created_at'))}` **{r.get('symbol')} {r.get('side')}** `{r.get('tier')}` score `{r.get('score')}` — {r.get('reason')}")
        await interaction.response.send_message("\n".join(lines)[:1900], ephemeral=True)

    @tree.command(name="admin_recent_sent", description="Admin: recent sent/reserved signal records")
    @app_commands.describe(symbol="Optional coin, e.g. BTC", limit="How many rows")
    async def admin_recent_sent(interaction: discord.Interaction, symbol: str = "", limit: int = 10):
        if not await _guard(interaction):
            return
        rows = db.recent_sent(max(1, min(int(limit), 20)), _norm_symbol(symbol) if symbol else None)
        if not rows:
            await interaction.response.send_message("No sent signals logged yet.", ephemeral=True)
            return
        lines = []
        for r in rows:
            ts = r.get('sent_at') or r.get('reserved_at')
            lines.append(f"`{_fmt_ts(ts)}` **{r.get('symbol')} {r.get('side')}** `{r.get('tier')}` status `{r.get('status')}` score `{r.get('score')}` id `{r.get('signal_id')}`")
        await interaction.response.send_message("\n".join(lines)[:1900], ephemeral=True)

    @tree.command(name="admin_why", description="Admin: explain why a coin would/wouldn't send now")
    @app_commands.describe(symbol="Coin, e.g. BTC or BTCUSDT")
    async def admin_why(interaction: discord.Interaction, symbol: str):
        if not await _guard(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        sym = _norm_symbol(symbol)
        df = market_data.get_ohlcv(sym, interval="5m", limit=180)
        ind = _calc_indicators(df)
        sig, price, rsi, conf = _signal_from_ind(ind)
        if not ind or not price:
            await interaction.followup.send(f"{sym}: nu am destule date de piață pentru analiză.", ephemeral=True)
            return
        mtf = {"5m": {"signal": sig}}
        for tf in ("15m", "1h"):
            dft = market_data.get_ohlcv(sym, interval=tf, limit=180)
            indi = _calc_indicators(dft)
            st, _, _, _ = _signal_from_ind(indi)
            mtf[tf] = {"signal": st}
        free_ok, free_score, free_reason, free_candidate = signal_engine.check_signal_quality(sym, sig, price, ind, mtf=None, tier="free", consume=False)
        vip_ok, vip_score, vip_reason, vip_candidate = signal_engine.check_signal_quality(sym, sig, price, ind, mtf=mtf, tier="vip", consume=False)
        lines = [
            f"**{sym}** current setup",
            f"Signal: `{sig or 'NO SIGNAL'}` · Price: `{market_data.format_price(price)}` · RSI: `{rsi:.1f}` · Confidence: `{conf or '—'}`",
            f"MTF: 5m `{mtf['5m']['signal']}` · 15m `{mtf['15m']['signal']}` · 1h `{mtf['1h']['signal']}`",
            f"FREE: `{'ALLOW' if free_ok else 'BLOCK'}` · score `{free_score}/100` · {free_reason}",
            f"VIP: `{'ALLOW' if vip_ok else 'BLOCK'}` · score `{vip_score}/100` · {vip_reason}",
        ]
        for tier, cand in (("free", free_candidate), ("vip", vip_candidate)):
            if cand:
                cool = signal_engine.FREE_COOLDOWN_H if tier == "free" else signal_engine.VIP_COOLDOWN_H
                recent = db.has_recent_signal(sym, sig, tier, cool)
                lines.append(f"{tier.upper()} persistent cooldown: `{'active' if recent else 'clear'}` · R:R `{cand.get('rr')}`")
        await interaction.followup.send("\n".join(lines)[:1900], ephemeral=True)

    @tree.command(name="admin_channels", description="Admin: check configured Discord channel IDs and permissions")
    async def admin_channels(interaction: discord.Interaction):
        if not await _guard(interaction):
            return
        lines = []
        import os
        for name in CHANNEL_ENV_NAMES:
            raw = os.environ.get(name, "")
            if not raw:
                lines.append(f"`{name}` not set")
                continue
            try:
                cid = int(raw)
            except Exception:
                lines.append(f"`{name}` invalid: `{raw}`")
                continue
            ch = client.get_channel(cid)
            if ch is None:
                try:
                    ch = await client.fetch_channel(cid)
                except Exception as exc:
                    lines.append(f"`{name}` `{cid}` fetch failed: `{type(exc).__name__}`")
                    continue
            guild = getattr(ch, "guild", None)
            me = guild.me if guild else None
            perms = ch.permissions_for(me) if me else None
            ok = bool(perms and perms.send_messages and perms.embed_links)
            file_ok = bool(perms and perms.attach_files)
            lines.append(f"`{name}` <#{cid}> send/embed `{ok}` attach `{file_ok}`")
        await interaction.response.send_message("\n".join(lines)[:1900], ephemeral=True)
