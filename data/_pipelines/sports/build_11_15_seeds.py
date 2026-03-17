"""
Build NCAA 11-15 seed first round results from unified_ncaa.csv + seeds reference.

Joins tournament seed data with game results to produce accurate
underdog/favorite matchups with real moneylines for seeds 11-15.

Usage:
    python build_11_15_seeds.py

Output:
    ../../apps/ncaa_11_15_seeds/data/results.json
"""

import csv
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent.parent / "raw" / "ncaab"
OUTPUT_DIR = SCRIPT_DIR.parent.parent.parent / "apps" / "ncaa_11_15_seeds" / "data"

CSV_PATH = DATA_DIR / "unified_ncaa.csv"
SEEDS_PATH = DATA_DIR / "ncaa_tournament_seeds.json"
OUTPUT_PATH = OUTPUT_DIR / "results.json"

# NCAA first round matchups: seed vs (17 - seed)
OPPONENT_SEED = {11: 6, 12: 5, 13: 4, 14: 3, 15: 2}
TARGET_SEEDS = {11, 12, 13, 14, 15}

# Manual corrections for games with missing or incorrect data in the CSV.
# Key: (year, underdog_display_name) → {"won": bool, "odds": int|None}
# Only use when the source CSV has missing/bad data that can't be fixed upstream.
CORRECTIONS = {
    # CSV has empty score fields for these mislabeled R32 games
    (2024, "Grand Canyon"): {"won": True},     # GCU 75, Saint Mary's 66
    (2025, "Bryant"): {"won": False},          # Bryant 62, Michigan State 87
}

# Team name normalization — map display names from CSV to seed reference names
# Only add entries where they differ
NAME_MAP = {
    "UConn": "UConn",
    "Connecticut": "UConn",
    "Loyola-Chicago": "Loyola Chicago",
    "Loyola (Chi)": "Loyola Chicago",
    "Miami": "Miami (FL)",
    "Miami FL": "Miami (FL)",
    "Miami (Fla.)": "Miami (FL)",
    "Little Rock": "Little Rock",
    "Arkansas-Little Rock": "Little Rock",
    "UALR": "Little Rock",
    "LIU": "LIU Brooklyn",
    "LIU Brooklyn": "LIU Brooklyn",
    "Long Island": "LIU Brooklyn",
    "NC State": "NC State",
    "N.C. State": "NC State",
    "Ole Miss": "Ole Miss",
    "Mississippi": "Ole Miss",
    "UMass": "UMass",
    "Massachusetts": "UMass",
    "St. John's": "St. John's",
    "Saint John's": "St. John's",
    "St. Bonaventure": "St. Bonaventure",
    "Saint Bonaventure": "St. Bonaventure",
    "St. Peter's": "St. Peter's",
    "Saint Peter's": "St. Peter's",
    "St. Joseph's": "St. Joseph's",
    "Saint Joseph's": "St. Joseph's",
    "SIU-Edwardsville": "SIU Edwardsville",
    "SIU Edwardsville": "SIU Edwardsville",
    "SIUE": "SIU Edwardsville",
    "Southern Illinois-Edwardsville": "SIU Edwardsville",
    "UC-San Diego": "UC San Diego",
    "UCSD": "UC San Diego",
    "UC-Irvine": "UC Irvine",
    "UC-Santa Barbara": "UC Santa Barbara",
    "UCSB": "UC Santa Barbara",
    "Texas A&M-CC": "Texas A&M-Corpus Christi",
    "Texas A&M-Corpus Christi": "Texas A&M-Corpus Christi",
    "Cal State Bakersfield": "Cal State Bakersfield",
    "CSU Bakersfield": "Cal State Bakersfield",
    "Cal State Fullerton": "Cal State Fullerton",
    "CSU Fullerton": "Cal State Fullerton",
    "Cal State Northridge": "Cal State Northridge",
    "CSU Northridge": "Cal State Northridge",
    "Long Beach State": "Long Beach State",
    "Long Beach St.": "Long Beach State",
    "CS Long Beach": "Long Beach State",
    "North Carolina Central": "North Carolina Central",
    "NC Central": "North Carolina Central",
    "N.C. Central": "North Carolina Central",
    "North Carolina A&T": "North Carolina A&T",
    "NC A&T": "North Carolina A&T",
    "UNC Asheville": "UNC Asheville",
    "UNC-Asheville": "UNC Asheville",
    "UNC Greensboro": "UNC Greensboro",
    "UNC-Greensboro": "UNC Greensboro",
    "UNC Wilmington": "UNC Wilmington",
    "UNC-Wilmington": "UNC Wilmington",
    "Loyola (MD)": "Loyola (MD)",
    "Loyola Maryland": "Loyola (MD)",
    "Detroit Mercy": "Detroit Mercy",
    "Detroit": "Detroit Mercy",
    "College of Charleston": "College of Charleston",
    "Charleston": "College of Charleston",
    "Stephen F. Austin": "Stephen F. Austin",
    "SFA": "Stephen F. Austin",
    "East Tennessee State": "East Tennessee State",
    "ETSU": "East Tennessee State",
    "Fairleigh Dickinson": "Fairleigh Dickinson",
    "FDU": "Fairleigh Dickinson",
    "Florida Gulf Coast": "Florida Gulf Coast",
    "FGCU": "Florida Gulf Coast",
    "McNeese State": "McNeese",
    "McNeese St.": "McNeese",
    "Mount St. Mary's": "Mount St. Mary's",
    "Mt. St. Mary's": "Mount St. Mary's",
    "North Dakota State": "North Dakota State",
    "NDSU": "North Dakota State",
    "South Dakota State": "South Dakota State",
    "SDSU": "South Dakota State",
    "North Texas": "North Texas",
    "Northern Kentucky": "Northern Kentucky",
    "NKU": "Northern Kentucky",
    "San Diego State": "San Diego State",
    "Jacksonville State": "Jacksonville State",
    "Jax State": "Jacksonville State",
    "Arkansas-Pine Bluff": "Arkansas-Pine Bluff",
    "UAPB": "Arkansas-Pine Bluff",
    "Florida Atlantic": "Florida Atlantic",
    "FAU": "Florida Atlantic",
    "Eastern Washington": "Eastern Washington",
    "E. Washington": "Eastern Washington",
    "Western Kentucky": "Western Kentucky",
    "W. Kentucky": "Western Kentucky",
    "Western Michigan": "Western Michigan",
    "W. Michigan": "Western Michigan",
    "Sam Houston State": "Sam Houston State",
    "Sam Houston": "Sam Houston State",
    "Gardner-Webb": "Gardner-Webb",
    "High Point": "High Point",
    "Grand Canyon": "Grand Canyon",
    "GCU": "Grand Canyon",
    "Robert Morris": "Robert Morris",
    "Oral Roberts": "Oral Roberts",
    "Northwestern State": "Northwestern State",
    "NW State": "Northwestern State",
    "Oakland": "Oakland",
    "Grambling": "Grambling",
    "Grambling State": "Grambling",
    "Omaha": "Omaha",
    "Nebraska-Omaha": "Omaha",
    "Stetson": "Stetson",
    "Wagner": "Wagner",
    "Wofford": "Wofford",
    "Bryant": "Bryant",
    "Alabama State": "Alabama State",
    "Norfolk State": "Norfolk State",
    "Coastal Carolina": "Coastal Carolina",
    "Kennesaw State": "Kennesaw State",
    "Montana State": "Montana State",
    "Weber State": "Weber State",
    "UW-Milwaukee": "Milwaukee",
    "Wisconsin-Green Bay": "Green Bay",
    "Lamar": "Lamar",
    "Mount St. Mary's": "Mount St. Mary's",
    "Mt. St. Mary's": "Mount St. Mary's",
    "Nebraska-Omaha": "Omaha",
}


