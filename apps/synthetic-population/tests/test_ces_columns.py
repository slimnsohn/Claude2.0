import pytest
from engine.ces_columns import CES_COLUMNS, match_question


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
