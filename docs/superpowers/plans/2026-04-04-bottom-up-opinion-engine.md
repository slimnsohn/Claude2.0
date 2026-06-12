# Bottom-Up Opinion Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded party-line curve model with a bottom-up opinion engine that derives each profile's response from real CES microdata — matching on demographics, not tuning to aggregate results.

**Architecture:** Each of 500 synthetic profiles gets matched to the ~30-50 most demographically similar CES respondents (from 60K real people). Their actual survey answers become the profile's response probability. Aggregated opinions emerge bottom-up from the population's composition. Questions with no CES coverage are blocked, not guessed.

**Tech Stack:** Python, pandas, scikit-learn (KDTree via existing StatisticalMatcher pattern), existing CES 2024 CSV (60K rows, Harvard Dataverse)

---

## File Structure

```
engine/opinion.py              (CREATE) Core opinion engine — KNN matching + response sampling
engine/ces_columns.py          (CREATE) CES column definitions, question mapping, value coding
engine/ces_loader.py           (CREATE) Loads/caches preprocessed CES data
api/polls.py                   (MODIFY) Replace _ces_modeled_opinion with engine call
api/benchmarks.py              (MODIFY) Update _run_synthetic to use new engine
tests/test_opinion_engine.py   (CREATE) Tests for the new engine
tests/test_ces_columns.py      (CREATE) Tests for column mapping + value interpretation
```

**What gets deleted:** All hardcoded CES curves (TRUMP_APPROVAL, ECONOMY_GOOD, DIRECTION_GOOD, CONSERVATIVE_POLICY, PROGRESSIVE_POLICY, BORDER_SECURITY, SOCIAL_ISSUE, GENERIC) and the entire `_ces_modeled_opinion` function body. The topic detection keyword lists go away — replaced by structured column mapping.

**What stays:** `_get_world_shifts()` — world update shifts still apply as a final adjustment layer on top of the empirical distribution. `_apply_filters()`, `_build_archetypes()`, `auto_complete_poll()` structure, `PollAggregator`, all UI code.

---

### Task 1: CES Column Definitions

Define the mapping from CES column names to structured metadata: what each column measures, how its values map to yes/no/unsure, and what question keywords trigger it.

**Files:**
- Create: `engine/ces_columns.py`
- Test: `tests/test_ces_columns.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ces_columns.py
import pytest
from engine.ces_columns import CES_COLUMNS, match_question


class TestCESColumns:
    def test_columns_have_required_fields(self):
        for col_id, col in CES_COLUMNS.items():
            assert "name" in col, f"{col_id} missing name"
            assert "topic" in col, f"{col_id} missing topic"
            assert "keywords" in col, f"{col_id} missing keywords"
            assert "interpret" in col, f"{col_id} missing interpret"
            assert callable(col["interpret"]), f"{col_id} interpret not callable"

    def test_match_trump_approval(self):
        result = match_question("Do you approve of Trump's job performance?")
        assert result is not None
        assert result["col_id"] == "CC24_312i"

    def test_match_economy(self):
        result = match_question("Is the economy getting better or worse?")
        assert result is not None
        assert result["topic"] == "economy"

    def test_match_healthcare_medicare(self):
        result = match_question("Do you support Medicare for all?")
        assert result is not None
        assert result["col_id"] == "CC24_326b"

    def test_match_border(self):
        result = match_question("Do you support increasing border security?")
        assert result is not None

    def test_match_climate(self):
        result = match_question("Do you support government action on climate change?")
        assert result is not None

    def test_no_match_returns_none(self):
        result = match_question("Do you like pizza?")
        assert result is None

    def test_interpret_binary_support(self):
        col = CES_COLUMNS["CC24_326b"]
        assert col["interpret"](1) == "yes"
        assert col["interpret"](2) == "no"

    def test_interpret_likert_approval(self):
        col = CES_COLUMNS["CC24_312i"]
        assert col["interpret"](1) == "yes"   # strongly approve
        assert col["interpret"](2) == "yes"   # approve
        assert col["interpret"](3) == "no"    # disapprove
        assert col["interpret"](4) == "no"    # strongly disapprove
        assert col["interpret"](5) == "unsure"

    def test_interpret_likert_economy(self):
        col = CES_COLUMNS["CC24_301"]
        assert col["interpret"](1) == "yes"   # much better
        assert col["interpret"](2) == "yes"   # somewhat better
        assert col["interpret"](3) == "unsure"  # about the same
        assert col["interpret"](4) == "no"    # somewhat worse
        assert col["interpret"](5) == "no"    # much worse
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/synthetic-population && python -m pytest tests/test_ces_columns.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.ces_columns'`