def normalize_team(name):
    """Normalize a team name to match the seed reference."""
    name = name.strip()
    if name in NAME_MAP:
        return NAME_MAP[name]
    return name


def load_seeds():
    """Load seed reference and build lookup: (year, normalized_team) -> seed."""
    with open(SEEDS_PATH, "r") as f:
        seeds = json.load(f)

    lookup = {}
    for entry in seeds:
        key = (entry["year"], entry["team"])
        lookup[key] = entry["seed"]
    return lookup


def load_r64_games():
    """Load all R64 NCAA tournament games from the CSV.

    Also loads R32-tagged games as candidates — some R64 games are
    mislabeled as R32 in the source data (e.g., 2012 Lehigh vs Duke,
    2024 Grand Canyon vs Saint Mary's).
    """
    r64_games = []
    r32_candidates = []
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["game_type"] == "ncaa_tournament":
                if row["round"] == "R64":
                    r64_games.append(row)
                elif row["round"] == "R32":
                    r32_candidates.append(row)
    return r64_games, r32_candidates


def find_team_seed(team_display, year, seed_lookup):
    """Try to find a team's seed, attempting various normalizations."""
    normalized = normalize_team(team_display)
    key = (year, normalized)
    if key in seed_lookup:
        return seed_lookup[key]

    # Try the raw name
    key = (year, team_display)
    if key in seed_lookup:
        return seed_lookup[key]

    return None


