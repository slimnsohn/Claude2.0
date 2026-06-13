"""Flask web server — dashboard UI for the mismatch detector."""

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, jsonify, send_from_directory

from config import (
    ANALYSIS_BATCH_SIZE, CROSS_PLATFORM_MATCH_THRESHOLD,
    MIN_VOLUME_THRESHOLD, REPORTS_DIR,
)
from db.database import Database
from ingestion.polymarket import PolymarketClient
from ingestion.kalshi import KalshiClient
from ingestion.normalizer import normalize_market, compute_rules_hash
from analysis.claude_client import ClaudeClient
from analysis.prompts import get_primary_prompt, PROMPT_VERSION
from analysis.scorer import build_scan_queue, calculate_priority
from analysis.source_quirks import find_relevant_quirks, format_quirks_for_prompt
from analysis.rules_adjusted import estimate_rules_adjusted_probability
from analysis.rule_diff import analyze_cross_platform_diff
from matching.cross_platform import find_cross_platform_matches
from matching.arb_detector import detect_structural_arb
from monitoring.source_poller import poll_all_sources
from monitoring.rule_change_detector import check_for_rule_changes

app = Flask(__name__, static_folder="static")
db = Database()

# Map modes to feature categories
MODE_FEATURE = {
    "fetch": "fetch", "fetch-polymarket": "fetch", "fetch-kalshi": "fetch",
    "analyze": "analyze", "daily": "fetch",  # daily spans both
    "cross-platform": "analyze", "monitor": "fetch",
    "report": "report",
}

# --- Shared job state (polling-based, no SSE) ---
job_lock = threading.Lock()
cancel_flag = threading.Event()  # set to signal cancel
job_state = {
    "running": False,
    "mode": None,
    "feature": None,
    "percent": 0,
    "phase": "",
    "logs": [],
    "log_cursor": 0,
    "done": False,
    "summary": None,
}