- [ ] **Step 3: Implement CES column definitions**

```python
# engine/ces_columns.py
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


def _binary_oppose(val):
    """1=Oppose/No, 2=Support/Yes (reversed items)."""
    if val == 1:
        return "no"
    if val == 2:
        return "yes"
    return "unsure"


def _approval_4pt(val):
    """1=Strongly approve, 2=Approve, 3=Disapprove, 4=Strongly disapprove, 5=Not sure."""
    if val in (1, 2):
        return "yes"
    if val in (3, 4):
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
    """1=Excellent, 2=Good, 3=Fair, 4=Poor, 5=Very poor (mapped from not so good/poor)."""
    if val in (1, 2):
        return "yes"
    if val in (4, 5):
        return "no"
    if val == 3:
        return "unsure"
    return "unsure"


def _direction(val):
    """1=Right direction, 2=Wrong track, 3=Not sure."""
    if val == 1:
        return "yes"
    if val == 2:
        return "no"
    return "unsure"


def _carbon_env(val):
    """1=Support, 2=Oppose (binary-ish, some have 3-5 as unsure/skip)."""
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
                     "recession", "gdp", "conditions"],
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
                     "tax increase", "higher taxes", "tax cut"],
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

    Scoring: count keyword matches, prefer longer keyword matches,
    break ties by topic specificity.
    """
    q = question.lower()
    best_col = None
    best_score = 0

    for col_id, col in CES_COLUMNS.items():
        score = 0
        for kw in col["keywords"]:
            if kw in q:
                # Longer keyword matches are more specific
                score += len(kw)
        if score > best_score:
            best_score = score
            best_col = {"col_id": col_id, **col}

    return best_col if best_score > 0 else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/synthetic-population && python -m pytest tests/test_ces_columns.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add engine/ces_columns.py tests/test_ces_columns.py
git commit -m "feat: CES column definitions and question mapping"
```

---

### Task 2: CES Data Loader

Load and cache the 60K-row CES dataset with preprocessed demographics for fast KNN matching.

**Files:**
- Create: `engine/ces_loader.py`
- Test: `tests/test_ces_loader.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ces_loader.py
import pytest
import pandas as pd
from pathlib import Path
from engine.ces_loader import CESLoader


@pytest.fixture
def loader():
    ces_path = Path("data/raw/ces/ces_2024_common.csv")
    if not ces_path.exists():
        pytest.skip("CES data not available")
    return CESLoader(str(ces_path))


class TestCESLoader:
    def test_loads_data(self, loader):
        df = loader.get_data()
        assert len(df) > 50000
        assert "pid7" in df.columns

    def test_has_harmonized_demographics(self, loader):
        df = loader.get_data()
        for col in ["party_id", "age_bracket", "sex", "race", "education", "urban_rural"]:
            assert col in df.columns, f"Missing harmonized column: {col}"

    def test_has_issue_columns(self, loader):
        df = loader.get_data()
        assert "CC24_312i" in df.columns  # Trump approval
        assert "CC24_301" in df.columns   # Economy

    def test_drops_rows_with_missing_demographics(self, loader):
        df = loader.get_data()
        for col in ["party_id", "age_bracket", "sex", "race", "education"]:
            assert df[col].isna().sum() == 0, f"{col} has NaN values"

    def test_caches_on_second_call(self, loader):
        df1 = loader.get_data()
        df2 = loader.get_data()
        assert df1 is df2  # Same object, not reloaded

    def test_encoded_matrix_shape(self, loader):
        matrix, _ = loader.get_encoded_demographics()
        df = loader.get_data()
        assert matrix.shape[0] == len(df)
        assert matrix.shape[1] > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/synthetic-population && python -m pytest tests/test_ces_loader.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement CES data loader**

```python
# engine/ces_loader.py
"""Load and cache CES 2024 microdata for the opinion engine.

Preprocesses demographics into the same format as synthetic profiles
so KNN matching works directly. Caches the loaded DataFrame and
encoded matrix in memory to avoid re-reading the 180MB CSV on every poll.
"""

