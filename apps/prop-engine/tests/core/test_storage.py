from datetime import datetime
import pytest
from core.storage import StorageBackend


@pytest.fixture
def storage(tmp_path):
    db = StorageBackend(str(tmp_path / "test.db"))
    db.initialize()
    return db


def test_initialize_creates_tables(storage):
    tables = storage.list_tables()
    assert {"sports", "markets", "book_lines", "projections", "plays",
            "bets_placed", "runs", "config"}.issubset(set(tables))


def test_upsert_sport_is_idempotent(storage):
    sid = storage.upsert_sport("wnba")
    same = storage.upsert_sport("wnba")
    assert sid == same


def test_start_and_finish_run(storage):
    sid = storage.upsert_sport("wnba")
    run_id = storage.start_run(sid)
    assert run_id > 0
    storage.append_run_log(run_id, "ingest start")
    storage.finish_run(run_id, status="success", n_markets=12, n_plays=3)
    row = storage.get_run(run_id)
    assert row["status"] == "success"
    assert row["n_plays"] == 3
    assert "ingest start" in row["log"]


def test_record_book_line(storage):
    sid = storage.upsert_sport("wnba")
    mid = storage.upsert_market(
        sport_id=sid, event_id="evt-1", market_type="player_points",
        player_name="A'ja Wilson", line_value=22.5, side="over",
        commence_time=datetime(2026, 5, 19, 19, 30), is_alternate=False,
    )
    storage.record_book_line(market_id=mid, book="pinnacle",
                              american_odds=-110,
                              fetched_at=datetime(2026, 5, 19, 18, 0))
    storage.record_book_line(market_id=mid, book="fanduel",
                              american_odds=-115,
                              fetched_at=datetime(2026, 5, 19, 18, 1))
    lines = storage.latest_book_lines(mid)
    assert len(lines) == 2
    books = sorted(bl["book"] for bl in lines)
    assert books == ["fanduel", "pinnacle"]


def test_config_set_and_get(storage):
    storage.set_config("bankroll", "10000")
    assert storage.get_config("bankroll") == "10000"
    storage.set_config("bankroll", "12500")
    assert storage.get_config("bankroll") == "12500"


def test_log_bet_flips_play_status(storage):
    sid = storage.upsert_sport("wnba")
    mid = storage.upsert_market(
        sport_id=sid, event_id="evt-1", market_type="player_points",
        player_name="P", line_value=20.0, side="over",
        commence_time=datetime(2026, 5, 19, 19, 30),
    )
    run_id = storage.start_run(sid)
    proj_id = storage.record_projection(
        market_id=mid, run_id=run_id, sigma_used=4.0,
        consensus_prob=0.5, mu_implied=20.0, mu_adjusted=21.0,
        posterior_prob=0.6, residual_breakdown={}, notes=[],
    )
    play_id = storage.record_play(
        projection_id=proj_id, book="pinnacle", offered_odds=-110,
        edge_pct=0.05, recommended_stake=50.0, ev_dollars=2.5,
    )
    bet_id = storage.log_bet(play_id, 50.0, -110, "pinnacle")
    assert bet_id > 0
    plays_open = storage.open_plays()
    assert all(p["id"] != play_id for p in plays_open)