# Persistent feature timestamps (survive across jobs)
feature_state = {
    "fetch": {"last_run": None, "last_status": "idle", "last_detail": "No data fetched yet"},
    "analyze": {"last_run": None, "last_status": "idle", "last_detail": "Not analyzed yet"},
    "report": {"last_run": None, "last_status": "idle", "last_detail": "No report generated"},
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def reset_job(mode: str):
    feature = MODE_FEATURE.get(mode, "fetch")
    cancel_flag.clear()
    job_state["running"] = True
    job_state["mode"] = mode
    job_state["feature"] = feature
    job_state["percent"] = 0
    job_state["phase"] = ""
    job_state["logs"] = []
    job_state["log_cursor"] = 0
    job_state["done"] = False
    job_state["summary"] = None
    feature_state[feature]["last_status"] = "running"
    feature_state[feature]["last_detail"] = f"Running {mode}..."


def is_cancelled() -> bool:
    """Check if current job was cancelled. Call this in loops."""
    return cancel_flag.is_set()


def emit_log(message: str, level: str = "info"):
    job_state["logs"].append({"message": message, "level": level, "time": _now()})
    job_state["log_cursor"] = len(job_state["logs"])


def emit_progress(current: int, total: int, phase: str = ""):
    job_state["percent"] = round(current / max(total, 1) * 100)
    job_state["phase"] = phase


def emit_done(summary: dict):
    feature = job_state.get("feature")
    job_state["running"] = False
    job_state["done"] = True
    job_state["summary"] = summary
    job_state["percent"] = 100

    if feature and feature in feature_state:
        feature_state[feature]["last_run"] = _now()
        if summary.get("error"):
            feature_state[feature]["last_status"] = "error"
            feature_state[feature]["last_detail"] = summary["error"][:80]
        else:
            feature_state[feature]["last_status"] = "done"
            # Build a useful summary string
            parts = []
            if summary.get("markets_cached"):
                parts.append(f"{summary['markets_cached']} cached")
            if summary.get("new_markets"):
                parts.append(f"{summary['new_markets']} new")
            if summary.get("markets_analyzed"):
                parts.append(f"{summary['markets_analyzed']} analyzed")
            if summary.get("mismatches_found"):
                parts.append(f"{summary['mismatches_found']} mismatches")
            if summary.get("report"):
                parts.append("generated")
            feature_state[feature]["last_detail"] = " | ".join(parts) if parts else "Complete"


# --- Shared analysis helper ---

def _analyze_batch(markets: list[dict], client: ClaudeClient) -> dict:
    batch = build_scan_queue(markets, position_checker=db.has_position)[:ANALYSIS_BATCH_SIZE]
    analyzed = 0
    mismatches = 0

    for i, market in enumerate(batch):
        if is_cancelled():
            emit_log("Cancelled.", "warn")
            break
        if db.is_dismissed(market["id"]):
            continue

        emit_progress(i, len(batch), f"Analyzing ({i+1}/{len(batch)}): {market['title'][:45]}...")

        quirks = find_relevant_quirks(market.get("resolution_rules", ""))
        prompt = get_primary_prompt(
            platform=market["platform"],
            title=market["title"],
            rules=market["resolution_rules"],
            yes_price=market.get("current_yes_price", 0.5),
            end_date=market.get("end_date", ""),
            source_quirks_context=format_quirks_for_prompt(quirks),
        )

        try:
            result = client.analyze(prompt)
        except Exception as e:
            emit_log(f"Analysis failed for {market['title'][:40]}: {e}", "error")
            continue

        meta = result.pop("_meta", {})
        has_pos = db.has_position(market["id"])
        priority = calculate_priority(result, market, has_position=has_pos)

        db.insert_analysis({
            "market_id": market["id"],
            "analyzed_at": _now(),
            "rules_hash": compute_rules_hash(market["resolution_rules"]),
            "prompt_version": PROMPT_VERSION,
            "mismatch_found": 1 if result.get("mismatch_found") else 0,
            "severity": result.get("severity", "none"),
            "mismatch_categories": json.dumps(result.get("categories", [])),
            "retail_assumption": result.get("retail_assumption", ""),
            "actual_resolution": result.get("actual_resolution", ""),
            "market_price_at_analysis": market.get("current_yes_price"),
            "price_divergence": result.get("divergence"),
            "priority_score": priority,
            "raw_response": meta.get("raw_response", ""),
        })
        analyzed += 1

        if result.get("mismatch_found"):
            mismatches += 1
            sev = result.get("severity", "?")
            emit_log(f"MISMATCH [{sev.upper()}] {market['title'][:60]} (priority={priority:.2f})", "warn")

    return {"analyzed": analyzed, "mismatches": mismatches}


# --- Shared fetch helper ---

def _store_markets(raw_markets: list[dict], platform: str) -> dict:
    """Store fetched markets in DB, detect new + rule changes. Returns stats."""
    new_count = 0
    updated_count = 0
    for i, raw in enumerate(raw_markets):
        if is_cancelled():
            emit_log("Cancelled during store.", "warn")
            break
        m = normalize_market(raw, platform)
        existing = db.get_market(m["id"])
        if not existing:
            new_count += 1
        elif compute_rules_hash(existing.get("resolution_rules", "")) != compute_rules_hash(m["resolution_rules"]):
            updated_count += 1
            emit_log(f"RULE CHANGE: {m['title'][:60]}", "warn")
        db.upsert_market(m)
        db.insert_rule_snapshot(m["id"], m["resolution_rules"], compute_rules_hash(m["resolution_rules"]))
    return {"stored": len(raw_markets), "new": new_count, "rule_changes": updated_count}


# --- Mode runners (threaded) ---

def run_fetch_polymarket():
    try:
        emit_log("Fetching Polymarket markets...")
        emit_progress(0, 2, "Fetching Polymarket")
        poly_client = PolymarketClient()
        poly_markets = poly_client.fetch_active_markets(min_volume=0)
        emit_log(f"Polymarket: {len(poly_markets)} markets fetched")

        emit_progress(1, 2, "Storing + diffing")
        stats = _store_markets(poly_markets, "polymarket")
        cache = db.get_cache_stats()
        emit_log(f"Done: {stats['stored']} stored ({stats['new']} new, {stats['rule_changes']} rule changes)")
        emit_log(f"Cache: {cache['total_markets']} total, {cache['unanalyzed']} unanalyzed")
        emit_progress(2, 2, "Complete")
        emit_done({"markets_cached": stats["stored"], "new_markets": stats["new"],
                    "rule_changes": stats["rule_changes"], "unanalyzed": cache["unanalyzed"]})
    except Exception as e:
        emit_log(f"Polymarket fetch failed: {e}", "error")
        emit_done({"error": str(e)})


def run_fetch_kalshi():
    try:
        emit_log("Fetching Kalshi markets...")
        emit_progress(0, 2, "Fetching Kalshi")
        kalshi_client = KalshiClient()
        kalshi_markets = kalshi_client.fetch_active_markets(min_volume=0)
        emit_log(f"Kalshi: {len(kalshi_markets)} markets fetched")

        emit_progress(1, 2, "Storing + diffing")
        stats = _store_markets(kalshi_markets, "kalshi")
        cache = db.get_cache_stats()
        emit_log(f"Done: {stats['stored']} stored ({stats['new']} new, {stats['rule_changes']} rule changes)")
        emit_log(f"Cache: {cache['total_markets']} total, {cache['unanalyzed']} unanalyzed")
        emit_progress(2, 2, "Complete")
        emit_done({"markets_cached": stats["stored"], "new_markets": stats["new"],
                    "rule_changes": stats["rule_changes"], "unanalyzed": cache["unanalyzed"]})
    except Exception as e:
        emit_log(f"Kalshi fetch failed: {e}", "error")
        emit_done({"error": str(e)})


def run_fetch():
    try:
        emit_log("Fetching Polymarket markets...")
        emit_progress(0, 4, "Fetching Polymarket")
        poly_client = PolymarketClient()
        poly_markets = poly_client.fetch_active_markets(min_volume=0)
        emit_log(f"Polymarket: {len(poly_markets)} markets")

        emit_progress(1, 4, "Fetching Kalshi")
        emit_log("Fetching Kalshi markets...")
        kalshi_client = KalshiClient()
        kalshi_markets = kalshi_client.fetch_active_markets(min_volume=0)
        emit_log(f"Kalshi: {len(kalshi_markets)} markets")

        emit_progress(2, 4, "Storing Polymarket")
        poly_stats = _store_markets(poly_markets, "polymarket")
        emit_progress(3, 4, "Storing Kalshi")
        kalshi_stats = _store_markets(kalshi_markets, "kalshi")

        total = poly_stats["stored"] + kalshi_stats["stored"]
        new_total = poly_stats["new"] + kalshi_stats["new"]
        changes_total = poly_stats["rule_changes"] + kalshi_stats["rule_changes"]
        cache = db.get_cache_stats()
        emit_log(f"Done: {total} markets cached ({new_total} new, {changes_total} rule changes)")
        emit_log(f"Cache: {cache['total_markets']} total, {cache['unanalyzed']} unanalyzed")
        emit_progress(4, 4, "Complete")
        emit_done({"markets_cached": total, "new_markets": new_total,
                    "rule_changes": changes_total, "unanalyzed": cache["unanalyzed"]})
    except Exception as e:
        emit_log(f"Fetch failed: {e}", "error")
        emit_done({"error": str(e)})


def run_analyze():
    try:
        cache = db.get_cache_stats()
        if cache["total_markets"] == 0:
            emit_log("No cached markets. Run Fetch first.", "error")
            emit_done({"error": "No cached data. Fetch first."})
            return

        emit_log(f"Cache: {cache['total_markets']} markets, {cache['unanalyzed']} unanalyzed")
        emit_progress(0, 2, "Finding markets to analyze")

        unanalyzed = db.get_unanalyzed_markets(min_volume=0)
        stale = db.get_stale_markets()
        seen = set()
        to_analyze = []
        for m in stale + unanalyzed:
            if m["id"] not in seen:
                seen.add(m["id"])
                to_analyze.append(m)

        if not to_analyze:
            emit_log("All cached markets already analyzed. Nothing to do.")
            emit_progress(1, 1, "Complete")
            emit_done({"analyzed": 0, "mismatches": 0, "note": "all up to date"})
            return

        emit_log(f"Found {len(to_analyze)} markets to analyze ({len(stale)} stale, {len(unanalyzed)} new)")
        emit_progress(1, 2, "Analyzing with Claude")

        client = ClaudeClient()
        stats = _analyze_batch(to_analyze, client)

        from output.report_generator import generate_daily_report
        report_path = generate_daily_report(db)

        spend = client.get_spend_summary()
        emit_progress(1, 1, "Complete")
        emit_done({"markets_analyzed": stats["analyzed"], "mismatches_found": stats["mismatches"],
                    "report": report_path, "calls": spend["total_calls"]})
    except Exception as e:
        emit_log(f"Analyze failed: {e}", "error")
        emit_done({"error": str(e)})


def run_daily():
    try:
        emit_log("=== FETCH PHASE ===")
        emit_progress(0, 5, "Fetching Polymarket")
        poly_client = PolymarketClient()
        poly_markets = poly_client.fetch_active_markets(min_volume=0)
        emit_log(f"Polymarket: {len(poly_markets)} markets")

        emit_progress(1, 5, "Fetching Kalshi")
        kalshi_client = KalshiClient()
        kalshi_markets = kalshi_client.fetch_active_markets(min_volume=0)
        emit_log(f"Kalshi: {len(kalshi_markets)} markets")

        emit_progress(2, 5, "Storing markets")
        all_markets = []
        for raw in poly_markets:
            m = normalize_market(raw, "polymarket")
            db.upsert_market(m)
            db.insert_rule_snapshot(m["id"], m["resolution_rules"], compute_rules_hash(m["resolution_rules"]))
            all_markets.append(m)
        for raw in kalshi_markets:
            m = normalize_market(raw, "kalshi")
            db.upsert_market(m)
            db.insert_rule_snapshot(m["id"], m["resolution_rules"], compute_rules_hash(m["resolution_rules"]))
            all_markets.append(m)
        emit_log(f"Stored {len(all_markets)} total markets")

        emit_log("=== ANALYZE PHASE ===")
        emit_progress(3, 5, "Analyzing markets")
        client = ClaudeClient()
        stats = _analyze_batch(all_markets, client)

        emit_progress(4, 5, "Generating report")
        from output.report_generator import generate_daily_report
        report_path = generate_daily_report(db)

        spend = client.get_spend_summary()
        emit_progress(5, 5, "Complete")
        emit_done({"markets_fetched": len(all_markets), "markets_analyzed": stats["analyzed"],
                    "mismatches_found": stats["mismatches"], "report": report_path,
                    "calls": spend["total_calls"]})
    except Exception as e:
        emit_log(f"Daily scan failed: {e}", "error")
        emit_done({"error": str(e)})


def run_cross_platform():
    try:
        client = ClaudeClient()
        emit_progress(0, 2, "Matching markets")
        emit_log("Finding cross-platform matches...")
        poly_markets = db.get_markets(platform="polymarket", min_volume=0)
        kalshi_markets = db.get_markets(platform="kalshi", min_volume=0)
        matches = find_cross_platform_matches(poly_markets, kalshi_markets,
                                              threshold=CROSS_PLATFORM_MATCH_THRESHOLD)
        emit_log(f"Found {len(matches)} match candidates")

        emit_progress(1, 2, "Analyzing diffs")
        arbs = 0
        for i, match in enumerate(matches):
            emit_progress(i, len(matches), f"Comparing pair {i+1}/{len(matches)}")
            poly = db.get_market(match["polymarket_id"])
            kalshi = db.get_market(match["kalshi_id"])
            if not poly or not kalshi:
                continue
            try:
                diff = analyze_cross_platform_diff(client, poly, kalshi)
            except Exception as e:
                emit_log(f"Diff failed: {e}", "error")
                continue
            meta = diff.pop("_meta", {})
            db.insert_cross_match({
                "polymarket_id": match["polymarket_id"],
                "kalshi_id": match["kalshi_id"],
                "match_confidence": match["match_confidence"],
                "title_similarity": match["title_similarity"],
                "date_match": match["date_match"],
                "rule_divergence_summary": json.dumps(diff.get("key_differences", [])),
                "arb_signal": 1 if diff.get("arb_opportunity") else 0,
                "detected_at": _now(),
                "last_checked_at": _now(),
            })
            arb = detect_structural_arb(
                match, poly.get("current_yes_price", 0.5),
                kalshi.get("current_yes_price", 0.5), diff,
            )
            if arb:
                arbs += 1
                emit_log(f"ARB DETECTED: {poly['title'][:40]} vs {kalshi['title'][:40]}", "warn")
        emit_progress(len(matches), len(matches), "Complete")
        emit_done({"matches": len(matches), "arbs_detected": arbs})
    except Exception as e:
        emit_log(f"Cross-platform scan failed: {e}", "error")
        emit_done({"error": str(e)})


def run_monitor():
    try:
        emit_progress(0, 1, "Polling sources")
        emit_log("Polling resolution sources...")
        flagged = poll_all_sources(db)
        emit_log(f"Flagged {len(flagged)} markets from source updates")
        for f in flagged:
            emit_log(f"  {f['market_id']}: {f['event']} (urgency: {f['urgency']})", "warn")
        emit_progress(1, 1, "Complete")
        emit_done({"flagged_markets": len(flagged)})
    except Exception as e:
        emit_log(f"Monitor failed: {e}", "error")
        emit_done({"error": str(e)})


def run_report():
    try:
        emit_progress(0, 1, "Generating report")
        emit_log("Generating report from latest data...")
        from output.report_generator import generate_daily_report
        path = generate_daily_report(db)
        emit_log(f"Report written to {path}")
        emit_progress(1, 1, "Complete")
        emit_done({"report": path})
    except Exception as e:
        emit_log(f"Report failed: {e}", "error")
        emit_done({"error": str(e)})


MODE_RUNNERS = {
    "fetch": run_fetch,
    "fetch-polymarket": run_fetch_polymarket,
    "fetch-kalshi": run_fetch_kalshi,
    "analyze": run_analyze,
    "daily": run_daily,
    "cross-platform": run_cross_platform,
    "monitor": run_monitor,
    "report": run_report,
}


# --- Routes ---

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/dashboard")
def dashboard():
    return send_from_directory("static", "dashboard.html")


@app.route("/api/run/<mode>", methods=["POST"])
def api_run_mode(mode):
    if mode not in MODE_RUNNERS:
        return jsonify({"error": f"Unknown mode: {mode}"}), 400
    with job_lock:
        if job_state["running"]:
            return jsonify({"error": f"Already running: {job_state['mode']}"}), 409
        reset_job(mode)
    emit_log(f"Starting {mode}...")
    thread = threading.Thread(target=MODE_RUNNERS[mode], daemon=True)
    thread.start()
    return jsonify({"status": "started", "mode": mode})


@app.route("/api/cancel", methods=["POST"])
def api_cancel():
    if not job_state["running"]:
        return jsonify({"status": "nothing running"})
    cancel_flag.set()
    emit_log("Cancelling...", "warn")
    return jsonify({"status": "cancelling", "mode": job_state["mode"]})


@app.route("/api/progress")
def api_progress():
    """Polled by frontend every second. Returns new logs + progress + feature states."""
    since = int(request_args_get("since", 0))
    new_logs = job_state["logs"][since:]
    return jsonify({
        "running": job_state["running"],
        "mode": job_state["mode"],
        "feature": job_state.get("feature"),
        "percent": job_state["percent"],
        "phase": job_state["phase"],
        "logs": new_logs,
        "log_cursor": job_state["log_cursor"],
        "features": feature_state,
        "done": job_state["done"],
        "summary": job_state["summary"],
    })


def request_args_get(key, default=None):
    from flask import request
    return request.args.get(key, default)


@app.route("/api/status")
def api_status():
    high = db.get_analyses(severity="high")
    medium = db.get_analyses(severity="medium")
    cache = db.get_cache_stats()
    return jsonify({
        "running": job_state["running"],
        "current_mode": job_state["mode"],
        "high_severity": len(high),
        "medium_severity": len(medium),
        "positions": len(db.get_all_positions()),
        "watchlist": len(db.get_watchlist()),
        "cache": cache,
        "features": feature_state,
    })


@app.route("/api/results")
def api_results():
    high = db.get_analyses(severity="high")
    medium = db.get_analyses(severity="medium")
    low = db.get_analyses(severity="low")

    def enrich(a):
        market = db.get_market(a["market_id"])
        return {
            **{k: a[k] for k in a.keys()},
            "market_title": market["title"] if market else "Unknown",
            "market_platform": market["platform"] if market else "",
            "market_price": market["current_yes_price"] if market else None,
            "market_volume": market["volume"] if market else 0,
            "market_end_date": market["end_date"] if market else None,
            "resolution_rules": market["resolution_rules"] if market else "",
            "fetched_at": market["last_updated_at"] if market else None,
        }

    return jsonify({
        "high": [enrich(a) for a in high],
        "medium": [enrich(a) for a in medium],
        "low": [enrich(a) for a in low],
    })


@app.route("/api/report/latest")
def api_latest_report():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    reports = sorted(REPORTS_DIR.glob("report_*.md"), reverse=True)
    if not reports:
        return jsonify({"content": "No reports generated yet."})
    return jsonify({"content": reports[0].read_text(encoding="utf-8"), "file": reports[0].name})


@app.route("/api/markets")
def api_markets():
    """Browse/search cached markets. Params: platform, q, sort, limit, offset."""
    from flask import request
    platform = request.args.get("platform")  # polymarket, kalshi, or None for all
    query = request.args.get("q", "").strip().lower()
    sort = request.args.get("sort", "volume")  # volume, price, title, end_date
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    conn = db._connect()

    # Build query
    sql = "SELECT * FROM markets WHERE 1=1"
    params = []
    if platform:
        sql += " AND platform = ?"
        params.append(platform)
    if query:
        sql += " AND (LOWER(title) LIKE ? OR LOWER(resolution_rules) LIKE ?)"
        params.extend([f"%{query}%", f"%{query}%"])

    # Count total before pagination
    count_sql = sql.replace("SELECT *", "SELECT COUNT(*)")
    total = conn.execute(count_sql, params).fetchone()[0]

    # Sort
    sort_map = {
        "volume": "volume DESC",
        "price": "current_yes_price DESC",
        "title": "title ASC",
        "end_date": "end_date ASC",
        "recent": "last_updated_at DESC",
    }
    sql += f" ORDER BY {sort_map.get(sort, 'volume DESC')}"
    sql += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    markets = []
    for r in rows:
        m = dict(r)
        # Check if analyzed
        analysis = db.get_latest_analysis(m["id"])
        m["analyzed"] = analysis is not None
        m["mismatch_severity"] = analysis["severity"] if analysis and analysis["mismatch_found"] else None
        # Trim raw_json for response size
        m.pop("raw_json", None)
        markets.append(m)

    return jsonify({"markets": markets, "total": total, "limit": limit, "offset": offset})


@app.route("/api/markets/<path:market_id>")
def api_market_detail(market_id):
    """Get full detail for a single market including analysis."""
    market = db.get_market(market_id)
    if not market:
        return jsonify({"error": "Market not found"}), 404

    market.pop("raw_json", None)
    analysis = db.get_latest_analysis(market_id)
    position = db.get_position(market_id)

    return jsonify({
        "market": market,
        "analysis": dict(analysis) if analysis else None,
        "position": dict(position) if position else None,
    })


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    print("\n  Resolution Mismatch Detector — http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