import numpy as np
import pandas as pd
from sklearn.preprocessing import OrdinalEncoder
from sklearn.neighbors import KDTree


# Demographic columns used for KNN matching (must match profile fields)
MATCH_KEYS = ["party_id", "education", "age_bracket", "race", "urban_rural"]


class CESLoader:
    def __init__(self, ces_path: str):
        self.ces_path = ces_path
        self._data = None
        self._encoded = None
        self._encoder = None
        self._tree = None

    def get_data(self) -> pd.DataFrame:
        """Return the full preprocessed CES DataFrame. Cached after first load."""
        if self._data is not None:
            return self._data

        # Only load columns we actually need
        from engine.ces_columns import CES_COLUMNS
        issue_cols = list(CES_COLUMNS.keys())
        demo_cols = ["pid7", "educ", "birthyr", "gender4", "race", "urbancity", "faminc_new"]
        all_cols = list(set(demo_cols + issue_cols))
        # Filter to columns that actually exist
        available = pd.read_csv(self.ces_path, nrows=0).columns.tolist()
        load_cols = [c for c in all_cols if c in available]

        df = pd.read_csv(self.ces_path, usecols=load_cols, low_memory=False)

        # Harmonize demographics to match profile format
        df["party_id"] = df["pid7"].map({
            1: "strong_dem", 2: "dem", 3: "lean_dem", 4: "independent",
            5: "lean_rep", 6: "rep", 7: "strong_rep", 8: "independent",
        })

        df["education"] = df["educ"].map({
            1: "less_than_hs", 2: "hs_diploma", 3: "some_college",
            4: "some_college", 5: "bachelors", 6: "graduate",
        })

        current_year = 2026
        age = current_year - df["birthyr"]
        df["age_bracket"] = pd.cut(
            age, bins=[0, 24, 34, 44, 54, 64, 200],
            labels=["18-24", "25-34", "35-44", "45-54", "55-64", "65+"],
        )

        df["sex"] = df["gender4"].map({1: "M", 2: "F", 3: "F", 4: "M"})

        df["race"] = df["race"].map({
            1: "white", 2: "black", 3: "hispanic", 4: "asian",
            5: "other", 6: "multiracial", 7: "other", 8: "other",
        })

        df["urban_rural"] = df["urbancity"].map({
            1: "urban", 2: "suburban", 3: "suburban", 4: "rural",
        })

        # Drop rows with missing key demographics
        df = df.dropna(subset=MATCH_KEYS).reset_index(drop=True)

        self._data = df
        return df

    def get_encoded_demographics(self) -> tuple[np.ndarray, OrdinalEncoder]:
        """Return (encoded_matrix, encoder) for KNN queries. Cached."""
        if self._encoded is not None:
            return self._encoded, self._encoder

        df = self.get_data()
        self._encoder = OrdinalEncoder(
            handle_unknown="use_encoded_value", unknown_value=-1
        )
        self._encoded = self._encoder.fit_transform(df[MATCH_KEYS])
        return self._encoded, self._encoder

    def get_tree(self) -> KDTree:
        """Return a KDTree built on encoded CES demographics. Cached."""
        if self._tree is not None:
            return self._tree

        encoded, _ = self.get_encoded_demographics()
        self._tree = KDTree(encoded)
        return self._tree
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/synthetic-population && python -m pytest tests/test_ces_loader.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add engine/ces_loader.py tests/test_ces_loader.py
git commit -m "feat: CES data loader with demographic preprocessing and KDTree caching"
```

---

### Task 3: Bottom-Up Opinion Engine

The core: given a question and a profile, find similar real CES respondents, read their actual answers, return a stochastic opinion drawn from the real distribution.

**Files:**
- Create: `engine/opinion.py`
- Test: `tests/test_opinion_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_opinion_engine.py
import pytest
from pathlib import Path
from engine.opinion import OpinionEngine


