"""Multi-exchange price fetcher with parallel async execution.
All public endpoints, no API keys.
Supports: Binance Global/US, Bybit, OKX, KuCoin, Coinbase, Kraken.
"""
import asyncio
import requests
import market_data

UA = {"User-Agent": "crypto-ai-bot/2026"}
TIMEOUT = 5  # tighter timeout so a slow exchange can't stall us


def _safe(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except Exception:
        return None


def binance(symbol="BTCUSDT"):
    return market_data.get_current_price(symbol)


def bybit(symbol="BTCUSDT"):
    r = requests.get(f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={symbol}", headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    items = r.json().get("result", {}).get("list", [])
    if not items: return None
    return float(items[0]["lastPrice"])


def okx(symbol="BTC-USDT"):
    r = requests.get(f"https://www.okx.com/api/v5/market/ticker?instId={symbol}", headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    items = r.json().get("data", [])
    if not items: return None
    return float(items[0]["last"])


def kucoin(symbol="BTC-USDT"):
    r = requests.get(f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={symbol}", headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json().get("data")
    if not data: return None
    return float(data["price"])


def coinbase(symbol="BTC-USD"):
    r = requests.get(f"https://api.coinbase.com/v2/prices/{symbol}/spot", headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    return float(r.json()["data"]["amount"])


def kraken(symbol="XBTUSDT"):
    r = requests.get(f"https://api.kraken.com/0/public/Ticker?pair={symbol}", headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    result = r.json().get("result", {})
    if not result: return None
    first = next(iter(result.values()))
    return float(first["c"][0])


def _to_dash(symbol):
    if symbol.endswith("USDT"): return symbol[:-4] + "-USDT"
    if symbol.endswith("USD"): return symbol[:-3] + "-USD"
    return symbol


def _to_coinbase(symbol):
    if symbol.endswith("USDT"): return symbol[:-4] + "-USD"
    if symbol.endswith("USD"): return symbol[:-3] + "-USD"
    return symbol


def _to_kraken(symbol):
    if symbol.startswith("BTC"): return "XBT" + symbol[3:]
    return symbol


def all_prices(symbol="BTCUSDT"):
    """Sync fetch — each exchange runs in its own thread so total time = slowest."""
    dash = _to_dash(symbol)
    cb = _to_coinbase(symbol)
    kr = _to_kraken(symbol)
    # Use a small thread pool to fan out
    from concurrent.futures import ThreadPoolExecutor
    jobs = {
        "Binance":    (binance, (symbol,)),
        "Bybit":      (bybit,   (symbol,)),
        "OKX":        (okx,     (dash,)),
        "KuCoin":     (kucoin,  (dash,)),
        "Coinbase":   (coinbase,(cb,)),
        "Kraken":     (kraken,  (kr,)),
    }
    results = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(_safe, fn, *args): name for name, (fn, args) in jobs.items()}
        for fut, name in futs.items():
            try:
                results[name] = fut.result(timeout=TIMEOUT + 1)
            except Exception:
                results[name] = None
    return results


def arbitrage(symbol="BTCUSDT"):
    """Find biggest spread across exchanges. Uses parallel all_prices."""
    prices = {k: v for k, v in all_prices(symbol).items() if v is not None}
    if len(prices) < 2:
        return None
    low_ex = min(prices, key=prices.get)
    high_ex = max(prices, key=prices.get)
    low, high = prices[low_ex], prices[high_ex]
    spread_pct = ((high - low) / low) * 100 if low else 0
    return {
        "low_exchange": low_ex,
        "low_price": low,
        "high_exchange": high_ex,
        "high_price": high,
        "spread_pct": spread_pct,
        "prices": prices,
    }
