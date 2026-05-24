"""Seed reference tables: bookmakers and segment_types."""
from odds_pipeline.store import migrate

BOOKMAKERS = [
    # key, title, region, sharp
    ("pinnacle",   "Pinnacle",   "eu", 1),
    ("draftkings", "DraftKings", "us", 0),
    ("fanduel",    "FanDuel",    "us", 0),
    ("betmgm",     "BetMGM",     "us", 0),
    ("caesars",    "Caesars",    "us", 0),
    ("betrivers",  "BetRivers",  "us", 0),
    ("pointsbetus","PointsBet",  "us", 0),
    ("williamhill_us", "William Hill US", "us", 0),
]

# Segment types per sport. (sport, segment_key, kind, order_idx)
SEGMENT_TYPES = [
    # NBA: 4 quarters, 2 halves, FULL, up to 4 OTs
    ("NBA", "FULL", "full",    0),
    ("NBA", "Q1",   "quarter", 1),
    ("NBA", "Q2",   "quarter", 2),
    ("NBA", "Q3",   "quarter", 3),
    ("NBA", "Q4",   "quarter", 4),
    ("NBA", "H1",   "half",    5),
    ("NBA", "H2",   "half",    6),
    ("NBA", "OT1",  "overtime", 7),
    ("NBA", "OT2",  "overtime", 8),
    ("NBA", "OT3",  "overtime", 9),
    ("NBA", "OT4",  "overtime", 10),
    # NFL: same shape as NBA, single OT
    ("NFL", "FULL", "full",    0),
    ("NFL", "Q1",   "quarter", 1),
    ("NFL", "Q2",   "quarter", 2),
    ("NFL", "Q3",   "quarter", 3),
    ("NFL", "Q4",   "quarter", 4),
    ("NFL", "H1",   "half",    5),
    ("NFL", "H2",   "half",    6),
    ("NFL", "OT1",  "overtime", 7),
    # NCAAF: like NFL but multiple OTs possible
    ("NCAAF", "FULL", "full",    0),
    ("NCAAF", "Q1",   "quarter", 1),
    ("NCAAF", "Q2",   "quarter", 2),
    ("NCAAF", "Q3",   "quarter", 3),
    ("NCAAF", "Q4",   "quarter", 4),
    ("NCAAF", "H1",   "half",    5),
    ("NCAAF", "H2",   "half",    6),
    ("NCAAF", "OT1",  "overtime", 7),
    ("NCAAF", "OT2",  "overtime", 8),
    ("NCAAF", "OT3",  "overtime", 9),
    # NHL: 3 periods, OT, shootout
    ("NHL", "FULL", "full",     0),
    ("NHL", "P1",   "period",   1),
    ("NHL", "P2",   "period",   2),
    ("NHL", "P3",   "period",   3),
    ("NHL", "OT1",  "overtime", 4),
    ("NHL", "SO",   "shootout", 5),
    # NCAAB: 2 halves, multiple OTs
    ("NCAAB", "FULL", "full",     0),
    ("NCAAB", "H1",   "half",     1),
    ("NCAAB", "H2",   "half",     2),
    ("NCAAB", "OT1",  "overtime", 3),
    ("NCAAB", "OT2",  "overtime", 4),
    # MLB: 9 innings, F5 inning_range
    ("MLB", "FULL",  "full",          0),
    ("MLB", "INN1",  "inning",        1),
    ("MLB", "INN2",  "inning",        2),
    ("MLB", "INN3",  "inning",        3),
    ("MLB", "INN4",  "inning",        4),
    ("MLB", "INN5",  "inning",        5),
    ("MLB", "INN6",  "inning",        6),
    ("MLB", "INN7",  "inning",        7),
    ("MLB", "INN8",  "inning",        8),
    ("MLB", "INN9",  "inning",        9),
    ("MLB", "F5",    "inning_range",  10),
]


def seed_bookmakers(db_path: str) -> None:
    conn = migrate.connect(db_path)
    try:
        conn.executemany(
            "INSERT OR IGNORE INTO bookmakers (key, title, region, sharp) VALUES (?, ?, ?, ?)",
            BOOKMAKERS,
        )
        conn.commit()
    finally:
        conn.close()


def seed_segment_types(db_path: str) -> None:
    conn = migrate.connect(db_path)
    try:
        conn.executemany(
            "INSERT OR IGNORE INTO segment_types (sport, segment_key, kind, order_idx) VALUES (?, ?, ?, ?)",
            SEGMENT_TYPES,
        )
        conn.commit()
    finally:
        conn.close()


def seed_all(db_path: str) -> None:
    seed_bookmakers(db_path)
    seed_segment_types(db_path)
