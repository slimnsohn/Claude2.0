import httpx
import pytest

from pmtrader.datalayer.coinbase import CoinbaseClient


def make_client(handler):
    return CoinbaseClient(http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                          retry_base_delay=0.0)


async def test_candles_sorted_oldest_first():
    payload = [[200, 1, 2, 1.5, 99000.0, 10], [140, 1, 2, 1.5, 98000.0, 10],
               [80, 1, 2, 1.5, 97000.0, 10]]  # newest first, per API

    def handler(request):
        assert "BTC-USD" in str(request.url)
        return httpx.Response(200, json=payload)

    candles = await make_client(handler).candles()
    assert candles == [(80.0, 97000.0), (140.0, 98000.0), (200.0, 99000.0)]


async def test_spot():
    def handler(request):
        return httpx.Response(200, json={"price": "61234.5"})

    assert await make_client(handler).spot() == pytest.approx(61234.5)
