"""
Plausibility Filter — Common Sense Heuristics for Synthetic Profiles

The "Reddit roast test": would someone call this profile out as obviously fake?
Catches implausible combinations that SDV generates because it doesn't enforce
cross-variable logical constraints.

Applied during generation AND as a cleanup pass on existing profiles.
"""

import random
import math


def fix_profile(profile: dict) -> dict:
    """Apply all plausibility fixes to a profile. Modifies in place and returns it."""
    _fix_income(profile)
    _fix_age_education(profile)
    _fix_age_family(profile)
    _fix_age_occupation(profile)
    _fix_age_employment(profile)
    _fix_widowed_age(profile)
    _fix_retirement_age(profile)
    _fix_children_household(profile)
    return profile


def check_profile(profile: dict) -> list[str]:
    """Return list of implausibility flags (for diagnostics, not fixing)."""
    flags = []
    age = _age(profile)
    if age is None:
        return flags

    edu = profile.get("education", "")
    marital = profile.get("marital_status", "")
    kids = _int_or(profile.get("children_count"), 0)
    occ = profile.get("occupation", "")
    income = _float_or(profile.get("income"), 0)
    income_source = profile.get("income_source", "")
    emp = profile.get("employment_status", "")

    # Age-education
    if edu == "graduate" and age < 24:
        flags.append(f"graduate degree at age {age}")
    if edu == "bachelors" and age < 21:
        flags.append(f"bachelor's degree at age {age}")

    # Age-family
    if kids > 0 and age < 18 + kids:
        flags.append(f"{kids} children at age {age}")
    if marital == "married" and age < 19:
        flags.append(f"married at age {age}")
    if kids >= 3 and age < 25:
        flags.append(f"{kids} children at age {age}")
    if marital == "widowed" and age < 35:
        flags.append(f"widowed at age {age}")
    if marital == "divorced" and age < 22:
        flags.append(f"divorced at age {age}")

    # Age-occupation
    if occ in ("management", "manager", "director", "executive") and age < 26:
        flags.append(f"management role at age {age}")
    if occ in ("surgeon", "attorney", "professor", "physician") and age < 28:
        flags.append(f"{occ} at age {age}")

    # Income
    if income < 0:
        flags.append(f"negative income: {income}")
    if income > 500000 and edu in ("less_than_hs", "hs_diploma") and age < 30:
        flags.append(f"${income:,} income with {edu} at age {age}")

    # Retirement
    if income_source == "retirement" and age < 50:
        flags.append(f"retirement income at age {age}")
    if emp == "not_in_labor_force" and age < 22 and edu not in ("less_than_hs",):
        flags.append(f"not in labor force at age {age} with {edu}")

    return flags


# ---------------------------------------------------------------------------
# Fix functions — each handles one category of implausibility
# ---------------------------------------------------------------------------

def _fix_income(p: dict):
    """Clamp negative income, adjust implausible income for age/education."""
    income = _float_or(p.get("income"), None)
    if income is None:
        return
    if income < 0:
        p["income"] = abs(income)
        income = p["income"]

    age = _age(p)
    edu = p.get("education", "")

    # Very young people shouldn't have high incomes
    if age and age < 22 and income > 60000:
        p["income"] = random.randint(15000, 45000)
    elif age and age < 25 and income > 120000 and edu != "graduate":
        p["income"] = random.randint(25000, 70000)

    # Recalculate income bracket
    _recalc_income_bracket(p)


def _fix_age_education(p: dict):
    """Graduate degrees require realistic minimum age."""
    age = _age(p)
    if age is None:
        return
    edu = p.get("education", "")

    if edu == "graduate" and age < 24:
        p["education"] = "some_college" if age < 21 else "bachelors"
    elif edu == "bachelors" and age < 21:
        p["education"] = "some_college"


