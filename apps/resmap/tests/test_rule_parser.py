"""Tests for parse/claude_cli.py and parse/rule_parser.py.

Unit tests monkeypatch subprocess — no claude CLI, no network. The stale
re-parse loop test is an integration test against resmap_test with the LLM
mocked at the parse_rules_text level.
"""
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import parse.claude_cli as claude_cli
import parse.rule_parser as rule_parser
from ingest.core import MarketRecord, ingest
from parse.claude_cli import ClaudeCliError, _extract_json, call_claude_json
from parse.rule_parser import ParseValidationError, parse_rules_text

GOOD_RESPONSE = {
    "resolution_logic": "Resolves YES if CPI rises more than 0.3% in June 2026.",
    "authoritative_source": "BLS CPI release",       # short canonical entity
    "source_fallback": "consensus of credible reporting",  # procedure, separate
    "source_type": "official_data",
    "cutoff_time": "2026-07-15T12:30:00Z",
    "cutoff_basis": "data_release",
    "tie_handling": "exact threshold value resolves NO",
    "revision_handling": "first print only; revisions ignored",
    "threshold_def": "> 0.3% single-decimal",
    "confidence": 0.92,
}


def _fake_run_factory(stdouts: list[str], returncodes: list[int] | None = None):
    """subprocess.run replacement yielding queued stdouts."""
    calls = []

    def fake_run(cmd, **kwargs):
        i = min(len(calls), len(stdouts) - 1)
        calls.append(cmd)
        rc = (returncodes or [0] * len(stdouts))[i]
        return SimpleNamespace(returncode=rc, stdout=stdouts[i], stderr="")

    fake_run.calls = calls
    return fake_run


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    monkeypatch.setattr(claude_cli.time, "sleep", lambda s: None)
    monkeypatch.setattr(claude_cli, "_claude_bin", "claude-fake")


# ── claude_cli ───────────────────────────────────────────────────────────────

def test_call_claude_json_happy_path(monkeypatch):
    fake = _fake_run_factory([json.dumps(GOOD_RESPONSE)])
    monkeypatch.setattr(claude_cli.subprocess, "run", fake)
    assert call_claude_json("prompt") == GOOD_RESPONSE


def test_call_claude_json_strips_markdown_fences(monkeypatch):
    wrapped = f"Here you go:\n```json\n{json.dumps(GOOD_RESPONSE)}\n```"
    fake = _fake_run_factory([wrapped])
    monkeypatch.setattr(claude_cli.subprocess, "run", fake)
    assert call_claude_json("prompt") == GOOD_RESPONSE


def test_call_claude_json_retries_garbage_then_succeeds(monkeypatch):
    fake = _fake_run_factory(["complete garbage no braces",
                              json.dumps(GOOD_RESPONSE)])
    monkeypatch.setattr(claude_cli.subprocess, "run", fake)
    assert call_claude_json("prompt") == GOOD_RESPONSE
    assert len(fake.calls) == 2


def test_call_claude_json_retries_nonzero_exit(monkeypatch):
    fake = _fake_run_factory(["", json.dumps(GOOD_RESPONSE)],
                             returncodes=[1, 0])
    monkeypatch.setattr(claude_cli.subprocess, "run", fake)
    assert call_claude_json("prompt") == GOOD_RESPONSE


def test_call_claude_json_exhausts_retries(monkeypatch):
    fake = _fake_run_factory(["garbage"] * 3)
    monkeypatch.setattr(claude_cli.subprocess, "run", fake)
    with pytest.raises(ClaudeCliError):
        call_claude_json("prompt", max_retries=3)


def test_extract_json_first_brace_to_last():
    text = 'CLI update available!\n{"a": 1, "b": {"c": 2}}\ndone'
    assert _extract_json(text) == {"a": 1, "b": {"c": 2}}


def test_extract_json_returns_none_for_garbage():
    assert _extract_json("no json here") is None


# ── parse_rules_text validation ──────────────────────────────────────────────

def _patch_response(monkeypatch, response: dict | str):
    out = response if isinstance(response, str) else json.dumps(response)
    monkeypatch.setattr(claude_cli.subprocess, "run", _fake_run_factory([out]))


