from core.ev import (
    edge_pct, ev_dollars, extract_implied_mu, posterior_prob_from_mu,
)


def test_edge_pct_positive():
    assert abs(edge_pct(0.55, 100) - 0.10) < 1e-9


def test_edge_pct_negative():
    assert edge_pct(0.45, 100) < 0


def test_ev_dollars():
    assert abs(ev_dollars(0.10, 200) - 20.0) < 1e-9


def test_extract_implied_mu_at_50pct_returns_line():
    mu = extract_implied_mu(consensus_prob=0.5, line=22.5, sigma=4.0)
    assert abs(mu - 22.5) < 1e-9


def test_extract_implied_mu_at_high_prob_above_line():
    mu = extract_implied_mu(consensus_prob=0.8413, line=22.5, sigma=4.0)
    assert 26.0 < mu < 27.0


def test_posterior_prob_from_mu_round_trip():
    mu_in = 25.0
    prob = posterior_prob_from_mu(mu=mu_in, line=22.5, sigma=4.0)
    mu_back = extract_implied_mu(consensus_prob=prob, line=22.5, sigma=4.0)
    assert abs(mu_back - mu_in) < 1e-3


def test_posterior_prob_from_mu_clipped():
    p = posterior_prob_from_mu(mu=100, line=22.5, sigma=4.0)
    assert 0.999 < p <= 1.0