def _fix_age_family(p: dict):
    """Adjust children count and marital status for age."""
    age = _age(p)
    if age is None:
        return

    kids = _int_or(p.get("children_count"), 0)
    marital = p.get("marital_status", "")

    # Max plausible children by age: roughly (age - 18) / 2.5, min 0
    if age < 20:
        max_kids = 1
    elif age < 25:
        max_kids = 2
    elif age < 30:
        max_kids = 3
    else:
        max_kids = min(kids, 10)  # older adults can have many kids

    if kids > max_kids:
        p["children_count"] = max_kids

    # Marriage age
    if marital == "married" and age < 19:
        p["marital_status"] = "never_married"
        p["children_count"] = min(p.get("children_count", 0), 1)
    elif marital == "divorced" and age < 22:
        p["marital_status"] = "never_married"


def _fix_age_occupation(p: dict):
    """Young people shouldn't be in senior/professional roles requiring years of experience."""
    age = _age(p)
    if age is None:
        return

    occ = p.get("occupation", "")
    edu = p.get("education", "")

    # Management/director roles: need at least mid-20s
    senior_roles = {"management", "manager", "director", "executive", "senior"}
    if occ in senior_roles and age < 26:
        # Downgrade to entry-level equivalent
        entry_map = {
            "management": "sales",
            "manager": "service",
            "director": "professional",
            "executive": "sales",
            "senior": "professional",
        }
        p["occupation"] = entry_map.get(occ, "service")

    # Professional roles requiring advanced degrees
    adv_roles = {"surgeon", "attorney", "professor", "physician", "pharmacist"}
    if occ in adv_roles and age < 28:
        p["occupation"] = "professional"

    # Very young (18-19) should be entry-level
    if age < 20 and occ in ("professional", "management", "manager"):
        p["occupation"] = random.choice(["service", "sales", "other"])


def _fix_age_employment(p: dict):
    """Adjust employment status for age."""
    age = _age(p)
    if age is None:
        return

    emp = p.get("employment_status", "")

    # "Not in labor force" for young educated people → likely student, adjust to employed
    if emp == "not_in_labor_force" and age < 25 and age >= 18:
        edu = p.get("education", "")
        if edu in ("some_college", "bachelors"):
            # Could be a student — leave it, but ensure no senior occupation
            pass


def _fix_widowed_age(p: dict):
    """Widowed very unlikely under 35."""
    age = _age(p)
    if age is None:
        return

    if p.get("marital_status") == "widowed" and age < 35:
        if age < 25:
            p["marital_status"] = "never_married"
        else:
            p["marital_status"] = random.choice(["married", "never_married", "divorced"])


def _fix_retirement_age(p: dict):
    """Retirement income source unlikely under 50."""
    age = _age(p)
    if age is None:
        return

    if p.get("income_source") == "retirement" and age < 50:
        p["income_source"] = "wages"

    # People 65+ who are "not in labor force" should likely have retirement income
    if age >= 65 and p.get("employment_status") == "not_in_labor_force":
        if p.get("income_source") not in ("retirement", "investments", "benefits"):
            p["income_source"] = "retirement"


def _fix_children_household(p: dict):
    """Household size should be at least 1 + children_count if married."""
    kids = _int_or(p.get("children_count"), 0)
    hh = _int_or(p.get("household_size"), None)
    marital = p.get("marital_status", "")

    if hh is not None and kids > 0:
        min_hh = 1 + kids + (1 if marital == "married" else 0)
        if hh < min_hh:
            p["household_size"] = min_hh


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _age(p: dict):
    """Get age as int, handling NaN/None."""
    age = p.get("age")
    if age is None:
        return None
    if isinstance(age, float) and (math.isnan(age) or math.isinf(age)):
        return None
    return int(age)


def _int_or(val, default):
    if val is None:
        return default
    if isinstance(val, float) and math.isnan(val):
        return default
    return int(val)


def _float_or(val, default):
    if val is None:
        return default
    if isinstance(val, float) and math.isnan(val):
        return default
    return float(val)


def _recalc_income_bracket(p: dict):
    income = _float_or(p.get("income"), None)
    if income is None:
        return
    if income < 25000:
        p["income_bracket"] = "under-25k"
    elif income < 50000:
        p["income_bracket"] = "25-50k"
    elif income < 75000:
        p["income_bracket"] = "50-75k"
    elif income < 100000:
        p["income_bracket"] = "75-100k"
    elif income < 150000:
        p["income_bracket"] = "100-150k"
    else:
        p["income_bracket"] = "150k+"
