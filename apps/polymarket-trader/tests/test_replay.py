"""Replay engine: deterministic, no-lookahead, hand-verifiable arithmetic."""
import pytest

from pmtrader.backtest.costs import CostModel
from pmtrader.backtest.replay import ReplayEngine
from pmtrader.core.fees import FeeSchedule
from pmtrader.core.models import Intent, Market, Side
from pmtrader.datalayer.store import Store
from pmtrader.strategies.base import Strategy, StrategyContext

GENERAL = FeeSchedule(exponent=1, rate=0.05, taker_only=True, rebate_rate=0.25)


def make_market(cid="c1", category="general", schedule=GENERAL):
    return Market(condition_id=cid, question="Q?", category=category,
                  token_id_yes=f"{cid}-yes", token_id_no=f"{cid}-no",
                  neg_risk=False, end_date="2026-01-03T00:00:00Z",
                  fee_schedule=schedule, active=False)


class BuyAndHold(Strategy):
    """Toy: buy 100 YES at first sight, hold to resolution."""
    name = "toy_bah"

    def __init__(self, params=None):
        super().__init__(params)
        self.bought = set()

    def on_books(self, market, books, ctx: StrategyContext):
        if market.condition_id in self.bought:
            return []
        self.bought.add(market.condition_id)
        ask = books[market.token_id_yes].best_ask
        return [Intent(strategy=self.name, token_id=market.token_id_yes,
                       side=Side.BUY, price=ask, size=100, expected_edge=0.0,
                       reasoning="toy buy-and-hold",
                       condition_id=market.condition_id)]


class RestingBid(Strategy):
    """Toy maker: rest a bid at fixed price on first sight."""
    name = "toy_rest"

    def __init__(self, price, params=None):
        super().__init__(params)
        self.price = price
        self.placed = set()

    def on_books(self, market, books, ctx):
        if market.condition_id in self.placed:
            return []
        self.placed.add(market.condition_id)
        return [Intent(strategy=self.name, token_id=market.token_id_yes,
                       side=Side.BUY, price=self.price, size=100, expected_edge=0.0,
                       reasoning="toy resting bid", post_only=True,
                       condition_id=market.condition_id)]


class TsProbe(Strategy):
    name = "toy_probe"

    def __init__(self, params=None):
        super().__init__(params)
        self.seen = []

    def on_books(self, market, books, ctx):
        self.seen.append(ctx.now)
        return []


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "bt.db")
    m = make_market()
    s.upsert_market(m)
    # YES price path: 0.40 -> 0.45 -> 0.50; YES resolves as winner
    s.insert_price_history(m.token_id_yes, [(1000.0, 0.40), (2000.0, 0.45), (3000.0, 0.50)])
    s.insert_price_history(m.token_id_no, [(1000.0, 0.60), (2000.0, 0.55), (3000.0, 0.50)])
    s.set_resolution(m.condition_id, m.token_id_yes, 4000.0)
    yield s
    s.close()


def run(store, strategy, **cost_kw):
    cost = CostModel(half_spread=0.01, slippage_bps=50, **cost_kw)
    engine = ReplayEngine(store, [strategy], cost, start_ts=0.0, end_ts=10_000.0,
                          starting_cash=1000.0)
    return engine.run()


class TestTakerArithmetic:
    def test_final_equity_hand_computed(self, store):
        result = run(store, BuyAndHold())
        # buy 100 YES at first tick: synthetic ask = 0.40 + 0.01 = 0.41
        # notional = 41.0
        # slippage = 50bps * 41.0 = 0.205
        # taker fee = 100 * 0.05 * 0.41 * 0.59 = 1.2095
        # total cost = 42.4145 ; payout at resolution = 100
        expected_pnl = 100 - (41.0 + 0.205 + 1.2095)
        assert result.per_trade_pnl == [pytest.approx(expected_pnl)]
        assert result.final_equity == pytest.approx(1000.0 + expected_pnl)

    def test_equity_curve_marks_to_market(self, store):
        result = run(store, BuyAndHold())
        # curve has one point per tick ts + settlement
        assert [p[0] for p in result.equity_curve] == [1000.0, 2000.0, 3000.0, 4000.0]
        # at ts=2000 position marks at 0.45 mid
        cost = 41.0 + 0.205 + 1.2095
        assert result.equity_curve[1][1] == pytest.approx(1000.0 - cost + 100 * 0.45)

    def test_deterministic(self, store):
        r1 = run(store, BuyAndHold())
        r2 = run(store, BuyAndHold())
        assert r1.per_trade_pnl == r2.per_trade_pnl
        assert r1.equity_curve == r2.equity_curve


class TestMakerFills:
    def test_resting_bid_fills_only_on_trade_through(self, store):
        # bid at 0.42: price path 0.40 (already below? no - placed AT first tick,
        # fills only on a LATER tick strictly below) -> use bid 0.44: tick 2 at
        # 0.45 doesn't cross, never goes below 0.44 again -> no fill
        result = run(store, RestingBid(0.44))
        assert result.per_trade_pnl == []

    def test_resting_bid_fills_when_crossed(self, tmp_path):
        s = Store(tmp_path / "bt2.db")
        m = make_market()
        s.upsert_market(m)
        s.insert_price_history(m.token_id_yes,
                               [(1000.0, 0.50), (2000.0, 0.43), (3000.0, 0.50)])
        s.insert_price_history(m.token_id_no,
                               [(1000.0, 0.50), (2000.0, 0.57), (3000.0, 0.50)])
        s.set_resolution(m.condition_id, m.token_id_yes, 4000.0)
        result = run(s, RestingBid(0.44))
        # filled at our bid 0.44 (maker: no fee, no slippage), resolves to $1
        assert result.per_trade_pnl == [pytest.approx(100 - 44.0)]
        s.close()

    def test_touch_is_not_fill(self, tmp_path):
        s = Store(tmp_path / "bt3.db")
        m = make_market()
        s.upsert_market(m)
        s.insert_price_history(m.token_id_yes,
                               [(1000.0, 0.50), (2000.0, 0.44), (3000.0, 0.50)])
        s.insert_price_history(m.token_id_no,
                               [(1000.0, 0.50), (2000.0, 0.56), (3000.0, 0.50)])
        s.set_resolution(m.condition_id, m.token_id_yes, 4000.0)
        result = run(s, RestingBid(0.44))  # price equals bid, never strictly below
        assert result.per_trade_pnl == []
        s.close()


class TestNoLookahead:
    def test_strategy_sees_monotonic_time(self, store):
        probe = TsProbe()
        run(store, probe)
        assert probe.seen == sorted(probe.seen)
        assert len(probe.seen) == 3


class TestLosingSide:
    def test_losing_position_settles_to_zero(self, tmp_path):
        s = Store(tmp_path / "bt4.db")
        m = make_market()
        s.upsert_market(m)
        s.insert_price_history(m.token_id_yes, [(1000.0, 0.40)])
        s.insert_price_history(m.token_id_no, [(1000.0, 0.60)])
        s.set_resolution(m.condition_id, m.token_id_no, 4000.0)  # NO wins
        result = run(s, BuyAndHold())
        cost = 41.0 + 0.205 + 1.2095
        assert result.per_trade_pnl == [pytest.approx(-cost)]
        s.close()
