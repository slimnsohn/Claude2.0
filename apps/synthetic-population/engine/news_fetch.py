"""RSS fetching and relevance sampling (moved from api/world_updates.py)."""

import re
import xml.etree.ElementTree as ET
from html import unescape

import requests

from engine.news_scoring import TOPIC_KEYWORDS, POSITIVE_SIGNALS, NEGATIVE_SIGNALS

# ---------------------------------------------------------------------------
# RSS feed sources — no API keys, all public
# ---------------------------------------------------------------------------

RSS_FEEDS = {
    "AP News": "https://rsshub.app/apnews/topics/apf-topnews",
    "NPR": "https://feeds.npr.org/1001/rss.xml",
    "BBC": "http://feeds.bbci.co.uk/news/rss.xml",
    "Reuters": "https://rsshub.app/reuters/world",
    "Google News": "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
}

# Fallback: if RSS feeds fail, try Google News search for key topics
GOOGLE_NEWS_TOPICS = [
    "https://news.google.com/rss/search?q=US+economy&hl=en-US&gl=US",
    "https://news.google.com/rss/search?q=US+politics&hl=en-US&gl=US",
    "https://news.google.com/rss/search?q=congress+legislation&hl=en-US&gl=US",
]


def strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    clean = re.sub(r"<[^>]+>", "", text)
    return unescape(clean).strip()


def fetch_rss(url: str, timeout: int = 8) -> list[dict]:
    """Fetch and parse an RSS feed, returning list of {title, description, date, source}."""
    try:
        resp = requests.get(url, timeout=timeout, headers={
            "User-Agent": "SyntheticPopulationEngine/1.0"
        })
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        items = []
        # Standard RSS 2.0
        for item in root.findall(".//item"):
            title = item.findtext("title", "").strip()
            desc = strip_html(item.findtext("description", ""))
            pub_date = item.findtext("pubDate", "")
            source = item.findtext("source", "")
            if title:
                items.append({
                    "title": title,
                    "description": desc[:300] if desc else "",
                    "pub_date": pub_date,
                    "source": source,
                })
        return items
    except Exception:
        return []


def fetch_headlines(max_per_feed: int = 10) -> list[dict]:
    """Fetch recent headlines from all RSS feeds."""
    all_items = []
    for name, url in RSS_FEEDS.items():
        items = fetch_rss(url)
        for item in items[:max_per_feed]:
            item["feed"] = name
        all_items.extend(items[:max_per_feed])

    # If we got nothing from main feeds, try Google News topic searches
    if len(all_items) < 5:
        for url in GOOGLE_NEWS_TOPICS:
            items = fetch_rss(url)
            for item in items[:5]:
                item["feed"] = "Google News"
            all_items.extend(items[:5])

    return all_items


def sample_relevant(headlines: list[dict], n: int = 8) -> list[dict]:
    """Sample headlines biased toward politically/economically relevant stories.

    Real people don't read every headline — they catch a handful.
    We bias toward stories that would actually shift opinions.
    """
    import random

    if not headlines:
        return []

    # Score each headline by relevance to opinion-forming topics
    scored = []
    for h in headlines:
        text = (h.get("title", "") + " " + h.get("description", "")).lower()
        score = 0
        for topic, keywords in TOPIC_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                score += 2
        # Boost headlines with strong sentiment signals
        if any(s in text for s in POSITIVE_SIGNALS + NEGATIVE_SIGNALS):
            score += 1
        scored.append((score, h))

    # Sort by score, take top candidates, then sample from those
    scored.sort(key=lambda x: -x[0])
    top_pool = scored[:max(n * 3, 15)]

    # Weight sampling toward higher-scored items
    if len(top_pool) <= n:
        return [h for _, h in top_pool]

    weights = [max(s + 1, 1) for s, _ in top_pool]
    selected = []
    pool = list(top_pool)
    w = list(weights)
    for _ in range(min(n, len(pool))):
        if not pool:
            break
        chosen = random.choices(range(len(pool)), weights=w, k=1)[0]
        selected.append(pool[chosen][1])
        pool.pop(chosen)
        w.pop(chosen)

    return selected
