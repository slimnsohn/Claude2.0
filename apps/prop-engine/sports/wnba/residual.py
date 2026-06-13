"""Residual adjustment layer for WNBA prop projections.

v1 signals: rest/b2b and teammate-out usage redistribution. Conservative by
design — most plays will have residual.total = 0 and the consensus price
stands. Adjustments add to the implied mean μ before posterior P is recomputed.
"""
from __future__ import annotations
import json
from pathlib import Path
from core.types import ResidualAdjustment
from sports.wnba.features import STAT_TO_COL

PRIORS = json.loads((Path(__file__).with_name("league_priors.json")).read_text())

ELASTICITY = 0.65
TEAMMATE_OUT_CAP_FRACTION = 0.25
MIN_B2B_SAMPLE = 8


def _delta_rest(stat: str, position: str, is_b2b: bool,
                  b2b_history, player_stat_avg: float) -> float:
    if not is_b2b:
        return 0.0
    col = STAT_TO_COL.get(stat)

    if isinstance(b2b_history, dict):
        b2b_games = b2b_history.get("b2b", [])
        rest_games = b2b_history.get("rest", [])
        if (len(b2b_games) >= MIN_B2B_SAMPLE and
                len(rest_games) >= MIN_B2B_SAMPLE):
            mean_b2b = sum(g[col] for g in b2b_games) / len(b2b_games)
            mean_rest = sum(g[col] for g in rest_games) / len(rest_games)
            return mean_b2b - mean_rest

    factor = PRIORS["b2b_factor_by_stat"][stat].get(
        position, PRIORS["b2b_factor_by_stat"][stat]["G"]
    )
    return player_stat_avg * factor - player_stat_avg


def _delta_teammate_out(teammates_out, player_stat_avg: float) -> float:
    total_usage = sum(t.get("usage_rate", 0.0) for t in teammates_out)
    raw = player_stat_avg * total_usage * ELASTICITY
    cap = player_stat_avg * TEAMMATE_OUT_CAP_FRACTION
    return min(raw, cap)


def compute_residual(stat: str, position: str, is_b2b: bool,
                       b2b_history, teammates_out: list,
                       player_stat_avg: float) -> ResidualAdjustment:
    notes = []
    rest_delta = _delta_rest(stat, position, is_b2b, b2b_history, player_stat_avg)
    if rest_delta != 0:
        notes.append("rest_b2b")
    out_delta = _delta_teammate_out(teammates_out or [], player_stat_avg)
    if out_delta != 0:
        notes.append("teammate_out")
    return ResidualAdjustment(rest=rest_delta, teammate_out=out_delta,
                                notes=tuple(notes))