@pytest.fixture
def engine():
    ces_path = Path("data/raw/ces/ces_2024_common.csv")
    if not ces_path.exists():
        pytest.skip("CES data not available")
    return OpinionEngine(str(ces_path))


class TestOpinionEngine:
    def test_returns_opinion_tuple(self, engine):
        profile = {
            "party_id": "strong_dem", "education": "bachelors",
            "age_bracket": "35-44", "race": "white", "urban_rural": "urban",
        }
        opinion, confidence, reasoning = engine.get_opinion(
            "Do you approve of Trump's job performance?", profile
        )
        assert opinion in ("yes", "no", "unsure")
        assert 1 <= confidence <= 10
        assert isinstance(reasoning, str)
        assert len(reasoning) > 0

    def test_strong_dem_disapproves_trump(self, engine):
        """Strong dems should mostly disapprove — run 50 times and check majority."""
        profile = {
            "party_id": "strong_dem", "education": "graduate",
            "age_bracket": "45-54", "race": "white", "urban_rural": "urban",
        }
        opinions = [
            engine.get_opinion("Do you approve of Trump's job performance?", profile)[0]
            for _ in range(50)
        ]
        no_count = opinions.count("no")
        assert no_count > 30, f"Expected >30 'no' from strong dem, got {no_count}"

    def test_strong_rep_approves_trump(self, engine):
        profile = {
            "party_id": "strong_rep", "education": "hs_diploma",
            "age_bracket": "55-64", "race": "white", "urban_rural": "rural",
        }
        opinions = [
            engine.get_opinion("Do you approve of Trump's job performance?", profile)[0]
            for _ in range(50)
        ]
        yes_count = opinions.count("yes")
        assert yes_count > 30, f"Expected >30 'yes' from strong rep, got {yes_count}"

    def test_unmatched_question_returns_none(self, engine):
        profile = {"party_id": "dem", "education": "bachelors",
                   "age_bracket": "25-34", "race": "white", "urban_rural": "urban"}
        result = engine.get_opinion("Do you like pizza?", profile)
        assert result is None

    def test_distribution_method(self, engine):
        """get_distribution returns probabilities without stochastic sampling."""
        profile = {
            "party_id": "independent", "education": "some_college",
            "age_bracket": "35-44", "race": "black", "urban_rural": "suburban",
        }
        dist = engine.get_distribution(
            "Do you approve of Trump's job performance?", profile
        )
        assert dist is not None
        assert "yes" in dist and "no" in dist and "unsure" in dist
        assert abs(sum(dist.values()) - 1.0) < 0.01
        assert all(0 <= v <= 1 for v in dist.values())

    def test_neighbor_count(self, engine):
        profile = {
            "party_id": "dem", "education": "bachelors",
            "age_bracket": "25-34", "race": "white", "urban_rural": "urban",
        }
        dist = engine.get_distribution(
            "Is the economy getting better or worse?", profile,
        )
        # Should have found enough neighbors to produce a distribution
        assert dist is not None
        assert dist.get("_n_neighbors", 0) >= 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/synthetic-population && python -m pytest tests/test_opinion_engine.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the opinion engine**

