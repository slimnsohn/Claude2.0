"""GammaClient tests against recon-captured real payloads via MockTransport."""
import json

import httpx
import pytest

from pmtrader.datalayer.gamma import GammaClient, parse_market


def make_client(handler) -> GammaClient:
    transport = httpx.MockTransport(handler)
    return GammaClient(http=httpx.AsyncClient(transport=transport), retry_base_delay=0.0)


class TestParseMarket:
    def test_parses_real_payload(self, fixture_json):
        raw = fixture_json("gamma_markets.json")[0]
        m = parse_market(raw)
        assert m.condition_id == raw["conditionId"]
        assert m.token_id_yes == json.loads(raw["clobTokenIds"])[0]
        assert m.token_id_no == json.loads(raw["clobTokenIds"])[1]
        assert m.fee_schedule is not None
        assert m.fee_schedule.rate == raw["feeSchedule"]["rate"]
        assert m.fee_schedule.taker_only is raw["feeSchedule"]["takerOnly"]
        assert m.fees_enabled is raw["feesEnabled"]
        assert m.active is True

    def test_category_from_fee_type(self, fixture_json):
        raw = dict(fixture_json("gamma_markets.json")[1])  # world cup, sports_fees_v2
        m = parse_market(raw)
        assert m.category == "sports"

    def test_category_from_event_tags_when_present(self, fixture_json):
        raw = dict(fixture_json("gamma_markets.json")[0])
        raw["events"] = [{"id": "1", "tags": [{"slug": "geopolitics"}]}]
        m = parse_market(raw)
        assert m.category == "geopolitics"

    def test_category_fallback_general(self, fixture_json):
        raw = dict(fixture_json("gamma_markets.json")[0])  # general_fees, no tags
        raw["events"] = []
        m = parse_market(raw)
        assert m.category == "general"

    def test_missing_fee_schedule_yields_none(self, fixture_json):
        raw = dict(fixture_json("gamma_markets.json")[0])
        raw.pop("feeSchedule")
        m = parse_market(raw)
        assert m.fee_schedule is None

    def test_unparseable_market_returns_none(self):
        assert parse_market({"conditionId": "x"}) is None  # no token ids


class TestGammaClient:
    async def test_active_markets_paginates(self, fixture_json):
        markets_page = fixture_json("gamma_markets.json")
        calls = []

        def handler(request):
            calls.append(dict(request.url.params))
            offset = int(request.url.params.get("offset", 0))
            return httpx.Response(200, json=markets_page if offset == 0 else [])

        client = make_client(handler)
        result = await client.active_markets(page_size=5)
        assert len(result) == 5
        assert len(calls) == 2  # page 1 exactly full -> page 2 empty stops
        assert calls[0]["active"] == "true"

    async def test_resolved_markets_yields_winner(self, fixture_json):
        resolved = fixture_json("gamma_resolved.json")

        def handler(request):
            offset = int(request.url.params.get("offset", 0))
            return httpx.Response(200, json=resolved if offset == 0 else [])

        client = make_client(handler)
        out = await client.resolved_markets()
        assert len(out) >= 1
        for market, winner in out:
            assert winner in (market.token_id_yes, market.token_id_no)

    async def test_events_parse(self, fixture_json):
        events = fixture_json("gamma_events.json")

        def handler(request):
            offset = int(request.url.params.get("offset", 0))
            return httpx.Response(200, json=events if offset == 0 else [])

        client = make_client(handler)
        out = await client.events()
        assert len(out) == 3
        e = out[1]
        assert e.neg_risk is True
        assert len(e.markets) >= 1

    async def test_retry_on_429_then_success(self, fixture_json):
        markets_page = fixture_json("gamma_markets.json")
        attempts = {"n": 0}

        def handler(request):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return httpx.Response(429)
            offset = int(request.url.params.get("offset", 0))
            return httpx.Response(200, json=markets_page if offset == 0 else [])

        client = make_client(handler)
        result = await client.active_markets()
        assert len(result) == 5
        assert attempts["n"] >= 2

    async def test_persistent_failure_raises_data_error(self):
        from pmtrader.datalayer.errors import DataError

        def handler(request):
            return httpx.Response(500)

        client = make_client(handler)
        with pytest.raises(DataError):
            await client.active_markets()

    async def test_mid_pagination_failure_returns_partial(self, fixture_json):
        # Gamma 422s past its offset cap — keep what we already fetched
        markets_page = fixture_json("gamma_markets.json")

        def handler(request):
            offset = int(request.url.params.get("offset", 0))
            if offset >= 5:
                return httpx.Response(422)
            return httpx.Response(200, json=markets_page)

        client = make_client(handler)
        result = await client.active_markets(page_size=5, max_pages=10)
        assert len(result) == 5
