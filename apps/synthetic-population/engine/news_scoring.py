"""News scoring: keyword heuristics (moved from api/world_updates.py) + LLM batch scoring.

Event schema (one per headline):
  {text, description, feed, topics: [str], direction: float -1..1,
   salience: float 0..1, framing: {right,left,mainstream: float -1..1},
   scoring_method: "llm" | "keyword"}

Sign conventions (also stated in the LLM prompt):
  economy +: conditions good/improving      trump_approval +: favorable to administration
  immigration +: pro-enforcement mood       healthcare +: pro-public-program mood
  climate +: pro-climate-action mood        fiscal +: pro-progressive-tax mood
  education +: pro-debt-relief mood         crime/foreign_policy/social +: favors incumbent
"""
import json
import os
import re

import requests

BELIEF_TOPICS = ["economy", "trump_approval", "immigration", "healthcare", "climate",
                 "fiscal", "education", "crime", "foreign_policy", "social"]

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
SCORING_MODEL = "claude-haiku-4-5-20251001"

# ---------------------------------------------------------------------------
# Topic detection heuristics — moved verbatim from api/world_updates.py
# ---------------------------------------------------------------------------

TOPIC_KEYWORDS = {
    "economy": [
        "economy", "economic", "inflation", "recession", "gdp", "unemployment",
        "jobs report", "wages", "stock market", "housing", "interest rate",
        "federal reserve", "fed ", "dow", "nasdaq", "s&p", "tariff", "trade",
        "consumer", "spending", "debt", "deficit", "gas price", "oil price",
        "retail", "manufacturing",
    ],
    "trump_approval": [
        "trump", "president", "white house", "executive order", "administration",
        "oval office", "mar-a-lago", "presidential",
    ],
    "immigration": [
        "border", "immigration", "immigrant", "migrant", "asylum", "deportation",
        "ice ", "customs", "visa", "refugee", "undocumented", "daca",
    ],
    "healthcare": [
        "healthcare", "health care", "insurance", "medicaid", "medicare",
        "obamacare", "aca ", "hospital", "drug price", "pharmaceutical",
    ],
    "climate": [
        "climate", "environment", "emissions", "renewable", "fossil fuel",
        "carbon", "epa", "clean energy", "solar", "wind power", "wildfire",
        "hurricane", "flood", "drought",
    ],
    "gun_policy": [
        "gun", "firearm", "shooting", "second amendment", "nra",
        "background check", "assault weapon",
    ],
    "foreign_policy": [
        "russia", "ukraine", "china", "nato", "military", "war ",
        "iran", "north korea", "israel", "gaza", "taiwan", "sanctions",
        "missile", "troops",
    ],
    "social": [
        "abortion", "roe", "supreme court", "scotus", "transgender",
        "lgbtq", "marriage equality", "dei", "affirmative action",
    ],
    "education": [
        "school", "education", "student loan", "college", "university",
        "teacher", "curriculum",
    ],
    "crime": [
        "crime", "police", "law enforcement", "prison", "fentanyl",
        "drug ", "murder", "violent crime", "theft",
    ],
}

POSITIVE_SIGNALS = [
    "improve", "surge", "gain", "rise", "boost", "record high", "growth",
    "recover", "pass", "sign into law", "bipartisan", "agreement",
    "strong", "beat expectations", "optimis", "deal", "success",
]
NEGATIVE_SIGNALS = [
    "crash", "decline", "fall", "drop", "crisis", "scandal", "fail",
    "worse", "collapse", "layoff", "cut", "slash", "protest",
    "backlash", "concern", "fear", "warning", "record low", "pessimis",
    "indict", "investigation", "shutdown", "attack", "threat", "tension",
]

# Bad news about public programs/climate action confirms Republican-leaning priors;
# good news confirms Democratic-leaning priors (used by the belief layer's
# confirmation-bias alignment).
PARTY_VALENCE = {
    "economy":         {"positive": "incumbent", "negative": "opposition"},
    "trump_approval":  {"positive": "rep", "negative": "dem"},
    "immigration":     {"positive": "rep", "negative": "dem"},
    "healthcare":      {"positive": "dem", "negative": "rep"},
    "climate":         {"positive": "dem", "negative": "rep"},
    "gun_policy":      {"positive": "dem", "negative": "rep"},
    "foreign_policy":  {"positive": "incumbent", "negative": "opposition"},
    "social":          {"positive": "mixed", "negative": "mixed"},
    "education":       {"positive": "dem", "negative": "mixed"},
    "crime":           {"positive": "rep", "negative": "rep"},
}


def detect_topics(text: str) -> list[str]:
    lower = text.lower()
    found = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            found.append(topic)
    return found or ["general"]


def detect_direction(text: str) -> str:
    lower = text.lower()
    pos = sum(1 for s in POSITIVE_SIGNALS if s in lower)
    neg = sum(1 for s in NEGATIVE_SIGNALS if s in lower)
    if pos > neg:
        return "positive"
    elif neg > pos:
        return "negative"
    return "neutral"


