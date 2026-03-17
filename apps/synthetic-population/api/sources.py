"""Data Sources API — reports what's loaded, what's missing, and how to get it."""
import json
from pathlib import Path
from flask import Blueprint, jsonify, current_app

sources_bp = Blueprint("sources", __name__)

# Each source: what it provides, where to get it, what format
SOURCE_REGISTRY = [
    {
        "id": "acs_pums",
        "name": "ACS PUMS",
        "full_name": "American Community Survey Public Use Microdata Sample",
        "provider": "U.S. Census Bureau",
        "url": "https://api.census.gov/data/2022/acs/acs1/pums",
        "access": "Public API — no registration required",
        "access_level": "public_api",
        "format": "JSON API / CSV download",
        "update_cycle": "Annual (December)",
        "records": "~3.5M (1-year), ~16M (5-year)",
        "variables_provided": [
            "age", "age_bracket", "sex", "race", "education", "income", "income_bracket",
            "marital_status", "state", "veteran_status", "disability", "citizenship",
            "language", "household_size", "employment_status", "homeownership",
            "health_insurance", "commute_mode"
        ],
        "raw_file": "acs_pums_sample.csv",
        "layer": "Demographics (backbone)",
    },
    {
        "id": "ces",
        "name": "CES",
        "full_name": "Cooperative Election Study",
        "provider": "Harvard University / Tufts / YouGov",
        "url": "https://dataverse.harvard.edu/dataverse/cces",
        "access": "Free account required — Harvard Dataverse login",
        "access_level": "free_registration",
        "format": "Stata (.dta) or CSV",
        "update_cycle": "Annual (election + off-years)",
        "records": "~60,000/year",
        "variables_provided": [
            "party_id", "ideology", "vote_2020", "vote_2024",
            "abortion", "gun_control", "immigration", "climate_policy",
            "healthcare_system", "government_spending", "trade_policy",
            "criminal_justice", "education_policy", "social_security",
            "marijuana", "minimum_wage", "foreign_policy", "tax_policy", "tech_regulation"
        ],
        "raw_file": "ces_2022.csv",
        "layer": "Political identity + policy positions",
    },
    {
        "id": "anes",
        "name": "ANES",
        "full_name": "American National Election Studies",
        "provider": "Stanford / University of Michigan",
        "url": "https://electionstudies.org/data-center/",
        "access": "Free account required — electionstudies.org registration",
        "access_level": "free_registration",
        "format": "Stata (.dta) or CSV",
        "update_cycle": "Election years (biennial)",
        "records": "~8,000/wave",
        "variables_provided": [
            "racial_resentment", "authoritarianism", "social_trust",
            "openness", "conscientiousness", "extraversion", "agreeableness",
            "neuroticism", "institutional_confidence", "meritocracy_belief", "political_efficacy"
        ],
        "raw_file": "anes_2024.csv",
        "layer": "Psychology / personality / values",
    },
    {
        "id": "gss",
        "name": "GSS",
        "full_name": "General Social Survey",
        "provider": "NORC at University of Chicago",
        "url": "https://gss.norc.org/get-the-data",
        "access": "Public download — no registration required",
        "access_level": "public_download",
        "format": "Stata (.dta), SPSS (.sav), or CSV",
        "update_cycle": "Biennial",
        "records": "~3,000/wave",
        "variables_provided": [
            "religion_affiliation", "religion_denomination", "religion_attendance",
            "religion_biblical_literalism", "religion_importance",
            "social_trust", "institutional_confidence"
        ],
        "raw_file": "gss_2022.csv",
        "layer": "Religion / social capital",
    },
    {
        "id": "pew_atp",
        "name": "Pew ATP",
        "full_name": "Pew American Trends Panel",
        "provider": "Pew Research Center",
        "url": "https://www.pewresearch.org/american-trends-panel-datasets/",
        "access": "Must request access — researcher application required",
        "access_level": "request_required",
        "format": "SPSS (.sav) or Stata (.dta)",
        "update_cycle": "130+ waves, ongoing",
        "records": "5,000–12,000/wave",
        "variables_provided": [
            "primary_news_source", "secondary_news_source", "social_media_primary",
            "social_media_news", "podcast_listener", "media_trust", "info_ecosystem",
            "vaccine_attitude", "climate_change_belief", "trust_scientific_establishment"
        ],
        "raw_file": "pew_atp_w120.csv",
        "layer": "Media diet / science attitudes",
    },
    {
        "id": "brfss",
        "name": "BRFSS",
        "full_name": "Behavioral Risk Factor Surveillance System",
        "provider": "CDC",
        "url": "https://www.cdc.gov/brfss/annual_data/annual_data.htm",
        "access": "Public download — no registration required",
        "access_level": "public_download",
        "format": "ASCII fixed-width or SAS transport (.xpt)",
        "update_cycle": "Annual",
        "records": "400,000+/year",
        "variables_provided": [
            "health_insurance", "disability"
        ],
        "custom_variables": [
            "brfss:chronic_conditions", "brfss:exercise_frequency",
            "brfss:tobacco_use", "brfss:alcohol_use", "brfss:mental_health_days"
        ],
        "raw_file": "brfss_2023.csv",
        "layer": "Health behaviors",
    },
    {
        "id": "cps",
        "name": "CPS",
        "full_name": "Current Population Survey",
        "provider": "U.S. Census Bureau / Bureau of Labor Statistics",
        "url": "https://www.census.gov/data/datasets/time-series/demo/cps/cps-basic.html",
        "access": "Public download — no registration required",
        "access_level": "public_download",
        "format": "CSV microdata",
        "update_cycle": "Monthly",
        "records": "~60,000/month",
        "variables_provided": [
            "employment_status", "occupation", "industry",
            "union_membership", "hours_worked", "income_source"
        ],
        "raw_file": "cps_2024.csv",
        "layer": "Employment / labor market",
    },
    {
        "id": "finra_nfcs",
        "name": "FINRA NFCS",
        "full_name": "National Financial Capability Study",
        "provider": "FINRA Investor Education Foundation",
        "url": "https://www.usfinancialcapability.org/downloads.php",
        "access": "Public download — no registration required",
        "access_level": "public_download",
        "format": "CSV or SPSS (.sav)",
        "update_cycle": "Every 3 years",
        "records": "~27,000",
        "variables_provided": [
            "financial_literacy_score", "financial_sophistication", "tax_approach",
            "retirement_strategy", "uses_financial_advisor", "insurance_coverage"
        ],
        "raw_file": "finra_nfcs_2021.csv",
        "layer": "Financial capability / literacy",
    },
    {
        "id": "fed_scf",
        "name": "Fed SCF",
        "full_name": "Survey of Consumer Finances",
        "provider": "Federal Reserve Board",
        "url": "https://www.federalreserve.gov/econres/scfindex.htm",
        "access": "Public download — no registration required",
        "access_level": "public_download",
        "format": "Stata (.dta) or CSV extract",
        "update_cycle": "Every 3 years",
        "records": "~6,000",
        "variables_provided": [
            "risk_tolerance", "investment_types", "debt_level", "savings_months"
        ],
        "custom_variables": [
            "fed_scf:net_worth_bracket", "fed_scf:financial_planning_horizon"
        ],
        "raw_file": "fed_scf_2022.csv",
        "layer": "Wealth / investment behavior",
    },
]


