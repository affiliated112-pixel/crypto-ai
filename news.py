"""
news.py — Crypto news din surse 100% gratuite, fara API key.

Surse folosite (toate public, fara autentificare):
  1. CoinDesk RSS       — cel mai mare site de crypto news
  2. Decrypt RSS        — stiri crypto independente
  3. Bitcoin Magazine   — focus BTC/macro
  4. CryptoSlate RSS    — altcoin + DeFi news
  5. CoinGecko News API — agregator gratuit, fara key
  6. Reddit r/CryptoCurrency — sentiment comunitate

Toate sursele sunt rotite automat. Daca una pica, celelalte raman.
"""

from __future__ import annotations

import re
import time
import logging
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError
import xml.etree.ElementTree as ET

log = logging.getLogger("news")

# ─── SURSE RSS (fara API key) ────────────────────────────────────────────────
RSS_SOURCES = [
    {
        "name":  "CoinDesk",
        "url":   "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "emoji": "📰",
    },
    {
        "name":  "Decrypt",
        "url":   "https://decrypt.co/feed",
        "emoji": "🔓",
    },
    {
        "name":  "Bitcoin Magazine",
        "url":   "https://bitcoinmagazine.com/.rss/full/",
        "emoji": "₿",
    },
    {
        "name":  "CryptoSlate",
        "url":   "https://cryptoslate.com/feed/",
        "emoji": "📊",
    },
    {
        "name":  "CryptoPotato",
        "url":   "https://cryptopotato.com/feed/",
        "emoji": "🥔",
    },
    {
        "name":  "The Block",
        "url":   "https://www.theblock.co/rss.xml",
        "emoji": "🧱",
    },
    {
        "name":  "NewsBTC",
        "url":   "https://www.newsbtc.com/feed/",
        "emoji": "📡",
    },
]

# ─── COINGECKO NEWS API (gratuit, fara key) ──────────────────────────────────
COINGECKO_NEWS_URL = "https://api.coingecko.com/api/v3/news"

# ─── CACHE intern (evita sa reposteze aceeasi stire) ─────────────────────────
_cache_links: set[str] = set()
_cache_max   = 200

def _clean_html(text: str) -> str:
    """Sterge taguri HTML dintr-un string."""
    clean = re.sub(r"<[^>]+>", "", text or "")
    return clean.strip()[:400]

def _user_agent_headers() -> dict:
    return {
        "User-Agent": "Mozilla/5.0 CryptoBot/2.0 (news aggregator; +https://discord.gg)",
        "Accept":     "application/rss+xml, application/xml, text/xml, */*",
    }

# ─── PARSARE RSS ──────────────────────────────────────────────────────────────
def _parse_rss(source: dict, timeout: int = 8) -> list[dict]:
    """
    Fetches and parses an RSS feed.
    Returns list of {title, link, summary, source, emoji}.
    """
    try:
        req  = Request(source["url"], headers=_user_agent_headers())
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
    except URLError as e:
        log.debug(f"[news] RSS {source['name']} URLError: {e}")
        return []
    except ET.ParseError as e:
        log.debug(f"[news] RSS {source['name']} ParseError: {e}")
        return []
    except Exception as e:
        log.debug(f"[news] RSS {source['name']} error: {e}")
        return []

    items = []
    # Suporta atat RSS (<channel><item>) cat si Atom (<entry>)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for item in root.iter("item"):
        title = item.findtext("title", "")
        link  = item.findtext("link", "") or item.findtext("guid", "")
        desc  = item.findtext("description", "")
        if not title or not link:
            continue
        items.append({
            "title":   _clean_html(title)[:200],
            "link":    link.strip(),
            "summary": _clean_html(desc)[:300],
            "source":  source["name"],
            "emoji":   source["emoji"],
        })
    # Fallback Atom feed
    if not items:
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            title = entry.findtext("{http://www.w3.org/2005/Atom}title", "")
            link_el = entry.find("{http://www.w3.org/2005/Atom}link")
            link    = link_el.get("href", "") if link_el is not None else ""
            summary = entry.findtext("{http://www.w3.org/2005/Atom}summary", "")
            if not title or not link:
                continue
            items.append({
                "title":   _clean_html(title)[:200],
                "link":    link.strip(),
                "summary": _clean_html(summary)[:300],
                "source":  source["name"],
                "emoji":   source["emoji"],
            })
    return items

