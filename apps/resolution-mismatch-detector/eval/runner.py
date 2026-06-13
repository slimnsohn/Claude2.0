"""Prompt A/B testing harness."""

import json
import logging
import time
from datetime import datetime
from pathlib import Path

from analysis.claude_client import ClaudeClient
from analysis.prompts import PROMPT_VERSION, get_primary_prompt
from analysis.source_quirks import find_relevant_quirks, format_quirks_for_prompt
from db.database import Database

logger = logging.getLogger(__name__)

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "labeled_markets.json"


def load_labeled_dataset(path: Path = None) -> list[dict]:
    """Load the labeled market dataset for evaluation."""
    path = path or FIXTURES_PATH
    with open(path) as f:
        return json.load(f)


def run_prompt_eval(
    prompt_version: str = None,
    labeled_data: list[dict] = None,
    client: ClaudeClient = None,
    db: Database = None,
) -> dict:
    """
    Run a prompt version against the labeled dataset.
    Track precision, recall, F1.
    Store results in prompt_evals table.
    """
    prompt_version = prompt_version or PROMPT_VERSION
    labeled_data = labeled_data or load_labeled_dataset()
    client = client or ClaudeClient()
    db = db or Database()

    results = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    category_results = {}

    for market in labeled_data:
        start_ms = time.time()

        quirks = find_relevant_quirks(market.get("rules", ""))
        quirks_text = format_quirks_for_prompt(quirks)

        prompt = get_primary_prompt(
            platform=market["platform"],
            title=market["title"],
            rules=market["rules"],
            yes_price=market.get("yes_price", 0.5),
            end_date=market.get("end_date", ""),
            source_quirks_context=quirks_text,
        )

        try:
            analysis = client.analyze(prompt)
        except Exception as e:
            logger.error(f"Failed to analyze {market['id']}: {e}")
            continue

        elapsed_ms = int((time.time() - start_ms) * 1000)
        predicted = analysis.get("mismatch_found", False)
        expected = market["expected_mismatch"]
        is_correct = predicted == expected

        # Confusion matrix
        if expected and predicted:
            results["tp"] += 1
        elif not expected and not predicted:
            results["tn"] += 1
        elif not expected and predicted:
            results["fp"] += 1
        else:
            results["fn"] += 1

        # Per-category tracking
        predicted_cats = set(analysis.get("categories", []))
        expected_cats = set(market.get("expected_categories", []))
        for cat in predicted_cats | expected_cats:
            if cat not in category_results:
                category_results[cat] = {"tp": 0, "fp": 0, "fn": 0}
            if cat in predicted_cats and cat in expected_cats:
                category_results[cat]["tp"] += 1
            elif cat in predicted_cats:
                category_results[cat]["fp"] += 1
            elif cat in expected_cats:
                category_results[cat]["fn"] += 1

        # Store in DB
        meta = analysis.get("_meta", {})
        db.insert_prompt_eval(
            prompt_version=prompt_version,
            eval_run_at=datetime.utcnow().isoformat(),
            labeled_market_id=market["id"],
            expected_mismatch=1 if expected else 0,
            predicted_mismatch=1 if predicted else 0,
            predicted_severity=analysis.get("severity"),
            is_correct=1 if is_correct else 0,
            latency_ms=elapsed_ms,
            token_count=meta.get("usage", {}).get("input_tokens", 0) +
                        meta.get("usage", {}).get("output_tokens", 0),
            notes=f"categories: {analysis.get('categories', [])}",
        )

        status = "CORRECT" if is_correct else "WRONG"
        logger.info(f"  {market['id']}: {status} (expected={expected}, predicted={predicted})")

    # Calculate metrics
    precision = results["tp"] / max(results["tp"] + results["fp"], 1)
    recall = results["tp"] / max(results["tp"] + results["fn"], 1)
    f1 = 2 * precision * recall / max(precision + recall, 0.001)

    summary = {
        "prompt_version": prompt_version,
        "total": sum(results.values()),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "confusion_matrix": results,
        "category_results": category_results,
    }

    logger.info(
        f"Eval complete: P={precision:.2f} R={recall:.2f} F1={f1:.2f} "
        f"(TP={results['tp']} FP={results['fp']} TN={results['tn']} FN={results['fn']})"
    )

    return summary
