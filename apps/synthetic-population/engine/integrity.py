"""
Hedge Detection & Integrity Checks for the Synthetic Population Engine.

check_hedge_score: measures how much a response hedges using known hedge phrases.
check_consistency: compares a new position against a persona's drift log and flags
                   reversals (position shift of 3+ steps on the same topic).
"""

from __future__ import annotations

HEDGE_PHRASES: list[str] = [
    "on the other hand",
    "however",
    "both sides",
    "it's complicated",
    "reasonable people disagree",
    "there are valid points on both sides",
    "nuanced",
    "multifaceted",
    "on the one hand",
]

# Ordered from most supportive to most opposed.
POSITION_SCALE: list[str] = [
    "strongly_support",
    "support",
    "lean_support",
    "neutral",
    "lean_oppose",
    "oppose",
    "strongly_oppose",
]


def check_hedge_score(response_text: str) -> float:
    """Return a hedge score in [0.0, 1.0].

    Score is based on the fraction of known hedge phrases present in the
    response. The score is capped at 1.0.

    A score close to 0 indicates a clear, direct opinion.
    A score above 0.5 indicates significant hedging.
    """
    if not response_text:
        return 0.0

    lowered = response_text.lower()
    hits = sum(1 for phrase in HEDGE_PHRASES if phrase in lowered)

    # Normalise: each phrase contributes equally; cap at 1.0.
    # Using half the total phrase list as the "full hedge" ceiling so that
    # responses containing ~4-5 phrases already score >= 0.5.
    ceiling = max(len(HEDGE_PHRASES) / 2, 1)
    score = min(hits / ceiling, 1.0)
    return score


def check_consistency(
    drift_log: list[dict],
    new_response: dict,
) -> list[str]:
    """Compare new_response against the most recent same-topic entry in drift_log.

    Returns a (possibly empty) list of human-readable flag strings.
    A 'contradiction' flag is raised when the position shifts 3+ steps on the
    POSITION_SCALE for the same topic.

    Parameters
    ----------
    drift_log:
        List of prior response dicts, each with at minimum 'topic' and 'position'.
    new_response:
        Dict with at minimum 'topic' and 'position'.
    """
    flags: list[str] = []

    topic = new_response.get("topic")
    new_position = new_response.get("position")

    if not topic or not new_position:
        return flags

    if new_position not in POSITION_SCALE:
        flags.append(f"unknown position '{new_position}' not in POSITION_SCALE")
        return flags

    # Find the most recent prior entry on the same topic.
    prior = None
    for entry in reversed(drift_log):
        if entry.get("topic") == topic:
            prior = entry
            break

    if prior is None:
        return flags  # No history for this topic — nothing to check.

    prior_position = prior.get("position")
    if prior_position not in POSITION_SCALE:
        # Prior entry has an unrecognised position; skip consistency check.
        return flags

    prior_idx = POSITION_SCALE.index(prior_position)
    new_idx = POSITION_SCALE.index(new_position)
    shift = abs(new_idx - prior_idx)

    if shift >= 3:
        flags.append(
            f"contradiction on '{topic}': shifted from '{prior_position}' to "
            f"'{new_position}' ({shift} steps)"
        )

    return flags
