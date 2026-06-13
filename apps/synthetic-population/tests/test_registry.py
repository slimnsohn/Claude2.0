from pipeline.registry import SourceRegistry
from pipeline.sources.base import DataSource
import pandas as pd


class StubSource(DataSource):
    name = "stub"
    variables_provided = ["party_id"]
    match_keys = ["age_bracket"]
    update_cycle = "annual"
    standard_column_map = {"party_id": "pid"}
    variable_maps = {}
    custom_columns = {}

    def download(self): return "path"
    def clean(self, raw_path): return pd.DataFrame()


def test_register_and_list():
    reg = SourceRegistry()
    reg.register(StubSource())
    assert "stub" in reg.list_sources()


def test_register_rejects_duplicate_name():
    reg = SourceRegistry()
    reg.register(StubSource())
    import pytest
    with pytest.raises(ValueError, match="already registered"):
        reg.register(StubSource())


def test_get_source_by_name():
    reg = SourceRegistry()
    src = StubSource()
    reg.register(src)
    assert reg.get("stub") is src


def test_get_nonexistent_raises():
    reg = SourceRegistry()
    import pytest
    with pytest.raises(KeyError):
        reg.get("nonexistent")


def test_variables_report():
    reg = SourceRegistry()
    reg.register(StubSource())
    report = reg.variables_report()
    assert report["party_id"] == "stub"
