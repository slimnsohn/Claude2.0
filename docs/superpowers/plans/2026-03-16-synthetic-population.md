# Synthetic Population Engine Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a synthetic population engine that generates statistically realistic AI individuals from public census/survey data for opinion simulation, prediction market analysis, and complex topic reasoning.

**Architecture:** Four-component pipeline: (1) plugin-based data pipeline that fuses ACS PUMS + survey datasets into a correlation-preserving synthesis model, (2) incremental profile generator with dedup and gap analysis, (3) archetype-based opinion engine with conviction-anchored LLM prompting via Claude Max, (4) event monitor with bounded drift. All backend in Python, JSON storage, CLI-first.

**Tech Stack:** Python 3.11+, pandas, sdv (Synthetic Data Vault), scipy, scikit-learn, pytest, JSON file storage

**Spec:** `docs/superpowers/specs/2026-03-16-synthetic-population-design.md`

---

## File Structure

```
apps/synthetic-population/
├── CLAUDE.md                          # Project overview (from template)
├── TODO.md                            # Task tracker (from template)
├── start.bat                          # Launch script (from template)
├── requirements.txt                   # Python dependencies
├── conftest.py                        # Shared pytest fixtures
│
├── schema/
│   ├── __init__.py
│   ├── standard.py                    # Standard variable schema definitions + enums
│   └── validation.py                  # Schema validation functions
│
├── pipeline/
│   ├── __init__.py
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── base.py                    # DataSource ABC + harmonize base logic
│   │   ├── acs_pums.py               # ACS PUMS source plugin
│   │   ├── ces.py                     # Cooperative Election Study plugin
│   │   ├── anes.py                    # American National Election Studies plugin
│   │   ├── gss.py                     # General Social Survey plugin
│   │   ├── pew_atp.py                # Pew American Trends Panel plugin
│   │   ├── brfss.py                   # CDC BRFSS plugin
│   │   ├── cps.py                     # Current Population Survey plugin
│   │   ├── finra_nfcs.py             # FINRA Financial Capability plugin
│   │   └── fed_scf.py                # Federal Reserve SCF plugin
│   ├── registry.py                    # Source registration + discovery
│   ├── fuse.py                        # Statistical matching across sources
│   ├── fit_model.py                   # Train SDV GaussianCopulaSynthesizer
│   └── calibrate.py                   # IPF calibration against census marginals
│
├── generator/
│   ├── __init__.py
│   ├── generate.py                    # CLI entry point: --count N --batch-name X
│   ├── dedup.py                       # Composite-key uniqueness checking
│   ├── gap_analysis.py                # Population vs marginal comparison
│   ├── backstory.py                   # Template-based narrative generation
│   └── archetypes.py                  # K-means clustering + archetype assignment
│
├── engine/
│   ├── __init__.py
│   ├── poll.py                        # Polling flow: select archetypes → build prompts → collect → aggregate
│   ├── prompts.py                     # Prompt templates with conviction anchoring
│   ├── aggregate.py                   # Weighted aggregation + confidence intervals
│   └── integrity.py                   # Hedge detection + consistency checks
│
├── monitor/
│   ├── __init__.py
│   ├── events.py                      # Event ingestion + tagging
│   └── drift.py                       # Bounded drift application to profiles
│
├── data/                              # Generated data (gitignored)
│   ├── models/                        # Fitted synthesizer models
│   ├── profiles/                      # Master registry JSON
│   ├── events/                        # Event log
│   └── polls/                         # Poll results archive
│
└── tests/
    ├── __init__.py
    ├── test_schema.py                 # Schema definitions + validation
    ├── test_source_base.py            # DataSource ABC contract tests
    ├── test_acs_pums.py               # ACS PUMS harmonization
    ├── test_ces.py                    # CES harmonization
    ├── test_registry.py               # Source registration
    ├── test_fuse.py                   # Statistical matching
    ├── test_fit_model.py              # Synthesizer training
    ├── test_calibrate.py              # IPF calibration
    ├── test_generate.py               # Profile generation + CLI
    ├── test_dedup.py                  # Dedup logic
    ├── test_gap_analysis.py           # Gap detection
    ├── test_backstory.py              # Narrative generation
    ├── test_archetypes.py             # Clustering
    ├── test_prompts.py                # Prompt construction
    ├── test_aggregate.py              # Weighted aggregation
    ├── test_integrity.py              # Hedge detection
    ├── test_poll.py                   # Full polling flow
    ├── test_events.py                 # Event ingestion
    └── test_drift.py                  # Drift application
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `apps/synthetic-population/CLAUDE.md` (from template)
- Create: `apps/synthetic-population/TODO.md` (from template)
- Create: `apps/synthetic-population/start.bat` (from template)
- Create: `apps/synthetic-population/requirements.txt`
- Create: `apps/synthetic-population/conftest.py`
- Create: `apps/synthetic-population/.gitignore`
- Modify: `workspace.json` (add project entry)

- [ ] **Step 1: Create project directory**

```bash
mkdir -p apps/synthetic-population
```

- [ ] **Step 2: Copy and fill CLAUDE.md template**

Fill placeholders:
- `{PROJECT_NAME}`: Synthetic Population Engine
- `{PROJECT_DESCRIPTION}`: Generates statistically realistic AI individuals from census/survey data for opinion simulation
- `{TECH_STACK}`: Python, pandas, SDV, scipy, scikit-learn

- [ ] **Step 3: Copy and fill TODO.md template**

Fill placeholders:
- `{PROJECT_NAME}`: Synthetic Population Engine
- `{FIRST_TASK}`: Build standard schema and validation

- [ ] **Step 4: Create requirements.txt**

```
pandas>=2.0
sdv>=1.10
scipy>=1.11
scikit-learn>=1.3
pytest>=7.4
requests>=2.31
```

- [ ] **Step 5: Create conftest.py with shared fixtures**

```python
import pytest
import pandas as pd
from pathlib import Path

@pytest.fixture
def sample_demographics():
    """Minimal demographic records for testing."""
    return pd.DataFrame({
        "age": [34, 52, 28, 67, 41],
        "sex": ["M", "F", "F", "M", "F"],
        "race": ["white", "white", "black", "hispanic", "asian"],
        "education": ["some_college", "bachelors", "graduate", "hs_diploma", "bachelors"],
        "income_bracket": ["50-75k", "50-75k", "75-100k", "25-50k", "100-150k"],
        "marital_status": ["married", "married", "never_married", "widowed", "married"],
        "state": ["MI", "OH", "GA", "TX", "CA"],
        "urban_rural": ["rural", "suburban", "urban", "rural", "urban"],
        "party_id": ["lean_rep", "lean_rep", "strong_dem", "dem", "lean_dem"],
        "religion_affiliation": ["evangelical", "mainline", "none", "catholic", "none"],
        "religion_attendance": ["weekly", "monthly", "never", "weekly", "never"],
    })

@pytest.fixture
def data_dir(tmp_path):
    """Temporary data directory structure."""
    for subdir in ["models", "profiles", "events", "polls"]:
        (tmp_path / subdir).mkdir()
    return tmp_path
