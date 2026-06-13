"""
Human review CLI for LLM rule parses. The review IS the moat — there is
deliberately no auto-accept path anywhere.

    python -m parse.review_cli list                # unreviewed, shakiest first
    python -m parse.review_cli show <id-prefix>    # parse beside verbatim rules
    python -m parse.review_cli approve <id-prefix> [...]
    python -m parse.review_cli list-sources        # source registry + merge status
    python -m parse.review_cli merge-source <alias> <canonical>   # dedupe authorities
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


# ── source curation (Layer 2: merge near-duplicate authority rows) ───────────

def _resolve_source(cur, needle: str) -> tuple[str, str]:
    """Resolve a source by exact name first, else source_id prefix /
    canonical_name substring (both case-insensitive). Exact match wins so a
    short name like "FIFA" resolves even when it's a substring of others.
    Returns (source_id, canonical_name); SystemExit if 0 or ambiguous."""
    cur.execute("SELECT source_id::text, canonical_name FROM sources "
                "WHERE canonical_name ILIKE %s", (needle,))
    exact = cur.fetchall()
    if len(exact) == 1:
        return exact[0]

    cur.execute("""
        SELECT source_id::text, canonical_name FROM sources
        WHERE source_id::text LIKE %s || '%%' OR canonical_name ILIKE '%%' || %s || '%%'
    """, (needle, needle))
    matches = cur.fetchall()
    if not matches:
        raise SystemExit(f"no source matches {needle!r}")
    if len(matches) > 1:
        names = ", ".join(n for _, n in matches[:5])
        raise SystemExit(f"ambiguous source {needle!r} matches {len(matches)}: {names}")
    return matches[0]


def cmd_merge_source(conn, alias_needle: str, canonical_needle: str) -> int:
    """Point `alias` at `canonical` (alias.merged_into = canonical). The
    equivalence source axis then treats them as the same authority. Curation
    is the moat — there is no automatic merge."""
    with conn.cursor() as cur:
        alias_id, alias_name = _resolve_source(cur, alias_needle)
        canon_id, canon_name = _resolve_source(cur, canonical_needle)

        if alias_id == canon_id:
            raise SystemExit(f"cannot merge {alias_name!r} into itself")

        cur.execute("SELECT merged_into FROM sources WHERE source_id=%s::uuid",
                    (canon_id,))
        if cur.fetchone()[0] is not None:
            raise SystemExit(
                f"target {canon_name!r} is not canonical (already merged into "
                f"another row); merge into the canonical row instead")

        cur.execute("SELECT count(*) FROM sources WHERE merged_into=%s::uuid",
                    (alias_id,))
        if cur.fetchone()[0]:
            raise SystemExit(
                f"{alias_name!r} has rows merged into it (dependents); merging "
                f"it would chain — re-point those first")

        cur.execute("UPDATE sources SET merged_into=%s::uuid WHERE source_id=%s::uuid",
                    (canon_id, alias_id))
    conn.commit()
    print(f"merged {alias_name!r} → {canon_name!r}")
    return 0


def cmd_list_sources(conn) -> int:
    """All source rows with live-parse counts and merge status — the curator's
    view for spotting near-duplicates to merge."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT s.canonical_name, s.merged_into IS NOT NULL AS is_alias,
                   c.canonical_name AS canon_name,
                   count(p.parsed_id) FILTER (WHERE p.is_stale = FALSE) AS live_parses
            FROM sources s
            LEFT JOIN sources c ON c.source_id = s.merged_into
            LEFT JOIN parsed_rules p ON p.source_id = s.source_id
            GROUP BY s.source_id, s.canonical_name, s.merged_into, c.canonical_name
            ORDER BY is_alias, live_parses DESC, s.canonical_name
        """)
        rows = cur.fetchall()
    for name, is_alias, canon_name, live in rows:
        if is_alias:
            print(f"  alias   {name[:48]:48} → {canon_name}")
        else:
            print(f"  {live:>4}   {name[:70]}")
    print(f"\n{sum(1 for r in rows if not r[1])} canonical, "
          f"{sum(1 for r in rows if r[1])} alias(es). "
          f"Merge: python -m parse.review_cli merge-source <alias> <canonical>")
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
    sub.add_parser("list-sources")
    p_merge = sub.add_parser("merge-source")
    p_merge.add_argument("alias")
    p_merge.add_argument("canonical")
    args = parser.parse_args(argv)

    conn = get_conn()
    try:
        if args.command == "list":
            return cmd_list(conn)
        if args.command == "show":
            return cmd_show(conn, args.parsed_id)
        if args.command == "approve":
            return cmd_approve(conn, args.parsed_ids)
        if args.command == "list-sources":
            return cmd_list_sources(conn)
        return cmd_merge_source(conn, args.alias, args.canonical)
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
