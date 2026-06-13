"""Import positions from cashflow logger CSV into the database."""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from db.database import Database

VALID_PLATFORMS = {"polymarket", "kalshi"}


def import_positions_from_csv(csv_path: str, db: Database = None):
    """
    Import positions from a cashflow logger CSV.

    Expected columns: platform, market_id, side, avg_price, quantity, entered_at

    Only imports rows where platform is 'polymarket' or 'kalshi'.
    market_id is prefixed as '{platform}:{market_id}'.
    """
    if db is None:
        db = Database()

    imported = 0
    skipped = 0

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            platform = row["platform"].strip().lower()
            if platform not in VALID_PLATFORMS:
                skipped += 1
                continue

            db.upsert_position(
                market_id=f"{platform}:{row['market_id'].strip()}",
                platform=platform,
                side=row["side"].strip().upper(),
                avg_price=float(row["avg_price"]),
                quantity=float(row["quantity"]),
                entered_at=row["entered_at"].strip(),
            )
            imported += 1

    return {"imported": imported, "skipped": skipped}
