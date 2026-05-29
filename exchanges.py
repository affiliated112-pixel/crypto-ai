"""Multi-exchange price fetcher — all public endpoints, no API keys.
Supports: Binance.US, Bybit, OKX, KuCoin, Coinbase, Kraken.
"""
import requests

UA = {"User-Agent": "crypto-ai-bot/2026"}
TIMEOUT = 8


def _safe(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except Exception:
        return None


def binance(symbol="BTCUSDT"):
    r = requests.get(f"https://api.binance.us/api/v3/ticker/price?symbol={symbol}", headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    return float(r.json()["price"])


def bybit(symbol="BTCUSDT"):
    r = requests.get(f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={symbol}", headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    items = r.json().get("result", {}).get("list", [])
    if not items:
        return None
    return float(items[0]["lastPrice"])


def okx(symbol="BTC-USDT"):
    r = requests.get(f"https://www.okx.com/api/v5/market/ticker?instId={symbol}", headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    items = r.json().get("data", [])
    if not items:
        return None
    return float(items[0]["last"])


def kucoin(symbol="BTC-USDT"):
    r = requests.get(f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={symbol}", headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json().get("data")
    if not data:
        return None
    return float(data["price"])


def coinbase(symbol="BTC-USD"):
    r = requests.get(f"https://api.coinbase.com/v2/prices/{symbol}/spot", headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    return float(r.json()["data"]["amount"])


def kraken(symbol="XBTUSDT"):
    r = requests.get(f"https://api.kraken.com/0/public/Ticker?pair={symbol}", headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    result = r.json().get("result", {})
    if not result:
        return None
    first = next(iter(result.values()))
    return float(first["c"][0])


def _to_dash(symbol):
    # BTCUSDT -> BTC-USDT, ETHUSDT -> ETH-USDT
    if symbol.endswith("USDT"):
        return symbol[:-4] + "-USDT"
    if symbol.endswith("USD"):
        return symbol[:-3] + "-USD"
    return symbol


def _to_coinbase(symbol):
    if symbol.endswith("USDT"):
        return symbol[:-4] + "-USD"
    if symbol.endswith("USD"):
        return symbol[:-3] + "-USD"
    return symbol


def _to_kraken(symbol):
    # Kraken uses XBT for BTC
    sym = symbol
    if sym.startswith("BTC"):
        sym = "XBT" + sym[3:]
    return sym


def all_prices(symbol="BTCUSDT"):
    """Get the price for one symbol across all supported exchanges.
    Returns dict {exchange: price_or_None}."""
    dash = _to_dash(symbol)
    cb = _to_coinbase(symbol)
    kr = _to_kraken(symbol)
    return {
        "Binance.US": _safe(binance, symbol),
        "Bybit": _safe(bybit, symbol),
        "OKX": _safe(okx, dash),
        "KuCoin": _safe(kucoin, dash),
        "Coinbase": _safe(coinbase, cb),
        "Kraken": _safe(kraken, kr),
    }


def arbitrage(symbol="BTCUSDT"):
    """Find biggest spread (potential arbitrage) across exchanges."""
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