```

- [ ] **Step 6: Create .gitignore**

```
data/models/
data/profiles/
data/events/
data/polls/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 7: Add project to workspace.json**

Add entry:
```json
{
  "name": "synthetic-population",
  "type": "PYTHON_CLI",
  "location": "apps/synthetic-population",
  "status": "in-development",
  "description": "Synthetic population engine for AI opinion simulation",
  "created": "2026-03-16"
}
```

- [ ] **Step 8: Create empty __init__.py files for all packages**

```bash
touch apps/synthetic-population/schema/__init__.py
touch apps/synthetic-population/pipeline/__init__.py
touch apps/synthetic-population/pipeline/sources/__init__.py
touch apps/synthetic-population/generator/__init__.py
touch apps/synthetic-population/engine/__init__.py
touch apps/synthetic-population/monitor/__init__.py
touch apps/synthetic-population/tests/__init__.py
```

- [ ] **Step 9: Run pytest to verify empty test suite passes**

Run: `cd apps/synthetic-population && python -m pytest --co -q`
Expected: "no tests ran"

- [ ] **Step 10: Commit checkpoint**

```bash
git add apps/synthetic-population/
git commit -m "scaffold: synthetic-population project structure"
```

---

## Task 2: Standard Schema & Validation

**Files:**
- Create: `apps/synthetic-population/schema/standard.py`
- Create: `apps/synthetic-population/schema/validation.py`
- Create: `apps/synthetic-population/tests/test_schema.py`

This defines all 142 variables, their types, allowed values, and validation logic. Everything downstream depends on this.

- [ ] **Step 1: Write failing tests for schema definitions**

```python
# tests/test_schema.py
from schema.standard import (
    STANDARD_SCHEMA, DEMOGRAPHICS, SOCIOECONOMICS, ECONOMIC_IDENTITY,
    FINANCIAL_BEHAVIOR, FINANCIAL_SOPHISTICATION, GEOGRAPHY, POLITICAL,
    POLICY_POSITIONS, PSYCHOLOGY, RELIGION, MEDIA_DIET, SCIENCE_HEALTH,
    ORIGIN_MOBILITY, SYSTEM_METADATA
)
from schema.validation import validate_profile, ValidationError

def test_schema_has_all_categories():
    categories = [
        DEMOGRAPHICS, SOCIOECONOMICS, ECONOMIC_IDENTITY, FINANCIAL_BEHAVIOR,
        FINANCIAL_SOPHISTICATION, GEOGRAPHY, POLITICAL, POLICY_POSITIONS,
        PSYCHOLOGY, RELIGION, MEDIA_DIET, SCIENCE_HEALTH, ORIGIN_MOBILITY,
        SYSTEM_METADATA
    ]
    total = sum(len(c) for c in categories)
    assert total >= 142, f"Expected 142+ variables, got {total}"

def test_each_variable_has_type_and_allowed_values():
    for name, spec in STANDARD_SCHEMA.items():
        assert "type" in spec, f"{name} missing type"
        assert spec["type"] in ("str", "int", "float", "bool"), f"{name} has invalid type"
        if spec["type"] == "str":
            assert "values" in spec, f"{name} (str) missing allowed values"

def test_validate_profile_accepts_valid():
    profile = {
        "age": 34, "sex": "M", "race": "white", "education": "some_college",
        "state": "MI", "party_id": "lean_rep", "urban_rural": "rural",
        "religion_affiliation": "evangelical", "religion_attendance": "weekly",
        "income_bracket": "50-75k", "marital_status": "married",
    }
    errors = validate_profile(profile, partial=True)
    assert errors == []

def test_validate_profile_rejects_invalid_values():
    profile = {"sex": "X", "race": "martian"}
    errors = validate_profile(profile, partial=True)
    assert len(errors) == 2

def test_validate_profile_rejects_wrong_type():
    profile = {"age": "thirty-four"}
    errors = validate_profile(profile, partial=True)
    assert len(errors) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/synthetic-population && python -m pytest tests/test_schema.py -v`
Expected: FAIL — imports don't exist yet

- [ ] **Step 3: Implement schema/standard.py**

Define all 14 categories with every variable, its type, and allowed values. Each category is a dict of `{variable_name: {"type": str, "values": [...], "description": str}}`. `STANDARD_SCHEMA` is the merged dict of all categories.

Key categories and their variables:

```python
DEMOGRAPHICS = {
    "age": {"type": "int", "range": [18, 99], "description": "Age in years"},
    "age_bracket": {"type": "str", "values": ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]},
    "sex": {"type": "str", "values": ["M", "F"]},
    "race": {"type": "str", "values": ["white", "black", "hispanic", "asian", "other", "multiracial"]},
    "education": {"type": "str", "values": ["less_than_hs", "hs_diploma", "some_college", "bachelors", "graduate"]},
    "marital_status": {"type": "str", "values": ["married", "divorced", "widowed", "separated", "never_married"]},
    "children_count": {"type": "int", "range": [0, 10]},
    "citizenship": {"type": "str", "values": ["us_born", "naturalized", "permanent_resident", "non_citizen"]},
    "veteran_status": {"type": "bool"},
    "disability": {"type": "bool"},
    "language": {"type": "str", "values": ["english_only", "spanish", "other", "bilingual_english_spanish"]},
    "household_size": {"type": "int", "range": [1, 10]},
    "generation": {"type": "str", "values": ["silent", "boomer", "gen_x", "millennial", "gen_z"]},
}
# ... (all 14 categories following same pattern)

STANDARD_SCHEMA = {**DEMOGRAPHICS, **SOCIOECONOMICS, **ECONOMIC_IDENTITY, ...}
```

Full implementation should define every variable from the spec's 142 list with exact allowed values.

- [ ] **Step 4: Implement schema/validation.py**

```python
from schema.standard import STANDARD_SCHEMA

class ValidationError:
    def __init__(self, field, message):
        self.field = field
        self.message = message
    def __repr__(self):
        return f"ValidationError({self.field}: {self.message})"

def validate_profile(profile: dict, partial: bool = False) -> list[ValidationError]:
    """Validate a profile dict against the standard schema.
    If partial=True, only validate fields that are present.
    If partial=False, also flag missing required fields.
    """
    errors = []
    for field, value in profile.items():
        if field not in STANDARD_SCHEMA:
            continue  # custom namespaced fields pass through
        spec = STANDARD_SCHEMA[field]
        if spec["type"] == "str" and value not in spec["values"]:
            errors.append(ValidationError(field, f"'{value}' not in {spec['values']}"))
        elif spec["type"] == "int" and not isinstance(value, int):
            errors.append(ValidationError(field, f"expected int, got {type(value).__name__}"))
        elif spec["type"] == "float" and not isinstance(value, (int, float)):
            errors.append(ValidationError(field, f"expected float, got {type(value).__name__}"))
        elif spec["type"] == "bool" and not isinstance(value, bool):
            errors.append(ValidationError(field, f"expected bool, got {type(value).__name__}"))
        # Range check for int/float
        if spec["type"] in ("int", "float") and "range" in spec:
            lo, hi = spec["range"]
            if isinstance(value, (int, float)) and not (lo <= value <= hi):
                errors.append(ValidationError(field, f"{value} not in range [{lo}, {hi}]"))
    return errors
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/synthetic-population && python -m pytest tests/test_schema.py -v`
Expected: All 5 tests PASS

