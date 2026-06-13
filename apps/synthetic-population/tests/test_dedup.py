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
