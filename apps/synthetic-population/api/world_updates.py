"""World Updates API — auto-fetch real public news to shift poll responses.

Fetches current headlines from public RSS feeds (AP, NPR, BBC, Reuters),
detects topics and sentiment direction, and computes per-party opinion shifts
that get applied to CES-modeled poll responses.
"""

import json
import random
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from html import unescape
from pathlib import Path

import requests

from flask import Blueprint, jsonify, request, current_app

from engine.news_scoring import (
    TOPIC_KEYWORDS, POSITIVE_SIGNALS, NEGATIVE_SIGNALS, PARTY_VALENCE,
    detect_topics as _detect_topics,
    detect_direction as _detect_direction,
    compute_party_shift as _compute_opinion_shift,
)

world_updates_bp = Blueprint("world_updates", __name__)


def _updates_path() -> Path:
    p = Path(current_app.config["DATA_DIR"]) / "world_updates.json"
    if not p.exists():
        p.write_text("[]")
    return p


def _load_updates() -> list:
    return json.loads(_updates_path().read_text())


def _save_updates(updates: list):
    _updates_path().write_text(json.dumps(updates, indent=2))


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


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    clean = re.sub(r"<[^>]+>", "", text)
    return unescape(clean).strip()


def _fetch_rss(url: str, timeout: int = 8) -> list[dict]:
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
            desc = _strip_html(item.findtext("description", ""))
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


def _fetch_headlines(max_per_feed: int = 10) -> list[dict]:
    """Fetch recent headlines from all RSS feeds."""
    all_items = []
    for name, url in RSS_FEEDS.items():
        items = _fetch_rss(url)
        for item in items[:max_per_feed]:
            item["feed"] = name
        all_items.extend(items[:max_per_feed])

    # If we got nothing from main feeds, try Google News topic searches
    if len(all_items) < 5:
        for url in GOOGLE_NEWS_TOPICS:
            items = _fetch_rss(url)
            for item in items[:5]:
                item["feed"] = "Google News"
            all_items.extend(items[:5])

    return all_items


def _sample_relevant(headlines: list[dict], n: int = 8) -> list[dict]:
    """Sample headlines biased toward politically/economically relevant stories.

    Real people don't read every headline — they catch a handful.
    We bias toward stories that would actually shift opinions.
    """
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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@world_updates_bp.route("/api/world-updates", methods=["GET"])
def list_updates():
    return jsonify(_load_updates())


@world_updates_bp.route("/api/world-updates", methods=["POST"])
def create_update():
    """Create a single world update from provided text."""
    body = request.get_json(force=True, silent=True) or {}
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400

    topics = _detect_topics(text)
    direction = _detect_direction(text)
    shifts = _compute_opinion_shift(topics, direction)

    update = {
        "id": f"WU-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "text": text,
        "date": body.get("date", datetime.now().strftime("%Y-%m-%d")),
        "created_at": datetime.now().isoformat(),
        "topics": topics,
        "direction": direction,
        "shifts": shifts,
        "active": True,
        "source": "manual",
    }

    updates = _load_updates()
    updates.insert(0, update)
    _save_updates(updates)

    return jsonify(update), 201


@world_updates_bp.route("/api/world-updates/fetch", methods=["POST"])
def fetch_updates():
    """Auto-fetch current headlines from public RSS feeds, detect topics, create updates.

    This simulates the population 'browsing the web' — sampling a handful
    of real headlines that real people would encounter in their news feeds.
    """
    # Clear previous auto-fetched items (keep manual ones)
    updates = _load_updates()
    updates = [u for u in updates if u.get("source") != "auto"]

    # Fetch live headlines
    headlines = _fetch_headlines(max_per_feed=10)
    if not headlines:
        return jsonify({"error": "Could not fetch any headlines. Check internet connection."}), 502

    # Sample what a typical person would actually see/read
    sampled = _sample_relevant(headlines, n=8)

    new_updates = []
    for i, h in enumerate(sampled):
        text = h["title"]
        if h.get("description"):
            text += ". " + h["description"]

        topics = _detect_topics(text)
        direction = _detect_direction(text)
        shifts = _compute_opinion_shift(topics, direction)

        update = {
            "id": f"WU-{datetime.now().strftime('%Y%m%d%H%M%S')}-{i:02d}",
            "text": h["title"],
            "description": h.get("description", ""),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "created_at": datetime.now().isoformat(),
            "topics": topics,
            "direction": direction,
            "shifts": shifts,
            "active": True,
            "source": "auto",
            "feed": h.get("feed", ""),
        }
        new_updates.append(update)

    # Prepend new auto-fetched updates
    updates = new_updates + updates
    _save_updates(updates)

    return jsonify({
        "fetched": len(new_updates),
        "headlines_scanned": len(headlines),
        "updates": new_updates,
    })


@world_updates_bp.route("/api/world-updates/<update_id>", methods=["DELETE"])
def delete_update(update_id):
    updates = _load_updates()
    updates = [u for u in updates if u["id"] != update_id]
    _save_updates(updates)
    return jsonify({"deleted": True})


@world_updates_bp.route("/api/world-updates/<update_id>/toggle", methods=["POST"])
def toggle_update(update_id):
    updates = _load_updates()
    for u in updates:
        if u["id"] == update_id:
            u["active"] = not u.get("active", True)
            _save_updates(updates)
            return jsonify(u)
    return jsonify({"error": "Not found"}), 404


@world_updates_bp.route("/api/world-updates/active-shifts", methods=["GET"])
def get_active_shifts():
    updates = _load_updates()
    combined = {"dem": 0.0, "rep": 0.0, "independent": 0.0}
    active_count = 0
    for u in updates:
        if not u.get("active", True):
            continue
        active_count += 1
        for party, shift in u.get("shifts", {}).items():
            combined[party] = combined.get(party, 0.0) + shift

    for k in combined:
        combined[k] = max(-0.15, min(0.15, combined[k]))

    return jsonify({"shifts": combined, "active_count": active_count})


@world_updates_bp.route("/api/world-updates/clear-auto", methods=["POST"])
def clear_auto():
    """Remove all auto-fetched updates, keep manual ones."""
    updates = _load_updates()
    updates = [u for u in updates if u.get("source") != "auto"]
    _save_updates(updates)
    return jsonify({"remaining": len(updates)})
