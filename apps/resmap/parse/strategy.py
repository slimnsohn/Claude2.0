"""
Divergence-play strategy for false_friend pairs.

A false_friend is two markets on the "same" event that can resolve DIFFERENTLY.
This pass asks Claude, for each false_friend: in the scenario where they resolve
differently, which market resolves YES and which resolves NO? That single fact
("divergence direction") makes the trade mechanical:

    buy YES on the side that resolves YES-in-divergence,
    buy NO  on the side that resolves NO-in-divergence.

  - If the two markets AGREE (the usual case): exactly one leg pays $1 → you get
    ~$1 back, so if you entered near $1 you scratch (~$0).
  - If they DIVERGE the predicted way: BOTH legs pay → $2 → win.
  - If they diverge the OTHER way: neither pays → $0 → you lose the entry cost.

So you're betting on the *divergence*, not on who wins the underlying event. The
dollar math (and the opposite-direction risk) is computed at display time from
live prices — this module only stores the direction + the reasoning.

NOT financial advice — a structural signal; you decide and execute.

    python -m parse.strategy            # analyse all un-analysed false_friends
"""
from __future__ import annotations

import argparse
import json
import logging
import os

logger = logging.getLogger(__name__)

STRATEGY_PROMPT = """Two prediction markets, A and B, are a "false friend": they \
track the same real-world event but their settlement rules can make them resolve \
DIFFERENTLY. Think like a lawyer comparing two contracts.

They differ on: {axes}

MARKET A — {title_a}
{rules_a}

MARKET B — {title_b}
{rules_b}

In the specific scenario where A and B resolve DIFFERENTLY (one YES, one NO), \
which one resolves YES? Return ONLY a JSON object: \
{{"yes_market": "a" | "b", "scenario": "<one sentence: the concrete case where \
they split>", "rationale": "<one or two sentences: why, naming the rule \
difference>"}}."""


class StrategyValidationError(ValueError):
    """Claude returned an unusable direction."""


def _default_judge(prompt: str) -> dict:
    from parse.claude_cli import call_claude_json
    return call_claude_json(prompt)


def _market_brief(m: dict) -> str:
    fields = [("resolution", m.get("resolution_logic")),
              ("source", m.get("source")),
              ("cutoff", m.get("cutoff")),
              ("tie handling", m.get("tie_handling")),
              ("threshold", m.get("threshold_def"))]
    return "\n".join(f"  {k}: {v}" for k, v in fields if v) or "  (no parsed rules)"


def analyze_pair(market_a: dict, market_b: dict, axes, judge=None) -> dict:
    """Return {direction: 'a'|'b', scenario, rationale}. direction = which market
    resolves YES in the divergence case."""
    judge = judge or _default_judge
    prompt = STRATEGY_PROMPT.format(
        axes=", ".join(axes) or "their settlement details",
        title_a=market_a.get("title", "A"), rules_a=_market_brief(market_a),
        title_b=market_b.get("title", "B"), rules_b=_market_brief(market_b))
    raw = judge(prompt)
    ym = raw.get("yes_market")
    if ym not in ("a", "b"):
        raise StrategyValidationError(f"bad yes_market: {ym!r}")
    return {"direction": ym,
            "scenario": str(raw.get("scenario", ""))[:500],
            "rationale": str(raw.get("rationale", ""))[:800]}


SELECT_PENDING = """
    SELECT e.equivalence_id, e.divergence_axes,
           ma.title AS title_a, pa.resolution_logic AS logic_a,
           pa.threshold_def AS thr_a, pa.tie_handling AS tie_a,
           pa.cutoff_basis AS cb_a, sa.canonical_name AS src_a,
           mb.title AS title_b, pb.resolution_logic AS logic_b,
           pb.threshold_def AS thr_b, pb.tie_handling AS tie_b,
           pb.cutoff_basis AS cb_b, sb.canonical_name AS src_b
    FROM equivalences e
    JOIN markets ma ON ma.market_id = e.market_a_id
    JOIN markets mb ON mb.market_id = e.market_b_id
    LEFT JOIN parsed_rules pa ON pa.parsed_id = e.parsed_a_id
    LEFT JOIN parsed_rules pb ON pb.parsed_id = e.parsed_b_id
    LEFT JOIN sources sa ON sa.source_id = COALESCE(
        (SELECT merged_into FROM sources WHERE source_id = pa.source_id), pa.source_id)
    LEFT JOIN sources sb ON sb.source_id = COALESCE(
        (SELECT merged_into FROM sources WHERE source_id = pb.source_id), pb.source_id)
    WHERE e.match_type = 'false_friend' AND e.divergence_direction IS NULL
"""


def run(conn, judge=None) -> dict:
    """Analyse every false_friend lacking a strategy. Commits per row."""
    stats = {"analyzed": 0, "failed": 0}
    with conn.cursor() as cur:
        cur.execute(SELECT_PENDING)
        cols = [c.name for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    print(f"{len(rows)} false_friend(s) to analyse")
    for row in rows:
        market_a = {"title": row["title_a"], "resolution_logic": row["logic_a"],
                    "threshold_def": row["thr_a"], "tie_handling": row["tie_a"],
                    "cutoff": row["cb_a"], "source": row["src_a"]}
        market_b = {"title": row["title_b"], "resolution_logic": row["logic_b"],
                    "threshold_def": row["thr_b"], "tie_handling": row["tie_b"],
                    "cutoff": row["cb_b"], "source": row["src_b"]}
        try:
            out = analyze_pair(market_a, market_b, row["divergence_axes"] or [],
                               judge=judge)
        except Exception as exc:  # noqa: BLE001
            logger.error("strategy failed for %s: %s", row["equivalence_id"], exc)
            stats["failed"] += 1
            continue
        with conn.cursor() as cur:
            cur.execute("""UPDATE equivalences SET divergence_direction=%s,
                strategy_scenario=%s, strategy_rationale=%s, updated_at=now()
                WHERE equivalence_id=%s""",
                (out["direction"], out["scenario"], out["rationale"],
                 row["equivalence_id"]))
        conn.commit()
        stats["analyzed"] += 1
    return stats


def main(argv: list[str] | None = None) -> int:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argparse.ArgumentParser(description="ResMap divergence-play strategy").parse_args(argv)

    import psycopg
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        stats = run(conn)
    finally:
        conn.close()
    print(f"[strategy] {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
