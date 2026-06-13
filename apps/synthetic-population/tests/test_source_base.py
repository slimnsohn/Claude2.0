import pytest
import pandas as pd
from pipeline.sources.base import DataSource

class FakeSource(DataSource):
    name = "fake"
    variables_provided = ["party_id", "ideology"]
    match_keys = ["age_bracket", "sex", "race", "education"]
    update_cycle = "annual"
    standard_column_map = {"party_id": "pid", "ideology": "ideo"}
    variable_maps = {
        "party_id": {1: "strong_dem", 2: "dem", 3: "lean_dem", 4: "independent",
                     5: "lean_rep", 6: "rep", 7: "strong_rep"},
    }
    custom_columns = {"approval_rating": "approve"}

    def download(self): return "fake_path"
    def clean(self, raw_path): return pd.DataFrame({"pid": [1,7], "ideo": [2,6], "approve": [45,80]})

def test_abc_requires_methods():
    with pytest.raises(TypeError):
        DataSource()

def test_harmonize_maps_standard_variables():
    source = FakeSource()
    raw = source.clean("path")
    result = source.harmonize(raw)
    assert list(result["party_id"]) == ["strong_dem", "strong_rep"]

def test_harmonize_namespaces_custom_variables():
    source = FakeSource()
    raw = source.clean("path")
    result = source.harmonize(raw)
    assert "fake:approval_rating" in result.columns
    assert list(result["fake:approval_rating"]) == [45, 80]

def test_harmonize_passes_unmapped_standard_through():
    source = FakeSource()
    raw = source.clean("path")
    result = source.harmonize(raw)
    # ideology has no variable_map, so it passes through directly
    assert list(result["ideology"]) == [2, 6]
