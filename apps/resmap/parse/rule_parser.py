"""
Rule parser: raw settlement text → structured parsed_rules row.

Uses Claude (via the `claude -p` CLI — Max plan, no per-call cost) to extract
structured fields from the verbatim rules blob, stores with reviewed=False.
A human then spot-checks via parse/review_cli.py and flips reviewed=True.
The human-in-the-loop review IS the moat — do not auto-accept.

    python -m parse.rule_parser --limit 20            # parse 20, volume-first
    python -m parse.rule_parser --limit 3 --dry-run   # print parses, no writes

Selection is volume-ordered (highest first) with no cutoff: every market gets
parsed eventually; throughput is bounded by the CLI, so run in --limit batches.
Stale re-parse needs no extra code — a rule change flips is_stale=TRUE on all
of a market's parses, so the NOT EXISTS predicate re-selects it next run.

PARSING CONTRACT (the JSON schema Claude must return — mirrors parsed_rules):
{
  "resolution_logic":  str,   # normalized "resolves YES if ..."
  "authoritative_source": str,# canonical settlement source, e.g. "AP race call"
  "source_type": str,         # official_data | media_call | exchange_discretion | onchain | other
  "cutoff_time": str|null,    # ISO8601 if determinable from rules text
  "cutoff_basis": str,        # event_time | data_release | venue_stated
  "tie_handling": str,        # what happens on tie/draw/push
  "revision_handling": str,   # what happens if source data is later revised
  "threshold_def": str,       # exact threshold/rounding, e.g. ">= 50.0%"
  "confidence": float         # 0..1 self-assessed
}
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime
from typing import Optional

from parse.claude_cli import call_claude_json

logger = logging.getLogger(__name__)

REQUIRED_KEYS = (
    "resolution_logic", "authoritative_source", "source_type", "cutoff_time",
    "cutoff_basis", "tie_handling", "revision_handling", "threshold_def",
    "confidence",
)

PARSE_SYSTEM_PROMPT = """You extract prediction-market settlement semantics from raw \
rules text. You think like a lawyer reading a contract, not a casual bettor reading \
a headline — the exact source, cutoff, tie handling, and threshold wording decide \
real money. Return ONLY a single JSON object with exactly these keys: resolution_logic, \
authoritative_source, source_type, cutoff_time, cutoff_basis, tie_handling, \
revision_handling, threshold_def, confidence. No prose, no markdown, no preamble. \
source_type must be one of: official_data | media_call | exchange_discretion | onchain | other. \
cutoff_basis must be one of: event_time | data_release | venue_stated. \
If a field is not determinable from the text, use null (and lower your confidence)."""


class ParseValidationError(ValueError):
    """Claude's response is missing keys or has unusable values."""


def parse_rules_text(raw_rules: str, model: str | None = None) -> dict:
    """Call Claude on the verbatim rules text and return a validated dict with
    exactly REQUIRED_KEYS (extras dropped, confidence clamped, cutoff_time as
    a datetime or None)."""
    prompt = f"{PARSE_SYSTEM_PROMPT}\n\nRULES TEXT:\n{raw_rules}"
    raw = call_claude_json(prompt, model=model)

    missing = [k for k in REQUIRED_KEYS if k not in raw]
    if missing:
        raise ParseValidationError(f"missing keys: {missing}")

    parsed = {k: raw[k] for k in REQUIRED_KEYS}

    try:
        confidence = float(parsed["confidence"])
    except (TypeError, ValueError):
        raise ParseValidationError(f"confidence not numeric: {parsed['confidence']!r}")
    parsed["confidence"] = max(0.0, min(1.0, confidence))

    parsed["cutoff_time"] = _parse_cutoff(parsed["cutoff_time"])
    return parsed


