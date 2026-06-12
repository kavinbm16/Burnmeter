"""Store aggregate tests."""

import pytest

from backend.providers.base import CostRecord, UsageRecord
from backend.store import Store


@pytest.fixture
async def store(tmp_path):
    s = Store(tmp_path / "t.db")
    await s.init()
    return s


def rec(**kw) -> UsageRecord:
    base = dict(
        provider="openai", model="gpt-4o", date="2026-06-01",
        input_tokens=100, output_tokens=50, requests=1, cost_usd=1.0,
        source="usage_api",
    )
    base.update(kw)
    return UsageRecord(**base)


async def test_upsert_replaces_not_duplicates(store):
    await store.upsert_usage([rec()])
    await store.upsert_usage([rec(input_tokens=200)])
    data = await store.overview("2026-06-01", "2026-06-30")
    assert data["totals"]["input_tokens"] == 200


async def test_increment_adds(store):
    await store.increment_usage(rec(provider="gemini", source="proxy"))
    await store.increment_usage(rec(provider="gemini", source="proxy"))
    data = await store.overview("2026-06-01", "2026-06-30")
    assert data["totals"]["input_tokens"] == 200
    assert data["totals"]["requests"] == 2


async def test_overview_groups_by_provider(store):
    await store.upsert_usage([rec(), rec(provider="gemini", source="proxy", cost_usd=0.5)])
    data = await store.overview("2026-06-01", "2026-06-30")
    assert {p["provider"] for p in data["by_provider"]} == {"openai", "gemini"}
    assert data["totals"]["cost_usd"] == 1.5


async def test_breakdown_filters_provider_and_dates(store):
    await store.upsert_usage([
        rec(), rec(date="2026-05-01"), rec(provider="gemini", source="proxy"),
    ])
    data = await store.breakdown("openai", "2026-06-01", "2026-06-30")
    assert len(data["daily"]) == 1
    assert data["by_model"][0]["model"] == "gpt-4o"


async def test_remove_provider_purges(store):
    await store.add_provider("openai", "OpenAI", "sk-…ab12", "ok")
    await store.upsert_usage([rec()])
    await store.upsert_costs([CostRecord("openai", "2026-06-01", 1.0)])
    await store.remove_provider("openai")
    assert await store.list_providers() == []
    data = await store.overview("2026-06-01", "2026-06-30")
    assert data["by_provider"] == []
