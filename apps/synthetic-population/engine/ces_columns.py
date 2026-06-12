"""CES 2024 column definitions and question-to-column mapping.

Each entry defines a CES survey question: what it measures, how to
interpret its coded values as yes/no/unsure, and what free-text
question keywords map to it.

Value codings verified against the CES 2024 codebook (Harvard Dataverse
doi:10.7910/DVN/X11EP6 guide + questionnaires) AND empirically against
data/raw/ces/ces_2024_common.csv (60K rows) via verify_ces_mappings.py:
every column's raw distribution and pid7 (party ID) cross-tab was checked
to confirm the partisan direction matches the item's known polarity.

Grid items:
  CC24_312  job approval grid (a=Biden, b=Congress, c=Supreme Court, i=Harris)
  CC24_321  guns (1=Support 2=Oppose)
  CC24_323  immigration (1=Support 2=Oppose; 323f = student debt forgiveness,
            misnumbered into the 323 grid in the released data)
  CC24_324  abortion (1=Support 2=Oppose)
  CC24_326  environment (1=Support 2=Oppose)
  CC24_328  housing/healthcare (1=Support 2=Oppose)
  CC24_308a Ukraine multi-select (1=selected, 2=not selected)
  CC24_410  2024 presidential vote (1=Harris, 2=Trump, 3-6=other, 8/9=did not vote)
"""


def _binary_support(val):
    """1=Support/Yes, 2=Oppose/No."""
    if val == 1:
        return "yes"
    if val == 2:
        return "no"
    return "unsure"


def _approval_4pt_correct(val):
    """CC24_312 grid: 1=Strongly approve, 2=Somewhat approve,
    3=Somewhat disapprove, 4=Strongly disapprove, 5=Not sure.

    Verified empirically: on CC24_312a (Biden) 81% of Democrats answer 1-2
    and 87% of Republicans answer 4 — approve codes are LOW, not high.
    """
    if val in (1, 2):
        return "yes"
    if val in (3, 4):
        return "no"
    return "unsure"


def _retro_5pt(val):
    """Past-year retrospective: 1=Much better/Increased a lot ...
    3=Stayed about the same ... 5=Much worse/Decreased a lot
    (CC24_301 also has 6=Not sure). 1,2=yes; 4,5=no; else unsure."""
    if val in (1, 2):
        return "yes"
    if val in (4, 5):
        return "no"
    return "unsure"


def _multiselect_selected(val):
    """Multi-select grid item: 1=selected, 2=not selected (no unsure code)."""
    if val == 1:
        return "yes"
    if val == 2:
        return "no"
    return "unsure"


def _trump_vote_proxy(val):
    """PROXY: 2024 Trump vote as stand-in for Trump approval; documented
    limitation. CES 2024 has NO direct Trump job-approval item (Trump was
    not in office at fielding), so the 2024 presidential vote (CC24_410)
    is used: 2=Trump vote -> yes, 1=Harris vote -> no,
    other candidate / did not vote / not sure -> unsure.

    Coding verified empirically: code 1 is 20951 dem vs 749 rep, code 2 is
    15836 rep vs 592 dem; ~93% of Republican voters chose code 2.
    """
    if val == 2:
        return "yes"
    if val == 1:
        return "no"
    return "unsure"


# ---------------------------------------------------------------------------
# Column registry
# ---------------------------------------------------------------------------

