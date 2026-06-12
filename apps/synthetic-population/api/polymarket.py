"""Polymarket API — trending markets with CES coverage + ask-the-population.

Pulls the top open markets by 24h volume from the public Polymarket Gamma
API (no key required), flags which ones the synthetic population can answer
from real CES survey data, and lets users run any covered question through
the population.

Important framing: the population answers what the PUBLIC believes/supports,
not what will happen — it is a public-opinion lens, not a price predictor.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from flask import Blueprint, jsonify, request, current_app

from api import benchmarks as _benchmarks
from engine.ces_columns import (
    match_question, detect_negated_phrasing, NEGATED_PHRASING_ERROR,
)

polymarket_bp = Blueprint("polymarket", __name__)

GAMMA_URL = "https://gamma-api.polymarket.com/markets"
GAMMA_PARAMS = {
    "closed": "false",
    "active": "true",
    "order": "volume24hr",
    "ascending": "false",
    "limit": "60",
}
MAX_RUNS = 25
DEFAULT_RUNS = 10

# Minimum summed keyword score for a trending market to be flagged "covered".
# A single generic keyword hit (bare "trump" scores 5) is not real coverage;
# /ask keeps the loose default because the user explicitly asked and the
# response shows ces_name, so they can see what was actually answered.
TRENDING_MIN_MATCH_SCORE = 10

# Sports futures and crypto markets are excluded from the trending feed:
# they price event outcomes, not public sentiment — there is no opinion
# the population could answer. Matched on Gamma's category field plus
# word-bounded keywords in the question/slug (\b so "ethics" never trips "eth").
EXCLUDED_CATEGORIES = {"sports", "crypto"}

_EXCLUDE_PATTERNS = re.compile(
    r"\b("
    # sports leagues, events, futures phrasing
    r"nba|nfl|mlb|nhl|ufc|mls|ncaa|fifa|uefa|pga|atp|wta|f1|formula 1|"
    r"grand prix|super bowl|world cup|world series|stanley cup|"
    r"premier league|champions league|la liga|serie a|bundesliga|ligue 1|"
    r"wimbledon|march madness|final four|heisman|olympics?|playoffs?|"
    r"grand slam|tour championship|ryder cup|"
    # esports
    r"esports|counter-strike|cs2|csgo|league of legends|lol|dota|valorant|"
    r"overwatch|iem|bo3|bo5|"
    # crypto assets and venues
    r"bitcoin|btc|ethereum|eth|solana|dogecoin|doge|xrp|cardano|ripple|"
    r"crypto(?:currency)?|stablecoin|memecoin|altcoin|nft|binance|coinbase|"
    r"satoshi"
    r")\b"
)

# Match-day futures ("Will Canada win on 2026-06-12?") are single-game sports
# markets whose question text carries no league keyword.
_MATCH_DAY_PATTERN = re.compile(r"\bwin (?:on|in) \d{4}-\d{2}-\d{2}\b")


def _is_excluded(m: dict, question: str) -> bool:
    """True when the market is a sports future or crypto market."""
    category = str(m.get("category") or "").strip().lower()
    if category in EXCLUDED_CATEGORIES:
        return True
    text = f"{question} {m.get('slug') or ''}".lower()
    return (_EXCLUDE_PATTERNS.search(text) is not None
            or _MATCH_DAY_PATTERN.search(text) is not None)


def _data_dir() -> Path:
    return Path(current_app.config["DATA_DIR"])


def _cache_path() -> Path:
    return _data_dir() / "polymarket_cache.json"


def _load_cache() -> dict | None:
    p = _cache_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _to_float(val) -> float | None:
    """Gamma returns numbers sometimes as floats, sometimes as strings."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _json_list(val) -> list:
    """Gamma encodes arrays like outcomes/outcomePrices as JSON strings."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _parse_market(m: dict) -> dict | None:
    """Parse one Gamma market defensively. Returns None if unusable."""
    if not isinstance(m, dict):
        return None
    question = (m.get("question") or "").strip()
    if not question:
        return None

    volume = _to_float(m.get("volume24hr"))
    if volume is None:
        volume = _to_float(m.get("volume24hrClob"))
    if volume is None:
        volume = 0.0

    outcomes = _json_list(m.get("outcomes"))
    prices = _json_list(m.get("outcomePrices"))
    implied_yes = None
    if outcomes and prices and str(outcomes[0]).strip().lower() == "yes":
        implied_yes = _to_float(prices[0])

    # Strict threshold for the coverage flag; loose match only for the
    # transparency score so users can see how weak a sub-threshold hit was.
    match = match_question(question, min_score=TRENDING_MIN_MATCH_SCORE)
    if match is not None:
        match_score = match["match_score"]
    else:
        loose = match_question(question)
        match_score = loose["match_score"] if loose else 0
    return {
        "question": question,
        "market_id": m.get("id"),
        "slug": m.get("slug"),
        "volume_24h": volume,
        "end_date": m.get("endDate"),
        "implied_yes": implied_yes,
        "covered": match is not None,
        "ces_column": match["col_id"] if match else None,
        "ces_name": match["name"] if match else None,
        "ces_topic": match["topic"] if match else None,
        "match_score": match_score,
    }


@polymarket_bp.route("/api/polymarket/trending", methods=["GET"])
def trending():
    """Top open Polymarket markets by 24h volume, with CES coverage flags."""
    try:
        limit = int(request.args.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 60))

    raw = None
    error = None
    try:
        resp = requests.get(
            GAMMA_URL,
            params=GAMMA_PARAMS,
            timeout=10,
            headers={"User-Agent": "SyntheticPopulationEngine/1.0"},
        )
        if resp.status_code == 200:
            raw = resp.json()
        else:
            error = f"Gamma API returned HTTP {resp.status_code}"
    except Exception as e:
        error = f"Gamma API unreachable: {e}"

    if raw is not None:
        markets = []
        excluded_count = 0
        for m in raw if isinstance(raw, list) else []:
            try:
                parsed = _parse_market(m)
                if parsed and _is_excluded(m, parsed["question"]):
                    excluded_count += 1
                    continue
            except Exception:
                continue  # skip malformed markets
            if parsed:
                markets.append(parsed)
        markets.sort(key=lambda x: x["volume_24h"] or 0, reverse=True)
        fetched_at = datetime.now(timezone.utc).isoformat()
        try:
            _cache_path().write_text(json.dumps(
                {"fetched_at": fetched_at, "markets": markets,
                 "excluded_count": excluded_count}, indent=2))
        except OSError:
            pass  # cache write failure should not break the response
        return jsonify({
            "fetched_at": fetched_at,
            "from_cache": False,
            "excluded_count": excluded_count,
            "markets": markets[:limit],
        })

    # Network/API failure — fall back to the last cached copy if present.
    cache = _load_cache()
    if cache is not None:
        return jsonify({
            "fetched_at": cache.get("fetched_at"),
            "from_cache": True,
            "markets": (cache.get("markets") or [])[:limit],
            "error": error,
        })
    return jsonify({
        "error": (f"Could not reach the Polymarket Gamma API and no cached "
                  f"copy exists yet. Try again when online. ({error})"),
    }), 502


@polymarket_bp.route("/api/polymarket/ask", methods=["POST"])
def ask():
    """Run a Polymarket-style question through the synthetic population.

    Body: { "question": "...", "runs": 10 }
    Multiple runs are averaged to reduce stochastic noise.
    """
    body = request.get_json(force=True, silent=True) or {}
    question = (body.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400

    # Reject negated question stems — the engine answers support/approval
    # distributions and would silently invert them (audit H2).
    if detect_negated_phrasing(question):
        return jsonify({"error": NEGATED_PHRASING_ERROR, "covered": False}), 400

    match = match_question(question)
    if match is None:
        return jsonify({"error": "Not covered by CES data", "covered": False}), 400

    try:
        n_runs = int(body.get("runs", DEFAULT_RUNS))
    except (TypeError, ValueError):
        n_runs = DEFAULT_RUNS
    n_runs = max(1, min(n_runs, MAX_RUNS))

    totals = {"yes": 0.0, "no": 0.0, "unsure": 0.0}
    meta = {}
    for _ in range(n_runs):
        result = _benchmarks._run_synthetic(question)
        if "error" in result:
            return jsonify(result), 400
        totals["yes"] += result["yes"]
        totals["no"] += result["no"]
        totals["unsure"] += result["unsure"]
        meta = result

    synthetic = {k: round(v / n_runs, 4) for k, v in totals.items()}

    return jsonify({
        "question": question,
        "covered": True,
        "ces_column": match["col_id"],
        "ces_name": match["name"],
        "ces_topic": match.get("topic"),
        "synthetic": synthetic,
        "runs": n_runs,
        "archetype_count": meta.get("archetype_count"),
        "profile_count": meta.get("profile_count"),
    })
