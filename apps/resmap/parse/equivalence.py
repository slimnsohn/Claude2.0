"""
Equivalence engine — THE CROWN JEWEL.

Given a candidate pair of same-event markets across venues, compare their
parsed interpretations and decide whether they actually resolve identically.
Persists to `equivalences`. This is the old resolution-mismatch detector, now
writing data.

The four divergence axes (compare parsed_rules A vs B on each):
  - source     : is the authoritative settlement source the same? (different
                 source = they CAN resolve differently on the same event)
  - cutoff     : same effective cutoff time / basis? (6pm vs 11:59pm is real)
  - tie        : same tie/draw/push handling?
  - threshold  : same threshold + rounding? (">=50.0%" vs ">50%" matters)

How an axis verdict is reached, cheapest first:
  1. Deterministic — normalized source_ids, exact cutoff timestamps, both-null
     or normalized-equal text. Never calls the LLM.
  2. LLM judge — only the axes deterministic comparison can't settle
     (paraphrased text, one-sided nulls) go to a single `claude -p` call per
     pair. Tests inject a fake judge.

Output:
  match_type: 'true_match' (risk 0) | 'near_match' (0 < risk <= 0.25)
              | 'false_friend' (risk > 0.25 — the trap a naive arb scanner
              calls free money; surfacing these is the product's edge)
  risk_score: sum of AXIS_WEIGHTS over differing axes.

    python -m parse.equivalence              # match + compare + persist
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
from typing import Callable, Optional

from parse.candidate_matcher import find_candidates
from parse.claude_cli import call_claude_json

logger = logging.getLogger(__name__)

DIVERGENCE_AXES = ("source", "cutoff", "tie", "threshold")

# Relative weight of each axis toward risk. Source divergence is the most
# dangerous; threshold/tie are situation-dependent. Tune against the
# hand-verified seed set.
AXIS_WEIGHTS = {"source": 0.45, "cutoff": 0.25, "threshold": 0.20, "tie": 0.10}

NEAR_MATCH_CEILING = 0.25

Judge = Callable[[dict, dict, list], dict]

JUDGE_PROMPT = """You compare how two prediction markets on the SAME real-world \
event would settle. You think like a lawyer reading two contracts: only flag an \
axis when the difference could plausibly change which way money is paid, not for \
phrasing differences. Return ONLY a JSON object: {{"axes_different": [...], \
"notes": "one short sentence per flagged axis"}}. Only consider these axes: {axes}.

Axis meanings:
- source: the authoritative settlement source differs in a way that could call the event differently
- cutoff: the effective settlement cutoff time/basis differs
- tie: tie/draw/push handling differs
- threshold: the threshold or rounding definition differs

MARKET A interpretation:
{a}

MARKET B interpretation:
{b}"""


def _normalize(text) -> str:
    if text is None:
        return ""
    return re.sub(r"[^a-z0-9 ]", "", " ".join(str(text).split()).lower())


def _axis_verdict(axis: str, a: dict, b: dict) -> Optional[bool]:
    """True = same, False = different, None = undetermined (ask the judge)."""
    if axis == "source":
        if a.get("source_id") and b.get("source_id"):
            return a["source_id"] == b["source_id"]
        if not a.get("source_name") and not b.get("source_name"):
            return True  # neither side names a source — nothing to diverge on
        if _normalize(a.get("source_name")) == _normalize(b.get("source_name")):
            return True
        return None

    if axis == "cutoff":
        ta, tb = a.get("cutoff_time"), b.get("cutoff_time")
        if ta and tb:
            return ta == tb
        if ta is None and tb is None:
            ba, bb = a.get("cutoff_basis"), b.get("cutoff_basis")
            if ba == bb:
                return True
            return None
        return None  # one-sided cutoff — semantic question

    # text axes: tie / threshold
    field = "tie_handling" if axis == "tie" else "threshold_def"
    va, vb = a.get(field), b.get(field)
    if va is None and vb is None:
        return True
    if _normalize(va) == _normalize(vb):
        return True
    return None


def _claude_judge(parsed_a: dict, parsed_b: dict, axes: list) -> dict:
    """Default judge: one `claude -p` call for the unresolved axes."""
    def brief(p: dict) -> str:
        return json.dumps({
            "resolution_logic": p.get("resolution_logic"),
            "source": p.get("source_name"),
            "cutoff_time": str(p.get("cutoff_time")),
            "cutoff_basis": p.get("cutoff_basis"),
            "tie_handling": p.get("tie_handling"),
            "threshold_def": p.get("threshold_def"),
        }, indent=1, default=str)

    prompt = JUDGE_PROMPT.format(axes=", ".join(axes),
                                 a=brief(parsed_a), b=brief(parsed_b))
    raw = call_claude_json(prompt)
    flagged = [a for a in raw.get("axes_different", []) if a in axes]
    return {"axes_different": flagged, "notes": str(raw.get("notes", ""))}


def compare(parsed_a: dict, parsed_b: dict, judge: Judge | None = None) -> dict:
    """Compare two parsed-rule dicts across the four axes. Returns dict with
    match_type, divergence_axes, risk_score, divergence_notes."""
    judge = judge or _claude_judge
    different: list[str] = []
    undetermined: list[str] = []
    notes: list[str] = []

    for axis in DIVERGENCE_AXES:
        verdict = _axis_verdict(axis, parsed_a, parsed_b)
        if verdict is False:
            different.append(axis)
            notes.append(f"{axis}: deterministic mismatch")
        elif verdict is None:
            undetermined.append(axis)

    if undetermined:
        result = judge(parsed_a, parsed_b, undetermined)
        judged = [a for a in result.get("axes_different", [])
                  if a in undetermined]
        different.extend(judged)
        if result.get("notes"):
            notes.append(result["notes"])

    risk = round(sum(AXIS_WEIGHTS[a] for a in different), 4)
    if risk == 0:
        match_type = "true_match"
    elif risk <= NEAR_MATCH_CEILING:
        match_type = "near_match"
    else:
        match_type = "false_friend"

    return {
        "match_type": match_type,
        "divergence_axes": sorted(different),
        "risk_score": risk,
        "divergence_notes": "; ".join(notes),
    }


# source_id/name resolve THROUGH sources.merged_into (Layer 2): a curator-merged
# alias compares as its canonical authority, so two differently-worded source
# rows for the same authority stop firing the source axis.
FRESH_PARSE = """
    SELECT p.parsed_id,
           COALESCE(s.merged_into, p.source_id)            AS source_id,
           COALESCE(canon.canonical_name, s.canonical_name) AS canonical_name,
           p.cutoff_time, p.cutoff_basis, p.tie_handling, p.threshold_def,
           p.resolution_logic
    FROM parsed_rules p
    LEFT JOIN sources s     ON s.source_id = p.source_id
    LEFT JOIN sources canon ON canon.source_id = s.merged_into
    WHERE p.market_id = %s AND p.is_stale = FALSE
    ORDER BY p.created_at DESC
    LIMIT 1