- [ ] **Step 6: Commit checkpoint**

```bash
git add apps/synthetic-population/schema/ apps/synthetic-population/tests/test_schema.py
git commit -m "feat: standard schema with 142 variables and validation"
```

---

## Task 3: Data Source Base Class & Plugin Interface

**Files:**
- Create: `apps/synthetic-population/pipeline/sources/base.py`
- Create: `apps/synthetic-population/tests/test_source_base.py`

- [ ] **Step 1: Write failing tests for the DataSource ABC**

```python
# tests/test_source_base.py
import pytest
import pandas as pd
from pipeline.sources.base import DataSource

class FakeSource(DataSource):
    name = "fake"
    variables_provided = ["party_id", "ideology"]
    match_keys = ["age_bracket", "sex", "race", "education"]
    update_cycle = "annual"
    standard_column_map = {"party_id": "pid", "ideology": "ideo"}
    variable_maps = {
        "party_id": {1: "strong_dem", 2: "dem", 3: "lean_dem", 4: "independent",
                     5: "lean_rep", 6: "rep", 7: "strong_rep"},
    }
    custom_columns = {"approval_rating": "approve"}

    def download(self): return "fake_path"
    def clean(self, raw_path): return pd.DataFrame({"pid": [1,7], "ideo": [2,6], "approve": [45,80]})

def test_abc_requires_methods():
    with pytest.raises(TypeError):
        DataSource()

def test_harmonize_maps_standard_variables():
    source = FakeSource()
    raw = source.clean("path")
    result = source.harmonize(raw)
    assert list(result["party_id"]) == ["strong_dem", "strong_rep"]

def test_harmonize_namespaces_custom_variables():
    source = FakeSource()
    raw = source.clean("path")
    result = source.harmonize(raw)
    assert "fake:approval_rating" in result.columns
    assert list(result["fake:approval_rating"]) == [45, 80]

def test_harmonize_passes_unmapped_standard_through():
    source = FakeSource()
    raw = source.clean("path")
    result = source.harmonize(raw)
    # ideology has no variable_map, so it passes through directly
    assert list(result["ideology"]) == [2, 6]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/synthetic-population && python -m pytest tests/test_source_base.py -v`
Expected: FAIL — base.py doesn't exist

- [ ] **Step 3: Implement pipeline/sources/base.py**

```python
from abc import ABC, abstractmethod
from pathlib import Path
import pandas as pd

class DataSource(ABC):
    """Base class for all data source plugins.

    Subclasses must define:
        name: str — unique source identifier
        variables_provided: list[str] — standard schema variables this source provides
        match_keys: list[str] — demographics used for matching with ACS backbone
        update_cycle: str — "annual", "biennial", "election_year", "triennial"
        standard_column_map: dict[str, str] — {standard_name: source_column_name}
        variable_maps: dict[str, dict] — {standard_name: {source_value: standard_value}}
        custom_columns: dict[str, str] — {custom_name: source_column_name}
    """
    name: str
    variables_provided: list
    match_keys: list
    update_cycle: str
    standard_column_map: dict
    variable_maps: dict = {}
    custom_columns: dict = {}

    @abstractmethod
    def download(self) -> Path:
        """Download raw data. Returns path to downloaded file."""
        ...

    @abstractmethod
    def clean(self, raw_path) -> pd.DataFrame:
        """Clean raw data. Returns DataFrame ready for harmonization."""
        ...

    def harmonize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map source columns to standard schema.
        Standard variables get mapped via variable_maps (if defined) or passed through.
        Custom variables get namespaced as {source_name}:{custom_name}.
        """
        result = pd.DataFrame()
        for standard_name, source_col in self.standard_column_map.items():
            mapping = self.variable_maps.get(standard_name)
            if mapping:
                result[standard_name] = df[source_col].map(mapping)
            else:
                result[standard_name] = df[source_col]
        for custom_name, source_col in self.custom_columns.items():
            result[f"{self.name}:{custom_name}"] = df[source_col]
        return result

    def match_config(self) -> dict:
        """Return configuration for statistical matching with ACS backbone."""
        return {
            "source": self.name,
            "match_keys": self.match_keys,
            "variables": self.variables_provided,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/synthetic-population && python -m pytest tests/test_source_base.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit checkpoint**

```bash
git add apps/synthetic-population/pipeline/sources/base.py apps/synthetic-population/tests/test_source_base.py
git commit -m "feat: DataSource ABC with harmonize and plugin interface"
```

---

## Task 4: Source Registry

**Files:**
- Create: `apps/synthetic-population/pipeline/registry.py`
- Create: `apps/synthetic-population/tests/test_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_registry.py
from pipeline.registry import SourceRegistry
from pipeline.sources.base import DataSource
import pandas as pd

class StubSource(DataSource):
    name = "stub"
    variables_provided = ["party_id"]
    match_keys = ["age_bracket"]
    update_cycle = "annual"
    standard_column_map = {"party_id": "pid"}
    variable_maps = {}
    custom_columns = {}
    def download(self): return "path"
    def clean(self, raw_path): return pd.DataFrame()

def test_register_and_list():
    reg = SourceRegistry()
    reg.register(StubSource())
    assert "stub" in reg.list_sources()

def test_register_rejects_duplicate_name():
    reg = SourceRegistry()
    reg.register(StubSource())
    import pytest
    with pytest.raises(ValueError, match="already registered"):
        reg.register(StubSource())

def test_get_source_by_name():
    reg = SourceRegistry()
    src = StubSource()
    reg.register(src)
    assert reg.get("stub") is src

def test_get_nonexistent_raises():
    reg = SourceRegistry()
    import pytest
    with pytest.raises(KeyError):
        reg.get("nonexistent")

def test_variables_report():
    reg = SourceRegistry()
    reg.register(StubSource())
    report = reg.variables_report()
    assert report["party_id"] == "stub"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/synthetic-population && python -m pytest tests/test_registry.py -v`
Expected: FAIL

- [ ] **Step 3: Implement pipeline/registry.py**

```python
from pipeline.sources.base import DataSource

class SourceRegistry:
    """Tracks registered data source plugins."""

    def __init__(self):
        self._sources: dict[str, DataSource] = {}

    def register(self, source: DataSource):
        if source.name in self._sources:
            raise ValueError(f"Source '{source.name}' already registered")
        self._sources[source.name] = source

    def list_sources(self) -> list[str]:
        return list(self._sources.keys())

    def get(self, name: str) -> DataSource:
        if name not in self._sources:
            raise KeyError(f"Source '{name}' not found")
        return self._sources[name]

    def all(self) -> list[DataSource]:
        return list(self._sources.values())

    def variables_report(self) -> dict[str, str]:
        """Map of {variable_name: source_name} showing which source provides each variable."""
        report = {}
        for source in self._sources.values():
            for var in source.variables_provided:
                report[var] = source.name
        return report
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/synthetic-population && python -m pytest tests/test_registry.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit checkpoint**

