"""
news.py — real crypto news from public, no-key sources.

Reliable-source mode for the RCB Discord market-news channel.
The bot pulls from established public feeds and labels the source in every
Discord embed. If one feed is unavailable, the next one is used automatically.
"""

from __future__ import annotations

import html
import json
import logging
import re
from urllib.error import URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

log = logging.getLogger("news")

# Public, no-key feeds. Keep this list conservative: fewer but stronger sources.
RSS_SOURCES = [
    {
        "name": "CoinDesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "emoji": "📰",
        "reliability": "established crypto newsroom",
    },
    {
        "name": "The Block",
        "url": "https://www.theblock.co/rss.xml",
        "emoji": "🧱",
        "reliability": "research + institutional crypto coverage",
    },
    {
        "name": "Decrypt",
        "url": "https://decrypt.co/feed",
        "emoji": "🔓",
        "reliability": "independent crypto newsroom",
    },
    {
        "name": "Cointelegraph",
        "url": "https://cointelegraph.com/rss",
        "emoji": "📡",
        "reliability": "major crypto newsroom",
    },
    {
        "name": "Bitcoin Magazine",
        "url": "https://bitcoinmagazine.com/.rss/full/",
        "emoji": "₿",
        "reliability": "Bitcoin-focused specialist outlet",
    },
    {
        "name": "CryptoSlate",
        "url": "https://cryptoslate.com/feed/",
        "emoji": "📊",
        "reliability": "crypto market + sector coverage",
    },
]

COINGECKO_NEWS_URL = "https://api.coingecko.com/api/v3/news"
_cache_links: set[str] = set()
_cache_max = 250

_BULL_WORDS = {
    "surge", "rally", "bull", "gain", "soar", "rise", "ath", "pump",
    "breakout", "adoption", "buy", "green", "recover", "climb", "high",
    "approval", "inflow", "accumulate", "support", "record", "upgrade",
}
_BEAR_WORDS = {
    "crash", "drop", "fall", "bear", "dump", "plunge", "sell", "red",
    "low", "hack", "ban", "fear", "down", "warning", "collapse", "outflow",
    "lawsuit", "exploit", "liquidation", "rejection", "risk", "probe",
}


def _user_agent_headers(accept: str = "application/rss+xml, application/xml, text/xml, */*") -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 RCB-Crypto-AI/3.0 (Discord market news bot)",
        "Accept": accept,
    }


def _clean_html(text: str, limit: int = 400) -> str:
    clean = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:limit]


def _canonical_link(link: str) -> str:
    """Remove fragments and obvious tracking query strings for dedupe."""
    link = (link or "").strip()
    if not link:
        return ""
    parts = urlsplit(link)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _source_payload(source: dict, title: str, link: str, summary: str) -> dict:
    return {
        "title": _clean_html(title, 220),
        "link": link.strip(),
        "summary": _clean_html(summary, 320),
        "source": source["name"],
        "emoji": source.get("emoji", "📰"),
        "reliability": source.get("reliability", "public crypto news feed"),
    }


def _parse_rss(source: dict, timeout: int = 8) -> list[dict]:
    """Fetch and parse RSS/Atom. Returns normalized news dictionaries."""
    try:
        req = Request(source["url"], headers=_user_agent_headers())
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
    except URLError as e:
        log.debug("[news] RSS %s URLError: %s", source["name"], e)
        return []
    except ET.ParseError as e:
        log.debug("[news] RSS %s ParseError: %s", source["name"], e)
        return []
    except Exception as e:
        log.debug("[news] RSS %s error: %s", source["name"], e)
        return []

    items: list[dict] = []
    for item in root.iter("item"):
        title = item.findtext("title", "")
        link = item.findtext("link", "") or item.findtext("guid", "")
        desc = item.findtext("description", "")
        if title and link:
            items.append(_source_payload(source, title, link, desc))

    if not items:
        atom_ns = "{http://www.w3.org/2005/Atom}"
        for entry in root.iter(f"{atom_ns}entry"):
            title = entry.findtext(f"{atom_ns}title", "")
            link_el = entry.find(f"{atom_ns}link")
            link = link_el.get("href", "") if link_el is not None else ""
            summary = entry.findtext(f"{atom_ns}summary", "")
            if title and link:
                items.append(_source_payload(source, title, link, summary))
    return items


def _coingecko_news(limit: int = 10) -> list[dict]:
    """Fetch CoinGecko public news API. Returns [] on rate limit/failure."""
    try:
        req = Request(
            COINGECKO_NEWS_URL,
            headers=_user_agent_headers("application/json, */*"),
        )
        with urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        articles = data.get("data") if isinstance(data, dict) else data
        items = []
        for art in (articles or [])[:limit]:
            title = art.get("title") or art.get("name", "")
            url = art.get("url") or art.get("news_url", "")
            if not title or not url:
                continue
            items.append({
                "title": _clean_html(title, 220),
                "link": url,
                "summary": _clean_html(art.get("description", ""), 320),
                "source": "CoinGecko",
                "emoji": "🦎",
                "reliability": "market data/news aggregator",
            })
        return items
    except Exception as e:
        log.debug("[news] CoinGecko error: %s", e)
        return []


