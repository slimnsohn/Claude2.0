"""CES 2024 column definitions and question-to-column mapping.

Each entry defines a CES survey question: what it measures, how to
interpret its coded values as yes/no/unsure, and what free-text
question keywords map to it.

Value codings verified against CES 2024 codebook + cross-tab validation
with pid7 (party ID) to confirm partisan direction is correct.
"""


def _binary_support(val):
    """1=Support/Yes, 2=Oppose/No."""
    if val == 1:
        return "yes"
    if val == 2:
        return "no"
    return "unsure"


def _approval_4pt(val):
    """1=Strongly disapprove, 2=Somewhat disapprove, 3=Somewhat approve, 4=Strongly approve, 5=Not sure.
    CES coding verified: strong dems cluster at 1, strong reps at 4."""
    if val in (3, 4):
        return "yes"
    if val in (1, 2):
        return "no"
    return "unsure"


def _economy_retro(val):
    """1=Much better, 2=Somewhat better, 3=About the same, 4=Somewhat worse, 5=Much worse."""
    if val in (1, 2):
        return "yes"
    if val in (4, 5):
        return "no"
    if val == 3:
        return "unsure"
    return "unsure"


def _economy_current(val):
    """1=Excellent, 2=Good, 3=Fair, 4=Poor, 5=Very poor."""
    if val in (1, 2):
        return "yes"
    if val in (4, 5):
        return "no"
    if val == 3:
        return "unsure"
    return "unsure"


def _carbon_env(val):
    """1=Support, 2=Oppose (some have 3-5 as unsure/skip)."""
    if val == 1:
        return "yes"
    if val == 2:
        return "no"
    return "unsure"


# ---------------------------------------------------------------------------
# Column registry
# ---------------------------------------------------------------------------

