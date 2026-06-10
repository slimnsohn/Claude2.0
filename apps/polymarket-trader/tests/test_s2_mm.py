"""S2 market maker: quoting, inventory skew, markout self-defense, selection.

Quote structure on a binary market: both quotes are BUYs — bid on YES, and
bid on NO at (1 - ask) which is the synthetic ask on YES. Implied YES ask
= 1 - NO bid price.
"""
import pytest

from pmtrader.core.fees import FeeSchedule
from pmtrader.core.models import Fill, Level, Market, OrderBook, Position, Side
from pmtrader.strategies.base import StrategyContext
from pmtrader.strategies.s2_mm import S2MarketMaker

GENERAL = FeeSchedule(exponent=1, rate=0.05, taker_only=True, rebate_rate=0.25)


def mk_market(cid="m1", **kw):
    base = dict(condition_id=cid, question="Q?", category="general",
                token_id_yes=f"{cid}-yes", token_id_no=f"{cid}-no",
                neg_risk=False, end_date="2026-12-31T00:00:00Z",
                fee_schedule=GENERAL, active=True, volume_24h=50_000.0,
                rewards_enabled=True)
    base.update(kw)
    return Market(**base)


def mk_books(market, bid=0.48, ask=0.52, depth=400.0, ts=100.0):
    def book(token, b, a):
        return OrderBook(token_id=token, ts=ts,
                         bids=[Level(price=b, size=depth)],
                         asks=[Level(price=a, size=depth)])
    return {market.token_id_yes: book(market.token_id_yes, bid, ask),
            market.token_id_no: book(market.token_id_no, 1 - ask, 1 - bid)}


def ctx(now=100.0, budget=1000.0, positions=None):
    return StrategyContext(now=now, cash=budget, budget=budget,
                           positions=positions or {})


def split(intents, market):
    yes_bid = next(i for i in intents if i.token_id == market.token_id_yes)
    no_bid = next(i for i in intents if i.token_id == market.token_id_no)
    return yes_bid, no_bid


def implied_ask(no_bid_intent):
    return 1.0 - no_bid_intent.price


def feed_calm_books(s2, market, n=20, mid=0.50, ts0=100.0):
    """Prime the vol estimator. With n=20 (the vol window) the LAST call
    produces the first quotes; further identical books are no-churn []."""
    intents = []
    for i in range(n):
        books = mk_books(market, bid=mid - 0.02, ask=mid + 0.02, ts=ts0 + i)
        intents = s2.on_books(market, books, ctx(now=ts0 + i))
    return intents


@pytest.fixture
def s2():
    return S2MarketMaker()


class TestQuoting:
    def test_emits_two_post_only_buy_quotes(self, s2):
        m = mk_market()
        intents = feed_calm_books(s2, m)
        assert len(intents) == 2
        assert all(i.post_only and i.side == Side.BUY for i in intents)
        yes_bid, no_bid = split(intents, m)
        assert yes_bid.price < 0.50 < implied_ask(no_bid)

    def test_no_quotes_before_vol_primed(self, s2):
        m = mk_market()
        assert s2.on_books(m, mk_books(m), ctx()) == []

    def test_no_churn_on_unchanged_book(self, s2):
        m = mk_market()
        feed_calm_books(s2, m)
        again = s2.on_books(m, mk_books(m, ts=201.0), ctx(now=201.0))
        assert again == []  # reference unmoved, inventory unchanged

    def test_spread_respects_minimum(self, s2):
        m = mk_market()
        intents = feed_calm_books(s2, m)
        yes_bid, no_bid = split(intents, m)
        assert implied_ask(no_bid) - yes_bid.price >= \
            s2.params["min_spread"] - 1e-9


class TestInventorySkew:
    def quotes_with_inventory(self, m, yes_size=0.0, no_size=0.0):
        mm = S2MarketMaker()
        feed_calm_books(mm, m, n=19)  # one short: assertion call quotes first
        positions = {}
        if yes_size:
            positions[m.token_id_yes] = Position(
                token_id=m.token_id_yes, size=yes_size, avg_cost=0.50,
                condition_id=m.condition_id)
        if no_size:
            positions[m.token_id_no] = Position(
                token_id=m.token_id_no, size=no_size, avg_cost=0.50,
                condition_id=m.condition_id)
        return mm, mm.on_books(m, mk_books(m, ts=130.0),
                               ctx(now=130.0, positions=positions))

    def test_long_inventory_shifts_quotes_down(self):
        m = mk_market()
        _, flat = self.quotes_with_inventory(m)
        _, long_ = self.quotes_with_inventory(m, yes_size=400.0)
        flat_bid, _ = split(flat, m)
        long_bid, _ = split(long_, m)
        assert long_bid.price < flat_bid.price  # less eager to add YES

    def test_skew_monotonic_in_net_inventory(self):
        m = mk_market()
        prices = []
        for inv in (0.0, 200.0, 400.0):
            _, intents = self.quotes_with_inventory(m, yes_size=inv)
            yes_bid, _ = split(intents, m)
            prices.append(yes_bid.price)
        assert prices[0] >= prices[1] >= prices[2]
        assert prices[0] > prices[2]

    def test_paired_inventory_is_neutral(self):
        m = mk_market()
        _, flat = self.quotes_with_inventory(m)
        _, paired = self.quotes_with_inventory(m, yes_size=300.0, no_size=300.0)
        assert split(flat, m)[0].price == pytest.approx(split(paired, m)[0].price)

    def test_max_inventory_one_sided(self):
        m = mk_market()
        mm = S2MarketMaker()
        feed_calm_books(mm, m, n=20)
        pos = {m.token_id_yes: Position(
            token_id=m.token_id_yes, size=mm.params["max_inventory"] + 100,
            avg_cost=0.50, condition_id=m.condition_id)}
        intents = mm.on_books(m, mk_books(m, ts=130.0),
                              ctx(now=130.0, positions=pos))
        # net long beyond cap: only the NO-side quote (reduces net) remains
        assert len(intents) == 1
        assert intents[0].token_id == m.token_id_no


