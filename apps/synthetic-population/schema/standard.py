"""Standard schema for synthetic population profiles.

Defines all 142+ variables across 14 categories with types, allowed values,
ranges, and descriptions. STANDARD_SCHEMA is the merged dict of all categories.
"""

DEMOGRAPHICS = {
    "age": {"type": "int", "range": [18, 99], "description": "Age in years"},
    "age_bracket": {"type": "str", "values": ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"], "description": "Age bracket"},
    "sex": {"type": "str", "values": ["M", "F"], "description": "Sex"},
    "race": {"type": "str", "values": ["white", "black", "hispanic", "asian", "other", "multiracial"], "description": "Race/ethnicity"},
    "education": {"type": "str", "values": ["less_than_hs", "hs_diploma", "some_college", "bachelors", "graduate"], "description": "Education level"},
    "marital_status": {"type": "str", "values": ["married", "divorced", "widowed", "separated", "never_married"], "description": "Marital status"},
    "children_count": {"type": "int", "range": [0, 10], "description": "Number of children"},
    "citizenship": {"type": "str", "values": ["us_born", "naturalized", "permanent_resident", "non_citizen"], "description": "Citizenship status"},
    "veteran_status": {"type": "bool", "description": "Military veteran"},
    "disability": {"type": "bool", "description": "Has disability"},
    "language": {"type": "str", "values": ["english_only", "spanish", "other", "bilingual_english_spanish"], "description": "Primary language"},
    "household_size": {"type": "int", "range": [1, 10], "description": "Household size"},
    "generation": {"type": "str", "values": ["silent", "boomer", "gen_x", "millennial", "gen_z"], "description": "Generation"},
}

SOCIOECONOMICS = {
    "income": {"type": "int", "range": [0, 10000000], "description": "Annual income in dollars"},
    "income_bracket": {"type": "str", "values": ["under_25k", "25-50k", "50-75k", "75-100k", "100-150k", "150-200k", "200k+"], "description": "Income bracket"},
    "employment_status": {"type": "str", "values": ["employed_full", "employed_part", "self_employed", "unemployed", "retired", "student", "disabled", "homemaker"], "description": "Employment status"},
    "occupation": {"type": "str", "values": ["management", "business_finance", "computer_math", "architecture_engineering", "life_physical_social_science", "community_social_service", "legal", "education_training", "arts_media", "healthcare_practitioner", "healthcare_support", "protective_service", "food_preparation", "building_maintenance", "personal_care", "sales", "office_admin", "farming_fishing", "construction", "installation_maintenance", "production", "transportation", "military", "none"], "description": "Occupation category"},
    "industry": {"type": "str", "values": ["agriculture", "mining", "construction", "manufacturing", "wholesale", "retail", "transportation", "utilities", "information", "finance_insurance", "real_estate", "professional_scientific", "management_enterprise", "admin_support", "education", "healthcare", "arts_entertainment", "accommodation_food", "public_admin", "military", "none"], "description": "Industry sector"},
    "union_membership": {"type": "bool", "description": "Union member"},
    "homeownership": {"type": "str", "values": ["own", "rent", "other"], "description": "Homeownership status"},
    "housing_type": {"type": "str", "values": ["single_family", "townhouse", "apartment", "condo", "mobile_home", "other"], "description": "Housing type"},
    "health_insurance": {"type": "str", "values": ["employer", "marketplace", "medicare", "medicaid", "military_va", "uninsured", "other"], "description": "Health insurance type"},
    "commute_mode": {"type": "str", "values": ["drive_alone", "carpool", "public_transit", "walk", "bike", "work_from_home", "other"], "description": "Commute mode"},
    "hours_worked": {"type": "int", "range": [0, 80], "description": "Hours worked per week"},
    "employer_size": {"type": "str", "values": ["self_only", "2-9", "10-49", "50-249", "250-999", "1000+"], "description": "Employer size"},
    "food_stamp_snap": {"type": "bool", "description": "Receives SNAP/food stamp benefits"},
}

ECONOMIC_IDENTITY = {
    "income_source": {"type": "str", "values": ["wages", "self_employment", "investments", "retirement", "disability", "government_assistance", "mixed"], "description": "Primary income source"},
    "business_size": {"type": "str", "values": ["none", "sole_proprietor", "1-4_employees", "5-19_employees", "20+_employees"], "description": "Business size if owner"},
    "entrepreneurial_history": {"type": "str", "values": ["never", "attempted", "current_owner", "former_owner", "serial_entrepreneur"], "description": "Entrepreneurial history"},
    "years_in_workforce": {"type": "int", "range": [0, 60], "description": "Years in workforce"},
    "income_trajectory": {"type": "str", "values": ["declining", "stagnant", "stable", "growing", "rapidly_growing"], "description": "Income trajectory over past 5 years"},
    "class_self_identification": {"type": "str", "values": ["lower", "working", "middle", "upper_middle", "upper"], "description": "Self-identified class"},
    "economic_mobility_perception": {"type": "str", "values": ["much_worse", "worse", "same", "better", "much_better"], "description": "Perceived economic mobility vs parents"},
    "side_hustle": {"type": "bool", "description": "Has side income or gig work"},
    "benefits_quality": {"type": "str", "values": ["none", "minimal", "basic", "good", "excellent"], "description": "Quality of employer benefits"},
    "job_security_perception": {"type": "str", "values": ["very_insecure", "insecure", "neutral", "secure", "very_secure"], "description": "Perceived job security"},
}

FINANCIAL_BEHAVIOR = {
    "risk_tolerance": {"type": "str", "values": ["very_low", "low", "moderate", "high", "very_high"], "description": "Investment risk tolerance"},
    "debt_level": {"type": "str", "values": ["none", "low", "moderate", "high", "very_high"], "description": "Overall debt level"},
    "homeowner_equity": {"type": "str", "values": ["none", "low", "moderate", "high", "very_high", "not_applicable"], "description": "Home equity level"},
    "investment_types": {"type": "str", "values": ["none", "savings_only", "retirement_only", "stocks_bonds", "real_estate", "diversified", "crypto_included"], "description": "Investment portfolio type"},
    "brand_orientation": {"type": "str", "values": ["price_driven", "value_driven", "brand_loyal", "premium", "luxury"], "description": "Brand orientation when shopping"},
    "shopping_mode": {"type": "str", "values": ["mostly_online", "mostly_in_store", "mixed", "deal_hunting", "convenience_first"], "description": "Shopping mode preference"},
    "car_ownership": {"type": "str", "values": ["none", "one_used", "one_new", "multiple", "luxury"], "description": "Car ownership"},
    "streaming_services": {"type": "str", "values": ["none", "one", "two_three", "four_plus", "all_major"], "description": "Streaming service usage"},
    "credit_score_bracket": {"type": "str", "values": ["poor", "fair", "good", "very_good", "excellent"], "description": "Credit score range"},
    "savings_months": {"type": "int", "range": [0, 36], "description": "Months of expenses in savings"},
}

FINANCIAL_SOPHISTICATION = {
    "financial_literacy_score": {"type": "float", "range": [0.0, 1.0], "description": "Financial literacy (0=low, 1=high)"},
    "financial_sophistication": {"type": "str", "values": ["naive", "basic", "competent", "sophisticated", "expert"], "description": "Financial sophistication level"},
    "tax_approach": {"type": "str", "values": ["simple_standard", "itemize_self", "paid_preparer", "cpa_accountant", "tax_attorney"], "description": "Tax filing approach"},
    "retirement_strategy": {"type": "str", "values": ["none", "employer_401k_only", "ira_only", "diversified_retirement", "aggressive_early_retirement"], "description": "Retirement strategy"},
    "uses_financial_advisor": {"type": "bool", "description": "Uses a financial advisor"},
    "insurance_coverage": {"type": "str", "values": ["minimal", "basic", "moderate", "comprehensive", "over_insured"], "description": "Insurance coverage level"},
    "financial_info_source": {"type": "str", "values": ["family_friends", "social_media", "news_media", "professional_advisor", "self_research", "none"], "description": "Primary financial info source"},
    "employer_match_awareness": {"type": "bool", "description": "Aware of employer 401k match"},
}

GEOGRAPHY = {
    "state": {"type": "str", "values": [
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC"
    ], "description": "State (2-letter code)"},
    "puma": {"type": "str", "values": [], "description": "Public Use Microdata Area code (validated externally)"},
    "urban_rural": {"type": "str", "values": ["urban", "suburban", "rural"], "description": "Urban/rural classification"},
    "region": {"type": "str", "values": ["northeast", "midwest", "south", "west"], "description": "Census region"},
    "census_division": {"type": "str", "values": [
        "new_england", "mid_atlantic", "east_north_central", "west_north_central",
        "south_atlantic", "east_south_central", "west_south_central", "mountain", "pacific"
    ], "description": "Census division"},
    "metro_area": {"type": "str", "values": ["metro", "micro", "non_metro"], "description": "Metropolitan status"},
    "county_type": {"type": "str", "values": ["large_metro", "medium_metro", "small_metro", "micropolitan", "noncore"], "description": "County type (NCHS Urban-Rural)"},
    "congressional_district": {"type": "str", "values": [], "description": "Congressional district code (validated externally)"},
    "border_state": {"type": "bool", "description": "State borders Mexico or Canada"},
    "climate_zone": {"type": "str", "values": ["hot_humid", "hot_dry", "mixed_humid", "mixed_dry", "cold", "very_cold", "subarctic", "marine"], "description": "Climate zone"},
    "local_economy_type": {"type": "str", "values": ["tech_hub", "manufacturing", "agriculture", "military", "government", "tourism", "energy", "finance", "healthcare", "mixed"], "description": "Local economy type"},
    "population_density": {"type": "str", "values": ["very_low", "low", "moderate", "high", "very_high"], "description": "Population density"},
    "cost_of_living_area": {"type": "str", "values": ["very_low", "low", "moderate", "high", "very_high"], "description": "Cost of living area"},
    "time_zone": {"type": "str", "values": ["eastern", "central", "mountain", "pacific", "alaska", "hawaii"], "description": "Time zone"},
}

POLITICAL = {
    "party_id": {"type": "str", "values": ["strong_dem", "lean_dem", "independent", "lean_rep", "strong_rep", "libertarian", "green", "other"], "description": "Party identification"},
    "ideology": {"type": "str", "values": ["very_liberal", "liberal", "moderate", "conservative", "very_conservative"], "description": "Political ideology"},
    "vote_2020": {"type": "str", "values": ["biden", "trump", "third_party", "did_not_vote", "not_eligible"], "description": "2020 presidential vote"},
    "vote_2024": {"type": "str", "values": ["harris", "trump", "third_party", "did_not_vote", "not_eligible"], "description": "2024 presidential vote"},
    "registration_status": {"type": "str", "values": ["registered_dem", "registered_rep", "registered_independent", "registered_other", "not_registered"], "description": "Voter registration status"},
    "political_interest": {"type": "str", "values": ["none", "low", "moderate", "high", "very_high"], "description": "Political interest level"},
    "trust_in_government": {"type": "float", "range": [0.0, 1.0], "description": "Trust in government (0=none, 1=complete)"},
    "political_efficacy": {"type": "float", "range": [0.0, 1.0], "description": "Belief that participation matters (0=none, 1=high)"},
    "partisan_strength": {"type": "float", "range": [0.0, 1.0], "description": "Strength of partisan identity (0=weak, 1=strong)"},
    "swing_voter": {"type": "bool", "description": "Has voted for different parties"},
}

POLICY_POSITIONS = {
    "abortion": {"type": "float", "range": [0.0, 1.0], "description": "Abortion access support (0=ban, 1=unrestricted)"},
    "gun_control": {"type": "float", "range": [0.0, 1.0], "description": "Gun control support (0=no regulation, 1=strict)"},
    "immigration": {"type": "float", "range": [0.0, 1.0], "description": "Immigration openness (0=restrictionist, 1=open borders)"},
    "climate_policy": {"type": "float", "range": [0.0, 1.0], "description": "Climate action support (0=oppose, 1=aggressive action)"},
    "healthcare_system": {"type": "float", "range": [0.0, 1.0], "description": "Government healthcare role (0=free market, 1=single payer)"},
    "government_spending": {"type": "float", "range": [0.0, 1.0], "description": "Government spending support (0=cut drastically, 1=increase significantly)"},
    "trade_policy": {"type": "float", "range": [0.0, 1.0], "description": "Free trade support (0=protectionist, 1=free trade)"},
    "criminal_justice": {"type": "float", "range": [0.0, 1.0], "description": "Criminal justice reform (0=tough on crime, 1=reform/abolish)"},
    "education_policy": {"type": "float", "range": [0.0, 1.0], "description": "Public education investment (0=privatize, 1=increase public funding)"},
    "social_security": {"type": "float", "range": [0.0, 1.0], "description": "Social security support (0=privatize, 1=expand)"},
    "marijuana": {"type": "float", "range": [0.0, 1.0], "description": "Marijuana legalization (0=ban, 1=full legalization)"},
    "minimum_wage": {"type": "float", "range": [0.0, 1.0], "description": "Minimum wage increase support (0=abolish, 1=significant increase)"},
    "foreign_policy": {"type": "float", "range": [0.0, 1.0], "description": "Interventionism (0=isolationist, 1=interventionist)"},
    "tax_policy": {"type": "float", "range": [0.0, 1.0], "description": "Progressive taxation (0=flat/cut, 1=highly progressive)"},
    "tech_regulation": {"type": "float", "range": [0.0, 1.0], "description": "Tech regulation support (0=no regulation, 1=heavy regulation)"},
}

PSYCHOLOGY = {
    "racial_resentment": {"type": "float", "range": [0.0, 1.0], "description": "Racial resentment scale (0=low, 1=high)"},
    "authoritarianism": {"type": "float", "range": [0.0, 1.0], "description": "Authoritarian disposition (0=libertarian, 1=authoritarian)"},
    "social_trust": {"type": "float", "range": [0.0, 1.0], "description": "Trust in other people (0=none, 1=high)"},
    "openness": {"type": "float", "range": [0.0, 1.0], "description": "Big Five: openness to experience"},
    "conscientiousness": {"type": "float", "range": [0.0, 1.0], "description": "Big Five: conscientiousness"},
    "extraversion": {"type": "float", "range": [0.0, 1.0], "description": "Big Five: extraversion"},
    "agreeableness": {"type": "float", "range": [0.0, 1.0], "description": "Big Five: agreeableness"},
    "neuroticism": {"type": "float", "range": [0.0, 1.0], "description": "Big Five: neuroticism"},
    "institutional_confidence": {"type": "float", "range": [0.0, 1.0], "description": "Confidence in institutions (0=none, 1=high)"},
    "meritocracy_belief": {"type": "float", "range": [0.0, 1.0], "description": "Belief in meritocracy (0=skeptic, 1=strong believer)"},
}

RELIGION = {
    "religion_affiliation": {"type": "str", "values": ["evangelical", "mainline_protestant", "catholic", "mormon", "jewish", "muslim", "hindu", "buddhist", "other_christian", "other_faith", "agnostic", "atheist", "nothing_in_particular"], "description": "Religious affiliation"},
    "religion_denomination": {"type": "str", "values": ["baptist", "methodist", "lutheran", "presbyterian", "pentecostal", "episcopal", "church_of_christ", "adventist", "nondenominational", "other", "not_applicable"], "description": "Denomination if Christian"},
    "religion_attendance": {"type": "str", "values": ["never", "seldom", "few_times_year", "monthly", "weekly", "more_than_weekly"], "description": "Religious service attendance"},
    "religion_biblical_literalism": {"type": "str", "values": ["literal_word", "inspired_not_literal", "ancient_fables", "not_applicable"], "description": "View of Bible"},
    "religion_importance": {"type": "str", "values": ["not_at_all", "not_very", "somewhat", "very", "extremely"], "description": "Importance of religion in life"},
}

MEDIA_DIET = {
    "primary_news_source": {"type": "str", "values": ["fox_news", "cnn", "msnbc", "network_tv", "local_tv", "npr", "nyt_wapo", "social_media", "talk_radio", "online_independent", "none"], "description": "Primary news source"},
    "secondary_news_source": {"type": "str", "values": ["fox_news", "cnn", "msnbc", "network_tv", "local_tv", "npr", "nyt_wapo", "social_media", "talk_radio", "online_independent", "none"], "description": "Secondary news source"},
    "podcast_listener": {"type": "bool", "description": "Listens to podcasts"},
    "podcast_type": {"type": "str", "values": ["political", "news", "comedy", "sports", "business", "true_crime", "educational", "none", "mixed"], "description": "Primary podcast type"},
    "social_media_primary": {"type": "str", "values": ["facebook", "twitter_x", "instagram", "tiktok", "youtube", "reddit", "truth_social", "nextdoor", "none"], "description": "Primary social media platform"},
    "social_media_news": {"type": "bool", "description": "Gets news from social media"},
    "youtube_political": {"type": "str", "values": ["never", "rarely", "sometimes", "often", "primary_source"], "description": "YouTube political content consumption"},
    "talk_radio": {"type": "str", "values": ["never", "rarely", "sometimes", "often", "daily"], "description": "Talk radio listening frequency"},
    "newspaper_reader": {"type": "str", "values": ["never", "rarely", "sometimes", "regularly", "daily"], "description": "Newspaper reading frequency"},
    "news_frequency": {"type": "str", "values": ["never", "few_times_month", "few_times_week", "daily", "multiple_daily"], "description": "Overall news consumption frequency"},
    "media_trust": {"type": "float", "range": [0.0, 1.0], "description": "Trust in mainstream media (0=none, 1=complete)"},
    "info_ecosystem": {"type": "str", "values": ["mainstream_left", "mainstream_center", "mainstream_right", "right_wing_media", "independent_left", "independent_right", "conspiracy_adjacent", "disengaged"], "description": "Information ecosystem"},
    "local_news_engagement": {"type": "str", "values": ["none", "low", "moderate", "high"], "description": "Local news engagement level"},
}

SCIENCE_HEALTH = {
    "vaccine_attitude": {"type": "str", "values": ["pro_vaccine", "generally_pro", "hesitant", "anti_vaccine", "selective"], "description": "General vaccine attitude"},
    "covid_vaccine_status": {"type": "str", "values": ["boosted", "fully_vaccinated", "partially_vaccinated", "unvaccinated_willing", "unvaccinated_unwilling"], "description": "COVID vaccine status"},
    "climate_change_belief": {"type": "str", "values": ["human_caused_urgent", "human_caused", "natural_cycles", "not_happening", "unsure"], "description": "Climate change belief"},
    "climate_policy_support": {"type": "float", "range": [0.0, 1.0], "description": "Climate policy support (0=oppose, 1=strong support)"},
    "evolution_belief": {"type": "str", "values": ["evolution_natural", "evolution_guided", "creationism", "unsure"], "description": "Evolution belief"},
    "gmo_attitude": {"type": "str", "values": ["safe", "mostly_safe", "concerned", "opposed", "unsure"], "description": "GMO attitude"},
    "trust_medical_establishment": {"type": "float", "range": [0.0, 1.0], "description": "Trust in medical establishment (0=none, 1=complete)"},
    "trust_scientific_establishment": {"type": "float", "range": [0.0, 1.0], "description": "Trust in scientific establishment (0=none, 1=complete)"},
    "covid_lockdown_opinion": {"type": "str", "values": ["too_strict", "about_right", "not_strict_enough", "depends_on_area"], "description": "Opinion on COVID lockdowns"},
    "pharma_trust": {"type": "float", "range": [0.0, 1.0], "description": "Trust in pharmaceutical companies (0=none, 1=complete)"},
    "mental_health_openness": {"type": "str", "values": ["very_closed", "reluctant", "neutral", "open", "very_open"], "description": "Openness to seeking mental health treatment"},
}

ORIGIN_MOBILITY = {
    "native_born": {"type": "bool", "description": "Born in the US"},
    "generation_if_immigrant": {"type": "str", "values": ["first", "second", "third_plus", "not_applicable"], "description": "Immigration generation"},
    "years_in_country": {"type": "int", "range": [0, 99], "description": "Years living in the US"},
    "moved_for_work": {"type": "bool", "description": "Has relocated for employment"},
    "hometown_vs_current": {"type": "str", "values": ["same_town", "same_state", "different_state", "different_country"], "description": "Current location vs hometown"},
}

SYSTEM_METADATA = {
    "profile_id": {"type": "str", "values": [], "description": "Unique profile identifier (UUID)"},
    "batch_id": {"type": "str", "values": [], "description": "Generation batch identifier"},
    "created_at": {"type": "str", "values": [], "description": "Profile creation timestamp (ISO 8601)"},
    "updated_at": {"type": "str", "values": [], "description": "Last update timestamp (ISO 8601)"},
    "archetype_id": {"type": "str", "values": [], "description": "Archetype identifier"},
    "backstory": {"type": "str", "values": [], "description": "Generated narrative backstory"},
}

# All categories for iteration
ALL_CATEGORIES = [
    DEMOGRAPHICS, SOCIOECONOMICS, ECONOMIC_IDENTITY, FINANCIAL_BEHAVIOR,
    FINANCIAL_SOPHISTICATION, GEOGRAPHY, POLITICAL, POLICY_POSITIONS,
    PSYCHOLOGY, RELIGION, MEDIA_DIET, SCIENCE_HEALTH, ORIGIN_MOBILITY,
    SYSTEM_METADATA,
]

# Merged schema of all variables
STANDARD_SCHEMA: dict = {}
for _category in ALL_CATEGORIES:
    STANDARD_SCHEMA.update(_category)