def _extract_seed_games(games, seed_lookup, target_seeds, opponent_seed_map):
    """Extract 11-15 seed games from a list of game rows."""
    results = []
    unmatched = []

    for game in games:
        year = int(game["season_end_year"])
        away_display = game["away_team_display"]
        home_display = game["home_team_display"]

        away_seed = find_team_seed(away_display, year, seed_lookup)
        home_seed = find_team_seed(home_display, year, seed_lookup)

        if away_seed is None:
            unmatched.append((year, away_display, "away"))
        if home_seed is None:
            unmatched.append((year, home_display, "home"))

        # Check if either team is an 11-15 seed
        for side in ["away", "home"]:
            if side == "away":
                underdog_seed = away_seed
                underdog_name = away_display
                underdog_ml = game["away_ml"]
                underdog_final = game["away_final"]
                favorite_seed = home_seed
                favorite_name = home_display
                favorite_ml = game["home_ml"]
                favorite_final = game["home_final"]
            else:
                underdog_seed = home_seed
                underdog_name = home_display
                underdog_ml = game["home_ml"]
                underdog_final = game["home_final"]
                favorite_seed = away_seed
                favorite_name = away_display
                favorite_ml = game["away_ml"]
                favorite_final = game["away_final"]

            if underdog_seed not in target_seeds:
                continue

            # Verify this is the expected first-round matchup (seed vs 17-seed)
            expected_opp = opponent_seed_map.get(underdog_seed)
            if favorite_seed != expected_opp:
                # Not a valid R64 matchup — skip (likely a mislabeled R32 game)
                continue

            # Determine winner
            try:
                u_score = float(underdog_final)
                f_score = float(favorite_final)
                won = u_score > f_score
                score_missing = False
            except (ValueError, TypeError):
                won = None  # MISSING — do not assume
                score_missing = True

            # Parse moneyline
            try:
                odds = int(underdog_ml) if underdog_ml != "NL" else None
            except (ValueError, TypeError):
                odds = None

            # Apply manual corrections for missing data
            correction = CORRECTIONS.get((year, underdog_name))
            if correction:
                if won is None and "won" in correction:
                    won = correction["won"]
                if odds is None and "odds" in correction:
                    odds = correction["odds"]

            result = {
                "year": year,
                "seed": underdog_seed,
                "underdog": underdog_name,
                "favorite": favorite_name,
                "underdog_seed": underdog_seed,
                "favorite_seed": favorite_seed,
                "odds": odds,
                "won": won,
                "game_date": game["game_date"],
            }
            results.append(result)

    return results, unmatched


def build_results():
    """Main pipeline: join seeds with R64 games, filter for 11-15 seeds."""
    seed_lookup = load_seeds()
    r64_games, r32_candidates = load_r64_games()

    # First pass: extract from properly tagged R64 games
    results, unmatched = _extract_seed_games(
        r64_games, seed_lookup, TARGET_SEEDS, OPPONENT_SEED
    )

    # Build set of (year, seed, underdog) already found
    found = {(r["year"], r["seed"], r["underdog"]) for r in results}

    # Second pass: check R32-tagged games for mislabeled R64 matchups
    r32_results, _ = _extract_seed_games(
        r32_candidates, seed_lookup, TARGET_SEEDS, OPPONENT_SEED
    )
    added_from_r32 = 0
    for r in r32_results:
        key = (r["year"], r["seed"], r["underdog"])
        if key not in found:
            results.append(r)
            found.add(key)
            added_from_r32 += 1
            print(f"  RECOVERED from R32: {r['year']} #{r['seed']} {r['underdog']} vs {r['favorite']}")

    if added_from_r32:
        print(f"  ({added_from_r32} games recovered from mislabeled R32 data)")

    # Sort by year, then seed
    results.sort(key=lambda r: (r["year"], r["seed"]))

    # Report unmatched teams
    if unmatched:
        print(f"\nWARNING: {len(unmatched)} unmatched team(s):")
        for year, team, side in sorted(set(unmatched)):
            print(f"  {year} | {team} ({side})")

    return results


def main():
    print(f"Loading seeds from: {SEEDS_PATH}")
    print(f"Loading games from: {CSV_PATH}")
    print(f"Output to: {OUTPUT_PATH}")
    print()

    results = build_results()

    # Stats
    years = sorted(set(r["year"] for r in results))
    print(f"Years: {years[0]}-{years[-1]} ({len(years)} seasons)")
    print(f"Total 11-15 seed games: {len(results)}")
    for s in [11, 12, 13, 14, 15]:
        sg = [r for r in results if r["seed"] == s]
        wins = sum(1 for r in sg if r["won"])
        print(f"  #{s}: {len(sg)} games, {wins} wins")

    missing_result = [r for r in results if r["won"] is None]
    if missing_result:
        print(f"\n*** MISSING RESULTS (won=null in output): {len(missing_result)} ***")
        for r in missing_result:
            print(f"  {r['year']} #{r['seed']} {r['underdog']} vs {r['favorite']} (date: {r['game_date']})")
        print("  >> These MUST be backfilled in CORRECTIONS or the source CSV!")

    no_odds = [r for r in results if r["odds"] is None]
    if no_odds:
        print(f"\nGames with no moneyline data: {len(no_odds)}")
        for r in no_odds:
            print(f"  {r['year']} #{r['seed']} {r['underdog']} vs {r['favorite']}")

    # Write output
    os.makedirs(OUTPUT_PATH.parent, exist_ok=True)

    # Clean up for output — remove internal fields
    output = []
    for r in results:
        output.append({
            "year": r["year"],
            "seed": r["seed"],
            "underdog": r["underdog"],
            "favorite": r["favorite"],
            "odds": r["odds"],
            "won": r["won"],
            "game_date": r["game_date"],
        })

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nWrote {len(output)} results to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