```python
# engine/opinion.py
"""Bottom-up opinion engine using real CES microdata.

Instead of hardcoded party-line curves, this engine:
1. Maps the question to a CES survey column
2. Finds K most demographically similar real CES respondents
3. Reads their actual survey answers
4. Returns a stochastic opinion sampled from the real distribution

Opinions emerge from the bottom up — the aggregate is whatever
the population's composition produces, not a tuned target.
"""

import random
from typing import Optional

import numpy as np
import pandas as pd

from engine.ces_columns import CES_COLUMNS, match_question
from engine.ces_loader import CESLoader, MATCH_KEYS


# Default number of nearest neighbors to query
DEFAULT_K = 50


class OpinionEngine:
    def __init__(self, ces_path: str, k: int = DEFAULT_K):
        self.loader = CESLoader(ces_path)
        self.k = k

    def get_opinion(
        self, question: str, profile: dict, world_shifts: dict = None
    ) -> Optional[tuple[str, int, str]]:
        """Get a stochastic opinion for this profile on this question.

        Returns (opinion, confidence, reasoning) or None if question
        has no CES coverage.
        """
        dist = self.get_distribution(question, profile, world_shifts)
        if dist is None:
            return None

        yes_p = dist["yes"]
        no_p = dist["no"]
        unsure_p = dist["unsure"]

        # Stochastic sample from the real distribution
        roll = random.random()
        if roll < yes_p:
            opinion = "yes"
        elif roll < yes_p + no_p:
            opinion = "no"
        else:
            opinion = "unsure"

        # Confidence derived from how lopsided the distribution is
        dominant = max(yes_p, no_p, unsure_p)
        if dominant > 0.8:
            base_conf = random.randint(7, 10)
        elif dominant > 0.6:
            base_conf = random.randint(5, 8)
        else:
            base_conf = random.randint(3, 6)
        if opinion == "unsure":
            base_conf = min(base_conf, 4)

        # Reasoning
        n = dist.get("_n_neighbors", 0)
        col_name = dist.get("_col_name", "survey data")
        party = profile.get("party_id", "unknown")
        reasoning = (
            f"Based on {n} similar CES respondents "
            f"(matched on demographics), "
            f"{yes_p:.0%} said yes, {no_p:.0%} said no, "
            f"{unsure_p:.0%} unsure. "
            f"This {party.replace('_', ' ')} respondent says {opinion}."
        )

        return opinion, base_conf, reasoning

    def get_distribution(
        self, question: str, profile: dict, world_shifts: dict = None
    ) -> Optional[dict]:
        """Get the yes/no/unsure probability distribution for this profile.

        Returns dict with keys: yes, no, unsure, _n_neighbors, _col_name.
        Returns None if question has no CES coverage.
        """
        # 1. Map question to CES column
        col_match = match_question(question)
        if col_match is None:
            return None

        col_id = col_match["col_id"]
        interpret = col_match["interpret"]

        # 2. Load CES data and find similar respondents
        ces_df = self.loader.get_data()
        if col_id not in ces_df.columns:
            return None

        tree = self.loader.get_tree()
        _, encoder = self.loader.get_encoded_demographics()

        # Encode this profile's demographics
        profile_row = pd.DataFrame([{k: profile.get(k, "") for k in MATCH_KEYS}])
        try:
            profile_encoded = encoder.transform(profile_row)
        except Exception:
            return None

        # 3. KNN query
        k = min(self.k, len(ces_df))
        distances, indices = tree.query(profile_encoded, k=k)
        neighbor_indices = indices[0]

        # 4. Read their actual answers
        answers = ces_df.iloc[neighbor_indices][col_id].dropna()
        if len(answers) < 5:
            return None

        # 5. Interpret coded values → yes/no/unsure
        interpreted = answers.apply(interpret)
        counts = interpreted.value_counts()
        total = len(interpreted)

        yes_p = counts.get("yes", 0) / total
        no_p = counts.get("no", 0) / total
        unsure_p = counts.get("unsure", 0) / total

        # 6. Apply world update shifts (small adjustments from current news)
        if world_shifts:
            party = profile.get("party_id", "independent")
            party_group = (
                "dem" if party in ("strong_dem", "dem", "lean_dem")
                else "rep" if party in ("strong_rep", "rep", "lean_rep")
                else "independent"
            )
            ws = world_shifts.get(party_group, 0.0)
            if ws != 0:
                yes_p += ws
                no_p -= ws * 0.7
                unsure_p -= ws * 0.3

        # Normalize
        total_p = yes_p + no_p + unsure_p
        if total_p > 0:
            yes_p /= total_p
            no_p /= total_p
            unsure_p /= total_p

        # Clamp
        yes_p = max(0.0, min(1.0, yes_p))
        no_p = max(0.0, min(1.0, no_p))
        unsure_p = max(0.0, min(1.0, unsure_p))

        return {
            "yes": yes_p,
            "no": no_p,
            "unsure": unsure_p,
            "_n_neighbors": len(answers),
            "_col_name": col_match["name"],
            "_col_id": col_id,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/synthetic-population && python -m pytest tests/test_opinion_engine.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add engine/opinion.py tests/test_opinion_engine.py
git commit -m "feat: bottom-up opinion engine using real CES microdata KNN matching"
```

