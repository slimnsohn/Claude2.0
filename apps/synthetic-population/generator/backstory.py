"""
Backstory Generator
Produces varied, template-based narrative paragraphs from a demographic profile dict.
"""

import random

# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------

STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "Washington D.C.",
}

EDUCATION_LABELS = {
    "less_than_hs": "never finished high school",
    "hs_diploma": "a high school diploma",
    "some_college": "some college",
    "associates": "an associate's degree",
    "bachelors": "a bachelor's degree",
    "graduate": "a graduate degree",
    "professional": "a professional degree",
}

RACE_LABELS = {
    "white": "white",
    "black": "Black",
    "hispanic": "Hispanic",
    "asian": "Asian",
    "native": "Native American",
    "multiracial": "multiracial",
    "other": "",
}

NEWS_LABELS = {
    "fox_news": "Fox News",
    "msnbc": "MSNBC",
    "cnn": "CNN",
    "npr": "NPR",
    "local_tv": "local TV news",
    "online_only": "online sources",
    "newspapers": "newspapers",
    "none": "no regular news source",
    "oann": "OAN",
    "newsmax": "Newsmax",
    "abc_nbc_cbs": "network TV news",
}

SOCIAL_LABELS = {
    "facebook": "Facebook",
    "twitter": "X (formerly Twitter)",
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "none": "no particular social platform",
    "reddit": "Reddit",
    "linkedin": "LinkedIn",
}

PARTY_LABELS = {
    "strong_rep": "a staunch Republican",
    "lean_rep": "a Republican-leaning voter",
    "independent": "a political independent",
    "lean_dem": "a Democrat-leaning voter",
    "strong_dem": "a committed Democrat",
    "libertarian": "a libertarian",
    "apolitical": "largely apolitical",
}

VOTE_LABELS = {
    "trump": "Donald Trump",
    "harris": "Kamala Harris",
    "third_party": "a third-party candidate",
    "did_not_vote": "did not vote",
}

OCCUPATION_DISPLAY = {
    "professional": "professional",
    "service": "service worker",
    "sales": "salesperson",
    "construction": "construction worker",
    "production": "production worker",
    "management": "manager",
    "other": "worker",
    "management_business_science_arts": "professional",
    "natural_resources_construction_maintenance": "tradesperson",
    "production_transportation_material_moving": "production worker",
    "sales_office": "office worker",
    "service_occupations": "service worker",
}

OCCUPATION_ARTICLES = {
    "a": [
        "accountant", "architect", "attorney", "auditor", "baker",
        "barista", "carpenter", "cashier", "chef", "coach",
        "consultant", "contractor", "custodian", "data analyst",
        "delivery driver", "dental hygienist", "designer",
        "diesel mechanic", "dispatcher", "electrician",
        "financial advisor", "firefighter", "forklift operator",
        "graphic designer", "healthcare worker", "home health aide",
        "homemaker", "hotel manager", "insurance agent",
        "landscaper", "librarian", "line cook", "locksmith",
        "machinist", "manager", "mechanic", "medical assistant",
        "nurse", "painter", "paralegal", "paramedic",
        "pharmacist", "pilot", "plumber", "police officer",
        "postal worker", "professor", "programmer", "project manager",
        "real estate agent", "receptionist", "recruiter",
        "registered nurse", "retail worker", "sales rep",
        "security guard", "server", "social worker",
        "software engineer", "soldier", "store manager",
        "surgeon", "teacher", "technician", "therapist",
        "truck driver", "tutor", "veterinarian", "warehouse worker",
        "welder", "writer",
    ],
}


def _article(occupation: str) -> str:
    """Return 'an' if occupation starts with a vowel sound, else 'a'."""
    if not occupation:
        return "a"
    return "an" if occupation[0].lower() in "aeiou" else "a"


def _pronouns(sex: str):
    """Return (subject, object, possessive) pronouns."""
    if sex.lower() in ("f", "female", "woman"):
        return "She", "her", "her"
    return "He", "him", "his"


def _format_income(income) -> str:
    if income is None or (isinstance(income, float) and (income != income)):  # NaN check
        return "an undisclosed amount"
    income = max(0, int(income))  # clamp negatives to 0
    return f"${income:,}"