CES_COLUMNS = {
    # --- Approval ---
    "CC24_410": {
        # PROXY: 2024 Trump vote as stand-in for Trump approval; documented
        # limitation (no direct CES 2024 Trump-approval item exists).
        "name": "Trump job approval (2024 Trump-vote proxy)",
        "topic": "approval",
        "keywords": ["trump", "approve", "approval", "job performance",
                     "president"],
        "interpret": _trump_vote_proxy,
    },
    "CC24_312a": {
        "name": "Biden job approval (historical)",
        "topic": "approval",
        "keywords": ["biden"],
        "interpret": _approval_4pt_correct,
    },
    "CC24_312b": {
        "name": "Congress approval",
        "topic": "approval",
        "keywords": ["congress", "congressional approval"],
        "interpret": _approval_4pt_correct,
    },
    "CC24_312i": {
        "name": "Harris approval (historical)",
        "topic": "approval",
        "keywords": ["harris", "vice president"],
        "interpret": _approval_4pt_correct,
    },

    # --- Economy ---
    "CC24_301": {
        "name": "Economy retrospective (nation's economy past year)",
        "topic": "economy",
        "keywords": ["economy", "economic", "getting better", "getting worse",
                     "recession", "gdp", "conditions", "direction",
                     "right track", "wrong track", "right direction",
                     "country is going", "tariff", "trade"],
        "interpret": _retro_5pt,
    },
    "CC24_302": {
        "name": "Household income past year (increased/decreased)",
        "topic": "economy",
        "keywords": ["personal finance", "your finances", "household income",
                     "better off"],
        "interpret": _retro_5pt,
    },
    "CC24_303": {
        "name": "Prices of everyday goods past year (increased/decreased)",
        "topic": "economy",
        # yes = prices increased (codes 1,2) — for questions like
        # "have prices / cost of living gone up?"
        "keywords": ["prices", "inflation", "cost of living", "afford"],
        "interpret": _retro_5pt,
    },

    # --- Immigration (CC24_323 grid, 1=Support 2=Oppose) ---
    "CC24_323a": {
        "name": "Grant legal status to tax-paying immigrants without felonies",
        "topic": "immigration",
        "keywords": ["legal status", "path to citizenship", "undocumented"],
        "interpret": _binary_support,
    },
    "CC24_323b": {
        "name": "Increase border patrols on US-Mexico border",
        "topic": "immigration",
        "keywords": ["border", "border patrol", "border security"],
        "interpret": _binary_support,
    },
    "CC24_323c": {
        "name": "Build a wall on the US-Mexico border",
        "topic": "immigration",
        "keywords": ["wall", "border wall"],
        "interpret": _binary_support,
    },
    "CC24_323d": {
        "name": "Pathway to citizenship for Dreamers (brought as children)",
        "topic": "immigration",
        "keywords": ["dreamer", "daca", "brought to the us as children"],
        "interpret": _binary_support,
    },

    # --- Healthcare (CC24_328 grid, 1=Support 2=Oppose) ---
    # NOTE: CES 2024 has NO Medicare-for-All item — that coverage is dropped.
    "CC24_328c": {
        "name": "Medicaid work requirement",
        "topic": "healthcare",
        "keywords": ["medicaid work requirement", "work requirement"],
        "interpret": _binary_support,
    },
    "CC24_328d": {
        "name": "Repeal the Affordable Care Act",
        "topic": "healthcare",
        "keywords": ["repeal", "obamacare", "affordable care act", "aca"],
        "interpret": _binary_support,
    },
    "CC24_328e": {
        "name": "Expand Medicaid",
        "topic": "healthcare",
        "keywords": ["expand medicaid", "medicaid expansion"],
        "interpret": _binary_support,
    },

    # --- Environment (CC24_326 grid, 1=Support 2=Oppose) ---
    "CC24_326a": {
        "name": "Give EPA power to regulate CO2 emissions",
        "topic": "environment",
        "keywords": ["regulate co2", "epa", "carbon regulation", "climate"],
        "interpret": _binary_support,
    },
    "CC24_326b": {
        "name": "Require at least 20% renewable electricity",
        "topic": "environment",
        "keywords": ["renewable", "clean energy", "solar", "wind"],
        "interpret": _binary_support,
    },
    "CC24_326d": {
        "name": "Increase fossil fuel production",
        "topic": "environment",
        "keywords": ["fossil fuel production", "drilling", "oil and gas"],
        "interpret": _binary_support,
    },
    "CC24_326e": {
        "name": "Halt new federal oil and gas leases",
        "topic": "environment",
        "keywords": ["oil and gas leases", "federal lands"],
        "interpret": _binary_support,
    },

    # --- Guns (CC24_321 grid, 1=Support 2=Oppose) ---
    "CC24_321a": {
        "name": "Ban assault rifles",
        "topic": "guns",
        "keywords": ["assault weapon", "assault rifle", "ban"],
        "interpret": _binary_support,
    },
    "CC24_321b": {
        "name": "Make it easier to obtain concealed-carry permits",
        "topic": "guns",
        "keywords": ["concealed carry"],
        "interpret": _binary_support,
    },
    "CC24_321c": {
        "name": "Require background checks on all gun sales",
        "topic": "guns",
        "keywords": ["background check"],
        "interpret": _binary_support,
    },

    # --- Abortion (CC24_324 grid, 1=Support 2=Oppose) ---
    "CC24_324a": {
        "name": "Always allow abortion as a matter of choice",
        "topic": "abortion",
        "keywords": ["abortion", "matter of choice", "roe"],
        "interpret": _binary_support,
    },
    "CC24_324c": {
        "name": "Make abortion illegal in all circumstances",
        "topic": "abortion",
        "keywords": ["abortion illegal", "ban abortion"],
        "interpret": _binary_support,
    },
    "CC24_324d": {
        "name": "Expand abortion access",
        "topic": "abortion",
        "keywords": ["abortion access"],
        "interpret": _binary_support,
    },

    # --- Education ---
    "CC24_323f": {
        # Misnumbered into the 323 immigration grid in the released data;
        # codebook confirms this is the student-debt forgiveness item.
        "name": "Forgive up to $20,000 in student loan debt",
        "topic": "education",
        "keywords": ["student loan", "student debt", "forgiveness"],
        "interpret": _binary_support,
    },

    # --- Foreign policy (CC24_308a Ukraine multi-select, 1=selected) ---
    "CC24_308a_4": {
        "name": "Provide arms to Ukraine",
        "topic": "foreign_policy",
        "keywords": ["ukraine", "arms", "military aid"],
        "interpret": _multiselect_selected,
    },
    "CC24_308a_1": {
        "name": "Do not get involved in Ukraine",
        "topic": "foreign_policy",
        "keywords": ["stay out of ukraine", "not get involved"],
        "interpret": _multiselect_selected,
    },
}


