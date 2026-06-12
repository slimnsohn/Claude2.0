"""Per-persona belief layer: media-diet exposure, bounded shifts, decay, audit trail.

Each profile carries:
  beliefs: {topic: {shift: float, exposures: int, last_updated: iso}}
Shift is a bounded (±BELIEF_BOUND) adjustment applied to the KNN yes-probability
of questions on that topic (sign per CES column via BELIEF_SIGN). Decays toward
zero (the CES-grounded baseline) with HALF_LIFE_DAYS.
"""
import random
from datetime import datetime

from engine.news_scoring import PARTY_VALENCE

BELIEF_BOUND = 0.15
BASE_RATE = 0.01
HALF_LIFE_DAYS = 14.0
DRIFT_LOG_MAX = 200
INCUMBENT = "rep"  # Trump administration 2025-2026
OPPOSITION = "dem"

OUTLET_FAMILY = {
    "fox_news": "right", "newsmax": "right", "oann": "right", "breitbart": "right",
    "msnbc": "left", "npr": "left", "new_york_times": "left",
    "washington_post": "left", "cnn": "left",
    "abc_news": "mainstream", "nbc_news": "mainstream", "cbs_news": "mainstream",
    "local_tv": "mainstream", "local_newspaper": "mainstream", "bbc": "mainstream",
    "the_hill": "mainstream", "politico": "mainstream",
}

# Deliberate design decision: belief topics WITHOUT a CES mapping (crime,
# fiscal) still accumulate and decay — they feed the population drift chart
# and are ready for future CES column coverage but do not influence opinion
# probabilities today.
# CES column topic → belief taxonomy topic
CES_TOPIC_TO_BELIEF = {
    "approval": "trump_approval", "economy": "economy", "immigration": "immigration",
    "healthcare": "healthcare", "environment": "climate", "fiscal": "fiscal",
    "education": "education", "guns": "social", "abortion": "social",
    "foreign_policy": "foreign_policy",
}

# Per-CES-column sign: how a positive topic shift maps onto the column's yes-probability.
# Conventions documented in engine/news_scoring.py. 0 = beliefs don't apply.
BELIEF_SIGN = {
    # approval: + favors the administration
    "CC24_410": +1,    # Trump-vote proxy: pro-Trump mood raises "yes" (Trump vote)
    "CC24_312a": -1,   # Biden approval moves opposite a pro-Trump mood
    "CC24_312b": +1,   # Congress approval (rep-controlled): + favors admin
    "CC24_312i": -1,   # Harris approval moves opposite a pro-Trump mood
    # economy: + = economy doing well
    "CC24_301": +1, "CC24_302": +1,
    "CC24_303": -1,    # "prices increased" yes = bad-economy answer
    # immigration: + = pro-enforcement mood
    "CC24_323b": +1, "CC24_323c": +1,                      # border patrol, wall
    "CC24_323a": -1, "CC24_323d": -1,                      # legal status, Dreamers
    # healthcare: + = pro-public-program mood
    "CC24_328e": +1,                                       # expand Medicaid
    "CC24_328d": -1, "CC24_328c": -1,                      # repeal ACA, work requirement
    # climate: + = pro-climate-action mood
    "CC24_326a": +1, "CC24_326b": +1, "CC24_326e": +1,
    "CC24_326d": -1,                                       # more fossil fuel production
    # social: + = favors incumbent/conservative mood
    "CC24_321a": -1,                                       # assault-rifle ban
    "CC24_321b": +1,                                       # easier concealed carry
    "CC24_321c": -1,                                       # background checks: 90%+ bipartisan, but pro-regulation
    "CC24_324a": -1, "CC24_324d": -1,                      # abortion choice / access
    "CC24_324c": +1,                                       # abortion illegal always
    # education: + = pro-debt-relief mood
    "CC24_323f": +1,                                       # forgive $20k student debt
    # foreign_policy: + = favors incumbent — Ukraine-aid items have no clean
    # partisan polarity under that convention, so beliefs don't apply (0)
    "CC24_308a_4": 0, "CC24_308a_1": 0,
}

_PARTY_GROUP = {
    "strong_dem": "dem", "dem": "dem", "lean_dem": "dem",
    "independent": "independent",
    "lean_rep": "rep", "rep": "rep", "strong_rep": "rep",
}
_STRONG = {"strong_dem", "strong_rep"}


def decay_factor(elapsed_days: float) -> float:
    return 0.5 ** (max(0.0, elapsed_days) / HALF_LIFE_DAYS)