def _state_name(code: str) -> str:
    return STATE_NAMES.get(code.upper(), code)


def _edu_phrase(education: str) -> str:
    return EDUCATION_LABELS.get(education, education.replace("_", " "))


def _race_label(race: str) -> str:
    return RACE_LABELS.get(race, race.replace("_", " "))


# ---------------------------------------------------------------------------
# Slot generators
# ---------------------------------------------------------------------------

def _slot_opening(p: dict) -> str:
    age = p.get("age", "")
    state_code = p.get("state", "")
    state = _state_name(state_code)
    race = _race_label(p.get("race", ""))
    sex = p.get("sex", "M")
    gender_word = "woman" if sex.lower() in ("f", "female", "woman") else "man"
    urban = p.get("urban_rural", "")
    descriptor = ""
    if urban == "rural":
        descriptor = "rural "
    elif urban == "urban":
        descriptor = "urban "
    elif urban == "suburban":
        descriptor = "suburban "

    race_gender = f"{race} {gender_word}".strip()
    if not race:
        race_gender = gender_word

    templates = [
        f"{age}-year-old {race_gender} who lives in {descriptor}{state}",
        f"{age}-year-old {race_gender} from {state}",
        f"{age}-year-old {race_gender} based in {state}",
        f"{age}-year-old {race_gender} who calls {state} home",
        f"{age}-year-old {race_gender} who grew up in and still lives in {state}",
        f"{age}-year-old {race_gender} residing in {state}",
    ]
    chosen = random.choice(templates)
    # Capitalize first letter for sentence start
    first_name = random.choice([
        "Alex", "Casey", "Jordan", "Morgan", "Taylor", "Sam",
        "Chris", "Dana", "Jamie", "Pat",
    ])
    sub, _, _ = _pronouns(sex)
    name_templates = [
        f"{first_name} is a {chosen}.",
        f"Meet {first_name}, a {chosen}.",
        f"{first_name}, a {chosen}, is the subject of this profile.",
    ]
    return random.choice(name_templates)


def _slot_education_work(p: dict, subj: str, poss: str) -> str:
    edu = p.get("education", "")
    raw_occ = p.get("occupation") or ""
    occ = OCCUPATION_DISPLAY.get(raw_occ, raw_occ.replace("_", " "))
    edu_phrase = _edu_phrase(edu)
    art = _article(occ)

    if edu == "less_than_hs":
        edu_templates = [
            f"{subj} left school before finishing and",
            f"{subj} never completed high school and",
            f"Without a high school diploma, {subj.lower()}",
        ]
    elif edu == "hs_diploma":
        edu_templates = [
            f"{subj} graduated high school and",
            f"After earning {poss} high school diploma, {subj.lower()}",
            f"{subj} has a high school diploma and",
        ]
    elif edu in ("some_college", "associates"):
        edu_templates = [
            f"{subj} attended college and",
            f"With {edu_phrase}, {subj.lower()}",
            f"{subj} has {edu_phrase} and",
        ]
    else:
        edu_templates = [
            f"{subj} holds {edu_phrase} and",
            f"With {edu_phrase}, {subj.lower()}",
            f"{subj} earned {edu_phrase} and",
        ]

    edu_part = random.choice(edu_templates)

    if occ:
        work_templates = [
            f" works as {art} {occ}.",
            f" has built a career as {art} {occ}.",
            f" currently works as {art} {occ}.",
            f" earns a living as {art} {occ}.",
        ]
        return edu_part + random.choice(work_templates)
    else:
        return edu_part + " is currently not employed."