@sources_bp.route("/api/sources")
def get_sources():
    """Return all data sources with loaded/missing status."""
    data_dir = Path(current_app.config["DATA_DIR"])
    raw_dir = data_dir / "raw"

    # Check which sources have data loaded
    # A source is "loaded" if its raw file exists OR if the profile registry
    # contains variables from that source
    registry_path = data_dir / "profiles" / "registry.json"
    profile_vars = set()
    profile_count = 0
    if registry_path.exists():
        profiles = json.loads(registry_path.read_text())
        profile_count = len(profiles)
        if profiles:
            # Collect all non-null variable names from first profile
            for p in profiles[:10]:  # Sample first 10
                for k, v in p.items():
                    if v is not None:
                        profile_vars.add(k)

    result = []
    total_vars = 0
    loaded_vars = 0

    for source in SOURCE_REGISTRY:
        src = dict(source)
        all_vars = source["variables_provided"] + source.get("custom_variables", [])
        total_vars += len(all_vars)

        # Check if raw file exists
        raw_exists = (raw_dir / source["raw_file"]).exists() if source.get("raw_file") else False

        # Check which variables are present in profiles
        present = [v for v in source["variables_provided"] if v in profile_vars]
        missing = [v for v in source["variables_provided"] if v not in profile_vars]
        loaded_vars += len(present)

        if raw_exists and len(present) == len(source["variables_provided"]):
            status = "loaded"
        elif raw_exists or len(present) > 0:
            status = "partial"
        else:
            status = "missing"

        src["status"] = status
        src["variables_present"] = present
        src["variables_missing"] = missing
        src["variables_total"] = len(all_vars)
        src["variables_loaded"] = len(present)
        src["raw_file_exists"] = raw_exists

        result.append(src)

    return jsonify({
        "sources": result,
        "summary": {
            "total_sources": len(SOURCE_REGISTRY),
            "loaded": sum(1 for s in result if s["status"] == "loaded"),
            "partial": sum(1 for s in result if s["status"] == "partial"),
            "missing": sum(1 for s in result if s["status"] == "missing"),
            "total_variables": total_vars,
            "loaded_variables": loaded_vars,
            "profile_count": profile_count,
        }
    })