def _parse_cutoff(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        logger.warning("unparseable cutoff_time %r — storing NULL", value)
        return None


def upsert_source(cur, canonical_name: str, source_type: str | None) -> str:
    """Dedupe settlement source into `sources`, return source_id."""
    cur.execute(
        """
        INSERT INTO sources (canonical_name, source_type)
        VALUES (%s, %s)
        ON CONFLICT (canonical_name) DO UPDATE SET source_type = COALESCE(sources.source_type, EXCLUDED.source_type)
        RETURNING source_id
        """,
        (canonical_name, source_type),
    )
    return cur.fetchone()[0]


# Latest snapshot per open market that has no fresh (non-stale) parse, ordered
# by venue-reported volume descending so high-value markets parse first.
# Volume lives in different raw_payload paths per venue; regex-guard the casts.
SELECT_UNPARSED = """
WITH latest AS (
    SELECT DISTINCT ON (m.market_id)
           m.market_id, s.snapshot_id, s.raw_rules, s.raw_payload
    FROM markets m
    JOIN rule_snapshots s ON s.market_id = m.market_id
    WHERE m.status = 'open'
      AND s.raw_rules <> ''
      AND NOT EXISTS (SELECT 1 FROM parsed_rules p
                      WHERE p.market_id = m.market_id AND p.is_stale = FALSE)
    ORDER BY m.market_id, s.fetched_at DESC
)
SELECT market_id, snapshot_id, raw_rules
FROM latest
ORDER BY GREATEST(
    CASE WHEN raw_payload->>'volume' ~ '^[0-9.]+$'
         THEN (raw_payload->>'volume')::float END,
    CASE WHEN raw_payload->>'volume_fp' ~ '^[0-9.]+$'
         THEN (raw_payload->>'volume_fp')::float END,
    CASE WHEN raw_payload->'event'->>'volume' ~ '^[0-9.]+$'
         THEN (raw_payload->'event'->>'volume')::float END
) DESC NULLS LAST
"""


def run(conn, limit: int | None = None, dry_run: bool = False,
        model: str | None = None) -> dict:
    """Parse un-parsed/stale snapshots, volume-first. Commits per row — LLM
    calls are expensive and a crash must not lose completed work."""
    stats = {"parsed": 0, "failed": 0}

    with conn.cursor() as cur:
        sql = SELECT_UNPARSED + (f" LIMIT {int(limit)}" if limit else "")
        cur.execute(sql)
        rows = cur.fetchall()

    print(f"{len(rows)} snapshot(s) queued for parsing")

    for market_id, snapshot_id, raw_rules in rows:
        try:
            parsed = parse_rules_text(raw_rules, model=model)
        except Exception as exc:  # noqa: BLE001 — log, skip, keep going
            logger.error("parse failed for market %s: %s", market_id, exc)
            stats["failed"] += 1
            continue

        if dry_run:
            print(json.dumps({**parsed,
                              "cutoff_time": str(parsed["cutoff_time"]),
                              "_market_id": str(market_id)}, indent=2))
            stats["parsed"] += 1
            continue

        with conn.cursor() as cur:
            source_id = None
            if parsed["authoritative_source"]:
                source_id = upsert_source(cur, parsed["authoritative_source"],
                                          parsed["source_type"])
            cur.execute(
                """
                INSERT INTO parsed_rules (market_id, snapshot_id, source_id,
                    resolution_logic, cutoff_time, cutoff_basis, tie_handling,
                    revision_handling, threshold_def, extraction_method,
                    confidence, reviewed, is_stale)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'llm',%s,FALSE,FALSE)
                """,
                (market_id, snapshot_id, source_id,
                 parsed["resolution_logic"], parsed["cutoff_time"],
                 parsed["cutoff_basis"], parsed["tie_handling"],
                 parsed["revision_handling"], parsed["threshold_def"],
                 parsed["confidence"]),
            )
        conn.commit()  # per row: a crash must not lose completed LLM work
        stats["parsed"] += 1
        print(f"  parsed {stats['parsed']}/{len(rows)} (market {market_id})")

    return stats


def main(argv: list[str] | None = None) -> int:
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="ResMap rule parser (claude -p)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="print parses without writing to the DB")
    parser.add_argument("--model", default=None,
                        help="claude CLI model override (default: env CLAUDE_CLI_MODEL or sonnet)")
    args = parser.parse_args(argv)

    import psycopg
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        stats = run(conn, limit=args.limit, dry_run=args.dry_run, model=args.model)
    finally:
        conn.close()
    print(f"[rule_parser] {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