def test_parse_rules_text_valid(monkeypatch):
    _patch_response(monkeypatch, GOOD_RESPONSE)
    parsed = parse_rules_text("If CPI rises...")
    assert parsed["authoritative_source"] == "BLS CPI release"
    assert parsed["cutoff_time"] == datetime(2026, 7, 15, 12, 30,
                                             tzinfo=timezone.utc)
    assert parsed["confidence"] == pytest.approx(0.92)


def test_parse_rules_text_missing_key_rejected(monkeypatch):
    bad = {k: v for k, v in GOOD_RESPONSE.items() if k != "tie_handling"}
    _patch_response(monkeypatch, bad)
    with pytest.raises(ParseValidationError, match="tie_handling"):
        parse_rules_text("rules")


def test_parse_rules_text_extra_keys_dropped(monkeypatch):
    _patch_response(monkeypatch, {**GOOD_RESPONSE, "bonus_field": "x"})
    parsed = parse_rules_text("rules")
    assert "bonus_field" not in parsed


def test_parse_rules_text_confidence_clamped(monkeypatch):
    _patch_response(monkeypatch, {**GOOD_RESPONSE, "confidence": 1.7})
    assert parse_rules_text("rules")["confidence"] == 1.0


def test_parse_rules_text_bad_confidence_rejected(monkeypatch):
    _patch_response(monkeypatch, {**GOOD_RESPONSE, "confidence": "high"})
    with pytest.raises(ParseValidationError, match="confidence"):
        parse_rules_text("rules")


def test_parse_rules_text_bad_cutoff_becomes_none(monkeypatch):
    _patch_response(monkeypatch, {**GOOD_RESPONSE,
                                  "cutoff_time": "the end of June-ish"})
    assert parse_rules_text("rules")["cutoff_time"] is None


def test_parse_rules_text_null_cutoff(monkeypatch):
    _patch_response(monkeypatch, {**GOOD_RESPONSE, "cutoff_time": None})
    assert parse_rules_text("rules")["cutoff_time"] is None


def test_parse_rules_text_returns_source_fallback(monkeypatch):
    # the fallback chain is procedure, kept out of the authority entity so the
    # source row dedupes cleanly
    _patch_response(monkeypatch, GOOD_RESPONSE)
    assert parse_rules_text("rules").get("source_fallback") == \
        "consensus of credible reporting"


def test_parse_rules_text_missing_source_fallback_rejected(monkeypatch):
    bad = {k: v for k, v in GOOD_RESPONSE.items() if k != "source_fallback"}
    _patch_response(monkeypatch, bad)
    with pytest.raises(ParseValidationError, match="source_fallback"):
        parse_rules_text("rules")


def test_parse_rules_text_null_source_fallback_allowed(monkeypatch):
    _patch_response(monkeypatch, {**GOOD_RESPONSE, "source_fallback": None})
    assert parse_rules_text("rules")["source_fallback"] is None


# ── run(): DB loop with mocked LLM (integration) ─────────────────────────────

