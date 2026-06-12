"""OpenAI adapter tests against recorded fixtures (respx mocks the HTTP layer)."""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from backend.providers.base import InvalidKeyError
from backend.providers.openai_adapter import OpenAIAdapter

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def adapter():
    return OpenAIAdapter()


@respx.mock
async def test_fetch_usage_normalizes(adapter):
    respx.get("https://api.openai.com/v1/organization/usage/completions").mock(
        return_value=httpx.Response(200, json=fixture("openai_usage.json"))
    )
    records = await adapter.fetch_usage("sk-admin-test", date(2026, 6, 1), date(2026, 6, 2))
    assert len(records) == 2
    r = records[0]
    assert r.provider == "openai"
    assert r.model == "gpt-4o-mini-2024-07-18"
    assert r.date == "2026-06-01"
    assert r.input_tokens == 12000
    assert r.output_tokens == 3400
    assert r.cache_read_tokens == 2000
    assert r.requests == 42
    assert r.source == "usage_api"


@respx.mock
async def test_fetch_costs_normalizes(adapter):
    respx.get("https://api.openai.com/v1/organization/costs").mock(
        return_value=httpx.Response(200, json=fixture("openai_costs.json"))
    )
    records = await adapter.fetch_costs("sk-admin-test", date(2026, 6, 1), date(2026, 6, 2))
    assert len(records) == 1
    assert records[0].cost_usd == 0.42
    assert records[0].date == "2026-06-01"


@respx.mock
async def test_non_admin_key_actionable_error(adapter):
    respx.get("https://api.openai.com/v1/organization/usage/completions").mock(
        return_value=httpx.Response(401, json={"error": {"message": "invalid key"}})
    )
    with pytest.raises(InvalidKeyError, match="Admin API key"):
        await adapter.validate_key("sk-proj-regular-key")


@respx.mock
async def test_pagination_follows_next_page(adapter):
    page1 = fixture("openai_usage.json")
    page1 = {**page1, "has_more": True, "next_page": "page_2"}
    page2 = fixture("openai_usage.json")

    route = respx.get("https://api.openai.com/v1/organization/usage/completions")
    route.side_effect = [
        httpx.Response(200, json=page1),
        httpx.Response(200, json=page2),
    ]
    records = await adapter.fetch_usage("sk-admin-test", date(2026, 6, 1), date(2026, 6, 2))
    assert len(records) == 4
    assert route.calls[1].request.url.params["page"] == "page_2"
