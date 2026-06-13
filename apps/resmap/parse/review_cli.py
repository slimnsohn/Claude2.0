"""
Human review CLI for LLM rule parses. The review IS the moat — there is
deliberately no auto-accept path anywhere.

    python -m parse.review_cli list                # unreviewed, shakiest first
    python -m parse.review_cli show <id-prefix>    # parse beside verbatim rules
    python -m parse.review_cli approve <id-prefix> [...]
"""
from __future__ import annotations

import argparse
import os
import sys


def get_conn():
    from dotenv import load_dotenv
    load_dotenv()
    import psycopg
    return psycopg.connect(os.environ["DATABASE_URL"])


def cmd_list(conn) -> int:
    """Unreviewed, non-stale parses — lowest confidence first (review the
    shaky ones before they mislead anyone)."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT left(p.parsed_id::text, 8), v.code, left(m.title, 48),
                   coalesce(s.canonical_name, '—'), coalesce(p.threshold_def, '—'),
                   p.confidence
            FROM parsed_rules p
            JOIN markets m USING (market_id)
            JOIN venues v USING (venue_id)
            LEFT JOIN sources s USING (source_id)
            WHERE p.reviewed = FALSE AND p.is_stale = FALSE
            ORDER BY p.confidence ASC NULLS FIRST
        """)
        rows = cur.fetchall()

    if not rows:
        print("no unreviewed parses — queue is clear")
        return 0

    print(f"{'id':8}  {'venue':10}  {'title':48}  {'source':24}  {'threshold':20}  conf")
    for pid, venue, title, source, threshold, conf in rows:
        conf_s = f"{conf:.2f}" if conf is not None else "  ? "
        print(f"{pid:8}  {venue:10}  {title:48}  {source[:24]:24}  {str(threshold)[:20]:20}  {conf_s}")
    print(f"\n{len(rows)} unreviewed parse(s). "
          f"`python -m parse.review_cli show <id>` to inspect.")
    return 0


def _resolve_prefix(cur, prefix: str) -> str:
    cur.execute("""
        SELECT parsed_id::text FROM parsed_rules
        WHERE parsed_id::text LIKE %s
    """, (prefix + "%",))
    matches = [r[0] for r in cur.fetchall()]
    if not matches:
        raise SystemExit(f"no parse matches id prefix {prefix!r}")
    if len(matches) > 1:
        raise SystemExit(f"ambiguous prefix {prefix!r} matches {len(matches)} parses")
    return matches[0]


def cmd_show(conn, prefix: str) -> int:
    """Parsed fields beside the exact snapshot text they were derived from —
    the reviewer verifies against the verbatim source, not from memory."""
    with conn.cursor() as cur:
        parsed_id = _resolve_prefix(cur, prefix)
        cur.execute("""
            SELECT v.code, m.title, p.resolution_logic, s.canonical_name,
                   s.source_type, p.source_fallback, p.cutoff_time,
                   p.cutoff_basis, p.tie_handling,
                   p.revision_handling, p.threshold_def, p.confidence,
                   p.reviewed, p.is_stale, snap.raw_rules, snap.fetched_at
            FROM parsed_rules p
            JOIN markets m USING (market_id)
            JOIN venues v USING (venue_id)
            JOIN rule_snapshots snap USING (snapshot_id)
            LEFT JOIN sources s USING (source_id)
            WHERE p.parsed_id = %s::uuid
        """, (parsed_id,))
        row = cur.fetchone()

    (venue, title, logic, source, source_type, fallback, cutoff, cutoff_basis,
     tie, revision, threshold, conf, reviewed, is_stale, raw_rules,
     fetched_at) = row

    print(f"parse {parsed_id}")
    print(f"  market:    [{venue}] {title}")
    print(f"  reviewed:  {reviewed}   stale: {is_stale}   confidence: {conf}")
    print( "  ── parsed interpretation ──")
    print(f"  logic:     {logic}")
    print(f"  source:    {source} ({source_type})")
    print(f"  fallback:  {fallback}")
    print(f"  cutoff:    {cutoff}  basis: {cutoff_basis}")
    print(f"  tie:       {tie}")
    print(f"  revision:  {revision}")
    print(f"  threshold: {threshold}")
    print(f"  ── verbatim rules (snapshot {fetched_at}) ──")
    for line in (raw_rules or "").splitlines():
        print(f"  | {line}")
    print(f"\napprove with: python -m parse.review_cli approve {parsed_id[:8]}")
    return 0


def cmd_approve(conn, prefixes: list[str]) -> int:
    with conn.cursor() as cur:
        ids = [_resolve_prefix(cur, p) for p in prefixes]
        cur.execute("""
            UPDATE parsed_rules
            SET reviewed = TRUE, extraction_method = 'llm_reviewed'
            WHERE parsed_id = ANY(%s::uuid[]) AND reviewed = FALSE
            RETURNING parsed_id
        """, (ids,))
        updated = cur.fetchall()
    conn.commit()
    print(f"approved {len(updated)} parse(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252, which can't print venue rules text
    # (em-dashes, curly quotes, ...). Never crash a review over encoding.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="ResMap parse review")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    p_show = sub.add_parser("show")
    p_show.add_argument("parsed_id")
    p_approve = sub.add_parser("approve")
    p_approve.add_argument("parsed_ids", nargs="+")
    args = parser.parse_args(argv)

    conn = get_conn()
    try:
        if args.command == "list":
            return cmd_list(conn)
        if args.command == "show":
            return cmd_show(conn, args.parsed_id)
        return cmd_approve(conn, args.parsed_ids)
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
