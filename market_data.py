"""market_data.py — central real market data helpers.

No generated prices, no hardcoded performance. Every value returned here is
fetched from public market APIs, with safe fallbacks and clear source labels.
"""
from __future__ import annotations

import os
import time
from typing import Any

import pandas as pd
import requests

try:
    import coins_config
except Exception:  # pragma: no cover - keeps this helper usable standalone
    coins_config = None

UA = {"User-Agent": os.environ.get("MARKET_DATA_UA", "crypto-ai-discord-bot/real-data")}
TIMEOUT = int(os.environ.get("MARKET_DATA_TIMEOUT", "10"))

# Use global Binance first because it has broader symbol coverage. Binance.US is
# kept as fallback for users who prefer or can only reach that endpoint.
_BINANCE_HOSTS_DEFAULT = "https://api.binance.com,https://api.binance.us"
BINANCE_HOSTS = [h.strip().rstrip("/") for h in os.environ.get("BINANCE_HOSTS", _BINANCE_HOSTS_DEFAULT).split(",") if h.strip()]

_EXTRA_COINGECKO_IDS = {
    "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana",
    "BNBUSDT": "binancecoin", "XRPUSDT": "ripple", "DOGEUSDT": "dogecoin",
    "ADAUSDT": "cardano", "AVAXUSDT": "avalanche-2", "DOTUSDT": "polkadot",
    "LINKUSDT": "chainlink", "LTCUSDT": "litecoin", "MATICUSDT": "matic-network",
    "POLUSDT": "polygon-ecosystem-token", "UNIUSDT": "uniswap", "ATOMUSDT": "cosmos",
    "XLMUSDT": "stellar", "NEARUSDT": "near", "FTMUSDT": "fantom",
    "ALGOUSDT": "algorand", "SANDUSDT": "the-sandbox", "MANAUSDT": "decentraland",
    "FILUSDT": "filecoin", "TRXUSDT": "tron", "ETCUSDT": "ethereum-classic",
    "AAVEUSDT": "aave", "GRTUSDT": "the-graph", "SHIBUSDT": "shiba-inu",
    "OPUSDT": "optimism", "ARBUSDT": "arbitrum", "INJUSDT": "injective-protocol",
    "SUIUSDT": "sui", "APTUSDT": "aptos",
}

_LAST_SOURCE: dict[str, str] = {}
_CACHE: dict[tuple[str, str, int], tuple[float, pd.DataFrame | None]] = {}
PRICE_CACHE: dict[str, tuple[float, float | None, str]] = {}
CACHE_SECONDS = int(os.environ.get("MARKET_DATA_CACHE_SECONDS", "20"))
PRICE_CACHE_SECONDS = int(os.environ.get("PRICE_CACHE_SECONDS", "10"))


def coingecko_id(symbol: str) -> str:
    symbol = (symbol or "").upper().strip()
    if coins_config and hasattr(coins_config, "COINGECKO_SLUG"):
        mapped = coins_config.COINGECKO_SLUG.get(symbol)
        if mapped:
            return mapped
    return _EXTRA_COINGECKO_IDS.get(symbol, symbol.replace("USDT", "").lower())


