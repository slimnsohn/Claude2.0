"""Tests for the rule-change severity classifier."""
import pytest

import parse.classify_changes as cc
from ingest.core import MarketRecord, ingest
from parse.classify_changes import ClassifyValidationError, classify_change, run


def _judge(resp):
    return lambda prompt: resp


def test_classify_cosmetic():
    out = classify_change("Resolves YES if X.", "resolves yes if x",
                          judge=_judge({"severity": "cosmetic", "diff_summary": "casing only"}))
    assert out["severity"] == "cosmetic"
    assert out["diff_summary"] == "casing only"


def test_classify_material():
    out = classify_change("cutoff 11:59pm", "cutoff 6:00pm",
                          judge=_judge({"severity": "material", "diff_summary": "cutoff moved"}))
    assert out["severity"] == "material"


def test_classify_rejects_bad_severity():
    with pytest.raises(ClassifyValidationError):
        classify_change("a", "b", judge=_judge({"severity": "maybe", "diff_summary": "x"}))


def test_classify_truncates_long_summary():
    out = classify_change("a", "b",
                          judge=_judge({"severity": "material", "diff_summary": "x" * 999}))
    assert len(out["diff_summary"]) <= 500


# ── run(): updates unknown-severity events (integration) ─────────────────────

@pytest.mark.integration
def test_run_classifies_unknown_events(db_conn, monkeypatch):
    ingest(db_conn, [MarketRecord(venue_code="polymarket", venue_market_id="0xC",
                                  title="T", raw_rules="cutoff 11:59pm ET", status="open")])
    # a rule edit creates an unknown-severity event
    ingest(db_conn, [MarketRecord(venue_code="polymarket", venue_market_id="0xC",
                                  title="T", raw_rules="cutoff 6:00pm ET", status="open")])
    monkeypatch.setattr(cc, "classify_change",
                        lambda prev, new, judge=None: {"severity": "material",
                                                       "diff_summary": "cutoff moved earlier"})
    stats = run(db_conn)
    assert stats == {"classified": 1, "failed": 0}
    with db_conn.cursor() as cur:
        cur.execute("SELECT severity, diff_summary FROM rule_change_events")
        sev, summ = cur.fetchone()
    assert sev == "material"
    assert summ == "cutoff moved earlier"


@pytest.mark.integration
def test_run_skips_already_classified(db_conn, monkeypatch):
    ingest(db_conn, [MarketRecord(venue_code="polymarket", venue_market_id="0xC",
                                  title="T", raw_rules="v1", status="open")])
    ingest(db_conn, [MarketRecord(venue_code="polymarket", venue_market_id="0xC",
                                  title="T", raw_rules="v2", status="open")])
    monkeypatch.setattr(cc, "classify_change",
                        lambda prev, new, judge=None: {"severity": "cosmetic", "diff_summary": "s"})
    assert run(db_conn)["classified"] == 1
    assert run(db_conn)["classified"] == 0   # nothing left in 'unknown'