```bash
git add apps/synthetic-population/pipeline/registry.py apps/synthetic-population/tests/test_registry.py
git commit -m "feat: source registry for plugin discovery"
```

---

## Task 5: ACS PUMS Source Plugin (First Real Source)

**Files:**
- Create: `apps/synthetic-population/pipeline/sources/acs_pums.py`
- Create: `apps/synthetic-population/tests/test_acs_pums.py`

This is the demographic backbone — the most important source. We implement it first as the reference implementation for all other source plugins.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_acs_pums.py
import pytest
import pandas as pd
from pipeline.sources.acs_pums import ACSPumsSource

@pytest.fixture
def source():
    return ACSPumsSource()

@pytest.fixture
def raw_pums_data():
    """Simulated raw PUMS data with real PUMS column names and codes."""
    return pd.DataFrame({
        "AGEP": [34, 52, 28, 67],
        "SEX": [1, 2, 2, 1],
        "RAC1P": [1, 1, 2, 6],
        "HISP": [1, 1, 1, 2],
        "SCHL": [19, 21, 22, 16],
        "PINCP": [52000, 68000, 85000, 35000],
        "MAR": [1, 1, 5, 3],
        "ST": [26, 39, 13, 48],
        "MIL": [4, 4, 4, 2],
        "DIS": [2, 2, 2, 1],
        "CIT": [1, 1, 1, 4],
        "ENG": [None, None, None, 2],
        "NP": [4, 3, 1, 2],
        "JWTRNS": [1, 1, 6, None],
        "ESR": [1, 1, 1, 6],
        "OCCP": ["4720", "3255", "2100", None],
        "INDP": ["7860", "8190", "6170", None],
        "HINS1": [2, 1, 1, 2],
        "TEN": [1, 1, 3, 1],
        "PWGTP": [45, 62, 38, 55],
    })

def test_source_metadata(source):
    assert source.name == "acs_pums"
    assert "age" in source.variables_provided
    assert "race" in source.variables_provided
    assert source.update_cycle == "annual"

def test_harmonize_maps_sex(source, raw_pums_data):
    result = source.harmonize(source.clean_dataframe(raw_pums_data))
    assert list(result["sex"]) == ["M", "F", "F", "M"]

def test_harmonize_maps_race_with_hispanic_override(source, raw_pums_data):
    result = source.harmonize(source.clean_dataframe(raw_pums_data))
    # Row 3 (index 3): RAC1P=6 but HISP=2 (Hispanic) → "hispanic"
    assert result["race"].iloc[3] == "hispanic"

def test_harmonize_maps_education(source, raw_pums_data):
    result = source.harmonize(source.clean_dataframe(raw_pums_data))
    # SCHL 19=some_college, 21=bachelors, 22=graduate, 16=hs_diploma
    expected = ["some_college", "bachelors", "graduate", "hs_diploma"]
    assert list(result["education"]) == expected

def test_harmonize_computes_age_bracket(source, raw_pums_data):
    result = source.harmonize(source.clean_dataframe(raw_pums_data))
    assert result["age_bracket"].iloc[0] == "25-34"
    assert result["age_bracket"].iloc[3] == "65+"

def test_harmonize_preserves_person_weight(source, raw_pums_data):
    result = source.harmonize(source.clean_dataframe(raw_pums_data))
    assert "acs_pums:person_weight" in result.columns
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/synthetic-population && python -m pytest tests/test_acs_pums.py -v`
Expected: FAIL

- [ ] **Step 3: Implement pipeline/sources/acs_pums.py**

Full implementation of `ACSPumsSource(DataSource)` with:
- `download()`: Downloads PUMS CSV from census.gov (or IPUMS) to `data/raw/acs_pums/`
- `clean_dataframe(df)`: Filters to ages 18+, drops records with missing critical fields
- `clean(raw_path)`: Reads CSV, calls `clean_dataframe`
- `harmonize()`: Override base class to handle PUMS-specific logic:
  - Hispanic origin override (HISP > 1 sets race to "hispanic" regardless of RAC1P)
  - Education mapping from 24 SCHL codes to 5 categories
  - Age bracket computation
  - State FIPS to 2-letter abbreviation
  - Veteran status from MIL codes
  - Person weight as custom variable for downstream weighting

Key variable mappings:
```python
SEX_MAP = {1: "M", 2: "F"}
RACE_MAP = {1: "white", 2: "black", 3: "other", 4: "other", 5: "other",
            6: "asian", 7: "other", 8: "multiracial", 9: "multiracial"}
