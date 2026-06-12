import pytest
from engine.ces_columns import CES_COLUMNS, match_question, detect_negated_phrasing


class TestCESColumns:
    def test_columns_have_required_fields(self):
        for col_id, col in CES_COLUMNS.items():
            assert "name" in col, f"{col_id} missing name"
            assert "topic" in col, f"{col_id} missing topic"
            assert "keywords" in col, f"{col_id} missing keywords"
            assert "interpret" in col, f"{col_id} missing interpret"
            assert callable(col["interpret"]), f"{col_id} interpret not callable"

    def test_match_trump_approval(self):
        # Calibration anchor question — must match the 2024-vote proxy.
        result = match_question("Do you approve of Trump's job performance?")
        assert result is not None
        assert result["col_id"] == "CC24_410"

    def test_match_biden_approval(self):
        # No "approve"/"approval"/"president" in the wording — those keywords
        # belong to the Trump proxy and would outscore the "biden" keyword.
        result = match_question("Did Biden do a good job?")
        assert result is not None
        assert result["col_id"] == "CC24_312a"

    def test_match_economy(self):
        # Calibration anchor question — must stay on CC24_301.
        result = match_question("Is the economy getting better or worse?")
        assert result is not None
        assert result["col_id"] == "CC24_301"
        assert result["topic"] == "economy"

    def test_match_aca_repeal(self):
        result = match_question("Do you support repealing Obamacare?")
        assert result is not None
        assert result["col_id"] == "CC24_328d"

    def test_medicare_for_all_has_no_coverage(self):
        # CES 2024 has no Medicare-for-All item; that coverage was dropped
        # deliberately rather than faking it with another column.
        assert match_question("Do you support Medicare for all?") is None

    def test_match_border(self):
        result = match_question("Do you support increasing border security?")
        assert result is not None
        assert result["col_id"] == "CC24_323b"

    def test_match_wall(self):
        result = match_question("Should we build a border wall?")
        assert result is not None
        assert result["col_id"] == "CC24_323c"

    def test_match_climate(self):
        result = match_question("Do you support government action on climate change?")
        assert result is not None
        assert result["col_id"] == "CC24_326a"

    def test_match_assault_ban(self):
        result = match_question("Do you support a ban on assault rifles?")
        assert result is not None
        assert result["col_id"] == "CC24_321a"

    def test_match_background_checks(self):
        result = match_question("Do you support universal background checks?")
        assert result is not None
        assert result["col_id"] == "CC24_321c"

    def test_match_abortion_choice(self):
        result = match_question("Should abortion be allowed as a matter of choice?")
        assert result is not None
        assert result["col_id"] == "CC24_324a"

    def test_match_ukraine_arms(self):
        result = match_question("Do you support providing arms to Ukraine?")
        assert result is not None
        assert result["col_id"] == "CC24_308a_4"

    def test_match_student_debt(self):
        result = match_question("Do you support student loan forgiveness?")
        assert result is not None
        assert result["col_id"] == "CC24_323f"

    def test_no_match_returns_none(self):
        result = match_question("Do you like pizza?")
        assert result is None

    def test_interpret_binary_support(self):
        col = CES_COLUMNS["CC24_323b"]
        assert col["interpret"](1) == "yes"
        assert col["interpret"](2) == "no"

    def test_interpret_likert_approval(self):
        # CES 2024 codebook: 1=Strongly approve, 2=Somewhat approve,
        # 3=Somewhat disapprove, 4=Strongly disapprove, 5=Not sure.
        col = CES_COLUMNS["CC24_312a"]
        assert col["interpret"](1) == "yes"
        assert col["interpret"](2) == "yes"
        assert col["interpret"](3) == "no"
        assert col["interpret"](4) == "no"
        assert col["interpret"](5) == "unsure"

    def test_interpret_likert_economy(self):
        col = CES_COLUMNS["CC24_301"]
        assert col["interpret"](1) == "yes"
        assert col["interpret"](2) == "yes"
        assert col["interpret"](3) == "unsure"
        assert col["interpret"](4) == "no"
        assert col["interpret"](5) == "no"
        assert col["interpret"](6) == "unsure"

    def test_interpret_trump_vote_proxy(self):
        # CC24_410: 1=Harris, 2=Trump, 3-6=other, 8/9=did not vote.
        col = CES_COLUMNS["CC24_410"]
        assert col["interpret"](2) == "yes"
        assert col["interpret"](1) == "no"
        assert col["interpret"](3) == "unsure"
        assert col["interpret"](8) == "unsure"

    def test_old_wrong_columns_removed(self):
        # These were mis-mapped in the original registry:
        # CC24_300_x = media use (not immigration), CC24_311a = governor-party
        # knowledge (not Congress approval), CC24_415c/d = state-leg vote
        # (not climate), CC24_312i = Harris (not Trump) — kept but relabeled.
        for stale in ("CC24_300_1", "CC24_300_2", "CC24_300_3", "CC24_300_4",
                      "CC24_311a", "CC24_415c", "CC24_415d", "CC24_308a_2",
                      "CC24_308a_3", "CC24_308a_5", "CC24_326c", "CC24_326f",
                      "CC24_328a", "CC24_328b"):
            assert stale not in CES_COLUMNS, f"stale column {stale} still in registry"
        assert CES_COLUMNS["CC24_312i"]["name"].lower().startswith("harris")