"""


def _fetch_parsed(cur, market_id: str) -> Optional[dict]:
    cur.execute(FRESH_PARSE, (market_id,))
    row = cur.fetchone()
    if not row:
        return None
    keys = ("parsed_id", "source_id", "source_name", "cutoff_time",
            "cutoff_basis", "tie_handling", "threshold_def", "resolution_logic")
    return dict(zip(keys, row))


def run(conn, judge: Judge | None = None,
        min_similarity: float | None = None,
        date_window_days: int | None = None,
        pairs: list | None = None) -> dict:
    """Find candidate pairs (or use precomputed `pairs` — matching the full
    registry takes minutes, so pipelines cache it), compare the freshly parsed
    interpretations, and upsert `equivalences` rows (canonical a<b ordering so
    re-runs update in place). Pairs lacking a fresh parse on either side are
    skipped and counted — parse them first, then re-run."""
    if pairs is None:
        kwargs = {}
        if min_similarity is not None:
            kwargs["min_similarity"] = min_similarity
        if date_window_days is not None:
            kwargs["date_window_days"] = date_window_days
        pairs = find_candidates(conn, **kwargs)

    stats = {"candidates": len(pairs), "compared": 0, "skipped_unparsed": 0}

    for pair in pairs:
        a_id, b_id = sorted((pair.market_a_id, pair.market_b_id))
        with conn.cursor() as cur:
            parsed_a = _fetch_parsed(cur, a_id)
            parsed_b = _fetch_parsed(cur, b_id)
            if not parsed_a or not parsed_b:
                stats["skipped_unparsed"] += 1
                continue

            verdict = compare(parsed_a, parsed_b, judge=judge)
            cur.execute(
                """
                INSERT INTO equivalences (market_a_id, market_b_id,
                    parsed_a_id, parsed_b_id, match_type, divergence_axes,
                    divergence_notes, risk_score, detected_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'auto')
                ON CONFLICT (market_a_id, market_b_id) DO UPDATE SET
                    parsed_a_id = EXCLUDED.parsed_a_id,
                    parsed_b_id = EXCLUDED.parsed_b_id,
                    match_type = EXCLUDED.match_type,
                    divergence_axes = EXCLUDED.divergence_axes,
                    divergence_notes = EXCLUDED.divergence_notes,
                    risk_score = EXCLUDED.risk_score,
                    updated_at = now()
                """,
                (a_id, b_id, parsed_a["parsed_id"], parsed_b["parsed_id"],
                 verdict["match_type"], verdict["divergence_axes"],
                 verdict["divergence_notes"], verdict["risk_score"]),
            )
        conn.commit()  # per pair — judge calls are expensive
        stats["compared"] += 1
        print(f"  [{verdict['match_type']:12}] risk={verdict['risk_score']:.2f}"
              f"  {pair.title_a[:40]} <-> {pair.title_b[:40]}")

    return stats


def main(argv: list[str] | None = None) -> int:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="ResMap equivalence engine")
    parser.add_argument("--min-similarity", type=float, default=None)
    parser.add_argument("--date-window-days", type=int, default=None)
    args = parser.parse_args(argv)

    import psycopg
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        stats = run(conn, min_similarity=args.min_similarity,
                    date_window_days=args.date_window_days)
    finally:
        conn.close()
    print(f"[equivalence] {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
