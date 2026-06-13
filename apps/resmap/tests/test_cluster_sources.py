"""Unit tests for the source-merge proposal logic (no DB, no LLM)."""
from scripts.cluster_sources import format_commands, propose_merges

NAMES = ["FIFA", "Fifa official body", "NASA GISS LOTI",
         "NASA Goddard land-ocean index", "AP"]


def _judge(response):
    return lambda prompt: response


def test_propose_merges_groups_same_authority():
    judge = _judge({"groups": [
        {"canonical": "FIFA", "aliases": ["Fifa official body"]},
        {"canonical": "NASA GISS LOTI", "aliases": ["NASA Goddard land-ocean index"]},
    ]})
    groups = propose_merges(NAMES, judge=judge)
    assert len(groups) == 2
    assert {"canonical": "FIFA", "aliases": ["Fifa official body"]} in groups


def test_propose_merges_drops_hallucinated_names():
    judge = _judge({"groups": [
        {"canonical": "FIFA", "aliases": ["Fifa official body", "INVENTED SOURCE"]},
    ]})
    groups = propose_merges(NAMES, judge=judge)
    assert groups[0]["aliases"] == ["Fifa official body"]   # invented one dropped


def test_propose_merges_ignores_canonical_not_in_list():
    judge = _judge({"groups": [{"canonical": "Soccer body", "aliases": ["FIFA"]}]})
    assert propose_merges(NAMES, judge=judge) == []         # canonical not real


def test_propose_merges_no_alias_claimed_twice():
    judge = _judge({"groups": [
        {"canonical": "FIFA", "aliases": ["Fifa official body"]},
        {"canonical": "AP", "aliases": ["Fifa official body"]},   # double-claim
    ]})
    groups = propose_merges(NAMES, judge=judge)
    claimed = [a for g in groups for a in g["aliases"]]
    assert claimed.count("Fifa official body") == 1


def test_propose_merges_drops_self_alias():
    judge = _judge({"groups": [{"canonical": "FIFA", "aliases": ["FIFA"]}]})
    assert propose_merges(NAMES, judge=judge) == []          # alias == canonical


def test_format_commands():
    groups = [{"canonical": "FIFA", "aliases": ["Fifa official body", "FIFA assoc"]}]
    cmds = format_commands(groups)
    assert cmds == [
        'python -m parse.review_cli merge-source "Fifa official body" "FIFA"',
        'python -m parse.review_cli merge-source "FIFA assoc" "FIFA"',
    ]