class TestNegationDetection:
    """Audit H2: negated question stems must be detectable so the API gates
    can reject them instead of silently returning the SUPPORT distribution."""

    def test_oppose_is_flagged(self):
        assert detect_negated_phrasing("Do you oppose building a border wall?") is True

    def test_disapprove_is_flagged(self):
        assert detect_negated_phrasing("Do you disapprove of Trump?") is True

    def test_against_is_flagged(self):
        assert detect_negated_phrasing("Are you against expanding Medicaid?") is True

    def test_do_you_not_support_is_flagged(self):
        assert detect_negated_phrasing("Do you not support the ACA?") is True

    def test_case_insensitive(self):
        assert detect_negated_phrasing("DO YOU OPPOSE the border wall?") is True

    def test_ban_is_content_not_negation(self):
        # "ban" is the proposal's content (column polarity handles it)
        assert detect_negated_phrasing("Do you support banning assault rifles?") is False

    def test_repeal_is_content_not_negation(self):
        assert detect_negated_phrasing("Do you support repealing the ACA?") is False

    def test_illegal_is_content_not_negation(self):
        assert detect_negated_phrasing("Should abortion be illegal in all circumstances?") is False

    def test_match_question_unchanged_for_negated_text(self):
        # match_question itself stays polarity-blind; gating happens at the
        # API entry points, not inside the matcher.
        result = match_question("Do you oppose building a border wall?")
        assert result is not None
        assert result["col_id"] == "CC24_323c"


class TestMatchScoreThreshold:
    """Fix 3: optional min_score lets broad question streams (Polymarket
    trending) require more than one generic keyword to count as covered."""

    def test_match_result_includes_match_score(self):
        result = match_question("Do you approve of Trump's job performance?")
        assert result["match_score"] == 27  # trump(5) + approve(7) + job performance(15)

    def test_default_min_score_keeps_loose_behavior(self):
        result = match_question("Will Trump restart Project Freedom by June 30?")
        assert result is not None
        assert result["col_id"] == "CC24_410"
        assert result["match_score"] == 5  # bare "trump" only

    def test_bare_generic_keyword_fails_min_score_10(self):
        assert match_question("Will Trump restart Project Freedom by June 30?",
                              min_score=10) is None

    def test_multi_keyword_passes_min_score_10(self):
        result = match_question("Will Trump's approval rating be above 45%?",
                                min_score=10)
        assert result is not None
        assert result["col_id"] == "CC24_410"
        assert result["match_score"] == 13  # trump(5) + approval(8)

    def test_no_match_still_none_with_min_score(self):
        assert match_question("Do you like pizza?", min_score=10) is None