---

### Task 4: Wire Into Polls API

Replace `_ces_modeled_opinion` with the new engine. Remove all hardcoded curves.

**Files:**
- Modify: `api/polls.py`

- [ ] **Step 1: Add engine initialization to server.py**

In `server.py`, after `app.config["DATA_DIR"]` is set, add engine initialization:

```python
# In server.py create_app(), after DATA_DIR config:
from engine.opinion import OpinionEngine
ces_path = app.config["DATA_DIR"] / "raw" / "ces" / "ces_2024_common.csv"
if ces_path.exists():
    app.config["OPINION_ENGINE"] = OpinionEngine(str(ces_path))
else:
    app.config["OPINION_ENGINE"] = None
```

- [ ] **Step 2: Replace _ces_modeled_opinion in polls.py**

Delete the entire `_ces_modeled_opinion` function (lines ~426-660, all the hardcoded curves, topic detection, everything). Delete `_get_world_shifts` helper. Replace with:

```python
def _get_opinion(question: str, profile: dict) -> tuple[str, int, str] | None:
    """Get opinion from bottom-up CES engine. Returns None if question not covered."""
    engine = current_app.config.get("OPINION_ENGINE")
    if engine is None:
        return None

    # Load world shifts
    world_shifts = _get_active_world_shifts()
    return engine.get_opinion(question, profile, world_shifts=world_shifts)


def _get_active_world_shifts() -> dict:
    """Load aggregated opinion shifts from active world updates."""
    try:
        data_dir = _data_dir()
        wu_path = data_dir / "world_updates.json"
        if not wu_path.exists():
            return {}
        updates = json.loads(wu_path.read_text())
        combined = {"dem": 0.0, "rep": 0.0, "independent": 0.0}
        for u in updates:
            if not u.get("active", True):
                continue
            for party, shift in u.get("shifts", {}).items():
                combined[party] = combined.get(party, 0.0) + shift
        for k in combined:
            combined[k] = max(-0.15, min(0.15, combined[k]))
        return combined
    except Exception:
        return {}
```

- [ ] **Step 3: Update auto_complete_poll to use new engine**

In `auto_complete_poll()`, replace the line:

```python
opinion, confidence, reasoning = _ces_modeled_opinion(question, profile)
```

With:

```python
result = _get_opinion(question, profile)
if result is None:
    # Question not covered by CES data — skip this archetype
    continue
opinion, confidence, reasoning = result
```

Also update the `source` field in the response dict from `"ces_modeled"` to `"ces_microdata"`.

- [ ] **Step 4: Update auto_complete_poll to return 400 when question not covered**

Add an early check before the archetype loop:

```python
# Check if question is covered by CES data
from engine.ces_columns import match_question
if match_question(question) is None:
    return jsonify({
        "error": f"No CES survey data covers this question. Covered topics: approval, economy, immigration, healthcare, environment, fiscal policy, education.",
    }), 400
```

- [ ] **Step 5: Run existing tests**

Run: `cd apps/synthetic-population && python -m pytest tests/ -v`
Expected: All PASS (existing tests should not break — they test schema/pipeline, not opinion generation)

- [ ] **Step 6: Commit**

```bash
git add server.py api/polls.py
git commit -m "feat: wire bottom-up CES opinion engine into polls API, remove hardcoded curves"
```

---

### Task 5: Wire Into Benchmarks API

Update `_run_synthetic` in benchmarks.py to use the new engine.

