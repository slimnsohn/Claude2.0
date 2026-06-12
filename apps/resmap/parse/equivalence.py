"""
Equivalence engine — THE CROWN JEWEL.

Given a candidate pair of same-event markets across venues, compare their parsed
interpretations and decide whether they actually resolve identically. Persists to
`equivalences`. This is the old resolution-mismatch detector, now writing data.

The four divergence axes (compare parsed_rules A vs B on each):
  - source     : is the authoritative settlement source the same? (different source =
                 they CAN resolve differently even on the same real-world event)
  - cutoff     : same effective cutoff time / basis? (a 6pm vs 11:59pm cutoff is a real gap)
  - tie        : same tie/draw/push handling?
  - threshold  : same threshold + rounding definition? (">=50.0%" vs ">50%" matters)

Output:
  match_type:
    - 'true_match'   : identical on all four axes → safe to treat as the same market
    - 'near_match'   : differ on a minor axis with low practical risk → flag, don't trust blindly
    - 'false_friend' : differ on a way that can flip resolution → THIS is the trap a naive
                       arb scanner calls "free money". Surfacing these is the product's edge.
  risk_score : 0 (safe) .. 1 (will plausibly resolve differently)

    python -m parse.equivalence
"""
from __future__ import annotations

DIVERGENCE_AXES = ("source", "cutoff", "tie", "threshold")

# Relative weight of each axis toward risk. Source divergence is the most dangerous;
# threshold/tie are situation-dependent. Tune against the hand-verified seed set.
AXIS_WEIGHTS = {"source": 0.45, "cutoff": 0.25, "threshold": 0.20, "tie": 0.10}


def compare(parsed_a: dict, parsed_b: dict) -> dict:
    """Compare two parsed-rule dicts. Return dict with match_type, divergence_axes,
    risk_score, divergence_notes.

    TODO: implement axis comparisons. For each axis decide same/different (use the
    normalized `sources` ids for the source axis, not raw strings). Sum AXIS_WEIGHTS
    over differing axes → risk_score. Map score → match_type:
        score == 0            -> true_match
        0 < score <= ~0.25    -> near_match
        score >  ~0.25        -> false_friend
    Thresholds are starting guesses; calibrate on the seed set.
    """
    raise NotImplementedError("implement four-axis comparison + risk scoring")


def run(conn) -> dict:
    """For each candidate pair lacking a current equivalence row, fetch both fresh
    parsed_rules, call compare(), upsert into `equivalences`. TODO."""
    raise NotImplementedError("implement equivalence persistence loop")
