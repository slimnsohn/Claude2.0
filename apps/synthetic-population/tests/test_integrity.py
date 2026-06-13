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
