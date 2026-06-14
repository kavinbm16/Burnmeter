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


@pytest.mark.asyncio
async def test_get_sync_state_returns_none_when_missing(store):
    result = await store.get_sync_state("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_get_sync_state_returns_dict_after_set(store):
    await store.set_sync_state("__gcp_billing__", "ok", watermark="2026-06-12")
    result = await store.get_sync_state("__gcp_billing__")
    assert result is not None
    assert result["status"] == "ok"
    assert result["watermark_date"] == "2026-06-12"


@pytest.mark.asyncio
async def test_ensure_provider_inserts_if_absent(store):
    await store.ensure_provider("vertex_ai", "Google Vertex AI", "via GCP billing", "billing export")
    rows = await store.list_providers()
    assert any(r["name"] == "vertex_ai" for r in rows)


@pytest.mark.asyncio
async def test_ensure_provider_does_not_overwrite_existing(store):
    await store.add_provider("vertex_ai", "Google Vertex AI", "via GCP billing", "billing export")
    # Calling ensure again should not raise or change anything
    await store.ensure_provider("vertex_ai", "CHANGED", "x", "y")
    rows = await store.list_providers()
    row = next(r for r in rows if r["name"] == "vertex_ai")
    assert row["display_name"] == "Google Vertex AI"


@pytest.mark.asyncio
async def test_reconciliation_summary_empty(store):
    result = await store.reconciliation_summary("gemini", "2026-06-01", "2026-06-30")
    assert result == []


@pytest.mark.asyncio
async def test_reconciliation_summary_with_proxy_and_billing(store):
    from backend.providers.base import CostRecord, UsageRecord

    # Proxy estimate
    await store.upsert_usage([UsageRecord(
        provider="gemini", model="gemini-2.0-flash", date="2026-06-10",
        source="proxy", cost_usd=1.00, cost_estimated=True
    )])
    # Billing actual
    await store.upsert_costs([CostRecord(
        provider="gemini", date="2026-06-10", cost_usd=1.05,
        line_item="Flash Input Tokens", source="billing_export"
    )])

    result = await store.reconciliation_summary("gemini", "2026-06-01", "2026-06-30")
    assert len(result) == 1
    row = result[0]
    assert row["date"] == "2026-06-10"
    assert row["estimated_cost"] == pytest.approx(1.00)
    assert row["actual_cost"] == pytest.approx(1.05)
    assert row["reconciled"] is True
    assert row["delta_pct"] == pytest.approx(5.0)
