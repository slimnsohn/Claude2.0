"""History fetcher planning/resume logic with mocked clients."""
from unittest.mock import AsyncMock

import pytest

from pmtrader.core.models import Market
from pmtrader.datalayer.history import HistoryFetcher
from pmtrader.datalayer.store import Store


def mk_market(i: int, active: bool = False) -> Market:
    return Market(
        condition_id=f"c{i}", question=f"Q{i}?", category="general",
        token_id_yes=f"ty{i}", token_id_no=f"tn{i}", neg_risk=False,
        end_date="2026-01-01T00:00:00Z", active=active,
    )


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


@pytest.fixture
def gamma():
    g = AsyncMock()
    g.resolved_markets.return_value = [(mk_market(i), f"ty{i}") for i in range(3)]
    g.active_markets.return_value = [mk_market(i, active=True) for i in (10, 11)]
    return g


@pytest.fixture
def clob():
    c = AsyncMock()
    c.prices_history.return_value = [(1000.0 + j * 60, 0.5) for j in range(10)]
    return c


async def test_fetch_stores_everything(store, gamma, clob):
    f = HistoryFetcher(store, gamma, clob, rate_limit_per_s=10_000)
    stats = await f.run(resolved_since="2024-01-01", max_markets=100)
    assert stats["markets"] == 5            # 3 resolved + 2 active
    assert stats["tokens_fetched"] == 10    # 2 tokens per market
    assert len(store.resolutions()) == 3
    assert len(store.all_markets()) == 5
    assert len(store.price_history("ty0")) == 10
    # both YES and NO token histories pulled
    assert len(store.price_history("tn0")) == 10


async def test_fetch_resumes_without_refetching(store, gamma, clob):
    f = HistoryFetcher(store, gamma, clob, rate_limit_per_s=10_000)
    await f.run(resolved_since="2024-01-01", max_markets=100)
    calls_after_first = clob.prices_history.await_count
    stats = await f.run(resolved_since="2024-01-01", max_markets=100)
    assert clob.prices_history.await_count == calls_after_first  # nothing refetched
    assert stats["tokens_fetched"] == 0
    assert stats["tokens_skipped"] == 10


async def test_max_markets_respected(store, gamma, clob):
    f = HistoryFetcher(store, gamma, clob, rate_limit_per_s=10_000)
    stats = await f.run(resolved_since="2024-01-01", max_markets=2)
    assert stats["markets"] == 2


async def test_fetch_error_skips_token_and_continues(store, gamma, clob):
    from pmtrader.datalayer.errors import DataError

    async def flaky(token_id, **kw):
        if token_id == "ty0":
            raise DataError("boom")
        return [(1000.0, 0.5)]

    clob.prices_history.side_effect = flaky
    f = HistoryFetcher(store, gamma, clob, rate_limit_per_s=10_000)
    stats = await f.run(resolved_since="2024-01-01", max_markets=100)
    assert stats["errors"] == 1
    assert len(store.price_history("tn0")) == 1  # sibling token still fetched
