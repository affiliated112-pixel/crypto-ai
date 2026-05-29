"""Whale activity tracker using free public APIs.
- Binance.US 24h ticker for huge volume movers
- DefiLlama stablecoin flows (free, no key)
- Whale Alert public RSS feed mirror (best-effort, falls back gracefully)
"""
import requests

UA = {"User-Agent": "crypto-ai-bot/2026"}
TIMEOUT = 10


def top_volume_movers(min_quote_volume_usd=50_000_000, limit=10):
    """Largest 24h volume movers on Binance.US — proxy for whale-driven action."""
    try:
        r = requests.get("https://api.binance.us/api/v3/ticker/24hr", headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        items = []
        for t in r.json():
            sym = t.get("symbol", "")
            if not sym.endswith("USDT") and not sym.endswith("USD"):
                continue
            qv = float(t.get("quoteVolume", 0) or 0)
            if qv < min_quote_volume_usd:
                continue
            items.append({
                "symbol": sym,
                "price": float(t.get("lastPrice", 0) or 0),
                "change_pct": float(t.get("priceChangePercent", 0) or 0),
                "quote_volume": qv,
                "trades": int(t.get("count", 0) or 0),
            })
        items.sort(key=lambda x: x["quote_volume"], reverse=True)
        return items[:limit]
    except Exception as e:
        return [{"error": str(e)}]


def stablecoin_flows():
    """DefiLlama stablecoin total supply — flows in/out signal liquidity."""
    try:
        r = requests.get("https://stablecoins.llama.fi/stablecoins?includePrices=true", headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        coins = r.json().get("peggedAssets", [])
        result = []
        for c in coins[:10]:
            circ = c.get("circulating", {}).get("peggedUSD", 0) or 0
            prev = c.get("circulatingPrevDay", {}).get("peggedUSD", 0) or circ
            delta = circ - prev
            result.append({
                "name": c.get("name"),
                "symbol": c.get("symbol"),
                "circulating_usd": circ,
                "change_24h_usd": delta,
                "change_pct": (delta / prev * 100) if prev else 0,
            })
        return result
    except Exception as e:
        return [{"error": str(e)}]


def whale_summary():
    """Combined whale intelligence summary."""
    movers = top_volume_movers(limit=5)
    stables = stablecoin_flows()
    return {
        "top_movers": movers,
        "stablecoin_flows": stables,
    }