def _slot_family(p: dict, subj: str, poss: str) -> str:
    marital = p.get("marital_status", "")
    kids = p.get("children_count", 0)

    if marital == "married":
        marital_phrases = [
            f"{subj} is married",
            f"{subj} has been married",
        ]
    elif marital == "divorced":
        marital_phrases = [
            f"{subj} is divorced",
            f"{subj} went through a divorce",
        ]
    elif marital == "widowed":
        marital_phrases = [
            f"{subj} is widowed",
            f"{subj} lost {poss} spouse",
        ]
    elif marital == "single":
        marital_phrases = [
            f"{subj} is single",
            f"{subj} has never married",
            f"{subj} is not currently married",
        ]
    elif marital == "cohabiting":
        marital_phrases = [
            f"{subj} lives with a partner",
            f"{subj} is in a committed relationship",
        ]
    else:
        marital_phrases = [f"{subj} is {marital.replace('_', ' ')}"]

    marital_part = random.choice(marital_phrases)

    if kids == 0:
        child_templates = [
            f"{marital_part} and has no children.",
            f"{marital_part} with no kids.",
            f"{marital_part} and does not have children.",
        ]
    elif kids == 1:
        child_templates = [
            f"{marital_part} with one child.",
            f"{marital_part} and has a child.",
            f"{marital_part} and is raising one child.",
        ]
    else:
        child_templates = [
            f"{marital_part} with {kids} children.",
            f"{marital_part} and has {kids} kids.",
            f"{marital_part} and is raising {kids} children.",
        ]

    return random.choice(child_templates)


def _slot_religion(p: dict, subj: str, poss: str) -> str:
    affil = p.get("religion_affiliation", "none")
    attend = p.get("religion_attendance", "never")

    if affil == "none":
        templates = [
            f"{subj} does not identify with any religion.",
            f"{subj} is not religious.",
            f"{subj} considers {subj.lower()}self non-religious.",
            f"Religion plays no role in {poss} life.",
        ]
    elif attend == "never":
        templates = [
            f"{subj} identifies as {affil.replace('_', ' ')} but rarely if ever attends services.",
            f"Though nominally {affil.replace('_', ' ')}, {subj.lower()} does not attend services.",
            f"{subj} has a cultural connection to {affil.replace('_', ' ')} but is not observant.",
        ]
    elif attend == "weekly":
        templates = [
            f"{subj} is an active {affil.replace('_', ' ')} and attends services weekly.",
            f"Faith is central to {poss} life; {subj.lower()} attends {affil.replace('_', ' ')} services every week.",
            f"{subj} is a committed {affil.replace('_', ' ')} who worships weekly.",
        ]
    elif attend in ("monthly", "occasionally"):
        templates = [
            f"{subj} identifies as {affil.replace('_', ' ')} and attends services occasionally.",
            f"{subj} is a {attend} churchgoer who identifies as {affil.replace('_', ' ')}.",
            f"Though {affil.replace('_', ' ')}, {subj.lower()} attends services only sometimes.",
        ]
    else:
        templates = [
            f"{subj} identifies as {affil.replace('_', ' ')}.",
            f"Religion plays some role in {poss} life; {subj.lower()} is {affil.replace('_', ' ')}.",
        ]

    return random.choice(templates)


def _slot_politics_media(p: dict, subj: str) -> str:
    party = p.get("party_id", "independent")
    vote = p.get("vote_2024", "")
    news_key = p.get("primary_news_source") or ""
    social_key = p.get("social_media_primary") or ""

    party_label = PARTY_LABELS.get(party, party.replace("_", " "))
    vote_label = VOTE_LABELS.get(vote, "")

    vote_part = ""
    if vote_label and vote_label != "did not vote":
        vote_part = f" and voted for {vote_label} in 2024"
    elif vote_label == "did not vote":
        vote_part = " and sat out the 2024 election"

    # Build media sentence only if we have data
    news_label = NEWS_LABELS.get(news_key, news_key.replace("_", " ")) if news_key else ""
    social_label = SOCIAL_LABELS.get(social_key, social_key.replace("_", " ")) if social_key else ""

    if news_label and social_label:
        media_part = f" {subj} primarily gets news from {news_label} and is most active on {social_label}."
    elif news_label:
        media_part = f" {subj} primarily gets news from {news_label}."
    elif social_label:
        media_part = f" {subj} is most active on {social_label}."
    else:
        media_part = ""

    templates = [
        f"{subj} is {party_label}{vote_part}.{media_part}",
        f"Politically, {subj.lower()} is {party_label}{vote_part}.{media_part}",
        f"{subj} identifies as {party_label}{vote_part}.{media_part}",
    ]

    return random.choice(templates)