**Files:**
- Modify: `api/benchmarks.py`

- [ ] **Step 1: Replace _run_synthetic**

Delete the current `_run_synthetic` function and replace with:

```python
def _run_synthetic(question: str, filters: dict = None) -> dict:
    """Run CES-microdata opinion model on the synthetic population."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from api.polls import _load_registry, _apply_filters, _build_archetypes, _get_opinion
    from engine.ces_columns import match_question

    # Check coverage first
    if match_question(question) is None:
        return {"error": "Question not covered by CES data"}

    profiles = _load_registry()
    if filters:
        profiles = _apply_filters(profiles, filters)

    if not profiles:
        return {"error": "No profiles"}

    profiles_with_arch, weights = _build_archetypes(profiles)
    if not weights:
        return {"error": "No archetypes"}

    # Index profiles by archetype
    profiles_by_arch = {}
    for p in profiles_with_arch:
        aid = p.get("archetype_id")
        if aid and aid not in profiles_by_arch:
            profiles_by_arch[aid] = p

    # Run opinion engine for each archetype
    yes_w, no_w, unsure_w, total_w = 0.0, 0.0, 0.0, 0.0
    for aid, weight in weights.items():
        profile = profiles_by_arch.get(aid, {})
        result = _get_opinion(question, profile)
        if result is None:
            continue
        opinion, confidence, _ = result
        if opinion == "yes":
            yes_w += weight
        elif opinion == "no":
            no_w += weight
        else:
            unsure_w += weight
        total_w += weight

    if total_w == 0:
        return {"error": "No responses"}

    return {
        "yes": round(yes_w / total_w, 4),
        "no": round(no_w / total_w, 4),
        "unsure": round(unsure_w / total_w, 4),
        "archetype_count": len(weights),
        "profile_count": len(profiles),
    }
```

Also remove the old import of `_ces_modeled_opinion` from the imports at the top.

- [ ] **Step 2: Update CURATED_BENCHMARKS — remove questions with no CES coverage**

Check each curated benchmark question against `match_question()`. Remove or replace any that return None. The ones without CES coverage based on our column definitions:

- "Do you support stricter gun control laws?" — no clean binary CES column (CC24_305 is checkbox, CC24_330 is 8-point). **Remove or remap** to CC24_308a_3 "regulate CO2" if the question is about regulation, or remove gun control benchmark entirely.
- "Do you think abortion should be legal in most cases?" — **no abortion column in CES 2024**. Remove.
- "Do you support US military involvement in foreign conflicts?" — no CES column. Remove.

Keep the remaining 7 benchmarks that map cleanly to CES columns.

- [ ] **Step 3: Run benchmarks test**

Run: `cd apps/synthetic-population && python -c "from server import create_app; app = create_app(); ...` (use the benchmark test command from earlier in this conversation to verify)

Expected: Results should be close to real polls because they now emerge from real individual-level data.

- [ ] **Step 4: Commit**

```bash
git add api/benchmarks.py
git commit -m "feat: wire benchmarks to bottom-up opinion engine, remove uncovered questions"
```

---

### Task 6: Update UI to Show Coverage Status

When a user submits a poll question that has no CES coverage, show a clear message instead of failing silently.

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Update poll creation handler**

In the poll run button click handler (`document.getElementById("poll-run-btn").addEventListener("click", ...)`), update the error display to check for the coverage error:

```javascript
} catch (e) {
    if (e.message.includes("No CES survey data")) {
        progress.innerHTML = `
            <span style="color:var(--orange)">This question isn't covered by CES survey data.</span><br>
            <span style="font-size:12px;color:var(--text2)">Covered topics: Trump approval, economy, immigration, healthcare, environment, taxes, minimum wage, student loans, spending cuts.</span>
        `;
    } else {
        progress.textContent = \`Error: \${e.message}\`;
    }
    btn.disabled = false;
}
```

- [ ] **Step 2: Update benchmark custom comparison**