EDUCATION_MAP = {
    **{i: "less_than_hs" for i in range(1, 16)},
    16: "hs_diploma", 17: "hs_diploma",
    18: "some_college", 19: "some_college", 20: "some_college",
    21: "bachelors",
    22: "graduate", 23: "graduate", 24: "graduate",
}
MARITAL_MAP = {1: "married", 2: "widowed", 3: "divorced", 4: "separated", 5: "never_married"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/synthetic-population && python -m pytest tests/test_acs_pums.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit checkpoint**

```bash
git add apps/synthetic-population/pipeline/sources/acs_pums.py apps/synthetic-population/tests/test_acs_pums.py
git commit -m "feat: ACS PUMS source plugin with demographic harmonization"
```

---

## Task 6: CES Source Plugin (Political Variables)

**Files:**
- Create: `apps/synthetic-population/pipeline/sources/ces.py`
- Create: `apps/synthetic-population/tests/test_ces.py`

Same pattern as ACS PUMS. CES provides party ID, ideology, vote choice, and policy positions. Match keys are the standard demographics shared with ACS.

- [ ] **Step 1: Write failing tests**

Tests should cover: source metadata, party_id mapping (7-point scale), ideology mapping, vote choice mapping, policy position mappings, and that match_keys include the demographics needed for fusion with ACS.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/synthetic-population && python -m pytest tests/test_ces.py -v`
Expected: FAIL

- [ ] **Step 3: Implement pipeline/sources/ces.py**

`CESSource(DataSource)` with:
- `download()`: Fetches from Harvard Dataverse
- Variable maps for: party_id (pid7), ideology (ideo5), vote_2020, vote_2024, 15+ policy positions
- Match keys: age_bracket, sex, race, education, income_bracket, state, urban_rural

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/synthetic-population && python -m pytest tests/test_ces.py -v`
Expected: All PASS

- [ ] **Step 5: Commit checkpoint**

```bash
git add apps/synthetic-population/pipeline/sources/ces.py apps/synthetic-population/tests/test_ces.py
git commit -m "feat: CES source plugin with political variables"
```

---

## Task 7: Remaining Source Plugins (ANES, GSS, Pew, BRFSS, CPS, FINRA, SCF)

**Files:**
- Create: one source file + one test file per source (7 sources × 2 files = 14 files)

Each follows the exact same pattern as Tasks 5-6. For each source:

- [ ] **Step 1: Implement ANES plugin** — psychology variables (racial_resentment, authoritarianism, Big Five, feeling thermometers). Download from electionstudies.org.
- [ ] **Step 2: Test ANES plugin**
- [ ] **Step 3: Commit ANES**
- [ ] **Step 4: Implement GSS plugin** — religion, social trust, institutional confidence, gender roles. Download from gss.norc.org.
- [ ] **Step 5: Test GSS plugin**
- [ ] **Step 6: Commit GSS**
- [ ] **Step 7: Implement Pew ATP plugin** — media consumption, tech use, vaccine attitudes, climate beliefs, science trust. Note: may require researcher application.
- [ ] **Step 8: Test Pew ATP plugin**
- [ ] **Step 9: Commit Pew ATP**
- [ ] **Step 10: Implement BRFSS plugin** — health behaviors, chronic conditions, insurance. Download from cdc.gov.
- [ ] **Step 11: Test BRFSS plugin**
- [ ] **Step 12: Commit BRFSS**
- [ ] **Step 13: Implement CPS plugin** — employment detail, union membership, income source. Download from census.gov.
- [ ] **Step 14: Test CPS plugin**
- [ ] **Step 15: Commit CPS**
- [ ] **Step 16: Implement FINRA NFCS plugin** — financial literacy, tax approach, retirement strategy. Download from usfinancialhealth.org.
- [ ] **Step 17: Test FINRA plugin**
- [ ] **Step 18: Commit FINRA**
- [ ] **Step 19: Implement Fed SCF plugin** — investment types, risk tolerance, wealth. Download from federalreserve.gov.
- [ ] **Step 20: Test SCF plugin**
- [ ] **Step 21: Commit SCF**

---

## Task 8: Statistical Fusion Engine

**Files:**
- Create: `apps/synthetic-population/pipeline/fuse.py`
- Create: `apps/synthetic-population/tests/test_fuse.py`

This is the core data engineering — merging variables from different sources onto the ACS backbone using predictive mean matching.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_fuse.py
import pytest
import pandas as pd
from pipeline.fuse import StatisticalMatcher

@pytest.fixture
def backbone():
    """ACS-like backbone with demographics only."""
    return pd.DataFrame({
        "age_bracket": ["25-34", "45-54", "25-34", "65+"],
        "sex": ["M", "F", "F", "M"],
        "race": ["white", "white", "black", "hispanic"],
        "education": ["some_college", "bachelors", "graduate", "hs_diploma"],
        "income_bracket": ["50-75k", "50-75k", "75-100k", "25-50k"],
        "state": ["MI", "OH", "GA", "TX"],
        "urban_rural": ["rural", "suburban", "urban", "rural"],
    })

@pytest.fixture
def donor():
    """CES-like donor with demographics + political variables."""
    return pd.DataFrame({
        "age_bracket": ["25-34", "25-34", "45-54", "45-54", "65+", "65+"],
        "sex": ["M", "M", "F", "F", "M", "M"],
        "race": ["white", "white", "white", "white", "hispanic", "hispanic"],
        "education": ["some_college", "some_college", "bachelors", "bachelors", "hs_diploma", "hs_diploma"],
        "party_id": ["lean_rep", "strong_rep", "lean_dem", "dem", "dem", "lean_rep"],
        "ideology": [5, 7, 3, 2, 3, 5],
    })

def test_match_returns_correct_shape(backbone, donor):
    matcher = StatisticalMatcher(match_keys=["age_bracket", "sex", "race", "education"])
    result = matcher.match(backbone, donor, variables=["party_id", "ideology"])
    assert len(result) == len(backbone)
    assert "party_id" in result.columns
    assert "ideology" in result.columns

def test_match_preserves_backbone_columns(backbone, donor):
    matcher = StatisticalMatcher(match_keys=["age_bracket", "sex", "race", "education"])
    result = matcher.match(backbone, donor, variables=["party_id", "ideology"])
    for col in backbone.columns:
        assert col in result.columns

def test_match_uses_nearest_donor(backbone, donor):
    matcher = StatisticalMatcher(match_keys=["age_bracket", "sex", "race", "education"])
    result = matcher.match(backbone, donor, variables=["party_id"])
    # Row 0: 25-34, M, white, some_college → should match donor rows 0 or 1
    assert result["party_id"].iloc[0] in ["lean_rep", "strong_rep"]

def test_match_handles_no_exact_match(backbone, donor):
    """When no exact match exists, falls back to closest partial match."""
    matcher = StatisticalMatcher(match_keys=["age_bracket", "sex", "race", "education"])
    result = matcher.match(backbone, donor, variables=["party_id"])
    # Row 2: 25-34, F, black, graduate — no exact match in donor
    # Should still produce a value (nearest neighbor fallback)
    assert pd.notna(result["party_id"].iloc[2])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/synthetic-population && python -m pytest tests/test_fuse.py -v`
Expected: FAIL

- [ ] **Step 3: Implement pipeline/fuse.py**

`StatisticalMatcher` using predictive mean matching (pure Python, no rpy2):
1. Encode categorical match keys as integers
2. For each backbone record, find k-nearest donors by Euclidean distance on encoded match keys
3. Randomly sample one of the k nearest donors (k=5 default)
4. Copy the requested variables from the selected donor to the backbone record

Uses `scipy.spatial.KDTree` for efficient nearest-neighbor lookup.

```python
import pandas as pd
import numpy as np
from scipy.spatial import KDTree
from sklearn.preprocessing import OrdinalEncoder

class StatisticalMatcher:
    def __init__(self, match_keys: list[str], k: int = 5):
        self.match_keys = match_keys
        self.k = k

    def match(self, backbone: pd.DataFrame, donor: pd.DataFrame,
              variables: list[str]) -> pd.DataFrame:
        # Encode match keys
        encoder = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
        all_keys = pd.concat([backbone[self.match_keys], donor[self.match_keys]])
        encoder.fit(all_keys)

        backbone_encoded = encoder.transform(backbone[self.match_keys])
        donor_encoded = encoder.transform(donor[self.match_keys])

        # Build KDTree on donor records
        tree = KDTree(donor_encoded)

        # For each backbone record, find k nearest donors, sample one
        result = backbone.copy()
        k = min(self.k, len(donor))
        distances, indices = tree.query(backbone_encoded, k=k)

        for var in variables:
            values = []
            for i in range(len(backbone)):
                neighbor_indices = indices[i] if k > 1 else [indices[i]]
                chosen = np.random.choice(neighbor_indices)
                values.append(donor[var].iloc[chosen])
            result[var] = values

        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/synthetic-population && python -m pytest tests/test_fuse.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit checkpoint**

```bash
git add apps/synthetic-population/pipeline/fuse.py apps/synthetic-population/tests/test_fuse.py
git commit -m "feat: statistical matching engine with KDTree nearest-neighbor"
```

---

## Task 9: Model Fitting (SDV Synthesizer)

**Files:**
- Create: `apps/synthetic-population/pipeline/fit_model.py`
- Create: `apps/synthetic-population/tests/test_fit_model.py`

Trains an SDV GaussianCopulaSynthesizer on the fused dataset so we can draw unlimited synthetic profiles.

- [ ] **Step 1: Write failing tests**

Tests should cover: fitting a model on sample data, saving/loading a model to disk, generating N samples from a fitted model, verifying generated samples have all expected columns, verifying generated values are within allowed ranges.

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement pipeline/fit_model.py**

`ModelTrainer` class that:
- Takes a fused DataFrame (output of `StatisticalMatcher`)
- Configures `GaussianCopulaSynthesizer` with column metadata (categorical vs numerical)
- Fits the model
- Saves to disk as pickle (in `data/models/`)
- Loads from disk
- Generates N samples

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit checkpoint**

```bash
git commit -m "feat: SDV model trainer with save/load/generate"
```

---

## Task 10: IPF Calibration

**Files:**
- Create: `apps/synthetic-population/pipeline/calibrate.py`
- Create: `apps/synthetic-population/tests/test_calibrate.py`

Adjusts generated population weights to match known census marginals.

- [ ] **Step 1: Write failing tests**

Tests should cover: calibrating a sample population against known marginals (e.g., 52% female, 60% white), verifying post-calibration marginals are within ±2pp of targets, verifying calibration doesn't destroy inter-variable correlations.

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement pipeline/calibrate.py**

`IPFCalibrator` class implementing Iterative Proportional Fitting:
- Takes a DataFrame + dict of target marginals `{"sex": {"M": 0.48, "F": 0.52}, "race": {...}}`
- Iteratively adjusts record weights until marginals converge (within tolerance)
- Returns DataFrame with `_weight` column

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit checkpoint**

```bash
git commit -m "feat: IPF calibration against census marginals"
```

---

## Task 11: Profile Deduplication

**Files:**
- Create: `apps/synthetic-population/generator/dedup.py`
- Create: `apps/synthetic-population/tests/test_dedup.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_dedup.py
from generator.dedup import DedupChecker

def test_no_duplicates_in_empty_registry():
    checker = DedupChecker(existing_profiles=[], composite_keys=[
        "age_bracket", "sex", "race", "education", "state", "party_id",
        "religion_affiliation", "income_source"
    ], threshold=6)
    candidate = {"age_bracket": "25-34", "sex": "M", "race": "white",
                 "education": "some_college", "state": "MI", "party_id": "lean_rep",
                 "religion_affiliation": "evangelical", "income_source": "wages"}
    assert checker.is_unique(candidate) is True

def test_exact_duplicate_rejected():
    existing = [{"age_bracket": "25-34", "sex": "M", "race": "white",
                 "education": "some_college", "state": "MI", "party_id": "lean_rep",
                 "religion_affiliation": "evangelical", "income_source": "wages"}]
    checker = DedupChecker(existing_profiles=existing, composite_keys=[
        "age_bracket", "sex", "race", "education", "state", "party_id",
        "religion_affiliation", "income_source"
    ], threshold=6)
    candidate = existing[0].copy()
    assert checker.is_unique(candidate) is False

def test_partial_overlap_below_threshold_accepted():
    existing = [{"age_bracket": "25-34", "sex": "M", "race": "white",
                 "education": "some_college", "state": "MI", "party_id": "lean_rep",
                 "religion_affiliation": "evangelical", "income_source": "wages"}]
    checker = DedupChecker(existing_profiles=existing, composite_keys=[
        "age_bracket", "sex", "race", "education", "state", "party_id",
        "religion_affiliation", "income_source"
    ], threshold=6)
    # Differs on 3 keys: state, party_id, religion → matches on 5 < threshold 6
    candidate = {"age_bracket": "25-34", "sex": "M", "race": "white",
                 "education": "some_college", "state": "OH", "party_id": "lean_dem",
                 "religion_affiliation": "none", "income_source": "wages"}
    assert checker.is_unique(candidate) is True
```

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement generator/dedup.py**

```python
class DedupChecker:
    def __init__(self, existing_profiles: list[dict], composite_keys: list[str], threshold: int = 6):
        self.existing = existing_profiles
        self.keys = composite_keys
        self.threshold = threshold

    def is_unique(self, candidate: dict) -> bool:
        for existing in self.existing:
            matches = sum(1 for k in self.keys if candidate.get(k) == existing.get(k))
            if matches >= self.threshold:
                return False
        return True
```

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit checkpoint**

```bash
git commit -m "feat: composite-key deduplication checker"
```

---

## Task 12: Gap Analysis

**Files:**
- Create: `apps/synthetic-population/generator/gap_analysis.py`
- Create: `apps/synthetic-population/tests/test_gap_analysis.py`

- [ ] **Step 1: Write failing tests**

Tests should cover: detecting underrepresented demographics vs national marginals, returning a priority-weighted sampling bias dict, handling an empty population (all demographics underrepresented).

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement generator/gap_analysis.py**

`GapAnalyzer` that:
- Takes current population DataFrame + target marginals dict
- Computes actual vs expected proportions for each category
- Returns `sampling_bias` dict: `{variable: {value: weight}}` where underrepresented categories get weight > 1.0

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit checkpoint**

```bash
git commit -m "feat: gap analysis with priority sampling weights"
```

---

## Task 13: Backstory Generator

**Files:**
- Create: `apps/synthetic-population/generator/backstory.py`
- Create: `apps/synthetic-population/tests/test_backstory.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_backstory.py
from generator.backstory import generate_backstory

def test_backstory_contains_key_demographics():
    profile = {
        "age": 34, "sex": "M", "race": "white", "education": "some_college",
        "state": "MI", "urban_rural": "rural", "occupation": "diesel_mechanic",
        "income": 52000, "marital_status": "married", "children_count": 3,
        "religion_affiliation": "evangelical", "religion_attendance": "weekly",
        "party_id": "lean_rep", "vote_2024": "trump",
        "primary_news_source": "fox_news", "social_media_primary": "facebook",
        "income_source": "wages", "tax_approach": "software_basic",
    }
    story = generate_backstory(profile)
    assert "34" in story
    assert "Michigan" in story or "MI" in story
    assert "married" in story.lower()

def test_backstory_varies_across_calls():
    profile = {
        "age": 52, "sex": "F", "race": "black", "education": "graduate",
        "state": "GA", "urban_rural": "urban", "occupation": "attorney",
        "income": 120000, "marital_status": "divorced", "children_count": 1,
        "religion_affiliation": "none", "religion_attendance": "never",
        "party_id": "strong_dem", "vote_2024": "harris",
        "primary_news_source": "msnbc", "social_media_primary": "twitter",
        "income_source": "wages", "tax_approach": "professional_cpa",
    }
    stories = {generate_backstory(profile) for _ in range(10)}
    # Should have some variation due to template randomization
    assert len(stories) > 1

def test_backstory_includes_financial_identity():
    profile = {
        "age": 45, "sex": "M", "race": "white", "education": "hs_diploma",
        "state": "TX", "urban_rural": "rural", "occupation": "contractor",
        "income": 95000, "marital_status": "married", "children_count": 2,
        "religion_affiliation": "evangelical", "religion_attendance": "weekly",
        "party_id": "strong_rep", "vote_2024": "trump",
        "primary_news_source": "fox_news", "social_media_primary": "facebook",
        "income_source": "self_employment", "tax_approach": "professional_cpa",
        "business_size": "1-10_employees",
    }
    story = generate_backstory(profile)
    # Should mention business ownership or self-employment
    assert any(term in story.lower() for term in ["own", "business", "self-employed", "run"])
```

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement generator/backstory.py**

Template-based system with ~10 sentence variants per slot:
- Opening (age, race, gender, location)
- Education & work
- Family
- Religion
- Politics & media
- Financial identity
- Economic perspective

Uses `random.choice` across variants. State codes mapped to full names. Income formatted with commas. Sentence connectors varied.

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit checkpoint**

```bash
git commit -m "feat: template-based backstory generator with variation"
```

---

## Task 14: Archetype Clustering

**Files:**
- Create: `apps/synthetic-population/generator/archetypes.py`
- Create: `apps/synthetic-population/tests/test_archetypes.py`

- [ ] **Step 1: Write failing tests**

Tests should cover: clustering profiles into archetypes, each profile gets an archetype_id, archetypes have population weights summing to 1.0, archetype centroids are computed correctly, finding the representative profile (closest to centroid) for each archetype.

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement generator/archetypes.py**

`ArchetypeBuilder` that:
- Takes profiles DataFrame
- Encodes clustering variables (party_id, race, education, religiosity, urban_rural, info_ecosystem)
- Uses categorical cross-tabulation (not k-means — these are all categorical) to define archetype cells
- Collapses cells with < N profiles (default 5) into nearest neighbor cell
- Computes population weight for each archetype
- Assigns archetype_id to each profile
- Identifies representative profile per archetype (most common variable combination)

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit checkpoint**

```bash
git commit -m "feat: archetype clustering with population weights"
```

---

## Task 15: Profile Generator CLI

**Files:**
- Create: `apps/synthetic-population/generator/generate.py`
- Create: `apps/synthetic-population/tests/test_generate.py`

This ties together model loading, sampling, dedup, gap analysis, backstory generation, and archetype assignment.

- [ ] **Step 1: Write failing tests**

Tests should cover: generating N profiles from a fitted model, dedup against existing registry, gap-biased sampling, each profile has all required fields (structured + backstory + archetype_id), profiles are appended to registry file, batch_id is assigned, CLI argument parsing (--count, --batch-name).

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement generator/generate.py**

`ProfileGenerator` class + CLI entry point:
```python
class ProfileGenerator:
    def __init__(self, model_path, registry_path, marginals_path):
        ...
    def generate_batch(self, count: int, batch_name: str = None) -> list[dict]:
        # 1. Load model + existing registry
        # 2. Run gap analysis
        # 3. Sample from model with gap bias
        # 4. Dedup each candidate
        # 5. Generate backstories
        # 6. Assign archetypes
        # 7. Append to registry
        # 8. Return new profiles

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--batch-name", type=str, default=None)
    parser.add_argument("--model", type=str, default="data/models/latest.pkl")
    parser.add_argument("--registry", type=str, default="data/profiles/registry.json")
    ...
```

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit checkpoint**

```bash
git commit -m "feat: profile generator CLI with batch creation"
```

---

## Task 16: Prompt Templates & Conviction Anchoring

**Files:**
- Create: `apps/synthetic-population/engine/prompts.py`
- Create: `apps/synthetic-population/tests/test_prompts.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_prompts.py
from engine.prompts import build_poll_prompt

def test_prompt_includes_backstory():
    profile = {"backstory": "I am a 34-year-old white man from rural Michigan."}
    prompt = build_poll_prompt(profile, "Should the US ban TikTok?")
    assert "34-year-old white man" in prompt

def test_prompt_includes_conviction_anchoring():
    profile = {"backstory": "I am a nurse from Ohio."}
    prompt = build_poll_prompt(profile, "Any question?")
    assert "NOT a policy analyst" in prompt or "real opinions" in prompt

def test_prompt_includes_media_diet():
    profile = {
        "backstory": "I am a nurse.",
        "primary_news_source": "fox_news",
        "social_media_primary": "facebook",
    }
    prompt = build_poll_prompt(profile, "Any question?")
    assert "Fox News" in prompt or "fox" in prompt.lower()

def test_prompt_includes_prior_opinions():
    profile = {
        "backstory": "I am a nurse.",
        "drift_log": [
            {"topic": "immigration", "position": "oppose", "confidence": 8},
        ],
    }
    prompt = build_poll_prompt(profile, "Should we increase immigration?")
    assert "immigration" in prompt.lower()

def test_prompt_requests_structured_response():
    profile = {"backstory": "I am a person."}
    prompt = build_poll_prompt(profile, "Any question?")
    assert "yes/no/unsure" in prompt.lower() or "confidence" in prompt.lower()
```

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement engine/prompts.py**

`build_poll_prompt(profile, question, include_history=True)` that assembles:
1. System instruction (you are roleplaying, stay in character)
2. Conviction anchoring block (not a policy analyst, media diet constrains awareness, strong opinions expressed strongly, misinformation reflected not corrected)
3. Backstory
4. Prior opinions from drift_log (if relevant to question topic)
5. The question
6. Response format instructions (opinion, confidence 1-10, 2-3 sentences reasoning)

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit checkpoint**

```bash
git commit -m "feat: poll prompt templates with conviction anchoring"
```

---

## Task 17: Hedge Detection & Integrity Checks

**Files:**
- Create: `apps/synthetic-population/engine/integrity.py`
- Create: `apps/synthetic-population/tests/test_integrity.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_integrity.py
from engine.integrity import check_hedge_score, check_consistency

def test_strong_opinion_scores_low():
    response = "Absolutely not. The government has no business telling people what to do."
    score = check_hedge_score(response)
    assert score < 0.3

def test_hedging_response_scores_high():
    response = "On the one hand, there are valid points. However, one must consider both sides. It's complicated and reasonable people disagree."
    score = check_hedge_score(response)
    assert score > 0.5

def test_consistency_flags_contradiction():
    drift_log = [{"topic": "immigration", "position": "strongly_oppose", "confidence": 9}]
    new_response = {"topic": "immigration", "position": "strongly_support", "confidence": 8}
    flags = check_consistency(drift_log, new_response)
    assert len(flags) > 0
    assert "contradiction" in flags[0].lower()

def test_consistency_allows_minor_shift():
    drift_log = [{"topic": "immigration", "position": "oppose", "confidence": 7}]
    new_response = {"topic": "immigration", "position": "lean_oppose", "confidence": 6}
    flags = check_consistency(drift_log, new_response)
    assert len(flags) == 0
```

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement engine/integrity.py**

`check_hedge_score(response_text)` — counts hedge phrases, returns 0.0-1.0 score.
`check_consistency(drift_log, new_response)` — compares new position against historical, flags reversals.

Hedge phrases list: "on the other hand", "however", "both sides", "it's complicated", "reasonable people disagree", "there are valid points on both sides", "nuanced", "multifaceted".

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit checkpoint**

```bash
git commit -m "feat: hedge detection and opinion consistency checks"
```

---

## Task 18: Weighted Aggregation

**Files:**
- Create: `apps/synthetic-population/engine/aggregate.py`
- Create: `apps/synthetic-population/tests/test_aggregate.py`

- [ ] **Step 1: Write failing tests**

Tests should cover: weighted aggregation of yes/no/unsure responses by archetype weight, demographic breakdowns (by party, education, etc.), confidence interval computation, handling of missing responses for some archetypes.

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement engine/aggregate.py**

`PollAggregator` that:
- Takes list of `{archetype_id, response, confidence, demographics}` + archetype weights
- Computes weighted opinion distribution
- Computes demographic sub-breakdowns
- Estimates confidence intervals via weighted bootstrap
- Returns structured `PollResult` dict

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit checkpoint**

```bash
git commit -m "feat: weighted poll aggregation with demographic breakdowns"
```

---

## Task 19: Polling Flow (Ties It Together)

**Files:**
- Create: `apps/synthetic-population/engine/poll.py`
- Create: `apps/synthetic-population/tests/test_poll.py`

- [ ] **Step 1: Write failing tests**

Tests should cover: selecting one representative per archetype, generating prompts for all selected profiles, collecting responses (mocked), running integrity checks on responses, aggregating results, saving poll results to `data/polls/`, generating a prompt batch file for manual Claude Max querying.

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement engine/poll.py**

`PollRunner` class with:
- `prepare(question, registry_path)` → selects archetypes, builds prompts, saves to `data/polls/{poll_id}/prompts.txt` (one prompt per section, numbered, ready for copy-paste into Claude Max)
- `record_response(archetype_id, response_text)` → parses response, runs integrity check
- `aggregate()` → runs weighted aggregation, saves results
- CLI entry: `python -m engine.poll --question "..." --registry data/profiles/registry.json`

The `prompts.txt` output format is critical for the Claude Max workflow:
```
=== ARCHETYPE A-001 (weight: 14.2%) ===
[full prompt ready for copy-paste]

=== ARCHETYPE A-002 (weight: 8.7%) ===
[full prompt ready for copy-paste]
...
```

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit checkpoint**

```bash
git commit -m "feat: polling flow with prompt batch generation"
```

---

## Task 20: Event Ingestion

**Files:**
- Create: `apps/synthetic-population/monitor/events.py`
- Create: `apps/synthetic-population/tests/test_events.py`

- [ ] **Step 1: Write failing tests**

Tests should cover: creating an event with affected segments, saving events to `data/events/`, loading event history, validating event schema (required fields: date, description, affected_segments), listing events by date range.

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement monitor/events.py**

`EventStore` class:
- `add(event_dict)` → validates, assigns event_id, saves to `data/events/{event_id}.json`
- `list(start_date, end_date)` → returns events in date range
- `get(event_id)` → returns single event

CLI entry: `python -m monitor.events add --description "..." --segments '{"party_id": {"republican": 0.1}}'`

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit checkpoint**

```bash
git commit -m "feat: event ingestion and storage"
```

---

## Task 21: Drift Engine

**Files:**
- Create: `apps/synthetic-population/monitor/drift.py`
- Create: `apps/synthetic-population/tests/test_drift.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_drift.py
from monitor.drift import DriftEngine

def test_drift_adjusts_responsive_variable():
    profile = {
        "party_id": "lean_rep",
        "climate_policy_support": 0.3,
        "drift_log": [],
    }
    event = {
        "event_id": "EVT-001",
        "affected_segments": {
            "party_id": {"lean_rep": {"climate_policy_support": +0.1}},
        },
    }
    updated = DriftEngine.apply(profile, event)
    assert updated["climate_policy_support"] == pytest.approx(0.4)
    assert len(updated["drift_log"]) == 1

def test_drift_clamps_to_bounds():
    profile = {
        "party_id": "strong_dem",
        "climate_policy_support": 0.95,
        "drift_log": [],
    }
    event = {
        "event_id": "EVT-002",
        "affected_segments": {
            "party_id": {"strong_dem": {"climate_policy_support": +0.2}},
        },
    }
    updated = DriftEngine.apply(profile, event)
    assert updated["climate_policy_support"] <= 1.0

def test_drift_ignores_immutable_variables():
    profile = {
        "party_id": "lean_rep",
        "race": "white",
        "drift_log": [],
    }
    event = {
        "event_id": "EVT-003",
        "affected_segments": {
            "party_id": {"lean_rep": {"race": "hispanic"}},
        },
    }
    updated = DriftEngine.apply(profile, event)
    assert updated["race"] == "white"

def test_drift_ignores_unaffected_profiles():
    profile = {
        "party_id": "strong_dem",
        "climate_policy_support": 0.9,
        "drift_log": [],
    }
    event = {
        "event_id": "EVT-004",
        "affected_segments": {
            "party_id": {"lean_rep": {"climate_policy_support": +0.1}},
        },
    }
    updated = DriftEngine.apply(profile, event)
    assert updated["climate_policy_support"] == 0.9
    assert len(updated["drift_log"]) == 0
```

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement monitor/drift.py**

`DriftEngine` with:
- `IMMUTABLE_VARS` set: age, race, sex, education, veteran_status, native_born
- `SLOW_VARS` set: party_id, religion_affiliation, urban_rural, income_bracket
- `apply(profile, event)` → checks if profile matches affected segment, applies delta to responsive variables only, clamps to [0, 1] range, logs to drift_log
- `apply_batch(registry_path, event)` → applies event to all affected profiles in registry

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit checkpoint**

```bash
git commit -m "feat: bounded drift engine with immutable variable protection"
```

---

## Task 22: Integration Test — Full Pipeline Smoke Test

**Files:**
- Create: `apps/synthetic-population/tests/test_integration.py`

- [ ] **Step 1: Write integration test**

End-to-end test using small synthetic data (no real downloads):
1. Create a tiny ACS-like backbone (20 records)
2. Create a tiny CES-like donor (30 records)
3. Fuse them via StatisticalMatcher
4. Fit an SDV model on the fused data
5. Generate 10 profiles via ProfileGenerator
6. Verify dedup works (generate 10 more, no duplicates)
7. Verify archetypes are assigned
8. Verify backstories are generated
9. Build poll prompts for a test question
10. Verify prompt output format is correct
11. Create a test event
12. Apply drift to profiles
13. Verify drift_log is populated

- [ ] **Step 2: Run integration test**

Run: `cd apps/synthetic-population && python -m pytest tests/test_integration.py -v`
Expected: All PASS

- [ ] **Step 3: Commit checkpoint**

```bash
git commit -m "test: full pipeline integration smoke test"
```

---

## Task 23: Final Validation & Cleanup

- [ ] **Step 1: Run full test suite**

Run: `cd apps/synthetic-population && python -m pytest -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Verify project structure matches spec**

Check all files from the file structure section exist and have the right responsibilities.

- [ ] **Step 3: Update TODO.md with next steps**

Now section: "Download real ACS PUMS data and run first batch generation"
Next section: "Build web UI for population browsing and polling"

- [ ] **Step 4: Final commit**

```bash
git add -A apps/synthetic-population/
git commit -m "feat: synthetic population engine v1 complete"
```
