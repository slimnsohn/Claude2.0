"""
Classify rule-change events: when a venue edits settlement criteria mid-market,
`ingest/core.py` records a `rule_change_events` row with severity='unknown'.
This pass compares the previous vs new rules text with Claude and labels each
'cosmetic' (wording/formatting only — same resolution) or 'material' (could
change how the market resolves), with a one-line diff summary. The 'material'
ones are the high-value alert.

    python -m parse.classify_changes              # classify all unknown events
    python -m parse.classify_changes --limit 20
"""
from __future__ import annotations

import argparse
import logging
import os

logger = logging.getLogger(__name__)

CLASSIFY_PROMPT = """You compare two versions of a prediction-market settlement \
rule (the venue edited it mid-market). Decide whether the change is "cosmetic" \
(wording, formatting, or clarification only — the market would resolve the same \
either way) or "material" (it could change which side the market resolves — a \
different source, cutoff, threshold, tie rule, or scope). When in doubt, choose \
material. Return ONLY a JSON object {{"severity": "cosmetic"|"material", \
"diff_summary": "<one sentence naming what changed>"}}.

PREVIOUS RULES:
{prev}

NEW RULES:
{new}"""


class ClassifyValidationError(ValueError):
    """Claude returned an unusable severity."""


def _default_judge(prompt: str) -> dict:
    from parse.claude_cli import call_claude_json
    return call_claude_json(prompt)


def classify_change(prev_rules: str, new_rules: str, judge=None) -> dict:
    """Return {severity, diff_summary}. severity ∈ {cosmetic, material}."""
    judge = judge or _default_judge
    raw = judge(CLASSIFY_PROMPT.format(prev=prev_rules or "(none)", new=new_rules))
    severity = raw.get("severity")
    if severity not in ("cosmetic", "material"):
        raise ClassifyValidationError(f"bad severity: {severity!r}")
    return {"severity": severity, "diff_summary": str(raw.get("diff_summary", ""))[:500]}


SELECT_UNKNOWN = """
    SELECT e.event_id, prev.raw_rules, new.raw_rules
    FROM rule_change_events e
    LEFT JOIN rule_snapshots prev ON prev.snapshot_id = e.prev_snapshot_id
    JOIN rule_snapshots new ON new.snapshot_id = e.new_snapshot_id
    WHERE e.severity = 'unknown' OR e.severity IS NULL
    ORDER BY e.detected_at DESC
"""


def run(conn, limit: int | None = None, judge=None) -> dict:
    """Classify every unknown-severity event. Commits per row."""
    stats = {"classified": 0, "failed": 0}
    with conn.cursor() as cur:
        sql = SELECT_UNKNOWN + (f" LIMIT {int(limit)}" if limit else "")
        cur.execute(sql)
        rows = cur.fetchall()

    print(f"{len(rows)} unclassified rule-change event(s)")
    for event_id, prev_rules, new_rules in rows:
        try:
            result = classify_change(prev_rules, new_rules, judge=judge)
        except Exception as exc:  # noqa: BLE001
            logger.error("classify failed for event %s: %s", event_id, exc)
            stats["failed"] += 1
            continue
        with conn.cursor() as cur:
            cur.execute("UPDATE rule_change_events SET severity=%s, diff_summary=%s "
                        "WHERE event_id=%s",
                        (result["severity"], result["diff_summary"], event_id))
        conn.commit()
        stats["classified"] += 1
    return stats


def main(argv: list[str] | None = None) -> int:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="classify rule-change severity")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    import psycopg
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        stats = run(conn, limit=args.limit)
    finally:
        conn.close()
    print(f"[classify_changes] {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