# ─── COINGECKO NEWS ──────────────────────────────────────────────────────────
def _coingecko_news(limit: int = 10) -> list[dict]:
    """
    Fetches news from CoinGecko public API.
    Free, no API key, no rate limit issues for low frequency.
    """
    try:
        import json
        req = Request(
            COINGECKO_NEWS_URL,
            headers={
                "User-Agent": "CryptoBot/2.0",
                "Accept":     "application/json",
            }
        )
        with urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        items = []
        for art in (data.get("data") or data)[:limit]:
            title = art.get("title") or art.get("name", "")
            url   = art.get("url") or art.get("news_url", "")
            if not title or not url:
                continue
            items.append({
                "title":   title[:200],
                "link":    url,
                "summary": (art.get("description") or "")[:300],
                "source":  "CoinGecko",
                "emoji":   "🦎",
            })
        return items
    except Exception as e:
        log.debug(f"[news] CoinGecko error: {e}")
        return []

# ─── DETECTIE SENTIMENT (simplu, fara AI) ────────────────────────────────────
_BULL_WORDS = {"surge", "rally", "bull", "gain", "soar", "rise", "ath", "pump",
               "breakout", "adoption", "buy", "green", "recover", "climb", "high"}
_BEAR_WORDS = {"crash", "drop", "fall", "bear", "dump", "plunge", "sell", "red",
               "low", "hack", "ban", "fear", "down", "warning", "collapse"}

def _detect_mood(title: str) -> str:
    """Returns emoji: 🟢 bullish | 🔴 bearish | ⚪ neutral"""
    t = title.lower()
    bull = sum(1 for w in _BULL_WORDS if w in t)
    bear = sum(1 for w in _BEAR_WORDS if w in t)
    if bull > bear:   return "🟢"
    if bear > bull:   return "🔴"
    return "⚪"

# ─── FUNCTIA PRINCIPALA ───────────────────────────────────────────────────────
def fetch_news(limit: int = 5, source_idx: int | None = None) -> list[dict]:
    """
    Fetches fresh crypto news from multiple free sources.
    Rotates through RSS sources + CoinGecko. Deduplicates by URL.
    Returns list of {title, link, summary, source, emoji, mood}.

    Args:
        limit:      how many articles to return
        source_idx: if set, use only that RSS source (for rotation)
    """
    global _cache_links

    all_items: list[dict] = []

    # Incearca RSS sources
    sources_to_try = (
        [RSS_SOURCES[source_idx % len(RSS_SOURCES)]]
        if source_idx is not None
        else RSS_SOURCES
    )
    for src in sources_to_try:
        items = _parse_rss(src)
        all_items.extend(items)
        if len(all_items) >= limit * 3:
            break

    # Fallback: CoinGecko daca toate RSS-urile au picat
    if not all_items:
        all_items = _coingecko_news(limit * 2)

    # Deduplicare + filtrare cache
    fresh = []
    for item in all_items:
        link = item.get("link", "")
        if not link or link in _cache_links:
            continue
        item["mood"] = _detect_mood(item["title"])
        fresh.append(item)
        _cache_links.add(link)
        if len(fresh) >= limit:
            break

    # Curata cache-ul daca e prea mare
    if len(_cache_links) > _cache_max:
        _cache_links = set(list(_cache_links)[-100:])

    return fresh

# ─── COMPATIBILITATE cu real_loops.py (inlocuieste cryptopanic_news) ─────────
def cryptopanic_news(limit: int = 5) -> list[dict]:
    """
    Drop-in replacement pentru vechea functie cryptopanic_news().
    Foloseste acum RSS multi-source in loc de CryptoPanic.
    """
    return fetch_news(limit=limit)
