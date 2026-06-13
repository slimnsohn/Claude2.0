"""End-to-end pipeline orchestration.

Run a single sport's daily ingest -> consensus -> posterior -> EV ranking.

Usage:
    python cli.py wnba               # live run (requires ODDS_API_KEY)
    python cli.py wnba --dry-run     # use committed fixtures only
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from core.storage import StorageBackend
from core.types import BookOdds
from core.consensus import weighted_consensus
from core.ev import edge_pct, ev_dollars, extract_implied_mu, posterior_prob_from_mu
from core.kelly import fractional_kelly_stake


def _load_config():
    books_cfg = json.loads((ROOT / "config" / "books.json").read_text())
    user_path = ROOT / "config" / "user.json"
    if not user_path.exists():
        raise RuntimeError(
            f"Missing {user_path}. Copy user.json.template and set your bankroll."
        )
    user_cfg = json.loads(user_path.read_text())
    if user_cfg.get("bankroll") is None:
        raise RuntimeError("config/user.json bankroll must be set.")
    return books_cfg, user_cfg


def _parse_iso(s):
    if isinstance(s, datetime):
        return s
    return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)


def _to_book_odds(rows):
    """Group flat odds rows into {(market_key): [BookOdds...], ...} for each side."""
    over, under = {}, {}
    for r in rows:
        key = (r["event_id"], r["market_type"], r["player_name"],
               r["line_value"], bool(r["is_alternate"]))
        bo = BookOdds(
            book=r["book"],
            american_odds=r["american_odds"],
            fetched_at=_parse_iso(r["fetched_at"]),
        )
        target = over if r["side"] == "over" else under
        target.setdefault(key, []).append(bo)
    return over, under


def _market_keys(over, under):
    return sorted(set(over.keys()) & set(under.keys()))


def _flatten_fixture(payload):
    """Flatten one event-odds payload into the row shape OddsAPIClient returns."""
    rows = []
    for bm in payload.get("bookmakers", []):
        for m in bm.get("markets", []):
            is_alt = m["key"].endswith("_alternate")
            base = m["key"].replace("_alternate", "")
            for o in m.get("outcomes", []):
                side = (o.get("name") or "").lower()
                if side not in ("over", "under"):
                    continue
                rows.append({
                    "event_id": payload["id"],
                    "commence_time": payload["commence_time"],
                    "market_type": base,
                    "player_name": o.get("description", ""),
                    "line_value": float(o["point"]),
                    "side": side,
                    "book": bm["key"],
                    "american_odds": int(o["price"]),
                    "fetched_at": bm["last_update"],
                    "is_alternate": is_alt,
                })
    return rows


def run_wnba(dry_run: bool = False) -> int:
    books_cfg, user_cfg = _load_config()
    bankroll = float(user_cfg["bankroll"])
    storage = StorageBackend(str(ROOT / "data" / "prop_engine.db"))
    storage.initialize()
    sport_id = storage.upsert_sport("wnba")
    run_id = storage.start_run(sport_id)

    def log(msg):
        storage.append_run_log(run_id, msg)

    log(f"start dry_run={dry_run} {datetime.now(timezone.utc).replace(tzinfo=None).isoformat()}")

    # 1. Ingest odds
    if dry_run:
        fix = ROOT / "tests" / "fixtures" / "odds_api_wnba_event_odds.json"
        payload = json.loads(fix.read_text())
        all_rows = _flatten_fixture(payload)
        log(f"dry-run: loaded {len(all_rows)} rows from fixture")
    else:
        from sports.wnba.odds import OddsAPIClient
        client = OddsAPIClient()
        events = client.fetch_events()
        all_rows = []
        for ev in events:
            try:
                all_rows.extend(client.fetch_event_player_props(
                    ev["event_id"], bookmakers=user_cfg["books_to_consider"]))
            except Exception as e:
                log(f"event {ev['event_id']} fetch error: {e}")
        log(f"fetched {len(all_rows)} odds rows from {len(events)} events")

    # 2. Persist book lines
    for r in all_rows:
        mid = storage.upsert_market(
            sport_id=sport_id, event_id=r["event_id"],
            market_type=r["market_type"], player_name=r["player_name"],
            line_value=r["line_value"], side=r["side"],
            commence_time=_parse_iso(r["commence_time"]),
            is_alternate=r["is_alternate"],
        )
        storage.record_book_line(
            market_id=mid, book=r["book"], american_odds=r["american_odds"],
            fetched_at=_parse_iso(r["fetched_at"]),
        )

    # 3. Group for consensus
    over_map, under_map = _to_book_odds(all_rows)
    snapshot = datetime.now(timezone.utc).replace(tzinfo=None)

    n_plays = 0
    market_keys = _market_keys(over_map, under_map)
    log(f"unique markets: {len(market_keys)}")

    # In v1, we use placeholder per-player stats. Once the feature lookup
    # is wired (TODO in TODO.md), pull real position/stat_avg/sigma per player.
    PLACEHOLDER_POSITION = "F"
    PLACEHOLDER_STAT_AVG = 20.0
    PLACEHOLDER_SIGMA = 5.0

    for mk in market_keys:
        event_id, market_type, player_name, line, is_alt = mk
        # Skip alt lines for count-stats per spec (Normal mis-specified in tails)
        if is_alt and market_type in ("player_threes", "player_steals", "player_blocks"):
            continue

        over_lines = over_map.get(mk, [])
        under_lines = under_map.get(mk, [])

        try:
            consensus_over, books_used = weighted_consensus(
                over_lines, under_lines,
                weights=books_cfg["consensus_weights"],
                staleness_seconds=books_cfg["staleness_seconds"],
                snapshot_time=snapshot,
                min_books=books_cfg["min_books_for_consensus"],
            )
        except ValueError as e:
            log(f"skip {market_type}/{player_name}@{line}: {e}")
            continue

        # Residual layer — placeholder inputs in v1
        from sports.wnba.residual import compute_residual
        residual = compute_residual(
            stat=market_type, position=PLACEHOLDER_POSITION,
            is_b2b=False, b2b_history=[], teammates_out=[],
            player_stat_avg=PLACEHOLDER_STAT_AVG,
        )

        sigma = PLACEHOLDER_SIGMA
        mu_implied = extract_implied_mu(consensus_over, line, sigma)
        mu_adjusted = mu_implied + residual.total
        notes = list(residual.notes)
        if abs(mu_adjusted - mu_implied) > 0.5 * sigma:
            notes.append("large_adjustment")
        if mu_adjusted < 0 or mu_adjusted > 2 * PLACEHOLDER_STAT_AVG * 1.5:
            log(f"implausible mu for {player_name}/{market_type}: {mu_adjusted}")
            continue

        posterior_over = posterior_prob_from_mu(mu_adjusted, line, sigma)

        for side, posterior in (("over", posterior_over), ("under", 1.0 - posterior_over)):
            mid = storage.upsert_market(
                sport_id=sport_id, event_id=event_id, market_type=market_type,
                player_name=player_name, line_value=line, side=side,
                commence_time=_parse_iso(over_lines[0].fetched_at) if over_lines else datetime.now(timezone.utc).replace(tzinfo=None),
                is_alternate=is_alt,
            )
            proj_id = storage.record_projection(
                market_id=mid, run_id=run_id, sigma_used=sigma,
                consensus_prob=consensus_over if side == "over" else 1 - consensus_over,
                mu_implied=mu_implied, mu_adjusted=mu_adjusted,
                posterior_prob=posterior,
                residual_breakdown={"rest": residual.rest, "teammate_out": residual.teammate_out},
                notes=notes,
            )
            side_lines = over_lines if side == "over" else under_lines
            for bl in side_lines:
                e = edge_pct(posterior, bl.american_odds)
                if e < user_cfg["min_edge_pct"]:
                    continue
                stake = fractional_kelly_stake(
                    posterior_prob=posterior, american_odds=bl.american_odds,
                    bankroll=bankroll, kelly_fraction=user_cfg["kelly_fraction"],
                    max_stake_pct=user_cfg["max_stake_pct"],
                    min_bet=user_cfg["min_bet_amount"],
                )
                if stake <= 0:
                    continue
                storage.record_play(
                    projection_id=proj_id, book=bl.book,
                    offered_odds=bl.american_odds, edge_pct=e,
                    recommended_stake=stake, ev_dollars=ev_dollars(e, stake),
                )
                n_plays += 1

    log(f"plays generated: {n_plays}")
    storage.finish_run(run_id, status="success",
                       n_markets=len(market_keys), n_plays=n_plays)

    # Write dashboard snapshot
    snapshot_path = ROOT / "core" / "dashboard" / "static" / "data" / "today.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    plays = storage.open_plays()
    snapshot_path.write_text(json.dumps({
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "n_plays": len(plays),
        "plays": plays,
    }, default=str, indent=2))
    print(f"Run {run_id} complete: {n_plays} plays.")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sport", choices=["wnba"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.sport == "wnba":
        return run_wnba(dry_run=args.dry_run)
    return 1


if __name__ == "__main__":
    sys.exit(main())