class TestMarkoutDefense:
    def fill(self, mm, m, ts, price=0.48):
        mm.on_fill(Fill(order_id="o", token_id=m.token_id_yes, side=Side.BUY,
                        price=price, size=100.0, fee=0.0, ts=ts, maker=True))

    def test_toxic_markouts_trigger_defense(self):
        m = mk_market()
        mm = S2MarketMaker()
        feed_calm_books(mm, m)
        # fills followed by adverse mid moves (bought 0.48, mid sinks to 0.44)
        for k in range(10):
            ts = 150.0 + k * 40
            self.fill(mm, m, ts)
            mm.on_books(m, mk_books(m, bid=0.42, ask=0.46, ts=ts + 31),
                        ctx(now=ts + 31))
        mm.on_books(m, mk_books(m, bid=0.42, ask=0.46, ts=600.0), ctx(now=600.0))
        assert mm.markout_avg(m.token_id_yes) < 0
        # avg markout -0.04 << 2x threshold (-0.01) -> quotes pulled
        assert mm.widen_mult[m.token_id_yes] == 0.0
        assert mm.on_books(m, mk_books(m, bid=0.40, ask=0.44, ts=601.0),
                           ctx(now=601.0)) == []

    def test_mildly_bad_markouts_widen(self):
        m = mk_market()
        mm = S2MarketMaker()
        feed_calm_books(mm, m)
        # fills with slightly adverse moves: markout ~ -0.007, between
        # threshold (-0.005) and 2x threshold (-0.010) -> widen, keep quoting
        for k in range(10):
            ts = 150.0 + k * 40
            self.fill(mm, m, ts, price=0.48)
            mm.on_books(m, mk_books(m, bid=0.453, ask=0.493, ts=ts + 31),
                        ctx(now=ts + 31))  # mid 0.473, markout -0.007
        intents = mm.on_books(m, mk_books(m, bid=0.44, ask=0.48, ts=600.0),
                              ctx(now=600.0))
        assert mm.widen_mult[m.token_id_yes] == 2.0
        assert len(intents) == 2

    def test_healthy_markouts_keep_quoting(self):
        m = mk_market()
        mm = S2MarketMaker()
        feed_calm_books(mm, m)
        for k in range(10):
            ts = 150.0 + k * 40
            self.fill(mm, m, ts, price=0.48)
            mm.on_books(m, mk_books(m, bid=0.48, ask=0.52, ts=ts + 31),
                        ctx(now=ts + 31))  # mid stays 0.50 >= fill price
        intents = mm.on_books(m, mk_books(m, bid=0.46, ask=0.50, ts=600.0),
                              ctx(now=600.0))  # ref moved -> requote
        assert mm.widen_mult[m.token_id_yes] == 1.0
        assert len(intents) == 2


class TestMarketSelection:
    def test_on_books_respects_own_filters(self):
        mm = S2MarketMaker()
        low_vol = mk_market(cid="lowvol", volume_24h=100.0)
        feed_calm_books(mm, low_vol, n=20)
        assert mm.on_books(low_vol, mk_books(low_vol, ts=200.0),
                           ctx(now=200.0)) == []

    def test_no_quotes_in_extreme_priced_books(self):
        mm = S2MarketMaker()
        m = mk_market()
        for i in range(21):
            books = mk_books(m, bid=0.002, ask=0.006, ts=100.0 + i)
            intents = mm.on_books(m, books, ctx(now=100.0 + i))
        assert intents == []

    def test_filters(self, s2):
        good = mk_market(cid="good")
        low_vol = mk_market(cid="lowvol", volume_24h=100.0)
        no_rewards = mk_market(cid="norew", rewards_enabled=False)
        ending = mk_market(cid="ending", end_date="2026-06-10T12:00:00Z")
        chosen = s2.select_markets(
            [good, low_vol, no_rewards, ending],
            now=1781136000.0)  # 2026-06-10T08:00Z -> 'ending' has <48h left
        ids = [m.condition_id for m in chosen]
        assert "good" in ids
        assert "lowvol" not in ids and "norew" not in ids and "ending" not in ids
