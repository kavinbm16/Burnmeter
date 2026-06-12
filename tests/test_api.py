"""API endpoint tests for budget, heatmap, models leaderboard, and live WS hub."""

from datetime import datetime, timezone

import pytest

from backend.main import LiveHub
from backend.providers.base import UsageRecord
from backend.store import Store


@pytest.fixture
async def store(tmp_path):
    s = Store(tmp_path / "t.db")
    await s.init()
    return s


async def test_budget_roundtrip(store):
    assert await store.get_budget() is None
    await store.set_budget(250.0)
    assert await store.get_budget() == 250.0
    await store.set_budget(100.0)
    assert await store.get_budget() == 100.0
    await store.set_budget(None)
    assert await store.get_budget() is None


async def test_heatmap_daily_totals(store):
    await store.upsert_usage([
        UsageRecord("openai", "gpt-4o", "2026-06-01", 100, 50, requests=1, cost_usd=1.0),
        UsageRecord("gemini", "gemini-2.5-flash", "2026-06-01", 200, 80, requests=2,
                    cost_usd=0.5, source="proxy"),
        UsageRecord("openai", "gpt-4o", "2026-06-02", 10, 5, requests=1, cost_usd=0.1),
    ])
    days = await store.heatmap("2026-06-01", "2026-06-30")
    assert len(days) == 2
    assert days[0]["date"] == "2026-06-01"
    assert days[0]["cost_usd"] == 1.5
    assert days[0]["total_tokens"] == 430


async def test_models_leaderboard_ranked(store):
    await store.upsert_usage([
        UsageRecord("openai", "gpt-4o", "2026-06-01", 100, 50, requests=1, cost_usd=5.0),
        UsageRecord("gemini", "gemini-2.5-flash", "2026-06-01", 200, 80, requests=2,
                    cost_usd=9.0, source="proxy", cost_estimated=True),
    ])
    models = await store.models_leaderboard("2026-06-01", "2026-06-30")
    assert [m["model"] for m in models] == ["gemini-2.5-flash", "gpt-4o"]
    assert models[0]["provider"] == "gemini"
    assert models[0]["cost_estimated"] == 1


async def test_live_hub_publishes_and_drops_dead_clients():
    hub = LiveHub()

    class FakeWS:
        def __init__(self, fail=False):
            self.fail = fail
            self.events = []

        async def accept(self):
            pass

        async def send_json(self, event):
            if self.fail:
                raise RuntimeError("gone")
            self.events.append(event)

    good, dead = FakeWS(), FakeWS(fail=True)
    await hub.connect(good)  # type: ignore[arg-type]
    await hub.connect(dead)  # type: ignore[arg-type]
    event = {"model": "gemini-2.5-flash", "cost_usd": 0.01,
             "ts": datetime.now(tz=timezone.utc).isoformat()}
    await hub.publish(event)
    assert good.events == [event]
    assert dead not in hub._clients
    assert good in hub._clients