def _get_json(url: str, *, params: dict[str, Any] | None = None, timeout: int = TIMEOUT) -> Any:
    r = requests.get(url, params=params, headers=UA, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _klines_from_binance_payload(data: Any) -> pd.DataFrame | None:
    if not isinstance(data, list) or len(data) < 20:
        return None
    df = pd.DataFrame(data, columns=[
        "time", "open", "high", "low", "close", "volume",
        "close_time", "qav", "trades", "tbbav", "tbqav", "ignore",
    ])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    return df if len(df) >= 20 else None


def get_ohlcv_binance(symbol: str, interval: str = "5m", limit: int = 150) -> pd.DataFrame | None:
    symbol = symbol.upper().strip()
    for host in BINANCE_HOSTS:
        try:
            data = _get_json(f"{host}/api/v3/klines", params={"symbol": symbol, "interval": interval, "limit": limit})
            df = _klines_from_binance_payload(data)
            if df is not None:
                df.attrs["symbol"] = symbol
                df.attrs["source"] = host.replace("https://", "")
                _LAST_SOURCE[symbol] = df.attrs["source"]
                return df
        except Exception as e:
            _LAST_SOURCE[symbol] = f"{host.replace('https://','')} error: {type(e).__name__}"
    return None


def _coingecko_days_for_limit(interval: str, limit: int) -> str:
    # CoinGecko decides exact granularity. These values keep requests small while
    # returning enough candles for RSI/MACD/EMA calculations.
    if interval in {"1m", "3m", "5m", "15m", "30m"}:
        return "1"
    if interval in {"1h", "2h", "4h", "6h", "8h", "12h"}:
        return "7"
    return "30"


def get_ohlcv_coingecko(symbol: str, interval: str = "5m", limit: int = 150) -> pd.DataFrame | None:
    symbol = symbol.upper().strip()
    coin_id = coingecko_id(symbol)
    try:
        data = _get_json(
            f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
            params={"vs_currency": "usd", "days": _coingecko_days_for_limit(interval, limit)},
        )
        prices = data.get("prices") or []
        volumes = data.get("total_volumes") or []
        if len(prices) < 20:
            return None
        rows = prices[-limit:]
        vol_by_ts = {int(ts): float(v or 0) for ts, v in volumes[-limit:]} if volumes else {}
        df = pd.DataFrame(rows, columns=["time", "close"])
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        # CoinGecko market_chart gives points, not OHLC candles. We keep this as a
        # fallback only and make OHLC equal to the real sampled price points.
        df["open"] = df["close"].shift(1).fillna(df["close"])
        df["high"] = df[["open", "close"]].max(axis=1)
        df["low"] = df[["open", "close"]].min(axis=1)
        df["volume"] = [vol_by_ts.get(int(ts), 0.0) for ts in df["time"]]
        df = df.dropna(subset=["open", "high", "low", "close"])
        if len(df) < 20:
            return None
        df.attrs["symbol"] = symbol
        df.attrs["source"] = "CoinGecko market_chart"
        _LAST_SOURCE[symbol] = df.attrs["source"]
        return df
    except Exception as e:
        _LAST_SOURCE[symbol] = f"CoinGecko error: {type(e).__name__}"
        return None


def get_ohlcv(symbol: str, interval: str = "5m", limit: int = 150) -> pd.DataFrame | None:
    symbol = symbol.upper().strip()
    key = (symbol, interval, int(limit))
    now = time.time()
    ts, cached = _CACHE.get(key, (0, None))
    if cached is not None and now - ts < CACHE_SECONDS:
        return cached.copy()

    df = get_ohlcv_binance(symbol, interval=interval, limit=limit)
    if df is None:
        df = get_ohlcv_coingecko(symbol, interval=interval, limit=limit)
    if df is not None:
        _CACHE[key] = (now, df.copy())
    return df


def get_current_price(symbol: str) -> float | None:
    symbol = symbol.upper().strip()
    now = time.time()
    ts, cached, _src = PRICE_CACHE.get(symbol, (0, None, ""))
    if cached is not None and now - ts < PRICE_CACHE_SECONDS:
        return cached

    for host in BINANCE_HOSTS:
        try:
            data = _get_json(f"{host}/api/v3/ticker/price", params={"symbol": symbol}, timeout=8)
            price = float(data["price"])
            PRICE_CACHE[symbol] = (now, price, host.replace("https://", ""))
            _LAST_SOURCE[symbol] = host.replace("https://", "")
            return price
        except Exception:
            pass

    # Fallback to CoinGecko simple price.
    try:
        coin_id = coingecko_id(symbol)
        data = _get_json(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": coin_id, "vs_currencies": "usd"}, timeout=8,
        )
        price = float(data.get(coin_id, {}).get("usd"))
        PRICE_CACHE[symbol] = (now, price, "CoinGecko simple")
        _LAST_SOURCE[symbol] = "CoinGecko simple"
        return price
    except Exception:
        return None


def get_price_info(symbol: str) -> dict[str, float | str] | None:
    symbol = symbol.upper().strip()
    for host in BINANCE_HOSTS:
        try:
            data = _get_json(f"{host}/api/v3/ticker/24hr", params={"symbol": symbol}, timeout=8)
            info = {
                "price":  float(data["lastPrice"]),
                "change": float(data["priceChangePercent"]),
                "high":   float(data["highPrice"]),
                "low":    float(data["lowPrice"]),
                "volume": float(data.get("quoteVolume") or data.get("volume") or 0),
                "source": host.replace("https://", ""),
            }
            _LAST_SOURCE[symbol] = str(info["source"])
            return info
        except Exception:
            pass

    try:
        coin_id = coingecko_id(symbol)
        data = _get_json(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": coin_id,
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_24hr_vol": "true",
            }, timeout=8,
        ).get(coin_id, {})
        price = float(data.get("usd"))
        change = float(data.get("usd_24h_change") or 0.0)
        vol = float(data.get("usd_24h_vol") or 0.0)
        info = {"price": price, "change": change, "high": price, "low": price, "volume": vol, "source": "CoinGecko simple"}
        _LAST_SOURCE[symbol] = "CoinGecko simple"
        return info
    except Exception:
        return None


def last_source(symbol: str) -> str:
    return _LAST_SOURCE.get(symbol.upper().strip(), "unknown")


def format_price(value: float | int | None) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except Exception:
        return "—"
    if abs(v) >= 100:
        return f"{v:,.2f}"
    if abs(v) >= 1:
        return f"{v:,.4f}"
    return f"{v:,.8f}".rstrip("0").rstrip(".")