def compute_party_shift(topics: list, direction: str) -> dict:
    incumbent = "rep"  # Trump in office 2025-2026
    opposition = "dem"

    shifts = {"dem": 0.0, "rep": 0.0, "independent": 0.0}

    for topic in topics:
        valence = PARTY_VALENCE.get(topic, {"positive": "mixed", "negative": "mixed"})
        beneficiary = valence.get(direction, "mixed")

        if beneficiary == "incumbent":
            beneficiary = incumbent
        elif beneficiary == "opposition":
            beneficiary = opposition

        magnitude = 0.01  # small per-topic; ~8 headlines = ~5% max shift

        if beneficiary == "rep":
            shifts["rep"] += magnitude
            shifts["dem"] -= magnitude * 0.5
        elif beneficiary == "dem":
            shifts["dem"] += magnitude
            shifts["rep"] -= magnitude * 0.5

    for k in shifts:
        shifts[k] = max(-0.10, min(0.10, shifts[k]))

    return shifts


# ---------------------------------------------------------------------------
# Keyword-to-BELIEF_TOPICS mapping
# ---------------------------------------------------------------------------

# NOTE: keyword detector emits topic "climate" already; its "gun_policy" maps to "social";
# "approval"-style topics aren't emitted by keywords (it emits "trump_approval"). Mapping:
_KEYWORD_TO_BELIEF = {t: t for t in BELIEF_TOPICS}
_KEYWORD_TO_BELIEF["gun_policy"] = "social"

_DIRECTION_VALUE = {"positive": 0.5, "negative": -0.5, "neutral": 0.0}


def score_events_keyword(headlines: list[dict]) -> list[dict]:
    events = []
    for h in headlines:
        text = (h.get("title", "") + " " + h.get("description", "")).strip()
        topics_raw = detect_topics(text)
        topics = sorted({_KEYWORD_TO_BELIEF.get(t) for t in topics_raw} - {None})
        direction_label = detect_direction(text)
        events.append({
            "text": h.get("title", ""),
            "description": h.get("description", ""),
            "feed": h.get("feed", ""),
            "topics": topics,
            "direction": _DIRECTION_VALUE[direction_label],
            "salience": 0.5,
            "framing": {"right": 1.0, "left": 1.0, "mainstream": 1.0},
            "scoring_method": "keyword",
        })
    return events


_LLM_SYSTEM = """You score news headlines for a public-opinion simulation. For each headline,
return an object: {"topics": [...], "direction": float, "salience": float,
"framing": {"right": float, "left": float, "mainstream": float}}.

topics: subset of """ + json.dumps(BELIEF_TOPICS) + """ (empty list if none apply).
direction (-1..1) sign conventions:
  economy: + = economic conditions good/improving
  trump_approval: + = favorable to the Trump administration
  immigration: + = strengthens pro-enforcement sentiment
  healthcare: + = strengthens support for public healthcare programs
  climate: + = strengthens support for climate action
  fiscal: + = strengthens support for taxing high incomes / opposing spending cuts
  education: + = strengthens support for student debt relief
  crime, foreign_policy, social: + = favorable to the incumbent administration
salience (0..1): how prominent/important the story is to the general public.
framing.X (-1..1): how X-leaning outlets spin it for their audience
(1 = amplify as-is, 0 = ignore, negative = spin to the opposite direction).

Return ONLY a JSON array, same length and order as the input. No prose."""


def score_events_llm(headlines: list[dict], api_key: str,
                     model: str = SCORING_MODEL, timeout: int = 60) -> list[dict] | None:
    """Batch-score headlines with one LLM call. Returns None on any failure (caller falls back)."""
    try:
        payload_in = [{"title": h.get("title", ""), "description": h.get("description", "")[:200]}
                      for h in headlines]
        resp = requests.post(
            ANTHROPIC_URL,
            timeout=timeout,
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": model, "max_tokens": 4000, "system": _LLM_SYSTEM,
                  "messages": [{"role": "user", "content": json.dumps(payload_in)}]},
        )
        if resp.status_code != 200:
            return None
        text = resp.json()["content"][0]["text"].strip()
        text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()
        scored = json.loads(text)
        if not isinstance(scored, list) or len(scored) != len(headlines):
            return None

        def clamp(v, lo=-1.0, hi=1.0):
            return max(lo, min(hi, float(v)))

        events = []
        for h, s in zip(headlines, scored):
            topics = [t for t in s.get("topics", []) if t in BELIEF_TOPICS]
            framing = s.get("framing", {})
            events.append({
                "text": h.get("title", ""),
                "description": h.get("description", ""),
                "feed": h.get("feed", ""),
                "topics": topics,
                "direction": clamp(s.get("direction", 0.0)),
                "salience": clamp(s.get("salience", 0.5), 0.0, 1.0),
                "framing": {fam: clamp(framing.get(fam, 1.0)) for fam in ("right", "left", "mainstream")},
                "scoring_method": "llm",
            })
        return events
    except Exception:
        return None


def score_events(headlines: list[dict]) -> tuple[list[dict], str]:
    """LLM scoring when ANTHROPIC_API_KEY is set; keyword fallback otherwise."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if api_key:
        events = score_events_llm(headlines, api_key)
        if events is not None:
            return events, "llm"
    return score_events_keyword(headlines), "keyword"
