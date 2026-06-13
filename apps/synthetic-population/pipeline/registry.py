from pipeline.sources.base import DataSource


class SourceRegistry:
    """Tracks registered data source plugins."""

    def __init__(self):
        self._sources: dict[str, DataSource] = {}

    def register(self, source: DataSource):
        if source.name in self._sources:
            raise ValueError(f"Source '{source.name}' already registered")
        self._sources[source.name] = source

    def list_sources(self) -> list[str]:
        return list(self._sources.keys())

    def get(self, name: str) -> DataSource:
        if name not in self._sources:
            raise KeyError(f"Source '{name}' not found")
        return self._sources[name]

    def all(self) -> list[DataSource]:
        return list(self._sources.values())

    def variables_report(self) -> dict[str, str]:
        """Map of {variable_name: source_name} showing which source provides each variable."""
        report = {}
        for source in self._sources.values():
            for var in source.variables_provided:
                report[var] = source.name
        return report
