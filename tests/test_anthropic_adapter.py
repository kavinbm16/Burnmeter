"""AnthropicAdapter tests against recorded fixtures (respx mocks the HTTP layer)."""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from backend.providers.anthropic_adapter import AnthropicAdapter
from backend.providers.base import InvalidKeyError

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://api.anthropic.com/v1"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def adapter():
    return AnthropicAdapter()


# ── validate_key ─────────────────────────────────────────────────────────────

@respx.mock
async def test_validate_admin_key_returns_polling_label(adapter):
    respx.get(f"{BASE}/models").mock(return_value=httpx.Response(200, json={"data": []}))
    info = await adapter.validate_key("sk-ant-admin01-test-key")
    assert info.provider == "anthropic"
    assert "polling" in info.label.lower() or "admin" in info.label.lower()
    assert "sk-" in info.masked_key


@respx.mock
async def test_validate_regular_key_returns_proxy_only_label(adapter):
    respx.get(f"{BASE}/models").mock(return_value=httpx.Response(200, json={"data": []}))
    info = await adapter.validate_key("sk-ant-api03-regular-key")
    assert "proxy" in info.label.lower()


@respx.mock
async def test_validate_invalid_key_raises(adapter):
    respx.get(f"{BASE}/models").mock(
        return_value=httpx.Response(401, json={"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}})
    )
    with pytest.raises(InvalidKeyError):
        await adapter.validate_key("sk-ant-bad-key")


# ── fetch_usage ───────────────────────────────────────────────────────────────

@respx.mock
async def test_fetch_usage_regular_key_returns_empty(adapter):
    records = await adapter.fetch_usage("sk-ant-api03-regular", date(2026, 6, 1), date(2026, 6, 2))
    assert records == []


@respx.mock
async def test_fetch_usage_admin_key_normalizes(adapter):
    respx.get(f"{BASE}/organizations/usage_report/messages").mock(
        return_value=httpx.Response(200, json=fixture("anthropic_usage.json"))
    )
    records = await adapter.fetch_usage("sk-ant-admin01-test", date(2026, 6, 1), date(2026, 6, 2))
    assert len(records) == 2

    r = records[0]
    assert r.provider == "anthropic"
    assert r.model == "claude-opus-4-8"
    assert r.date == "2026-06-01"
    # total input = uncached(6500) + cache_read(3000) + cache_write(400+100)
    assert r.input_tokens == 10000
    assert r.output_tokens == 2000
    assert r.cache_write_tokens == 500   # 400 + 100
    assert r.cache_read_tokens == 3000
    assert r.cost_usd is None
    assert r.source == "usage_api"
    assert r.cost_estimated is False


@respx.mock
async def test_fetch_usage_pagination(adapter):
    page1 = {**fixture("anthropic_usage.json"), "has_more": True, "next_page": "cursor_abc"}
    page2 = fixture("anthropic_usage.json")

    route = respx.get(f"{BASE}/organizations/usage_report/messages")
    route.side_effect = [
        httpx.Response(200, json=page1),
        httpx.Response(200, json=page2),
    ]
    records = await adapter.fetch_usage("sk-ant-admin01-test", date(2026, 6, 1), date(2026, 6, 2))
    assert len(records) == 4
    assert route.calls[1].request.url.params["page"] == "cursor_abc"


# ── fetch_costs ───────────────────────────────────────────────────────────────

@respx.mock
async def test_fetch_costs_regular_key_returns_empty(adapter):
    records = await adapter.fetch_costs("sk-ant-api03-regular", date(2026, 6, 1), date(2026, 6, 2))
    assert records == []


@respx.mock
async def test_fetch_costs_admin_key_normalizes(adapter):
    respx.get(f"{BASE}/organizations/cost_report").mock(
        return_value=httpx.Response(200, json=fixture("anthropic_costs.json"))
    )
    records = await adapter.fetch_costs("sk-ant-admin01-test", date(2026, 6, 1), date(2026, 6, 2))
    assert len(records) == 1
    assert records[0].provider == "anthropic"
    # 42.50 + 45.20 = 87.70 cents → $0.877
    assert records[0].cost_usd == pytest.approx(0.877)
    assert records[0].date == "2026-06-01"
    assert records[0].source == "usage_api"


@respx.mock
async def test_fetch_costs_404_returns_empty(adapter):
    respx.get(f"{BASE}/organizations/cost_report").mock(
        return_value=httpx.Response(404, json={"type": "error", "error": {"message": "not found"}})
    )
    records = await adapter.fetch_costs("sk-ant-admin01-test", date(2026, 6, 1), date(2026, 6, 2))
    assert records == []


@respx.mock
async def test_fetch_usage_429_retries(adapter):
    route = respx.get(f"{BASE}/organizations/usage_report/messages")
    route.side_effect = [
        httpx.Response(429, headers={"retry-after": "0"}, json={}),
        httpx.Response(200, json=fixture("anthropic_usage.json")),
    ]
    records = await adapter.fetch_usage("sk-ant-admin01-test", date(2026, 6, 1), date(2026, 6, 2))
    assert len(records) == 2
    assert route.call_count == 2
