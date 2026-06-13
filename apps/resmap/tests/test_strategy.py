"""Tests for the divergence-play strategy analysis."""
import pytest

import parse.strategy as strat
from ingest.core import MarketRecord, ingest
from parse.strategy import StrategyValidationError, analyze_pair, run


def _judge(resp):
    return lambda prompt: resp


# ── analyze_pair (unit, mocked judge) ────────────────────────────────────────

def test_analyze_pair_returns_yes_side_and_reasoning():
    out = analyze_pair({"title": "A"}, {"title": "B"}, ["threshold"],
                       judge=_judge({"yes_market": "b",
                                     "scenario": "on the boundary B is YES",
                                     "rationale": "B uses >= so equality counts"}))
    assert out["direction"] == "b"
    assert "boundary" in out["scenario"]
    assert "equality" in out["rationale"]


def test_analyze_pair_rejects_bad_direction():
    with pytest.raises(StrategyValidationError):
        analyze_pair({"title": "A"}, {"title": "B"}, ["x"],
                     judge=_judge({"yes_market": "maybe", "scenario": "s", "rationale": "r"}))


def test_analyze_pair_truncates_long_text():
    out = analyze_pair({"title": "A"}, {"title": "B"}, [],
                       judge=_judge({"yes_market": "a", "scenario": "s" * 999,
                                     "rationale": "r" * 999}))
    assert len(out["scenario"]) <= 500
    assert len(out["rationale"]) <= 800


# ── run(): fills strategy on false_friends (integration) ─────────────────────

def _seed_false_friend(db_conn, match_type="false_friend"):
    ingest(db_conn, [
        MarketRecord(venue_code="polymarket", venue_market_id="0xS1",
                     title="Will France win?", raw_rules="r1", status="open"),
        MarketRecord(venue_code="kalshi", venue_market_id="KXS1",
                     title="France wins?", raw_rules="r2", status="open"),
    ])
    with db_conn.cursor() as cur:
        cur.execute("""SELECT m.market_id, s.snapshot_id, v.code FROM markets m
                       JOIN rule_snapshots s USING(market_id) JOIN venues v USING(venue_id)""")
        rows = {code: (mid, snap) for mid, snap, code in
                [(r[0], r[1], r[2]) for r in cur.fetchall()]}
        parsed = {}
        for code, (mid, snap) in rows.items():
            cur.execute("""INSERT INTO parsed_rules (market_id, snapshot_id,
                resolution_logic, threshold_def, extraction_method, reviewed, is_stale)
                VALUES (%s,%s,'resolves YES if France wins','outright','llm',FALSE,FALSE)
                RETURNING parsed_id""", (mid, snap))
            parsed[code] = cur.fetchone()[0]
        cur.execute("""INSERT INTO equivalences (market_a_id, market_b_id, parsed_a_id,
            parsed_b_id, match_type, divergence_axes, risk_score)
            VALUES (%s,%s,%s,%s,%s,ARRAY['threshold'],0.7) RETURNING equivalence_id""",
            (rows["polymarket"][0], rows["kalshi"][0], parsed["polymarket"],
             parsed["kalshi"], match_type))
        eid = cur.fetchone()[0]
    db_conn.commit()
    return eid


@pytest.mark.integration
def test_run_fills_strategy(db_conn, monkeypatch):
    _seed_false_friend(db_conn)
    monkeypatch.setattr(strat, "analyze_pair",
                        lambda a, b, axes, judge=None: {
                            "direction": "a", "scenario": "A YES / B NO on boundary",
                            "rationale": "A looser threshold"})
    stats = run(db_conn)
    assert stats == {"analyzed": 1, "failed": 0}
    with db_conn.cursor() as cur:
        cur.execute("SELECT divergence_direction, strategy_scenario, strategy_rationale "
                    "FROM equivalences")
        d, sc, ra = cur.fetchone()
    assert d == "a"
    assert "boundary" in sc
    assert "threshold" in ra


@pytest.mark.integration
def test_run_skips_non_false_friends(db_conn, monkeypatch):
    _seed_false_friend(db_conn, match_type="near_match")
    monkeypatch.setattr(strat, "analyze_pair",
                        lambda a, b, axes, judge=None: {"direction": "a", "scenario": "x", "rationale": "y"})
    assert run(db_conn)["analyzed"] == 0


@pytest.mark.integration
def test_run_skips_already_analyzed(db_conn, monkeypatch):
    _seed_false_friend(db_conn)
    monkeypatch.setattr(strat, "analyze_pair",
                        lambda a, b, axes, judge=None: {"direction": "b", "scenario": "x", "rationale": "y"})
    assert run(db_conn)["analyzed"] == 1
    assert run(db_conn)["analyzed"] == 0   # divergence_direction now set
