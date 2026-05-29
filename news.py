"""News aggregation + sentiment from free sources.
- CryptoPanic public RSS (free, no key)
- Reddit r/CryptoCurrency JSON (free, no key)
Lightweight keyword-based sentiment scoring.
"""
import re
import requests
from xml.etree import ElementTree as ET

UA = {"User-Agent": "crypto-ai-bot/2026 (Discord; +https://github.com/affiliated112-pixel/crypto-ai)"}
TIMEOUT = 10

BULLISH = {
    "surge","rally","soar","breakout","bullish","moon","pump","gain","gains","rise","rises",
    "adopt","adoption","approve","approved","approval","upgrade","partnership","launch",
    "record","all-time-high","ath","buy","accumulate","institutional","etf","green","win",
}
BEARISH = {
    "crash","dump","plunge","drop","falls","bearish","sell-off","liquidation","liquidated",
    "hack","hacked","exploit","scam","rug","rugpull","ban","banned","lawsuit","sec","fine",
    "investigation","down","loss","losses","bear","red","correction","warning","risk",
}


def _score(text):
    t = text.lower()
    words = set(re.findall(r"[a-z\-]+", t))
    b = len(words & BULLISH)
    s = len(words & BEARISH)
    return b - s, b, s


def cryptopanic_news(limit=10):
    """Latest crypto news from CryptoPanic public RSS — free, no key."""
    try:
        r = requests.get(
            "https://cryptopanic.com/news/rss/",
            headers=UA, timeout=TIMEOUT,
        )
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = []
        for it in root.findall(".//item")[:limit]:
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            pub = (it.findtext("pubDate") or "").strip()
            score, b, s = _score(title)
            mood = "🟢" if score > 0 else "🔴" if score < 0 else "⚪"
            items.append({
                "title": title,
                "link": link,
                "published": pub,
                "score": score,
                "mood": mood,
            })
        return items
    except Exception as e:
        return [{"error": str(e)}]


def reddit_hot(subreddit="CryptoCurrency", limit=10):
    """Hot posts from a subreddit via public JSON API — free, no key."""
    try:
        r = requests.get(
            f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}",
            headers=UA, timeout=TIMEOUT,
        )
        r.raise_for_status()
        posts = []
        for p in r.json().get("data", {}).get("children", []):
            d = p["data"]
            score, b, s = _score(d.get("title", ""))
            posts.append({
                "title": d.get("title", ""),
                "url": f"https://reddit.com{d.get('permalink', '')}",
                "score": d.get("score", 0),
                "comments": d.get("num_comments", 0),
                "sentiment": score,
                "mood": "🟢" if score > 0 else "🔴" if score < 0 else "⚪",
            })
        return posts
    except Exception as e:
        return [{"error": str(e)}]


def aggregate_sentiment():
    """Combine news + reddit into one sentiment score."""
    news = cryptopanic_news(limit=20)
    reddit = reddit_hot(limit=20)
    news_score = sum(n.get("score", 0) for n in news if "error" not in n)
    reddit_score = sum(p.get("sentiment", 0) for p in reddit if "error" not in p)
    total = news_score + reddit_score
    if total >= 5:
        label, emoji = "Strongly Bullish", "🚀"
    elif total >= 2:
        label, emoji = "Bullish", "🟢"
    elif total <= -5:
        label, emoji = "Strongly Bearish", "🔥"
    elif total <= -2:
        label, emoji = "Bearish", "🔴"
    else:
        label, emoji = "Neutral", "⚪"
    return {
        "news_score": news_score,
        "reddit_score": reddit_score,
        "total": total,
        "label": label,
        "emoji": emoji,
        "news_count": len([n for n in news if "error" not in n]),
        "reddit_count": len([p for p in reddit if "error" not in p]),
    }