@pytest.mark.integration
def test_run_inserts_parse_and_source(db_conn, monkeypatch):
    ingest(db_conn, [MarketRecord(
        venue_code="polymarket", venue_market_id="0xP1",
        title="CPI?", raw_rules="If CPI rises more than 0.3% ...",
        status="open", raw_payload={"volume": "1000"})])

    monkeypatch.setattr(rule_parser, "parse_rules_text",
                        lambda raw_rules, model=None: dict(
                            parse_rules_text_result()))
    stats = rule_parser.run(db_conn)
    assert stats == {"parsed": 1, "failed": 0}

    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT p.reviewed, p.is_stale, p.extraction_method, s.canonical_name
            FROM parsed_rules p JOIN sources s USING (source_id)
        """)
        reviewed, is_stale, method, source = cur.fetchone()
    assert reviewed is False          # never auto-accepted
    assert is_stale is False
    assert method == "llm"
    assert source == "BLS CPI release"


def parse_rules_text_result():
    return {**GOOD_RESPONSE,
            "cutoff_time": datetime(2026, 7, 15, 12, 30, tzinfo=timezone.utc)}


@pytest.mark.integration
def test_run_stores_source_fallback(db_conn, monkeypatch):
    ingest(db_conn, [MarketRecord(
        venue_code="polymarket", venue_market_id="0xF1",
        title="World Cup?", raw_rules="FIFA decides; else consensus.",
        status="open")])
    monkeypatch.setattr(rule_parser, "parse_rules_text",
                        lambda raw_rules, model=None: parse_rules_text_result())
    rule_parser.run(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("SELECT source_fallback FROM parsed_rules")
        assert cur.fetchone()[0] == "consensus of credible reporting"


@pytest.mark.integration
def test_run_skips_already_parsed_markets(db_conn, monkeypatch):
    ingest(db_conn, [MarketRecord(
        venue_code="polymarket", venue_market_id="0xP1",
        title="CPI?", raw_rules="rules", status="open")])
    monkeypatch.setattr(rule_parser, "parse_rules_text",
                        lambda raw_rules, model=None: parse_rules_text_result())
    assert rule_parser.run(db_conn)["parsed"] == 1
    assert rule_parser.run(db_conn)["parsed"] == 0  # fresh parse exists → skip


@pytest.mark.integration
def test_stale_reparse_loop(db_conn, monkeypatch):
    """Rule change → is_stale flip → next run re-parses the NEW snapshot,
    keeping the old parse as history."""
    monkeypatch.setattr(rule_parser, "parse_rules_text",
                        lambda raw_rules, model=None: parse_rules_text_result())

    rec_v1 = MarketRecord(venue_code="polymarket", venue_market_id="0xP1",
                          title="CPI?", raw_rules="Cutoff 11:59pm ET.",
                          status="open")
    ingest(db_conn, [rec_v1])
    rule_parser.run(db_conn)

    rec_v2 = MarketRecord(venue_code="polymarket", venue_market_id="0xP1",
                          title="CPI?", raw_rules="Cutoff 6:00pm ET.",
                          status="open")
    stats = ingest(db_conn, [rec_v2])
    assert stats["rule_changes"] == 1

    assert rule_parser.run(db_conn)["parsed"] == 1  # re-selected after staling

    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT p.is_stale, s.raw_rules
            FROM parsed_rules p JOIN rule_snapshots s USING (snapshot_id)
            ORDER BY p.created_at
        """)
        rows = cur.fetchall()
    assert len(rows) == 2
    assert rows[0] == (True, "Cutoff 11:59pm ET.")    # history retained
    assert rows[1] == (False, "Cutoff 6:00pm ET.")    # fresh parse on NEW text


@pytest.mark.integration
def test_run_ids_filter_targets_specific_markets(db_conn, monkeypatch):
    ingest(db_conn, [
        MarketRecord(venue_code="polymarket", venue_market_id="0xBIG",
                     title="big", raw_rules="r1", status="open",
                     raw_payload={"volume": "999999"}),
        MarketRecord(venue_code="kalshi", venue_market_id="KX-TARGET",
                     title="target", raw_rules="r2", status="open"),
    ])
    monkeypatch.setattr(rule_parser, "parse_rules_text",
                        lambda raw_rules, model=None: parse_rules_text_result())
    stats = rule_parser.run(db_conn, ids=["KX-TARGET"])
    assert stats["parsed"] == 1  # only the targeted market, not the big one
    with db_conn.cursor() as cur:
        cur.execute("""SELECT m.venue_market_id FROM parsed_rules p
                       JOIN markets m USING (market_id)""")
        assert cur.fetchall() == [("KX-TARGET",)]


@pytest.mark.integration
def test_run_skips_empty_rules_markets(db_conn, monkeypatch):
    ingest(db_conn, [MarketRecord(
        venue_code="kalshi", venue_market_id="PARLAY-1",
        title="parlay", raw_rules="", status="open")])
    monkeypatch.setattr(rule_parser, "parse_rules_text",
                        lambda raw_rules, model=None: parse_rules_text_result())
    assert rule_parser.run(db_conn)["parsed"] == 0
