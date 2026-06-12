import pytest
import pandas as pd
from pathlib import Path
from engine.ces_loader import CESLoader


@pytest.fixture
def loader():
    ces_path = Path("data/raw/ces/ces_2024_common.csv")
    if not ces_path.exists():
        pytest.skip("CES data not available")
    return CESLoader(str(ces_path))


class TestCESLoader:
    def test_loads_data(self, loader):
        df = loader.get_data()
        assert len(df) > 50000
        assert "pid7" in df.columns

    def test_has_harmonized_demographics(self, loader):
        df = loader.get_data()
        for col in ["party_id", "age_bracket", "sex", "race", "education", "urban_rural"]:
            assert col in df.columns, f"Missing harmonized column: {col}"

    def test_has_issue_columns(self, loader):
        df = loader.get_data()
        assert "CC24_312i" in df.columns
        assert "CC24_301" in df.columns

    def test_drops_rows_with_missing_demographics(self, loader):
        df = loader.get_data()
        for col in ["party_id", "age_bracket", "sex", "race", "education"]:
            assert df[col].isna().sum() == 0, f"{col} has NaN values"

    def test_caches_on_second_call(self, loader):
        df1 = loader.get_data()
        df2 = loader.get_data()
        assert df1 is df2

    def test_encoded_matrix_shape(self, loader):
        matrix, _ = loader.get_encoded_demographics()
        df = loader.get_data()
        assert matrix.shape[0] == len(df)
        assert matrix.shape[1] > 0
