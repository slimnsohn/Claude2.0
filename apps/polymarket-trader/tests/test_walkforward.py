"""Walk-forward gate: K time folds, fresh strategies per fold, pooled CI."""
import pytest

from pmtrader.backtest.costs import CostModel
from pmtrader.backtest.walkforward import run_walkforward
from pmtrader.core.models import Intent, Market, Side
from pmtrader.datalayer.store import Store
from pmtrader.strategies.base import Strategy


class AlwaysBuy(Strategy):
    """Buys YES once per market at the ask; wins when the market resolves YES."""
    name = "always_buy"

    def __init__(self):
        super().__init__()
        self.done = set()

    def on_books(self, market, books, ctx):
        if market.condition_id in self.done:
            return []
        book = books.get(market.token_id_yes)
        if book is None or book.best_ask is None:
            return []
        self.done.add(market.condition_id)
        return [Intent(strategy=self.name, token_id=market.token_id_yes,
                       side=Side.BUY, price=book.best_ask, size=10.0,
                       expected_edge=0.05, reasoning="t",
                       condition_id=market.condition_id)]


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "wf.db")
    yield s
    s.close()


def seed(store, n_markets=8, span=8000.0):
    """n markets spread over [0, span], each with 3 ticks at 0.40 and a YES
    resolution shortly after its last tick."""
    for i in range(n_markets):
        cid = f"m{i}"
        m = Market(condition_id=cid, question="q", token_id_yes=f"{cid}-y",
                   token_id_no=f"{cid}-n", fees_enabled=False)
        store.upsert_market(m)
        t0 = i * (span / n_markets)
        pts = [(t0 + k * 10.0, 0.40) for k in range(3)]
        store.insert_price_history(m.token_id_yes, pts)
        store.insert_price_history(m.token_id_no, [(t, 1 - p) for t, p in pts])
        store.set_resolution(cid, winning_token_id=m.token_id_yes,
                             resolved_ts=t0 + 40.0)


class TestWalkForward:
    def test_positive_strategy_passes(self, store):
        seed(store)
        report = run_walkforward(store, lambda: [AlwaysBuy()], k=4,
                                 cost=CostModel(half_spread=0.01,
                                                slippage_bps=0.0,
                                                book_depth=50.0),
                                 min_pooled_trades=4, min_fold_trades=1,
                                 min_active_folds=2)
        r = report["strategies"]["always_buy"]
        assert r["n_trades"] >= 4
        assert r["pass"] is True
        assert len(r["fold_ns"]) == 4

    def test_strategy_with_no_trades_fails(self, store):
        seed(store)
        report = run_walkforward(store, lambda: [Strategy()], k=4)
        assert report["strategies"]["base"]["pass"] is False
        assert report["strategies"]["base"]["n_trades"] == 0

    def test_empty_store_reports_error(self, store):
        report = run_walkforward(store, lambda: [AlwaysBuy()], k=4)
        assert report["strategies"] == {}
        assert "error" in report
