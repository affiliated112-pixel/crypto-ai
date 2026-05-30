"""Backtest threshold calibration for the Discord signal bot.

Runs a simple historical candle simulation using the same quality score and
ATR level engine used by the live bot. It is designed for calibration, not as a
promise of future results.

Examples:
  python backtest_thresholds.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --interval 5m --limit 1000
  python backtest_thresholds.py --tier vip --min-score-start 45 --min-score-stop 75 --rr-values 1.5,1.8,2.0
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# The backtest should not touch persistent live cooldown/budget state.
os.environ.setdefault("USE_PERSISTENT_STATE", "0")

import pandas as pd

try:
    from ta.momentum import RSIIndicator, StochRSIIndicator, WilliamsRIndicator
    from ta.trend import MACD, ADXIndicator, EMAIndicator
    from ta.volatility import AverageTrueRange, BollingerBands
    from ta.volume import ChaikinMoneyFlowIndicator, OnBalanceVolumeIndicator, VolumeWeightedAveragePrice
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"Missing dependency 'ta'. Install requirements.txt first. Details: {exc}")

import coins_config
import market_data
import signal_engine


@dataclass
class Candidate:
    symbol: str
    index: int
    side: str
    price: float
    score: int
    rr: float
    levels: dict


@dataclass
class TradeResult:
    symbol: str
    side: str
    score: int
    rr: float
    result: str
    pnl_pct: float
    bars: int


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def calc_indicators(df: pd.DataFrame) -> dict | None:
    """Return indicator dict shaped for signal_engine.compute_quality_score."""
    if df is None or len(df) < 80:
        return None
    work = df.copy()
    for col in ("open", "high", "low", "close", "volume"):
        work[col] = _num(work[col])
    work = work.dropna(subset=["open", "high", "low", "close"])
    if len(work) < 80:
        return None

    close = work["close"]
    high = work["high"]
    low = work["low"]
    volume = work.get("volume", pd.Series([0.0] * len(work), index=work.index)).fillna(0)
    price = float(close.iloc[-1])

    try:
        rsi = RSIIndicator(close, window=14).rsi()
        macd = MACD(close)
        macd_h = macd.macd_diff()
        adx_i = ADXIndicator(high, low, close, window=14)
        atr = AverageTrueRange(high, low, close, window=14).average_true_range()
        bb = BollingerBands(close, window=20, window_dev=2)
        stoch = StochRSIIndicator(close, window=14).stochrsi_k()
        willr = WilliamsRIndicator(high, low, close, lbp=14).williams_r()
        cmf = ChaikinMoneyFlowIndicator(high, low, close, volume, window=20).chaikin_money_flow()
        obv = OnBalanceVolumeIndicator(close, volume).on_balance_volume()
        ema9 = EMAIndicator(close, window=9).ema_indicator()
        ema20 = EMAIndicator(close, window=20).ema_indicator()
        ema50 = EMAIndicator(close, window=50).ema_indicator()
        ema200 = EMAIndicator(close, window=200).ema_indicator() if len(work) >= 210 else ema50
        try:
            vwap = VolumeWeightedAveragePrice(high, low, close, volume, window=20).volume_weighted_average_price()
        except Exception:
            vwap = close.rolling(20).mean()
    except Exception:
        return None

    bb_low = bb.bollinger_lband().iloc[-1]
    bb_high = bb.bollinger_hband().iloc[-1]
    width = float(bb_high - bb_low) if not math.isnan(float(bb_high - bb_low)) else 0.0
    bb_pct = 0.5 if width <= 0 else float((price - bb_low) / width)

    macd_now = float(macd_h.iloc[-1]) if not pd.isna(macd_h.iloc[-1]) else 0.0
    macd_prev = float(macd_h.iloc[-2]) if len(macd_h) > 1 and not pd.isna(macd_h.iloc[-2]) else macd_now
    obv_now = float(obv.iloc[-1]) if not pd.isna(obv.iloc[-1]) else 0.0
    obv_prev = float(obv.iloc[-5]) if len(obv) >= 5 and not pd.isna(obv.iloc[-5]) else obv_now
    vol_ma = float(volume.rolling(20).mean().iloc[-1] or 0.0)
    vol_now = float(volume.iloc[-1] or 0.0)

    # Lightweight structure approximation: recent higher-high/higher-low or lower-high/lower-low.
    recent_high = high.tail(12)
    recent_low = low.tail(12)
    prev_high = high.iloc[-24:-12] if len(high) >= 24 else high.tail(12)
    prev_low = low.iloc[-24:-12] if len(low) >= 24 else low.tail(12)
    struct_bull = bool(recent_high.max() > prev_high.max() and recent_low.min() > prev_low.min())
    struct_bear = bool(recent_high.max() < prev_high.max() and recent_low.min() < prev_low.min())
    struct_score = 2 if (struct_bull or struct_bear) else 0

    def last(series: pd.Series, default: float = 0.0) -> float:
        value = series.iloc[-1]
        return float(default if pd.isna(value) else value)

    return {
        "price": price,
        "rsi": last(rsi, 50.0),
        "macd_hist": macd_now,
        "macd_prev": macd_prev,
        "adx": last(adx_i.adx(), 20.0),
        "adx_pos": last(adx_i.adx_pos(), 10.0),
        "adx_neg": last(adx_i.adx_neg(), 10.0),
        "atr": max(last(atr, price * 0.02), 1e-12),
        "bb_pct": max(0.0, min(1.0, bb_pct)),
        "bb_width": width / price if price else 0.0,
        "stoch_k": last(stoch, 0.5),
        "willr": last(willr, -50.0),
        "cmf": last(cmf, 0.0),
        "obv_up": obv_now > obv_prev,
        "vol_surge": bool(vol_ma > 0 and vol_now > vol_ma * 1.8),
        "ema9": last(ema9, price),
        "ema20": last(ema20, price),
        "ema50": last(ema50, price),
        "ema200": last(ema200, price),
        "vwap": last(vwap, price),
        "struct_bull": struct_bull,
        "struct_bear": struct_bear,
        "struct_score": struct_score,
        "poc": float(close.tail(50).median()),
        "bull_div": False,
        "bear_div": False,
    }


def choose_candidate(symbol: str, df: pd.DataFrame, idx: int) -> Candidate | None:
    window = df.iloc[: idx + 1]
    ind = calc_indicators(window)
    if not ind:
        return None
    price = float(ind["price"])
    atr = float(ind.get("atr") or price * 0.02)
    volatility_pct = atr / price if price else 0.02
    scores = {
        "BUY": signal_engine.compute_quality_score(ind, "BUY"),
        "SELL": signal_engine.compute_quality_score(ind, "SELL"),
    }
    side = max(scores, key=scores.get)
    score = scores[side]
    if score <= 0:
        return None
    levels = signal_engine.compute_levels(price, side, atr, volatility_pct)
    rr = float(levels.get("rr2") or signal_engine.compute_rr(price, side, atr, volatility_pct))
    return Candidate(symbol=symbol, index=idx, side=side, price=price, score=score, rr=rr, levels=levels)


def simulate_trade(c: Candidate, future: pd.DataFrame, fee_pct: float, slippage_pct: float) -> TradeResult:
    """Simulate TP1/TP2/TP3 partials with break-even after TP1."""
    remaining = 1.0
    pnl = 0.0
    hit_tp1 = hit_tp2 = hit_tp3 = False
    be_active = False
    entry = c.price
    sl = float(c.levels["sl"])
    targets = [("TP1", float(c.levels["tp1"]), 0.40), ("TP2", float(c.levels["tp2"]), 0.30), ("TP3", float(c.levels["tp3"]), 0.30)]
    close_cost = (fee_pct + slippage_pct) / 100.0

    def side_pnl(exit_price: float, amount: float) -> float:
        raw = ((exit_price - entry) / entry) if c.side == "BUY" else ((entry - exit_price) / entry)
        return (raw - close_cost) * amount * 100.0

    for bars, row in enumerate(future.itertuples(index=False), start=1):
        high = float(getattr(row, "high"))
        low = float(getattr(row, "low"))
        close = float(getattr(row, "close"))

        if c.side == "BUY":
            sl_hit = low <= (entry if be_active else sl)
            tp_hits = [(name, px, pct) for name, px, pct in targets if high >= px]
        else:
            sl_hit = high >= (entry if be_active else sl)
            tp_hits = [(name, px, pct) for name, px, pct in targets if low <= px]

        # Conservative assumption: if SL and TP are both touched in same candle before TP1, count SL first.
        if sl_hit and not be_active and not (hit_tp1 or hit_tp2 or hit_tp3):
            pnl += side_pnl(sl, remaining)
            return TradeResult(c.symbol, c.side, c.score, c.rr, "SL", pnl, bars)

        for name, px, pct in tp_hits:
            if name == "TP1" and not hit_tp1:
                amount = min(remaining, pct)
                pnl += side_pnl(px, amount)
                remaining -= amount
                hit_tp1 = True
                be_active = True
            elif name == "TP2" and hit_tp1 and not hit_tp2:
                amount = min(remaining, pct)
                pnl += side_pnl(px, amount)
                remaining -= amount
                hit_tp2 = True
            elif name == "TP3" and hit_tp1 and hit_tp2 and not hit_tp3:
                amount = remaining
                pnl += side_pnl(px, amount)
                remaining = 0.0
                hit_tp3 = True
                return TradeResult(c.symbol, c.side, c.score, c.rr, "TP3", pnl, bars)

        if sl_hit and be_active and remaining > 0:
            pnl += side_pnl(entry, remaining)
            label = "BE" if hit_tp1 else "SL"
            return TradeResult(c.symbol, c.side, c.score, c.rr, label, pnl, bars)

        if remaining <= 0:
            return TradeResult(c.symbol, c.side, c.score, c.rr, "TP3", pnl, bars)

    # Expired: close at the last available close.
    if len(future):
        pnl += side_pnl(float(future.iloc[-1]["close"]), remaining)
    label = "TP2" if hit_tp2 else "TP1" if hit_tp1 else "EXPIRED"
    return TradeResult(c.symbol, c.side, c.score, c.rr, label, pnl, len(future))


def parse_csv_list(raw: str, cast=str):
    return [cast(x.strip()) for x in raw.split(",") if x.strip()]


def grid_values(start: int, stop: int, step: int) -> list[int]:
    return list(range(int(start), int(stop) + 1, int(step)))


def summarize(results: list[TradeResult]) -> dict:
    if not results:
        return {
            "trades": 0, "win_rate": 0.0, "avg_pnl_pct": 0.0, "total_pnl_pct": 0.0,
            "tp1_rate": 0.0, "tp2_rate": 0.0, "tp3_rate": 0.0, "sl_rate": 0.0, "be_rate": 0.0,
            "avg_bars": 0.0,
        }
    wins = [r for r in results if r.pnl_pct > 0]
    tp1_plus = [r for r in results if r.result in {"TP1", "TP2", "TP3", "BE"}]
    tp2_plus = [r for r in results if r.result in {"TP2", "TP3"}]
    tp3 = [r for r in results if r.result == "TP3"]
    sl = [r for r in results if r.result == "SL"]
    be = [r for r in results if r.result == "BE"]
    return {
        "trades": len(results),
        "win_rate": round(len(wins) / len(results) * 100, 2),
        "avg_pnl_pct": round(statistics.mean(r.pnl_pct for r in results), 4),
        "total_pnl_pct": round(sum(r.pnl_pct for r in results), 4),
        "tp1_rate": round(len(tp1_plus) / len(results) * 100, 2),
        "tp2_rate": round(len(tp2_plus) / len(results) * 100, 2),
        "tp3_rate": round(len(tp3) / len(results) * 100, 2),
        "sl_rate": round(len(sl) / len(results) * 100, 2),
        "be_rate": round(len(be) / len(results) * 100, 2),
        "avg_bars": round(statistics.mean(r.bars for r in results), 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest score/R:R thresholds for the crypto Discord bot")
    parser.add_argument("--tier", choices=["free", "vip"], default="vip")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols. Default: FREE_SYMBOLS or ALL_VIP_SYMBOLS")
    parser.add_argument("--interval", default="5m")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--warmup", type=int, default=220)
    parser.add_argument("--lookahead", type=int, default=72)
    parser.add_argument("--stride", type=int, default=6, help="Evaluate every N candles to avoid over-sampling")
    parser.add_argument("--cooldown-bars", type=int, default=24)
    parser.add_argument("--min-score-start", type=int, default=35)
    parser.add_argument("--min-score-stop", type=int, default=75)
    parser.add_argument("--min-score-step", type=int, default=5)
    parser.add_argument("--rr-values", default="1.3,1.5,1.6,1.8,2.0,2.2")
    parser.add_argument("--fee-pct", type=float, default=float(os.environ.get("TRACKER_FEE_PCT", "0.10")))
    parser.add_argument("--slippage-pct", type=float, default=float(os.environ.get("TRACKER_SLIPPAGE_PCT", "0.05")))
    parser.add_argument("--output", default="backtest_results.csv")
    args = parser.parse_args()

    if args.symbols.strip():
        symbols = parse_csv_list(args.symbols.upper())
    else:
        symbols = coins_config.FREE_SYMBOLS if args.tier == "free" else coins_config.ALL_VIP_SYMBOLS

    print(f"Backtest started: tier={args.tier}, symbols={len(symbols)}, interval={args.interval}, limit={args.limit}")
    raw_candidates: list[tuple[Candidate, pd.DataFrame]] = []
    last_by_symbol_side: dict[tuple[str, str], int] = {}

    for symbol in symbols:
        df = market_data.get_ohlcv(symbol, interval=args.interval, limit=args.limit)
        if df is None or len(df) < args.warmup + args.lookahead:
            print(f"  {symbol}: skipped, not enough data")
            continue
        df = df.reset_index(drop=True)
        print(f"  {symbol}: {len(df)} candles from {market_data.last_source(symbol)}")
        for idx in range(args.warmup, len(df) - args.lookahead, args.stride):
            cand = choose_candidate(symbol, df, idx)
            if not cand:
                continue
            key = (symbol, cand.side)
            last_idx = last_by_symbol_side.get(key, -10**9)
            if idx - last_idx < args.cooldown_bars:
                continue
            last_by_symbol_side[key] = idx
            future = df.iloc[idx + 1 : idx + 1 + args.lookahead].copy()
            raw_candidates.append((cand, future))

    print(f"Candidates collected before grid filters: {len(raw_candidates)}")
    score_values = grid_values(args.min_score_start, args.min_score_stop, args.min_score_step)
    rr_values = parse_csv_list(args.rr_values, float)
    rows = []

    for min_score in score_values:
        for min_rr in rr_values:
            filtered = [
                simulate_trade(c, future, args.fee_pct, args.slippage_pct)
                for c, future in raw_candidates
                if c.score >= min_score and c.rr >= min_rr
            ]
            summary = summarize(filtered)
            rows.append({"tier": args.tier, "min_score": min_score, "min_rr": min_rr, **summary})

    rows.sort(key=lambda r: (r["avg_pnl_pct"], r["win_rate"], r["trades"]), reverse=True)
    out = Path(args.output)
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["tier", "min_score", "min_rr"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved: {out}")
    print("Top settings:")
    for row in rows[:10]:
        print(
            f"  score>={row['min_score']:>2} rr>={row['min_rr']:<3} "
            f"trades={row['trades']:<4} win={row['win_rate']:>5}% "
            f"avg_pnl={row['avg_pnl_pct']:>7}% total={row['total_pnl_pct']:>8}% "
            f"TP1={row['tp1_rate']:>5}% SL={row['sl_rate']:>5}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
