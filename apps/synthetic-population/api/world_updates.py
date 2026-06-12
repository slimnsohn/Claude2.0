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
# Topic detection heuristics
# ---------------------------------------------------------------------------

TOPIC_KEYWORDS = {
    "economy": [
        "economy", "economic", "inflation", "recession", "gdp", "unemployment",
        "jobs report", "wages", "stock market", "housing", "interest rate",
        "federal reserve", "fed ", "dow", "nasdaq", "s&p", "tariff", "trade",
        "consumer", "spending", "debt", "deficit", "gas price", "oil price",
        "retail", "manufacturing",
    ],
    "trump_approval": [
        "trump", "president", "white house", "executive order", "administration",
        "oval office", "mar-a-lago", "presidential",
    ],
    "immigration": [
        "border", "immigration", "immigrant", "migrant", "asylum", "deportation",
        "ice ", "customs", "visa", "refugee", "undocumented", "daca",
    ],
    "healthcare": [
        "healthcare", "health care", "insurance", "medicaid", "medicare",
        "obamacare", "aca ", "hospital", "drug price", "pharmaceutical",
    ],
    "climate": [
        "climate", "environment", "emissions", "renewable", "fossil fuel",
        "carbon", "epa", "clean energy", "solar", "wind power", "wildfire",
        "hurricane", "flood", "drought",
    ],
    "gun_policy": [
        "gun", "firearm", "shooting", "second amendment", "nra",
        "background check", "assault weapon",
    ],
    "foreign_policy": [
        "russia", "ukraine", "china", "nato", "military", "war ",
        "iran", "north korea", "israel", "gaza", "taiwan", "sanctions",
        "missile", "troops",
    ],
    "social": [
        "abortion", "roe", "supreme court", "scotus", "transgender",
        "lgbtq", "marriage equality", "dei", "affirmative action",
    ],
    "education": [
        "school", "education", "student loan", "college", "university",
        "teacher", "curriculum",
    ],
    "crime": [
        "crime", "police", "law enforcement", "prison", "fentanyl",
        "drug ", "murder", "violent crime", "theft",
    ],
}

POSITIVE_SIGNALS = [
    "improve", "surge", "gain", "rise", "boost", "record high", "growth",
    "recover", "pass", "sign into law", "bipartisan", "agreement",
    "strong", "beat expectations", "optimis", "deal", "success",
]
NEGATIVE_SIGNALS = [
    "crash", "decline", "fall", "drop", "crisis", "scandal", "fail",
    "worse", "collapse", "layoff", "cut", "slash", "protest",
    "backlash", "concern", "fear", "warning", "record low", "pessimis",
    "indict", "investigation", "shutdown", "attack", "threat", "tension",
]

PARTY_VALENCE = {
    "economy":         {"positive": "incumbent", "negative": "opposition"},
    "trump_approval":  {"positive": "rep", "negative": "dem"},
    "immigration":     {"positive": "rep", "negative": "dem"},
    "healthcare":      {"positive": "dem", "negative": "dem"},
    "climate":         {"positive": "dem", "negative": "dem"},
    "gun_policy":      {"positive": "dem", "negative": "dem"},
    "foreign_policy":  {"positive": "incumbent", "negative": "opposition"},
    "social":          {"positive": "mixed", "negative": "mixed"},
    "education":       {"positive": "dem", "negative": "mixed"},
    "crime":           {"positive": "rep", "negative": "rep"},
}


def _detect_topics(text: str) -> list[str]:
    lower = text.lower()
    found = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            found.append(topic)
    return found or ["general"]


def _detect_direction(text: str) -> str:
    lower = text.lower()
    pos = sum(1 for s in POSITIVE_SIGNALS if s in lower)
    neg = sum(1 for s in NEGATIVE_SIGNALS if s in lower)
    if pos > neg:
        return "positive"
    elif neg > pos:
        return "negative"
    return "neutral"


def _compute_opinion_shift(topics: list, direction: str) -> dict:
    incumbent = "rep"  # Trump in office 2025-2026
    opposition = "dem"

    shifts = {"dem": 0.0, "rep": 0.0, "independent": 0.0}

    for topic in topics:
        valence = PARTY_VALENCE.get(topic, {"positive": "mixed", "negative": "mixed"})
        beneficiary = valence.get(direction, "mixed")

        if beneficiary == "incumbent":
            beneficiary = incumbent
        elif beneficiary == "opposition":
            beneficiary = opposition

        magnitude = 0.01  # small per-topic; ~8 headlines = ~5% max shift

        if beneficiary == "rep":
            shifts["rep"] += magnitude
            shifts["dem"] -= magnitude * 0.5
        elif beneficiary == "dem":
            shifts["dem"] += magnitude
            shifts["rep"] -= magnitude * 0.5

    for k in shifts:
        shifts[k] = max(-0.10, min(0.10, shifts[k]))

    return shifts


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
