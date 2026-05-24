"""Static config: env keys, sport->market map, segment shape per sport."""
import os

THE_ODDS_API_KEY = os.environ.get("THE_ODDS_API_KEY", "")

# Markets to pull per sport. Names assumed; verify empirically against
# GET /v4/sports/{sport}/events/{eventId}/markets on first pull.
SPORT_MARKETS = {
    "NBA":   ["h2h", "spreads", "totals", "spreads_q1", "totals_q1", "spreads_h1", "totals_h1"],
    "NFL":   ["h2h", "spreads", "totals", "spreads_q1", "totals_q1", "spreads_h1", "totals_h1"],
    "NCAAF": ["h2h", "spreads", "totals", "spreads_q1", "totals_q1", "spreads_h1", "totals_h1"],
    "NHL":   ["h2h", "spreads", "totals", "spreads_p1", "totals_p1"],
    "MLB":   ["h2h", "spreads", "totals", "spreads_1st_5_innings", "totals_1st_5_innings"],
    "NCAAB": ["h2h", "spreads", "totals", "spreads_h1", "totals_h1"],
}

# Odds API sport keys
ODDS_API_SPORT_KEYS = {
    "NBA":   "basketball_nba",
    "NFL":   "americanfootball_nfl",
    "NCAAF": "americanfootball_ncaaf",
    "NHL":   "icehockey_nhl",
    "MLB":   "baseball_mlb",
    "NCAAB": "basketball_ncaab",
}

REGIONS = ["us", "eu"]

DATA_DIR = "data"
RAW_ODDS_DIR = f"{DATA_DIR}/raw/odds"
RAW_RESULTS_DIR = f"{DATA_DIR}/raw/results"
DB_PATH = f"{DATA_DIR}/odds_pipeline.db"