# ---------------------------------------------------------------------------
# Negated-phrasing detection (audit H2)
# ---------------------------------------------------------------------------
# The keyword matcher below is polarity-blind: "Do you oppose X?" matches X's
# column and would return the SUPPORT distribution as "yes". Policy: REJECT
# negated question stems at the API entry gates rather than try to flip them.
# Only question-STEM negations are listed here — words like "ban", "illegal",
# "repeal" are the proposal's content (handled by column polarity) and must
# NOT be flagged.

NEGATION_PATTERNS = [
    "do you oppose",
    "you opposed",
    "do you disapprove",
    "are you against",
    "should we not",
    "do you not support",
    "don't you support",
    "do you reject",
]

NEGATED_PHRASING_ERROR = (
    "Question uses negated phrasing ('oppose/disapprove/against'). "
    "Rephrase affirmatively (e.g. 'Do you support X?') — the engine answers "
    "support/approval distributions."
)


def detect_negated_phrasing(question: str) -> bool:
    """True if the question stem is negated (oppose/disapprove/against...).

    Callers (API entry gates) should reject such questions with
    NEGATED_PHRASING_ERROR instead of passing them to match_question.
    """
    q = question.lower()
    return any(pattern in q for pattern in NEGATION_PATTERNS)


def match_question(question: str, min_score: int = 1) -> dict | None:
    """Match a free-text question to the best CES column.

    Returns dict with col_id, name, topic, interpret function, and
    match_score, or None if no CES column covers this question.

    Scoring: count keyword matches weighted by keyword length (longer = more
    specific). min_score is the minimum summed score required to count as a
    match: the default (1) keeps the loose historical behavior where any
    single keyword hit matches; callers screening broad question streams
    (e.g. Polymarket trending) should raise it so one generic keyword
    (a bare "trump" scores 5) is not treated as coverage.

    NOTE: the matcher is polarity-blind — gate negated questions with
    detect_negated_phrasing() before calling this.
    """
    q = question.lower()
    best_col = None
    best_score = 0

    for col_id, col in CES_COLUMNS.items():
        score = 0
        for kw in col["keywords"]:
            if kw in q:
                score += len(kw)
        if score > best_score:
            best_score = score
            best_col = {"col_id": col_id, "match_score": score, **col}

    return best_col if best_score >= max(min_score, 1) else None
