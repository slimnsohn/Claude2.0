"""ClobRestClient tests against recon-captured real payloads."""
import httpx
import pytest

from pmtrader.datalayer.clob_rest import ClobRestClient
from pmtrader.datalayer.errors import DataError


def make_client(handler) -> ClobRestClient:
    transport = httpx.MockTransport(handler)
    return ClobRestClient(http=httpx.AsyncClient(transport=transport), retry_base_delay=0.0)


class TestBook:
    async def test_book_parses_real_payload(self, fixture_json):
        raw = fixture_json("clob_book.json")

        def handler(request):
            assert request.url.params["token_id"] == "tok1"
            return httpx.Response(200, json=raw)

        book = await make_client(handler).book("tok1")
        assert book.token_id == "tok1"
        # raw levels are strings sorted worst-first; model must give best-first floats
        assert 0 < book.best_bid < 1
        assert book.best_ask > book.best_bid
        assert book.ts == pytest.approx(int(raw["timestamp"]) / 1000)

    async def test_empty_book_ok(self):
        def handler(request):
            return httpx.Response(200, json={"bids": [], "asks": [], "timestamp": "1000"})

        book = await make_client(handler).book("tok1")
        assert book.best_bid is None and book.mid is None


class TestPricesHistory:
    async def test_history_parses(self, fixture_json):
        hist = fixture_json("prices_history.json")

        def handler(request):
            assert request.url.params["market"] == "tok1"
            return httpx.Response(200, json={"history": hist})

        points = await make_client(handler).prices_history("tok1")
        assert len(points) == len(hist)
        assert points[0] == (hist[0]["t"], hist[0]["p"])

    async def test_empty_history(self):
        def handler(request):
            return httpx.Response(200, json={"history": []})

        assert await make_client(handler).prices_history("tok1") == []


class TestRetry:
    async def test_retry_then_success(self, fixture_json):
        attempts = {"n": 0}

        def handler(request):
            attempts["n"] += 1
            if attempts["n"] < 3:
                return httpx.Response(503)
            return httpx.Response(200, json={"history": []})

        assert await make_client(handler).prices_history("tok1") == []
        assert attempts["n"] == 3

    async def test_gives_up_raises(self):
        def handler(request):
            return httpx.Response(503)

        with pytest.raises(DataError):
            await make_client(handler).prices_history("tok1")

    async def test_timeout_raises_data_error(self):
        def handler(request):
            raise httpx.ConnectTimeout("boom")

        with pytest.raises(DataError):
            await make_client(handler).book("tok1")