def decay_beliefs(profile: dict, now: datetime):
    """Decay every topic shift toward zero based on elapsed time."""
    beliefs = profile.get("beliefs") or {}
    for topic, b in beliefs.items():
        try:
            last = datetime.fromisoformat(b.get("last_updated", now.isoformat()))
        except (TypeError, ValueError):
            last = now
        elapsed = (now - last).total_seconds() / 86400.0
        if elapsed > 0:
            b["shift"] = round(b["shift"] * decay_factor(elapsed), 6)
            b["last_updated"] = now.isoformat()


def exposure_prob(salience: float, framing_mag: float) -> float:
    return min(1.0, salience * (0.5 + 0.5 * abs(framing_mag)))


def _alignment(party_group: str, topic: str, effective_direction: float) -> str:
    """'congenial' | 'counter' | 'neutral' for this party on this signed event."""
    if party_group == "independent" or effective_direction == 0:
        return "neutral"
    valence = PARTY_VALENCE.get(topic, {})
    key = "positive" if effective_direction > 0 else "negative"
    beneficiary = valence.get(key, "mixed")
    if beneficiary == "incumbent":
        beneficiary = INCUMBENT
    elif beneficiary == "opposition":
        beneficiary = OPPOSITION
    if beneficiary == "mixed":
        return "neutral"
    return "congenial" if beneficiary == party_group else "counter"


def susceptibility(party_id: str, topic: str, effective_direction: float) -> float:
    group = _PARTY_GROUP.get(party_id, "independent")
    base = 0.7 if party_id in _STRONG else 1.0
    if _alignment(group, topic, effective_direction) == "counter":
        return base * 0.4
    return base


def apply_event(profile: dict, event: dict, now: datetime, rng: random.Random,
                update_id: str) -> float:
    """Maybe expose profile to event; update beliefs. Returns total |delta| applied."""
    family = OUTLET_FAMILY.get(profile.get("primary_news_source", ""), "mainstream")
    framing = (event.get("framing") or {}).get(family, 1.0)
    salience = float(event.get("salience", 0.5))
    direction = float(event.get("direction", 0.0))
    effective = direction * framing
    if not event.get("topics") or effective == 0.0:
        return 0.0
    if rng.random() >= exposure_prob(salience, framing):
        return 0.0

    beliefs = profile.setdefault("beliefs", {})
    drift_log = profile.setdefault("drift_log", [])
    total = 0.0
    for topic in event["topics"]:
        susc = susceptibility(profile.get("party_id", "independent"), topic, effective)
        delta = effective * salience * susc * BASE_RATE
        if delta == 0.0:
            continue
        b = beliefs.setdefault(topic, {"shift": 0.0, "exposures": 0,
                                       "last_updated": now.isoformat()})
        b["shift"] = round(max(-BELIEF_BOUND, min(BELIEF_BOUND, b["shift"] + delta)), 6)
        b["exposures"] = b.get("exposures", 0) + 1
        b["last_updated"] = now.isoformat()
        drift_log.append({"date": now.isoformat(), "topic": topic,
                          "delta": round(delta, 6), "update_id": update_id,
                          "shift_after": b["shift"]})
        total += abs(delta)
    if len(drift_log) > DRIFT_LOG_MAX:
        del drift_log[:-DRIFT_LOG_MAX]
    return total


def update_population(profiles: list, events: list, now: datetime,
                      update_id: str) -> dict:
    """Decay all profiles, then expose each to each event. Deterministic per update_id."""
    exposures = 0
    for p in profiles:
        # Reset corrupt beliefs defensively
        if not isinstance(p.get("beliefs"), dict):
            p["beliefs"] = {}
        decay_beliefs(p, now)
        rng = random.Random(f"{update_id}:{p.get('profile_id', '')}")
        for ev in events:
            if apply_event(p, ev, now, rng, update_id) > 0:
                exposures += 1

    # Aggregate summary
    sums = {}
    for p in profiles:
        for topic, b in (p.get("beliefs") or {}).items():
            sums[topic] = sums.get(topic, 0.0) + b.get("shift", 0.0)
    n = max(1, len(profiles))
    return {
        "update_id": update_id,
        "date": now.isoformat(),
        "n_profiles": len(profiles),
        "n_events": len(events),
        "exposures": exposures,
        "mean_shift_by_topic": {t: round(s / n, 5) for t, s in sums.items()},
    }
