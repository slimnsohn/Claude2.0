from abc import ABC, abstractmethod
from pathlib import Path
import pandas as pd


class DataSource(ABC):
    """Base class for all data source plugins.

    Subclasses must define:
        name: str — unique source identifier
        variables_provided: list[str] — standard schema variables this source provides
        match_keys: list[str] — demographics used for matching with ACS backbone
        update_cycle: str — "annual", "biennial", "election_year", "triennial"
        standard_column_map: dict[str, str] — {standard_name: source_column_name}
        variable_maps: dict[str, dict] — {standard_name: {source_value: standard_value}}
        custom_columns: dict[str, str] — {custom_name: source_column_name}
    """
    name: str
    variables_provided: list
    match_keys: list
    update_cycle: str
    standard_column_map: dict
    variable_maps: dict = {}
    custom_columns: dict = {}

    @abstractmethod
    def download(self) -> Path:
        """Download raw data. Returns path to downloaded file."""
        ...

    @abstractmethod
    def clean(self, raw_path) -> pd.DataFrame:
        """Clean raw data. Returns DataFrame ready for harmonization."""
        ...

    def harmonize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map source columns to standard schema.

        Standard variables get mapped via variable_maps (if defined) or passed through.
        Custom variables get namespaced as {source_name}:{custom_name}.
        """
        result = pd.DataFrame()
        for standard_name, source_col in self.standard_column_map.items():
            mapping = self.variable_maps.get(standard_name)
            if mapping:
                result[standard_name] = df[source_col].map(mapping)
            else:
                result[standard_name] = df[source_col]
        for custom_name, source_col in self.custom_columns.items():
            result[f"{self.name}:{custom_name}"] = df[source_col]
        return result

    def match_config(self) -> dict:
        """Return configuration for statistical matching with ACS backbone."""
        return {
            "source": self.name,
            "match_keys": self.match_keys,
            "variables": self.variables_provided,
        }