def _detect_mood(title: str) -> str:
    t = (title or "").lower()
    bull = sum(1 for w in _BULL_WORDS if w in t)
    bear = sum(1 for w in _BEAR_WORDS if w in t)
    if bull > bear:
        return "🟢"
    if bear > bull:
        return "🔴"
    return "⚪"


def _with_mood(item: dict) -> dict:
    item = dict(item)
    item["mood"] = _detect_mood((item.get("title") or "") + " " + (item.get("summary") or ""))
    return item


def fetch_news(limit: int = 5, source_idx: int | None = None) -> list[dict]:
    """Fetch fresh crypto news from trusted public sources.

    Returns dicts with: title, link, summary, source, emoji, reliability, mood.
    Dedupes by canonical URL so the news channel does not repost the same link.
    """
    global _cache_links
    limit = max(1, min(int(limit or 5), 20))
    source_items: list[dict] = []

    sources = [RSS_SOURCES[source_idx % len(RSS_SOURCES)]] if source_idx is not None else RSS_SOURCES
    for src in sources:
        # Keep several per source so the output is not dominated by one feed.
        source_items.extend(_parse_rss(src)[: max(2, limit)])

    if not source_items:
        source_items = _coingecko_news(limit * 2)

    fresh: list[dict] = []
    seen: set[str] = set()
    for item in source_items:
        link = item.get("link", "")
        canonical = _canonical_link(link)
        if not canonical or canonical in seen or canonical in _cache_links:
            continue
        seen.add(canonical)
        _cache_links.add(canonical)
        fresh.append(_with_mood(item))
        if len(fresh) >= limit:
            break

    # If every candidate was already cached after a long runtime, return a small
    # safe fallback rather than leaving the channel silent forever.
    if not fresh:
        for item in source_items:
            link = item.get("link", "")
            canonical = _canonical_link(link)
            if not canonical or canonical in seen:
                continue
            seen.add(canonical)
            fresh.append(_with_mood(item))
            if len(fresh) >= limit:
                break

    if len(_cache_links) > _cache_max:
        _cache_links = set(list(_cache_links)[-125:])

    return fresh


def cryptopanic_news(limit: int = 5) -> list[dict]:
    """Compatibility wrapper for older callers. Uses current public sources."""
    return fetch_news(limit=limit)


def _sentiment_score_text(text: str) -> int:
    t = (text or "").lower()
    bull = sum(1 for w in _BULL_WORDS if w in t)
    bear = sum(1 for w in _BEAR_WORDS if w in t)
    return bull - bear


def _fetch_reddit_titles(limit: int = 15) -> list[str]:
    """Best-effort public Reddit JSON fetch. Returns [] when unavailable."""
    try:
        req = Request(
            f"https://www.reddit.com/r/CryptoCurrency/hot.json?limit={max(1, min(limit, 50))}",
            headers={
                "User-Agent": "RCB-Crypto-AI/3.0 sentiment check",
                "Accept": "application/json",
            },
        )
        with urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        posts = []
        for child in data.get("data", {}).get("children", []):
            d = child.get("data", {}) or {}
            title = d.get("title") or ""
            body = d.get("selftext") or ""
            if title:
                posts.append((title + " " + body).strip())
        return posts[:limit]
    except Exception as e:
        log.debug("[news] Reddit sentiment unavailable: %s", e)
        return []


def _fresh_news_for_sentiment(limit: int) -> list[dict]:
    """Fetch headlines for sentiment without consuming the repost cache."""
    items: list[dict] = []
    for src in RSS_SOURCES:
        items.extend(_parse_rss(src)[: max(1, limit // 2)])
        if len(items) >= limit:
            break
    if not items:
        items = _coingecko_news(limit)
    return [_with_mood(item) for item in items[:limit]]


def aggregate_sentiment(limit: int = 12, reddit_limit: int = 15) -> dict:
    """Transparent market sentiment from fetched headlines + public Reddit.

    No generated counts or unsupported summaries are used. All counts are based
    on fetched titles/summaries at runtime.
    """
    try:
        items = _fresh_news_for_sentiment(limit)
    except Exception:
        items = []
    try:
        reddit_posts = _fetch_reddit_titles(reddit_limit)
    except Exception:
        reddit_posts = []

    news_score = 0
    bullish = bearish = neutral = 0
    for item in items:
        score = _sentiment_score_text((item.get("title") or "") + " " + (item.get("summary") or ""))
        if score > 0:
            news_score += 1
            bullish += 1
        elif score < 0:
            news_score -= 1
            bearish += 1
        else:
            neutral += 1

    reddit_score = sum(_sentiment_score_text(p) for p in reddit_posts)
    total = news_score + reddit_score
    if total > 1:
        label, emoji = "Bullish", "🟢"
    elif total < -1:
        label, emoji = "Bearish", "🔴"
    else:
        label, emoji = "Neutral", "⚪"

    return {
        "total": int(total),
        "label": label,
        "emoji": emoji,
        "news_score": int(news_score),
        "reddit_score": int(reddit_score),
        "news_count": len(items),
        "reddit_count": len(reddit_posts),
        "bullish": bullish,
        "bearish": bearish,
        "neutral": neutral,
        "source": "CoinDesk/The Block/Decrypt/Cointelegraph/Bitcoin Magazine/CryptoSlate/CoinGecko + Reddit public JSON",
    }