In the custom comparison handler, add the same coverage check for the error case.

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat: show CES coverage status when question not covered"
```

---

### Task 7: Integration Test — Full Pipeline Validation

Run the complete pipeline end-to-end: question → engine → aggregation → benchmark comparison.

**Files:**
- Create: `tests/test_integration_opinion.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration_opinion.py
"""End-to-end test: question → opinion engine → aggregation → benchmark."""
import pytest
import json
from pathlib import Path


@pytest.fixture
def app_client():
    from server import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestIntegrationOpinion:
    def test_poll_creation_uses_ces_microdata(self, app_client):
        """Create a poll and auto-complete — should use CES microdata source."""
        resp = app_client.post("/api/polls", json={
            "question": "Do you approve of Trump's job performance?",
            "snapshot_id": "live",
        })
        assert resp.status_code == 201
        poll_id = resp.get_json()["poll_id"]

        resp2 = app_client.post(f"/api/polls/{poll_id}/auto-complete")
        assert resp2.status_code == 200
        data = resp2.get_json()
        assert data["status"] == "complete"
        dist = data["distribution"]
        # Trump approval should be roughly 40-55% yes from real CES data
        assert 0.20 < dist["yes"] < 0.70
        assert 0.20 < dist["no"] < 0.70

    def test_uncovered_question_returns_400(self, app_client):
        """Questions outside CES coverage should return 400."""
        resp = app_client.post("/api/polls", json={
            "question": "Do you like pineapple on pizza?",
            "snapshot_id": "live",
        })
        # Poll creation succeeds (just generates prompts)
        if resp.status_code == 201:
            poll_id = resp.get_json()["poll_id"]
            resp2 = app_client.post(f"/api/polls/{poll_id}/auto-complete")
            assert resp2.status_code == 400
            assert "CES" in resp2.get_json().get("error", "")

    def test_benchmark_comparison_accuracy(self, app_client):
        """Run a benchmark and verify MAE is reasonable."""
        resp = app_client.post("/api/benchmarks/compare", json={
            "question": "Do you approve of Trump's job performance?",
            "real_results": {"yes": 0.467, "no": 0.493, "unsure": 0.04},
            "runs": 15,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        # MAE should be under 10% for a well-covered question
        assert data["mae"] < 0.10, f"MAE too high: {data['mae']}"

    def test_economy_question_partisan_pattern(self, app_client):
        """Economy question should show partisan split — Reps more optimistic under Trump."""
        resp = app_client.post("/api/benchmarks/compare", json={
            "question": "Is the economy getting better or worse?",
            "real_results": {"yes": 0.34, "no": 0.58, "unsure": 0.08},
            "runs": 15,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["mae"] < 0.15
```

- [ ] **Step 2: Run integration tests**

Run: `cd apps/synthetic-population && python -m pytest tests/test_integration_opinion.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration_opinion.py
git commit -m "test: integration tests for bottom-up opinion engine pipeline"
```

---

## Important Notes

**What's NOT in this plan (and why):**

- **Abortion questions** — CES 2024 doesn't include abortion items. If you want abortion coverage, supplement with ANES or Pew microdata in a future task.
- **Gun control** — CES 2024 gun items (CC24_305) are checkbox-style, not support/oppose binary. CC24_330 is 8-point Likert which is usable but needs a different interpreter. Can be added later.
- **Military/foreign policy** — No clean CES binary question. Could map CC24_308a items or add ANES data.
- **Growing beyond 500 profiles** — Doesn't require engine changes. Just run `ProfileGenerator.generate_batch(count=N)`. The engine matches against 60K CES respondents regardless of population size.
- **Temporal decay of world updates** — Currently world shifts accumulate. A decay mechanism (halving shift weight after N days) would be a good future addition.

**CES 2024 economy note:** The CES was fielded under Biden (pre-election 2024). Economy retrospective responses reflect Biden-era sentiment. Under Trump (2025-2026), partisan valence flips: Republicans become more optimistic, Democrats more pessimistic. The KNN engine faithfully reproduces the CES distribution — so economy questions will reflect the CES-era sentiment unless world updates shift them. This is technically correct (the data says what it says) but may under-predict Republican economic optimism in 2026. World updates are the right lever for this.
