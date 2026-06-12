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
        result = match_question("Do you approve of Trump's job performance?")
        assert result is not None
        assert result["col_id"] == "CC24_312i"

    def test_match_economy(self):
        result = match_question("Is the economy getting better or worse?")
        assert result is not None
        assert result["topic"] == "economy"

    def test_match_healthcare_medicare(self):
        result = match_question("Do you support Medicare for all?")
        assert result is not None
        assert result["col_id"] == "CC24_326b"

    def test_match_border(self):
        result = match_question("Do you support increasing border security?")
        assert result is not None

    def test_match_climate(self):
        result = match_question("Do you support government action on climate change?")
        assert result is not None

    def test_no_match_returns_none(self):
        result = match_question("Do you like pizza?")
        assert result is None

    def test_interpret_binary_support(self):
        col = CES_COLUMNS["CC24_326b"]
        assert col["interpret"](1) == "yes"
        assert col["interpret"](2) == "no"

    def test_interpret_likert_approval(self):
        col = CES_COLUMNS["CC24_312i"]
        # CES coding: 1=Strongly disapprove, 4=Strongly approve, 5=Not sure
        assert col["interpret"](1) == "no"
        assert col["interpret"](2) == "no"
        assert col["interpret"](3) == "yes"
        assert col["interpret"](4) == "yes"
        assert col["interpret"](5) == "unsure"

    def test_interpret_likert_economy(self):
        col = CES_COLUMNS["CC24_301"]
        assert col["interpret"](1) == "yes"
        assert col["interpret"](2) == "yes"
        assert col["interpret"](3) == "unsure"
        assert col["interpret"](4) == "no"
        assert col["interpret"](5) == "no"