def _slot_financial(p: dict, subj: str, poss: str) -> str:
    income_source = p.get("income_source", "wages")
    tax_approach = p.get("tax_approach", "software_basic")
    income = p.get("income", 0)
    biz_size = p.get("business_size", "")
    income_str = _format_income(income)

    tax_desc = {
        "software_basic": "uses basic tax software to file",
        "software_advanced": "uses tax software to handle the details",
        "professional_cpa": "works with a CPA",
        "free_file": "uses the IRS free file system",
        "accountant": "relies on an accountant",
        "self_prepared": "prepares taxes manually",
    }.get(tax_approach, "files taxes independently")

    if income_source == "self_employment":
        biz_qualifier = f" with {biz_size.replace('_', ' ')} employees" if biz_size else ""
        templates = [
            f"{subj} is self-employed{biz_qualifier}, bringing in around {income_str} per year, and {tax_desc} each spring.",
            f"Running {poss} own operation{biz_qualifier}, {subj.lower()} earns roughly {income_str} annually and {tax_desc}.",
            f"{subj} owns and runs a business{biz_qualifier}, generating about {income_str} a year; {subj.lower()} {tax_desc}.",
        ]
    elif income_source == "business_owner":
        biz_qualifier = f" with {biz_size.replace('_', ' ')} employees" if biz_size else ""
        templates = [
            f"{subj} owns a business{biz_qualifier} that generates around {income_str} per year and {tax_desc}.",
            f"As a business owner{biz_qualifier}, {subj.lower()} brings in roughly {income_str} annually and {tax_desc}.",
        ]
    elif income_source == "investments":
        templates = [
            f"{subj} draws most of {poss} income from investments, totaling around {income_str} per year, and {tax_desc}.",
            f"Investment income of about {income_str} per year sustains {poss} lifestyle; {subj.lower()} {tax_desc}.",
        ]
    elif income_source == "benefits":
        templates = [
            f"{subj} relies primarily on government benefits as {poss} income source and {tax_desc}.",
            f"Benefits make up the bulk of {poss} income; {subj.lower()} {tax_desc}.",
        ]
    else:  # wages / salary
        templates = [
            f"{subj} earns around {income_str} per year in wages and {tax_desc}.",
            f"With an annual income of roughly {income_str}, {subj.lower()} {tax_desc}.",
            f"{subj} brings home about {income_str} a year and {tax_desc}.",
        ]

    return random.choice(templates)


def _slot_economic_perspective(p: dict, subj: str, poss: str) -> str:
    income = p.get("income", 0)
    edu = p.get("education", "")
    party = p.get("party_id", "independent")

    if income < 30000:
        econ_templates = [
            f"{subj} knows what it's like to stretch a dollar and thinks carefully about every purchase.",
            f"Money is tight, and {subj.lower()} has learned to be resourceful.",
            f"{subj} lives paycheck to paycheck and worries about unexpected expenses.",
        ]
    elif income < 60000:
        econ_templates = [
            f"{subj} gets by comfortably but watches spending closely.",
            f"Financially, {subj.lower()} feels stable but not flush.",
            f"{subj} considers {subj.lower()}self working class and believes in earning what you get.",
        ]
    elif income < 100000:
        econ_templates = [
            f"{subj} has worked hard to reach a comfortable middle-class life.",
            f"Financially, {subj.lower()} feels solidly middle class and wants to protect what {poss} built.",
            f"{subj} is in a good place economically and thinks about long-term security.",
        ]
    else:
        econ_templates = [
            f"{subj} has achieved significant financial success and thinks carefully about taxes and wealth preservation.",
            f"With a strong income, {subj.lower()} is focused on investing and building long-term wealth.",
            f"{subj} earns well and has the financial flexibility to plan ahead.",
        ]

    return random.choice(econ_templates)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_backstory(profile: dict) -> str:
    """
    Generate a varied narrative backstory from a demographic profile dict.

    Returns a multi-sentence paragraph string.
    """
    sex = profile.get("sex", "M")
    subj, obj, poss = _pronouns(sex)

    sentences = [
        _slot_opening(profile),
        _slot_education_work(profile, subj, poss),
        _slot_family(profile, subj, poss),
        _slot_religion(profile, subj, poss),
        _slot_politics_media(profile, subj),
        _slot_financial(profile, subj, poss),
        _slot_economic_perspective(profile, subj, poss),
    ]

    return " ".join(sentences)
