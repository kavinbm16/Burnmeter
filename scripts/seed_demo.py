"""Seed demo data so the dashboard can be previewed without real keys.

Usage: BURNMETER_DB=/tmp/burnmeter-demo.db .venv/bin/python scripts/seed_demo.py
"""

import asyncio
import math
import random
from datetime import date, timedelta

from backend.providers.base import CostRecord, UsageRecord
from backend.store import Store

MODELS = [
    ("openai", "gpt-4o", 2.5, 10.0, "usage_api"),
    ("openai", "gpt-4o-mini", 0.15, 0.6, "usage_api"),
    ("openai", "gpt-4.1", 2.0, 8.0, "usage_api"),
    ("gemini", "gemini-2.5-flash", 0.30, 2.5, "proxy"),
    ("gemini", "gemini-2.5-pro", 1.25, 10.0, "proxy"),
]


async def main() -> None:
    random.seed(7)
    store = Store()
    await store.init()
    today = date.today()
    usage, costs = [], []
    for back in range(120):
        d = today - timedelta(days=back)
        # weekly rhythm + slow growth so charts look alive
        wave = 1 + 0.5 * math.sin(back / 3.2) + (0.4 if d.weekday() < 5 else -0.5)
        scale = max(0.05, wave) * (1 + (120 - back) / 200)
        day_cost = 0.0
        for provider, model, in_rate, out_rate, source in MODELS:
            if random.random() < 0.15:
                continue
            inp = int(random.uniform(40_000, 400_000) * scale)
            out = int(inp * random.uniform(0.15, 0.45))
            cached = int(inp * random.uniform(0.05, 0.3))
            cost = (inp * in_rate + out * out_rate) / 1e6
            day_cost += cost
            usage.append(
                UsageRecord(
                    provider=provider, model=model, date=d.isoformat(),
                    input_tokens=inp, output_tokens=out, cache_read_tokens=cached,
                    requests=int(random.uniform(20, 220) * scale) + 1,
                    cost_usd=round(cost, 4), source=source,
                    cost_estimated=source == "proxy",
                )
            )
        costs.append(CostRecord("openai", d.isoformat(), round(day_cost * 0.62, 4)))
    await store.upsert_usage(usage)
    await store.upsert_costs(costs)
    await store.set_budget(120.0)
    await store.add_provider("openai", "OpenAI", "sk-…demo", "demo data")
    await store.add_provider("gemini", "Google Gemini", "AIz…demo", "demo data")
    print(f"seeded {len(usage)} usage rows into {store.db_path}")


if __name__ == "__main__":
    asyncio.run(main())
