"""Allocator: performance-weighted budgets, edge-decay demotion, paper gate."""
import pytest

from pmtrader.allocator import Allocator, GateStatus

NOW = 1_000_000.0
DAY = 86_400.0


def trades(mean, n, alt=0.0, start_ts=NOW - 30 * DAY):
    """Synthetic per-trade pnl list with a little alternation for variance."""
    out = []
    for i in range(n):
        pnl = mean + (alt if i % 2 == 0 else -alt)
        out.append({"pnl": pnl, "ts": start_ts + i * 600})
    return out


@pytest.fixture
def alloc():
    return Allocator(strategies=["s1", "s2", "s3"], bankroll=10_000.0)


class TestInitialState:
    def test_equal_weights_at_start(self, alloc):
        w = alloc.weights()
        assert w == {"s1": pytest.approx(1 / 3), "s2": pytest.approx(1 / 3),
                     "s3": pytest.approx(1 / 3)}

    def test_budgets_scale_bankroll(self, alloc):
        assert alloc.budget("s1") == pytest.approx(10_000 / 3)

    def test_new_strategies_start_in_paper_gate(self, alloc):
        assert alloc.gate("s1") == GateStatus.PAPER


class TestReweighting:
    def test_strong_beats_noise_beats_negative(self, alloc):
        alloc.record_trades("s1", trades(+0.50, 300, alt=0.3))
        alloc.record_trades("s2", trades(0.0, 300, alt=0.5))
        alloc.record_trades("s3", trades(-0.30, 300, alt=0.3))
        alloc.reweight(now=NOW)
        w = alloc.weights()
        assert w["s1"] > w["s2"] > w["s3"]

    def test_floor_and_cap_respected(self, alloc):
        alloc.record_trades("s1", trades(+2.0, 500, alt=0.1))
        alloc.record_trades("s2", trades(-2.0, 500, alt=0.1))
        alloc.record_trades("s3", trades(-2.0, 500, alt=0.1))
        alloc.reweight(now=NOW)
        w = alloc.weights()
        assert max(w.values()) <= 0.50 + 1e-9
        assert min(w.values()) >= 0.05 - 1e-9
        assert sum(w.values()) == pytest.approx(1.0)

    def test_shrinkage_dampens_small_samples(self):
        # same mean edge, more evidence -> higher score. (Weights can
        # saturate at the 50% cap for both — by design — so assert on the
        # score function that drives them.)
        a = Allocator(strategies=["a", "b"], bankroll=1000.0)
        a.record_trades("a", trades(+1.0, 10, alt=0.4))
        small_score = a._score("a")
        b = Allocator(strategies=["a", "b"], bankroll=1000.0)
        b.record_trades("a", trades(+1.0, 300, alt=0.4))
        big_score = b._score("a")
        assert 0 < small_score < big_score


class TestPaperGate:
    def test_gate_passes_with_enough_positive_trades(self, alloc):
        alloc.record_paper_trades("s1", trades(+0.5, 250, alt=0.2,
                                               start_ts=NOW - 10 * DAY))
        alloc.update_gates(now=NOW)
        assert alloc.gate("s1") == GateStatus.LIVE_ELIGIBLE

    def test_gate_blocks_too_few_trades(self, alloc):
        alloc.record_paper_trades("s1", trades(+0.5, 50, alt=0.2,
                                               start_ts=NOW - 10 * DAY))
        alloc.update_gates(now=NOW)
        assert alloc.gate("s1") == GateStatus.PAPER

    def test_gate_blocks_negative_ci(self, alloc):
        alloc.record_paper_trades("s1", trades(0.0, 250, alt=0.5,
                                               start_ts=NOW - 10 * DAY))
        alloc.update_gates(now=NOW)
        assert alloc.gate("s1") == GateStatus.PAPER

    def test_gate_blocks_too_recent(self, alloc):
        alloc.record_paper_trades("s1", trades(+0.5, 250, alt=0.2,
                                               start_ts=NOW - 2 * DAY))
        alloc.update_gates(now=NOW)
        assert alloc.gate("s1") == GateStatus.PAPER  # < 7 days of history


class TestEdgeDecay:
    def test_decayed_strategy_demoted(self, alloc):
        alloc.record_paper_trades("s1", trades(+0.5, 250, alt=0.2,
                                               start_ts=NOW - 40 * DAY))
        alloc.update_gates(now=NOW - 30 * DAY)
        assert alloc.gate("s1") == GateStatus.LIVE_ELIGIBLE
        # then live trades turn sour: rolling CI upper bound < 0
        alloc.record_trades("s1", trades(-0.8, 200, alt=0.1,
                                         start_ts=NOW - 5 * DAY))
        alloc.update_gates(now=NOW)
        assert alloc.gate("s1") == GateStatus.PAPER
        demotions = [d for d in alloc.events if d["kind"] == "demotion"]
        assert demotions and "ci" in demotions[0]["evidence"]

    def test_healthy_strategy_not_demoted(self, alloc):
        alloc.record_paper_trades("s1", trades(+0.5, 250, alt=0.2,
                                               start_ts=NOW - 40 * DAY))
        alloc.update_gates(now=NOW - 30 * DAY)
        alloc.record_trades("s1", trades(+0.4, 200, alt=0.2,
                                         start_ts=NOW - 5 * DAY))
        alloc.update_gates(now=NOW)
        assert alloc.gate("s1") == GateStatus.LIVE_ELIGIBLE
