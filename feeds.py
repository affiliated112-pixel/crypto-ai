"""Free crypto data feeds — no API keys required.
Aggregates Fear & Greed, CoinGecko prices/trending/global, and DeFiLlama TVL.
"""
import requests

UA = {"User-Agent": "crypto-ai-bot/2026"}
TIMEOUT = 10


def fear_greed_index():
    """Crypto Fear & Greed Index from alternative.me (free, no key)."""
    try:
        r = requests.get("https://api.alternative.me/fng/", headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        d = r.json().get("data", [{}])[0]
        return {
            "value": int(d.get("value", 0)),
            "classification": d.get("value_classification", "Unknown"),
            "timestamp": d.get("timestamp"),
        }
    except Exception as e:
        return {"error": str(e)}


def coingecko_price(coin_id):
    """Price + 24h change + mcap + volume via CoinGecko (free)."""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": coin_id,
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
        }
        r = requests.get(url, params=params, headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json().get(coin_id, {})
    except Exception as e:
        return {"error": str(e)}


def coingecko_search(query):
    """Resolve a coin id by name/symbol via CoinGecko free API."""
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/search",
            params={"query": query}, headers=UA, timeout=TIMEOUT,
        )
        r.raise_for_status()
        coins = r.json().get("coins", [])
        return coins[0]["id"] if coins else None
    except Exception:
        return None


def coingecko_trending():
    """Top 7 trending searched coins on CoinGecko in last 24h."""
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/search/trending",
            headers=UA, timeout=TIMEOUT,
        )
        r.raise_for_status()
        return [
            {
                "name": c["item"]["name"],
                "symbol": c["item"]["symbol"],
                "rank": c["item"].get("market_cap_rank"),
                "price_btc": c["item"].get("price_btc"),
            }
            for c in r.json().get("coins", [])[:7]
        ]
    except Exception:
        return []


def defillama_tvl():
    """Total DeFi TVL across all chains via DeFiLlama (free, no key)."""
    try:
        r = requests.get(
            "https://api.llama.fi/v2/historicalChainTvl",
            headers=UA, timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        latest = data[-1]
        prev = data[-2] if len(data) > 1 else latest
        change = ((latest["tvl"] - prev["tvl"]) / prev["tvl"] * 100) if prev["tvl"] else 0
        return {
            "tvl_usd": latest["tvl"],
            "change_24h_pct": change,
            "date": latest["date"],
        }
    except Exception as e:
        return {"error": str(e)}


def global_market():
    """Global crypto market data: total mcap, BTC dominance, ETH dominance."""
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/global",
            headers=UA, timeout=TIMEOUT,
        )
        r.raise_for_status()
        d = r.json()["data"]
        return {
            "total_mcap_usd": d["total_market_cap"]["usd"],
            "total_volume_usd": d["total_volume"]["usd"],
            "btc_dominance": d["market_cap_percentage"].get("btc", 0),
            "eth_dominance": d["market_cap_percentage"].get("eth", 0),
            "active_cryptos": d.get("active_cryptocurrencies", 0),
        }
    except Exception as e:
        return {"error": str(e)}
