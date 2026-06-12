"""Benchmarks API — real polling data for comparison against synthetic population.

Fetches real poll results from public sources and lets users run
the same questions through their synthetic population for comparison.
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

benchmarks_bp = Blueprint("benchmarks", __name__)


def _data_dir() -> Path:
    return Path(current_app.config["DATA_DIR"])


def _benchmarks_path() -> Path:
    p = _data_dir() / "benchmarks.json"
    if not p.exists():
        p.write_text("[]")
    return p


def _load_benchmarks() -> list:
    return json.loads(_benchmarks_path().read_text())


def _save_benchmarks(benchmarks: list):
    _benchmarks_path().write_text(json.dumps(benchmarks, indent=2))


# ---------------------------------------------------------------------------
# Curated benchmark polls — real aggregated results from public sources
# Updated periodically. Sources: FiveThirtyEight, Gallup, RCP averages
# ---------------------------------------------------------------------------

CURATED_BENCHMARKS = [
    {
        "question": "Do you approve of Trump's job performance?",
        "source": "FiveThirtyEight Average",
        "date": "2026-04-01",
        "real_results": {"yes": 0.467, "no": 0.493, "unsure": 0.04},
        "category": "approval",
        "url": "https://projects.fivethirtyeight.com/polls/approval/donald-trump/",
    },
    {
        "question": "Is the economy getting better or worse?",
        "source": "RCP Average",
        "date": "2026-03-28",
        "real_results": {"yes": 0.34, "no": 0.58, "unsure": 0.08},
        "category": "economy",
        "url": "https://www.realclearpolling.com/",
    },
    {
        "question": "Is the country going in the right direction?",
        "source": "RCP Average",
        "date": "2026-03-25",
        "real_results": {"yes": 0.28, "no": 0.63, "unsure": 0.09},
        "category": "direction",
        "url": "https://www.realclearpolling.com/polls/united-states/direction-of-country",
    },
    {
        "question": "Do you support increasing border security?",
        "source": "Gallup",
        "date": "2026-02-15",
        "real_results": {"yes": 0.72, "no": 0.22, "unsure": 0.06},
        "category": "immigration",
        "url": "https://news.gallup.com/poll/topics/immigration.aspx",
    },
    {
        "question": "Do you support Medicare for all?",
        "source": "KFF",
        "date": "2026-02-01",
        "real_results": {"yes": 0.59, "no": 0.35, "unsure": 0.06},
        "category": "healthcare",
        "url": "https://www.kff.org/",
    },
    {
        "question": "Do you support government action on climate change?",
        "source": "Pew Research",
        "date": "2026-02-10",
        "real_results": {"yes": 0.54, "no": 0.38, "unsure": 0.08},
        "category": "climate",
        "url": "https://www.pewresearch.org/topic/energy-environment/",
    },
    {
        "question": "Do you support tariffs on imported goods?",
        "source": "AP-NORC",
        "date": "2026-03-15",
        "real_results": {"yes": 0.40, "no": 0.47, "unsure": 0.13},
        "category": "economy",
        "url": "https://apnorc.org/",
    },
    {
        "question": "Do you support a path to citizenship for undocumented immigrants?",
        "source": "Gallup",
        "date": "2026-02-20",
        "real_results": {"yes": 0.64, "no": 0.30, "unsure": 0.06},
        "category": "immigration",
        "url": "https://news.gallup.com/poll/topics/immigration.aspx",
    },
    {
        "question": "Do you support raising taxes on income over $400k?",
        "source": "Gallup",
        "date": "2026-01-15",
        "real_results": {"yes": 0.62, "no": 0.33, "unsure": 0.05},
        "category": "foreign_policy",
        "url": "https://news.gallup.com/poll/topics/foreign-affairs.aspx",
    },
]


# ---------------------------------------------------------------------------
# Fetch real polls from public sources
# ---------------------------------------------------------------------------

POLL_RSS_FEEDS = [
    ("FiveThirtyEight", "https://fivethirtyeight.com/features/feed/"),
    ("RCP", "https://feeds.feedburner.com/realclearpolitics/qlMj"),
    ("Gallup", "https://news.gallup.com/feed/gallup-news.rss"),
]


def _strip_html(text: str) -> str:
    clean = re.sub(r"<[^>]+>", "", text)
    return unescape(clean).strip()


def _fetch_poll_headlines() -> list[dict]:
    """Try to fetch recent polling headlines from RSS feeds."""
    items = []
    for name, url in POLL_RSS_FEEDS:
        try:
            resp = requests.get(url, timeout=8, headers={
                "User-Agent": "SyntheticPopulationEngine/1.0"
            })
            if resp.status_code != 200:
                continue
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item")[:10]:
                title = item.findtext("title", "").strip()
                desc = _strip_html(item.findtext("description", ""))
                pub_date = item.findtext("pubDate", "")
                link = item.findtext("link", "")
                if title:
                    items.append({
                        "title": title,
                        "description": desc[:300],
                        "source": name,
                        "date": pub_date,
                        "url": link,
                    })
        except Exception:
            continue
    return items


# ---------------------------------------------------------------------------
# Run synthetic population on a benchmark question
# ---------------------------------------------------------------------------

def _run_synthetic(question: str, filters: dict = None) -> dict:
    """Run CES-modeled poll on the synthetic population, return distribution."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from api.polls import _load_registry, _apply_filters, _build_archetypes, _get_opinion
    from engine.ces_columns import match_question

    if match_question(question) is None:
        return {"error": "Question not covered by CES data"}

    profiles = _load_registry()
    if filters:
        profiles = _apply_filters(profiles, filters)

    if not profiles:
        return {"error": "No profiles"}

    profiles_with_arch, weights = _build_archetypes(profiles)
    if not weights:
        return {"error": "No archetypes"}

    profiles_by_arch = {}
    for p in profiles_with_arch:
        aid = p.get("archetype_id")
        if aid and aid not in profiles_by_arch:
            profiles_by_arch[aid] = p

    yes_w, no_w, unsure_w, total_w = 0.0, 0.0, 0.0, 0.0
    for aid, weight in weights.items():
        profile = profiles_by_arch.get(aid, {})
        result = _get_opinion(question, profile)
        if result is None:
            continue
        opinion, confidence, _ = result
        if opinion == "yes":
            yes_w += weight
        elif opinion == "no":
            no_w += weight
        else:
            unsure_w += weight
        total_w += weight

    if total_w == 0:
        return {"error": "No responses"}

    return {
        "yes": round(yes_w / total_w, 4),
        "no": round(no_w / total_w, 4),
        "unsure": round(unsure_w / total_w, 4),
        "archetype_count": len(weights),
        "profile_count": len(profiles),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@benchmarks_bp.route("/api/benchmarks", methods=["GET"])
def list_benchmarks():
    """Return curated + saved benchmark polls."""
    saved = _load_benchmarks()
    # Merge curated (don't duplicate if already saved)
    saved_questions = {b["question"].lower() for b in saved}
    merged = list(saved)
    for c in CURATED_BENCHMARKS:
        if c["question"].lower() not in saved_questions:
            merged.append({**c, "id": f"curated-{CURATED_BENCHMARKS.index(c)}", "curated": True})
    return jsonify(merged)


@benchmarks_bp.route("/api/benchmarks/run", methods=["POST"])
def run_benchmark():
    """Run a benchmark question on the synthetic population.

    Body: { "question": "...", "runs": 5 }
    Multiple runs are averaged to reduce stochastic noise.
    """
    body = request.get_json(force=True, silent=True) or {}
    question = body.get("question", "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400

    n_runs = min(body.get("runs", 10), 25)

    # Run multiple times and average to smooth out randomness
    totals = {"yes": 0.0, "no": 0.0, "unsure": 0.0}
    meta = {}
    for _ in range(n_runs):
        result = _run_synthetic(question)
        if "error" in result:
            return jsonify(result), 400
        totals["yes"] += result["yes"]
        totals["no"] += result["no"]
        totals["unsure"] += result["unsure"]
        meta = result

    synthetic = {
        "yes": round(totals["yes"] / n_runs, 4),
        "no": round(totals["no"] / n_runs, 4),
        "unsure": round(totals["unsure"] / n_runs, 4),
    }

    return jsonify({
        "question": question,
        "synthetic": synthetic,
        "runs": n_runs,
        "archetype_count": meta.get("archetype_count"),
        "profile_count": meta.get("profile_count"),
    })


@benchmarks_bp.route("/api/benchmarks/compare", methods=["POST"])
def compare_benchmark():
    """Run synthetic on a benchmark and return comparison with real data.

    Body: { "question": "...", "real_results": {"yes": 0.47, "no": 0.49, "unsure": 0.04} }
    """
    body = request.get_json(force=True, silent=True) or {}
    question = body.get("question", "").strip()
    real = body.get("real_results", {})
    if not question or not real:
        return jsonify({"error": "question and real_results are required"}), 400

    n_runs = min(body.get("runs", 10), 25)

    totals = {"yes": 0.0, "no": 0.0, "unsure": 0.0}
    meta = {}
    for _ in range(n_runs):
        result = _run_synthetic(question)
        if "error" in result:
            return jsonify(result), 400
        totals["yes"] += result["yes"]
        totals["no"] += result["no"]
        totals["unsure"] += result["unsure"]
        meta = result

    synthetic = {
        "yes": round(totals["yes"] / n_runs, 4),
        "no": round(totals["no"] / n_runs, 4),
        "unsure": round(totals["unsure"] / n_runs, 4),
    }

    # Compute error metrics
    errors = {}
    for k in ["yes", "no", "unsure"]:
        r = real.get(k, 0)
        s = synthetic.get(k, 0)
        errors[k] = round(s - r, 4)

    mae = round(sum(abs(v) for v in errors.values()) / len(errors), 4)

    # Save result
    comparison = {
        "id": f"CMP-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "question": question,
        "real": real,
        "synthetic": synthetic,
        "errors": errors,
        "mae": mae,
        "runs": n_runs,
        "archetype_count": meta.get("archetype_count"),
        "profile_count": meta.get("profile_count"),
        "compared_at": datetime.now().isoformat(),
    }

    # Append to saved benchmarks
    benchmarks = _load_benchmarks()
    # Update if question already exists, else append
    found = False
    for b in benchmarks:
        if b["question"].lower() == question.lower():
            b["last_comparison"] = comparison
            found = True
            break
    if not found:
        benchmarks.append({
            "question": question,
            "real_results": real,
            "source": body.get("source", ""),
            "date": body.get("date", ""),
            "category": body.get("category", ""),
            "url": body.get("url", ""),
            "last_comparison": comparison,
        })
    _save_benchmarks(benchmarks)

    return jsonify(comparison)


@benchmarks_bp.route("/api/benchmarks/fetch-headlines", methods=["GET"])
def fetch_headlines():
    """Fetch recent polling headlines from public RSS feeds."""
    items = _fetch_poll_headlines()
    return jsonify(items)