CES_COLUMNS = {
    # --- Approval ---
    "CC24_312i": {
        "name": "Trump job approval",
        "topic": "approval",
        "keywords": ["trump", "approve", "approval", "job performance", "president"],
        "interpret": _approval_4pt,
    },
    "CC24_311a": {
        "name": "Congress approval",
        "topic": "approval",
        "keywords": ["congress", "congressional approval", "legislature"],
        "interpret": _approval_4pt,
    },

    # --- Economy ---
    "CC24_301": {
        "name": "Economy retrospective (better/worse than year ago)",
        "topic": "economy",
        "keywords": ["economy", "economic", "getting better", "getting worse",
                     "recession", "gdp", "conditions", "direction",
                     "right track", "wrong track", "right direction",
                     "country is going", "tariff", "trade"],
        "interpret": _economy_retro,
    },
    "CC24_302": {
        "name": "Current economic conditions",
        "topic": "economy",
        "keywords": ["current economy", "economic conditions", "state of the economy"],
        "interpret": _economy_current,
    },
    "CC24_303": {
        "name": "Personal finances (better/worse than year ago)",
        "topic": "economy",
        "keywords": ["personal finance", "your finances", "household income",
                     "your economic", "cost of living", "afford"],
        "interpret": _economy_retro,
    },

    # --- Immigration ---
    "CC24_300_1": {
        "name": "Increase border patrol on US-Mexico border",
        "topic": "immigration",
        "keywords": ["border", "border patrol", "border security", "border wall"],
        "interpret": _binary_support,
    },
    "CC24_300_2": {
        "name": "Grant legal status to DREAMers (brought to US as children)",
        "topic": "immigration",
        "keywords": ["dreamer", "legal status", "path to citizenship",
                     "citizenship for", "undocumented", "daca"],
        "interpret": _binary_support,
    },
    "CC24_300_3": {
        "name": "Increase deportation of undocumented immigrants",
        "topic": "immigration",
        "keywords": ["deportation", "deport", "remove undocumented",
                     "illegal immigrant"],
        "interpret": _binary_support,
    },
    "CC24_300_4": {
        "name": "Identify and deport undocumented immigrants",
        "topic": "immigration",
        "keywords": ["identify and deport", "round up", "mass deportation"],
        "interpret": _binary_support,
    },

    # --- Healthcare ---
    "CC24_326a": {
        "name": "Repeal the Affordable Care Act (Obamacare)",
        "topic": "healthcare",
        "keywords": ["repeal", "obamacare", "affordable care act", "aca"],
        "interpret": _binary_support,
    },
    "CC24_326b": {
        "name": "Medicare for All / government health insurance plan",
        "topic": "healthcare",
        "keywords": ["medicare for all", "universal health", "single payer",
                     "government health", "public option"],
        "interpret": _binary_support,
    },
    "CC24_326c": {
        "name": "Expand Medicaid in all states",
        "topic": "healthcare",
        "keywords": ["expand medicaid", "medicaid expansion"],
        "interpret": _binary_support,
    },
    "CC24_326d": {
        "name": "Allow drug importation from Canada",
        "topic": "healthcare",
        "keywords": ["drug import", "prescription drug", "drug price",
                     "pharmaceutical", "canada"],
        "interpret": _binary_support,
    },
    "CC24_326e": {
        "name": "Require employers to provide health insurance",
        "topic": "healthcare",
        "keywords": ["employer mandate", "employer health", "employer insurance"],
        "interpret": _binary_support,
    },
    "CC24_326f": {
        "name": "Individual mandate (require health insurance purchase)",
        "topic": "healthcare",
        "keywords": ["individual mandate", "require insurance", "health insurance mandate"],
        "interpret": _binary_support,
    },

    # --- Environment ---
    "CC24_415c": {
        "name": "Carbon tax on fossil fuels",
        "topic": "environment",
        "keywords": ["carbon tax", "carbon", "fossil fuel", "climate change",
                     "climate", "environment", "emissions", "global warming"],
        "interpret": _carbon_env,
    },
    "CC24_415d": {
        "name": "Require renewable energy production",
        "topic": "environment",
        "keywords": ["renewable", "clean energy", "solar", "wind",
                     "green energy", "renewable mandate"],
        "interpret": _carbon_env,
    },

    # --- Policy grid (CC24_308a) — binary support/oppose ---
    "CC24_308a_1": {
        "name": "Cut federal spending by 5%",
        "topic": "fiscal",
        "keywords": ["cut spending", "reduce spending", "federal budget",
                     "government spending", "austerity"],
        "interpret": _binary_support,
    },
    "CC24_308a_2": {
        "name": "Raise federal minimum wage to $15/hour",
        "topic": "economy",
        "keywords": ["minimum wage", "raise wage", "$15", "living wage"],
        "interpret": _binary_support,
    },
    "CC24_308a_3": {
        "name": "Regulate CO2 as a pollutant",
        "topic": "environment",
        "keywords": ["regulate co2", "co2 pollutant", "epa regulate",
                     "carbon regulation"],
        "interpret": _binary_support,
    },
    "CC24_308a_4": {
        "name": "Raise taxes on income over $400k",
        "topic": "fiscal",
        "keywords": ["raise taxes", "tax the rich", "wealth tax", "income tax",
                     "tax increase", "higher taxes", "taxes on income over",
                     "tax cut"],
        "interpret": _binary_support,
    },
    "CC24_308a_5": {
        "name": "Forgive student loan debt up to $50k",
        "topic": "education",
        "keywords": ["student loan", "student debt", "loan forgiveness",
                     "college debt"],
        "interpret": _binary_support,
    },
}


def match_question(question: str) -> dict | None:
    """Match a free-text question to the best CES column.

    Returns dict with col_id, name, topic, interpret function, or None if
    no CES column covers this question.

    Scoring: count keyword matches weighted by keyword length (longer = more specific).
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
            best_col = {"col_id": col_id, **col}

    return best_col if best_score > 0 else None
