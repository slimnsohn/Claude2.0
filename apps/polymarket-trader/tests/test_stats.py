import statistics

import pytest

from pmtrader.backtest.stats import bootstrap_ci, max_drawdown, sharpe, walk_forward


class TestBootstrapCI:
    def test_contains_mean_for_positive_sample(self):
        trades = [0.01] * 150 + [-0.005] * 50  # clearly positive EV
        lo, hi = bootstrap_ci([float(x) for x in trades], n_boot=2000, alpha=0.05, seed=7)
        assert lo > 0
        assert lo < statistics.mean(trades) < hi

    def test_straddles_zero_for_noise(self):
        lo, hi = bootstrap_ci([0.01, -0.01] * 100, n_boot=2000, alpha=0.05, seed=7)
        assert lo < 0 < hi

    def test_deterministic_with_seed(self):
        xs = [0.01, -0.02, 0.03] * 40
        assert bootstrap_ci(xs, seed=1) == bootstrap_ci(xs, seed=1)

    def test_empty_and_tiny_samples(self):
        assert bootstrap_ci([]) == (0.0, 0.0)
        lo, hi = bootstrap_ci([0.05], seed=1)
        assert lo == hi == pytest.approx(0.05)


class TestWalkForward:
    def test_windows_never_overlap_eval(self):
        folds = walk_forward(n=1000, train=400, test=200)
        for tr, te in folds:
            assert max(tr) < min(te)  # strictly out-of-sample
        assert len(folds) == 3

    def test_covers_expected_ranges(self):
        folds = walk_forward(n=1000, train=400, test=200)
        (tr0, te0) = folds[0]
        assert (tr0.start, tr0.stop) == (0, 400)
        assert (te0.start, te0.stop) == (400, 600)
        (tr2, te2) = folds[2]
        assert (te2.start, te2.stop) == (800, 1000)

    def test_too_little_data_returns_empty(self):
        assert walk_forward(n=100, train=400, test=200) == []


class TestRiskMetrics:
    def test_max_drawdown(self):
        assert max_drawdown([1.0, 1.2, 0.9, 1.1]) == pytest.approx(0.25)

    def test_max_drawdown_monotonic_up_is_zero(self):
        assert max_drawdown([1.0, 1.1, 1.2]) == 0.0

    def test_max_drawdown_empty(self):
        assert max_drawdown([]) == 0.0

    def test_sharpe_constant_returns_capped(self):
        s = sharpe([0.01] * 50)
        assert s > 0 and s == pytest.approx(100.0)  # zero-vol guard cap

    def test_sharpe_zero_mean(self):
        assert sharpe([0.01, -0.01] * 50) == pytest.approx(0.0, abs=0.5)

    def test_sharpe_empty(self):
        assert sharpe([]) == 0.0
