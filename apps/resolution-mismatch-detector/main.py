"""CLI entry point for Resolution Rule Mismatch Detector."""

import argparse
import json
import logging
import sys
from datetime import datetime

from config import (
    ANALYSIS_BATCH_SIZE, CROSS_PLATFORM_MATCH_THRESHOLD,
    MIN_VOLUME_THRESHOLD, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


def mode_daily(db: Database, client: ClaudeClient):
    """Full daily scan: ingest, analyze top markets, generate report."""
    logger.info("=== DAILY SCAN ===")

    # 1. Ingest from both platforms
    logger.info("Fetching markets...")
    poly_client = PolymarketClient()
    kalshi_client = KalshiClient()

    poly_markets = poly_client.fetch_active_markets(min_volume=MIN_VOLUME_THRESHOLD)
    kalshi_markets = kalshi_client.fetch_active_markets(min_volume=MIN_VOLUME_THRESHOLD)

    logger.info(f"Fetched {len(poly_markets)} Polymarket, {len(kalshi_markets)} Kalshi markets")

    # 2. Normalize and store
    all_markets = []
    for raw in poly_markets:
        m = normalize_market(raw, "polymarket")
        db.upsert_market(m)
        rules_hash = compute_rules_hash(m["resolution_rules"])
        db.insert_rule_snapshot(m["id"], m["resolution_rules"], rules_hash)
        all_markets.append(m)

    for raw in kalshi_markets:
        m = normalize_market(raw, "kalshi")
        db.upsert_market(m)
        rules_hash = compute_rules_hash(m["resolution_rules"])
        db.insert_rule_snapshot(m["id"], m["resolution_rules"], rules_hash)
        all_markets.append(m)

    # 3. Build scan queue (pre-score before Claude API)
    queue = build_scan_queue(all_markets, position_checker=db.has_position)
    batch = queue[:ANALYSIS_BATCH_SIZE]
    logger.info(f"Analyzing top {len(batch)} markets by pre-score")

    # 4. Analyze each market
    analyzed = 0
    for market in batch:
        if db.is_dismissed(market["id"]):
            continue

        quirks = find_relevant_quirks(market.get("resolution_rules", ""))
        quirks_text = format_quirks_for_prompt(quirks)

        prompt = get_primary_prompt(
            platform=market["platform"],
            title=market["title"],
            rules=market["resolution_rules"],
            yes_price=market.get("current_yes_price", 0.5),
            end_date=market.get("end_date", ""),
            source_quirks_context=quirks_text,
        )

        try:
            result = client.analyze(prompt)
        except KeyboardInterrupt:
            logger.info("Interrupted, stopping analysis")
            break
        except Exception as e:
            logger.error(f"Analysis failed for {market['id']}: {e}")
            continue

        meta = result.pop("_meta", {})
        has_pos = db.has_position(market["id"])
        priority = calculate_priority(result, market, has_position=has_pos)

        db.insert_analysis({
            "market_id": market["id"],
            "analyzed_at": datetime.utcnow().isoformat(),
            "rules_hash": compute_rules_hash(market["resolution_rules"]),
            "prompt_version": PROMPT_VERSION,
            "mismatch_found": 1 if result.get("mismatch_found") else 0,
            "severity": result.get("severity", "none"),
            "mismatch_categories": json.dumps(result.get("categories", [])),
            "retail_assumption": result.get("retail_assumption", ""),
            "actual_resolution": result.get("actual_resolution", ""),
            "rules_adjusted_probability": result.get("rules_adjusted_probability"),
            "market_price_at_analysis": market.get("current_yes_price"),
            "price_divergence": result.get("divergence"),
            "priority_score": priority,
            "raw_response": meta.get("raw_response", ""),
        })
        analyzed += 1

        if result.get("mismatch_found"):
            logger.info(
                f"  MISMATCH [{result.get('severity')}] {market['title'][:60]} "
                f"(priority={priority:.2f})"
            )

    # 5. Generate report
    from output.report_generator import generate_daily_report
    report_path = generate_daily_report(db)

    spend = client.get_spend_summary()
    logger.info(
        f"Daily scan complete: {analyzed} analyzed, "
        f"${spend['daily_spend_usd']:.2f} spent, report at {report_path}"
    )


def mode_incremental(db: Database, client: ClaudeClient):
    """Incremental: check for rule changes and new markets only."""
    logger.info("=== INCREMENTAL SCAN ===")

    poly_client = PolymarketClient()
    kalshi_client = KalshiClient()

    poly_markets = poly_client.fetch_active_markets(min_volume=MIN_VOLUME_THRESHOLD)
    kalshi_markets = kalshi_client.fetch_active_markets(min_volume=MIN_VOLUME_THRESHOLD)

    all_normalized = []
    for raw in poly_markets:
        m = normalize_market(raw, "polymarket")
        db.upsert_market(m)
        all_normalized.append(m)
    for raw in kalshi_markets:
        m = normalize_market(raw, "kalshi")
        db.upsert_market(m)
        all_normalized.append(m)

    # Check for rule changes
    changes = check_for_rule_changes(all_normalized, db)
    if changes:
        logger.info(f"Found {len(changes)} rule changes")
        for change in changes:
            pos = db.get_position(change["market_id"])
            if pos:
                from analysis.rule_diff import analyze_rule_change_impact
                impact = analyze_rule_change_impact(
                    client,
                    db.get_market(change["market_id"]),
                    change["old_rules"],
                    change["new_rules"],
                    pos,
                )
                logger.warning(
                    f"Rule change on position {change['market_id']}: "
                    f"{impact.get('summary', 'N/A')}"
                )

    # Analyze new markets (not yet in analysis_results)
    new_markets = [
        m for m in all_normalized
        if not db.get_latest_analysis(m["id"]) and not db.is_dismissed(m["id"])
    ]
    queue = build_scan_queue(new_markets, position_checker=db.has_position)
    batch = queue[:ANALYSIS_BATCH_SIZE]
    logger.info(f"Analyzing {len(batch)} new markets")

    for market in batch:
        quirks = find_relevant_quirks(market.get("resolution_rules", ""))
        quirks_text = format_quirks_for_prompt(quirks)

        prompt = get_primary_prompt(
            platform=market["platform"],
            title=market["title"],
            rules=market["resolution_rules"],
            yes_price=market.get("current_yes_price", 0.5),
            end_date=market.get("end_date", ""),
            source_quirks_context=quirks_text,
        )

        try:
            result = client.analyze(prompt)
        except KeyboardInterrupt:
            logger.info("Interrupted, stopping")
            break
        except Exception as e:
            logger.error(f"Analysis failed for {market['id']}: {e}")
            continue

        meta = result.pop("_meta", {})
        priority = calculate_priority(result, market, db.has_position(market["id"]))

        db.insert_analysis({
            "market_id": market["id"],
            "analyzed_at": datetime.utcnow().isoformat(),
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


def mode_cross_platform(db: Database, client: ClaudeClient):
    """Cross-platform matching and arb detection."""
    logger.info("=== CROSS-PLATFORM SCAN ===")

    poly_markets = db.get_markets(platform="polymarket", min_volume=MIN_VOLUME_THRESHOLD)
    kalshi_markets = db.get_markets(platform="kalshi", min_volume=MIN_VOLUME_THRESHOLD)

    matches = find_cross_platform_matches(poly_markets, kalshi_markets,
                                          threshold=CROSS_PLATFORM_MATCH_THRESHOLD)
    logger.info(f"Found {len(matches)} cross-platform match candidates")

    for match in matches:
        poly = db.get_market(match["polymarket_id"])
        kalshi = db.get_market(match["kalshi_id"])
        if not poly or not kalshi:
            continue

        try:
            diff = analyze_cross_platform_diff(client, poly, kalshi)
        except KeyboardInterrupt:
            logger.info("Interrupted, stopping")
            break
        except Exception as e:
            logger.error(f"Cross-platform diff failed: {e}")
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
            "detected_at": datetime.utcnow().isoformat(),
            "last_checked_at": datetime.utcnow().isoformat(),
        })

        # Check for structural arb
        arb = detect_structural_arb(
            match,
            poly.get("current_yes_price", 0.5),
            kalshi.get("current_yes_price", 0.5),
            diff,
        )
        if arb:
            logger.warning(f"STRUCTURAL ARB: {arb}")


def mode_monitor(db: Database):
    """Poll resolution sources for updates."""
    logger.info("=== SOURCE MONITORING ===")
    flagged = poll_all_sources(db)
    if flagged:
        logger.info(f"Flagged {len(flagged)} markets from source updates")
        for f in flagged:
            logger.info(f"  {f['market_id']}: {f['event']} (urgency: {f['urgency']})")
    else:
        logger.info("No source updates detected")


def mode_report(db: Database):
    """Regenerate report from latest data."""
    from output.report_generator import generate_daily_report
    path = generate_daily_report(db)
    logger.info(f"Report generated: {path}")


def mode_eval(db: Database, client: ClaudeClient, prompt_version: str = None):
    """Run prompt evaluation against labeled dataset."""
    from eval.runner import run_prompt_eval
    results = run_prompt_eval(prompt_version=prompt_version, client=client, db=db)
    print(json.dumps(results, indent=2))


def mode_audit(db: Database, client: ClaudeClient):
    """Backfill resolved markets and calculate calibration metrics."""
    from audit.backfill import backfill_resolved_markets
    from audit.calibration import calculate_calibration_metrics
    backfill_resolved_markets(db=db, client=client)
    metrics = calculate_calibration_metrics(db=db)
    print(json.dumps(metrics, indent=2))


def mode_import_positions(db: Database, filepath: str):
    """Import positions from CSV."""
    from ingestion.position_importer import import_positions_from_csv
    import_positions_from_csv(filepath, db=db)
    logger.info(f"Positions imported from {filepath}")


def main():
    parser = argparse.ArgumentParser(description="Resolution Rule Mismatch Detector")
    parser.add_argument(
        "--mode", required=True,
        choices=["daily", "incremental", "cross-platform", "monitor",
                 "report", "eval", "audit", "import-positions"],
        help="Operating mode",
    )
    parser.add_argument("--prompt-version", default=None, help="Prompt version for eval mode")
    parser.add_argument("--file", default=None, help="File path for import modes")
    args = parser.parse_args()

    db = Database()
    client = None

    # Only create Claude client when needed
    if args.mode in ("daily", "incremental", "cross-platform", "eval", "audit"):
        client = ClaudeClient()

    try:
        if args.mode == "daily":
            mode_daily(db, client)
        elif args.mode == "incremental":
            mode_incremental(db, client)
        elif args.mode == "cross-platform":
            mode_cross_platform(db, client)
        elif args.mode == "monitor":
            mode_monitor(db)
        elif args.mode == "report":
            mode_report(db)
        elif args.mode == "eval":
            mode_eval(db, client, prompt_version=args.prompt_version)
        elif args.mode == "audit":
            mode_audit(db, client)
        elif args.mode == "import-positions":
            if not args.file:
                print("Error: --file required for import-positions mode")
                sys.exit(1)
            mode_import_positions(db, args.file)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)

    if client:
        spend = client.get_spend_summary()
        logger.info(f"Session: {spend['total_calls']} CLI calls ({spend['backend']})")


if __name__ == "__main__":
    main()
