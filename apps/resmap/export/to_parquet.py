"""
Export Postgres → partitioned Parquet for DuckDB / analytical buyers (the data product
for backtesters and researchers). Postgres stays the source of truth; this is a snapshot.

    python -m export.to_parquet --out ./export/parquet

Suggested layout (partition by venue + resolution month for cheap pruning in DuckDB):
    parquet/markets/venue=kalshi/...
    parquet/parsed_rules/...
    parquet/equivalences/...
    parquet/rule_changes/...

Use DuckDB itself to read from Postgres and COPY ... TO with FORMAT parquet, or pull via
psycopg into Arrow and write with pyarrow. Keep resolved-market history append-only.
"""
from __future__ import annotations


def export(out_dir: str = "./export/parquet") -> None:
    """TODO: implement Postgres → Parquet snapshot."""
    raise NotImplementedError("implement parquet export")


if __name__ == "__main__":
    export()
