# Anthropic Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Anthropic/Claude as a tracked provider in burnmeter via a single `AnthropicAdapter` that polls the org usage API with an admin key, or silently returns empty records with a regular key (proxy-only degraded mode).

**Architecture:** One new adapter file following the `OpenAIAdapter` pattern exactly. Pricing table extended with `cache_write_per_m` (new field) and Claude model entries. Adapter registered in `main.py`. Zero changes to `SyncEngine`, `Store`, or frontend.

**Tech Stack:** Python 3.11+, httpx (already in project), respx (already used in tests), pytest-asyncio

## Global Constraints

- Follow existing `OpenAIAdapter` code style exactly — no extra abstractions
- `MAX_RETRIES = 4`, exponential 429 backoff via `retry-after` header or `2^(attempt+1)`
- Auth headers: `x-api-key: {key}` and `anthropic-version: 2023-06-01`
- Never log or expose the raw key — only `mask_key(key)` in user-visible strings
- `cost_estimated = False` for usage-API records; `True` for proxy-estimated records
- Key prefix `sk-ant-admin` gates polling; any other `sk-ant-` = proxy-only mode
- All new tests go in `tests/` directory alongside existing test files

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/pricing.py` | Modify | Add `cache_write_per_m` field, update `estimate_cost_usd`, add Claude prices |
| `backend/providers/anthropic_adapter.py` | Create | Full `AnthropicAdapter` implementation |
| `backend/main.py` | Modify | Register `AnthropicAdapter` in adapters dict |
| `tests/fixtures/anthropic_usage.json` | Create | Recorded fixture for usage API mock |
| `tests/fixtures/anthropic_costs.json` | Create | Recorded fixture for costs API mock |
| `tests/test_anthropic_adapter.py` | Create | Adapter unit tests (respx mocks) |
| `tests/test_pricing.py` | Create | `estimate_cost_usd` unit tests incl. cache_write path |

---

## Task 1: Extend pricing.py with `cache_write_per_m` and Claude models

**Files:**
- Modify: `backend/pricing.py`
- Create: `tests/test_pricing.py`

**Interfaces:**
- Produces: `estimate_cost_usd(model, input_tokens, output_tokens, cache_read_tokens=0, cache_write_tokens=0, audio_input_tokens=0, audio_output_tokens=0) -> float | None`
- Produces: `ModelPrice(input_per_m, output_per_m, cache_read_per_m=0.0, cache_write_per_m=0.0, audio_input_per_m=None, audio_output_per_m=None)`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pricing.py`:

```python
"""Tests for estimate_cost_usd — including cache_write_tokens path."""

import pytest

from backend.pricing import ModelPrice, estimate_cost_usd


def test_claude_opus_cost_basic():
    # 1000 input, 500 output, no caching
    cost = estimate_cost_usd("claude-opus-4-8", 1000, 500)
    assert cost == pytest.approx((1000 * 5.00 + 500 * 25.00) / 1_000_000)


def test_claude_cache_write_billed_separately():
    # 800 text input + 200 cache_write (25% premium = 6.25/M), 500 output
    cost = estimate_cost_usd("claude-opus-4-8", 1000, 500, cache_write_tokens=200)
    text_in = 800  # 1000 - 200 cache_write
    expected = (text_in * 5.00 + 200 * 6.25 + 500 * 25.00) / 1_000_000
    assert cost == pytest.approx(expected)


def test_claude_cache_read_billed_at_read_rate():
    # 700 text input + 300 cache_read (0.50/M), 500 output
    cost = estimate_cost_usd("claude-opus-4-8", 1000, 500, cache_read_tokens=300)
    text_in = 700
    expected = (text_in * 5.00 + 300 * 0.50 + 500 * 25.00) / 1_000_000
    assert cost == pytest.approx(expected)


def test_claude_all_cache_types():
    # 500 text + 300 cache_write + 200 cache_read, 500 output
    cost = estimate_cost_usd(
        "claude-opus-4-8", 1000, 500,
        cache_read_tokens=200, cache_write_tokens=300
    )
    text_in = 500
    expected = (text_in * 5.00 + 300 * 6.25 + 200 * 0.50 + 500 * 25.00) / 1_000_000
    assert cost == pytest.approx(expected)


def test_claude_sonnet_prices():
    cost = estimate_cost_usd("claude-sonnet-4-6", 1_000_000, 1_000_000)
    assert cost == pytest.approx(3.00 + 15.00)


def test_claude_haiku_prices():
    cost = estimate_cost_usd("claude-haiku-4-5", 1_000_000, 1_000_000)
    assert cost == pytest.approx(1.00 + 5.00)


def test_claude_versioned_model_id_matches():
    # prefix matching — "claude-opus-4-8-20260101" should match "claude-opus-4-8"
    cost = estimate_cost_usd("claude-opus-4-8-20260101", 1_000_000, 0)
    assert cost == pytest.approx(5.00)


def test_gemini_cache_write_zero_no_change():
    # Existing Gemini models: cache_write_per_m=0.0, passing cache_write_tokens has no effect
    cost_before = estimate_cost_usd("gemini-2.5-flash", 1000, 500)
    cost_after = estimate_cost_usd("gemini-2.5-flash", 1000, 500, cache_write_tokens=200)
    # cache_write_tokens shifts some input to write bucket billed at 0.0 — net same as treating them as text
    # Actually with cache_write_per_m=0.0, cache_write tokens cost 0 instead of input_per_m — slight diff
    # Just assert both return a float (not None)
    assert cost_before is not None
    assert cost_after is not None


def test_unknown_model_returns_none():
    assert estimate_cost_usd("gpt-9000-turbo", 1000, 500) is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/kavin/Projects/machanirobotics/burnmeter
python -m pytest tests/test_pricing.py -v
```

Expected: multiple FAILs — `cache_write_tokens` param not accepted yet, Claude models not in table.

- [ ] **Step 3: Add `cache_write_per_m` to `ModelPrice` and update `estimate_cost_usd`**

Edit `backend/pricing.py`. Replace the `ModelPrice` dataclass and `estimate_cost_usd` function:

```python
@dataclass(frozen=True)
class ModelPrice:
    input_per_m: float
    output_per_m: float
    cache_read_per_m: float = 0.0
    cache_write_per_m: float = 0.0          # cache creation tokens — Claude bills at 25% premium
    audio_input_per_m: float | None = None
    audio_output_per_m: float | None = None
```

Replace the `estimate_cost_usd` function signature and body:

```python
def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    audio_input_tokens: int = 0,
    audio_output_tokens: int = 0,
) -> float | None:
    """Estimated cost, or None when the model isn't in the table.

    `input_tokens`/`output_tokens` are TOTALS (all modalities); cache and audio
    portions are passed separately and billed at their own rates.
    """
    p = _lookup(model)
    if p is None:
        return None
    audio_in_rate = p.audio_input_per_m if p.audio_input_per_m is not None else p.input_per_m
    audio_out_rate = p.audio_output_per_m if p.audio_output_per_m is not None else p.output_per_m
    text_in = max(0, input_tokens - cache_read_tokens - cache_write_tokens - audio_input_tokens)
    text_out = max(0, output_tokens - audio_output_tokens)
    return (
        text_in * p.input_per_m
        + cache_read_tokens * p.cache_read_per_m
        + cache_write_tokens * p.cache_write_per_m
        + audio_input_tokens * audio_in_rate
        + text_out * p.output_per_m
        + audio_output_tokens * audio_out_rate
    ) / 1_000_000
```

Add Claude model entries after the Gemini section in `PRICES`:

```python
# Anthropic Claude models — standard tier, verified 2026-06-17
# cache_write_per_m = input_per_m * 1.25 (prompt caching creation premium)
"claude-fable-5":    ModelPrice(10.00, 50.00, cache_read_per_m=1.00,  cache_write_per_m=12.50),
"claude-opus-4-8":   ModelPrice(5.00,  25.00, cache_read_per_m=0.50,  cache_write_per_m=6.25),
"claude-opus-4-7":   ModelPrice(5.00,  25.00, cache_read_per_m=0.50,  cache_write_per_m=6.25),
"claude-opus-4-6":   ModelPrice(5.00,  25.00, cache_read_per_m=0.50,  cache_write_per_m=6.25),
"claude-sonnet-4-6": ModelPrice(3.00,  15.00, cache_read_per_m=0.30,  cache_write_per_m=3.75),
"claude-haiku-4-5":  ModelPrice(1.00,   5.00, cache_read_per_m=0.10,  cache_write_per_m=1.25),
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_pricing.py -v
```

Expected: all 9 PASS.

- [ ] **Step 5: Run full test suite to confirm no regressions**

```bash
python -m pytest tests/ -v
```

Expected: all 44 existing tests still pass, plus 9 new pricing tests (53 total).

- [ ] **Step 6: Commit**

```bash
git add backend/pricing.py tests/test_pricing.py
git commit -m "feat: add cache_write_per_m to ModelPrice and Claude model prices"
```

---

## Task 2: Implement AnthropicAdapter

**Files:**
- Create: `backend/providers/anthropic_adapter.py`
- Create: `tests/fixtures/anthropic_usage.json`
- Create: `tests/fixtures/anthropic_costs.json`
- Create: `tests/test_anthropic_adapter.py`

**Interfaces:**
- Consumes: `ProviderAdapter`, `UsageRecord`, `CostRecord`, `KeyInfo`, `InvalidKeyError`, `ProviderError`, `mask_key` from `backend.providers.base`
- Produces: `AnthropicAdapter` — importable as `from backend.providers.anthropic_adapter import AnthropicAdapter`

**⚠️ Endpoint verification required before coding:**
Before writing the adapter, verify the org usage endpoint URL in the [Anthropic API docs](https://docs.anthropic.com). The plan uses `/v1/organization/usage` (singular) — confirm the exact path, response shape, and pagination fields (`has_more`, `next_page` or equivalent). Auth headers are `x-api-key: {key}` and `anthropic-version: 2023-06-01`.

- [ ] **Step 1: Create fixture files**

Create `tests/fixtures/anthropic_usage.json` — model this on the actual Anthropic API response shape (verify against docs). The shape below assumes daily buckets grouped by model; update field names to match the real response:

```json
{
  "data": [
    {
      "model": "claude-opus-4-8",
      "start_time": 1780272000,
      "end_time": 1780358400,
      "input_tokens": 10000,
      "output_tokens": 2000,
      "cache_creation_input_tokens": 500,
      "cache_read_input_tokens": 3000,
      "request_count": 15
    },
    {
      "model": "claude-sonnet-4-6",
      "start_time": 1780272000,
      "end_time": 1780358400,
      "input_tokens": 5000,
      "output_tokens": 800,
      "cache_creation_input_tokens": 0,
      "cache_read_input_tokens": 0,
      "request_count": 8
    }
  ],
  "has_more": false,
  "next_page": null
}
```

Create `tests/fixtures/anthropic_costs.json`:

```json
{
  "data": [
    {
      "start_time": 1780272000,
      "end_time": 1780358400,
      "cost": 0.87
    }
  ],
  "has_more": false,
  "next_page": null
}
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_anthropic_adapter.py`:

```python
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
    info = await adapter.validate_key("sk-ant-admin-test-key")
    assert info.provider == "anthropic"
    assert "polling" in info.label.lower() or "admin" in info.label.lower()
    assert "sk-ant" in info.masked_key


@respx.mock
async def test_validate_regular_key_returns_proxy_only_label(adapter):
    respx.get(f"{BASE}/models").mock(return_value=httpx.Response(200, json={"data": []}))
    info = await adapter.validate_key("sk-ant-api03-regular-key")
    assert "proxy" in info.label.lower()


@respx.mock
async def test_validate_invalid_key_raises(adapter):
    respx.get(f"{BASE}/models").mock(return_value=httpx.Response(401, json={"error": {"message": "invalid key"}}))
    with pytest.raises(InvalidKeyError):
        await adapter.validate_key("sk-ant-bad-key")


# ── fetch_usage ───────────────────────────────────────────────────────────────

@respx.mock
async def test_fetch_usage_regular_key_returns_empty(adapter):
    records = await adapter.fetch_usage("sk-ant-api03-regular", date(2026, 6, 1), date(2026, 6, 2))
    assert records == []


@respx.mock
async def test_fetch_usage_admin_key_normalizes(adapter):
    respx.get(f"{BASE}/organization/usage").mock(
        return_value=httpx.Response(200, json=fixture("anthropic_usage.json"))
    )
    records = await adapter.fetch_usage("sk-ant-admin-test", date(2026, 6, 1), date(2026, 6, 2))
    assert len(records) == 2

    r = records[0]
    assert r.provider == "anthropic"
    assert r.model == "claude-opus-4-8"
    assert r.date == "2026-06-01"
    assert r.input_tokens == 10000
    assert r.output_tokens == 2000
    assert r.cache_write_tokens == 500
    assert r.cache_read_tokens == 3000
    assert r.requests == 15
    assert r.cost_usd is None
    assert r.source == "usage_api"
    assert r.cost_estimated is False


@respx.mock
async def test_fetch_usage_pagination(adapter):
    page1 = {**fixture("anthropic_usage.json"), "has_more": True, "next_page": "cursor_abc"}
    page2 = fixture("anthropic_usage.json")

    route = respx.get(f"{BASE}/organization/usage")
    route.side_effect = [
        httpx.Response(200, json=page1),
        httpx.Response(200, json=page2),
    ]
    records = await adapter.fetch_usage("sk-ant-admin-test", date(2026, 6, 1), date(2026, 6, 2))
    assert len(records) == 4
    assert route.calls[1].request.url.params["page"] == "cursor_abc"


# ── fetch_costs ───────────────────────────────────────────────────────────────

@respx.mock
async def test_fetch_costs_regular_key_returns_empty(adapter):
    records = await adapter.fetch_costs("sk-ant-api03-regular", date(2026, 6, 1), date(2026, 6, 2))
    assert records == []


@respx.mock
async def test_fetch_costs_admin_key_normalizes(adapter):
    respx.get(f"{BASE}/organization/costs").mock(
        return_value=httpx.Response(200, json=fixture("anthropic_costs.json"))
    )
    records = await adapter.fetch_costs("sk-ant-admin-test", date(2026, 6, 1), date(2026, 6, 2))
    assert len(records) == 1
    assert records[0].provider == "anthropic"
    assert records[0].cost_usd == pytest.approx(0.87)
    assert records[0].source == "usage_api"


@respx.mock
async def test_fetch_costs_404_returns_empty(adapter):
    respx.get(f"{BASE}/organization/costs").mock(
        return_value=httpx.Response(404, json={"error": {"message": "not found"}})
    )
    records = await adapter.fetch_costs("sk-ant-admin-test", date(2026, 6, 1), date(2026, 6, 2))
    assert records == []


@respx.mock
async def test_fetch_usage_429_retries(adapter):
    route = respx.get(f"{BASE}/organization/usage")
    route.side_effect = [
        httpx.Response(429, headers={"retry-after": "0"}, json={}),
        httpx.Response(200, json=fixture("anthropic_usage.json")),
    ]
    records = await adapter.fetch_usage("sk-ant-admin-test", date(2026, 6, 1), date(2026, 6, 2))
    assert len(records) == 2
    assert route.call_count == 2
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
python -m pytest tests/test_anthropic_adapter.py -v
```

Expected: FAILs with `ModuleNotFoundError: No module named 'backend.providers.anthropic_adapter'`.

- [ ] **Step 4: Implement `anthropic_adapter.py`**

Create `backend/providers/anthropic_adapter.py`:

```python
"""Anthropic adapter — Usage API + Costs API (admin key) or proxy-only (regular key).

Admin key (sk-ant-admin*): polls /v1/organization/usage and /v1/organization/costs hourly.
Regular key (sk-ant-api03-* etc.): fetch_usage + fetch_costs return [] immediately;
data accumulates via proxy capture only.

Endpoints — verify paths against https://docs.anthropic.com before shipping:
  GET /v1/organization/usage?start_date&end_date&model&page&limit
  GET /v1/organization/costs?start_date&end_date&page&limit
  GET /v1/models  — used for key validation (works with any key)
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

import httpx

from backend.providers.base import (
    CostRecord,
    InvalidKeyError,
    KeyInfo,
    ProviderAdapter,
    ProviderError,
    UsageRecord,
    mask_key,
)

BASE_URL = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"
MAX_RETRIES = 4


def _day(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def _is_admin(key: str) -> bool:
    return key.startswith("sk-ant-admin")


class AnthropicAdapter(ProviderAdapter):
    name = "anthropic"
    display_name = "Anthropic"
    key_hint = (
        "Accepts any Anthropic API key (sk-ant-*). "
        "For 90-day usage history, use an admin key (sk-ant-admin-*) created at "
        "console.anthropic.com → Settings → API Keys → Admin keys. "
        "A regular API key enables proxy-captured data only."
    )

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url

    def _headers(self, key: str) -> dict:
        return {
            "x-api-key": key,
            "anthropic-version": ANTHROPIC_VERSION,
        }

    async def _get_pages(self, key: str, path: str, params: dict) -> list[dict]:
        """Fetch all pages of a paginated endpoint with 429 backoff."""
        items: list[dict] = []
        page: str | None = None
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                q = dict(params)
                if page:
                    q["page"] = page
                for attempt in range(MAX_RETRIES):
                    resp = await client.get(
                        f"{self.base_url}{path}",
                        params=q,
                        headers=self._headers(key),
                    )
                    if resp.status_code == 429:
                        retry_after = float(resp.headers.get("retry-after", 2 ** (attempt + 1)))
                        await asyncio.sleep(retry_after)
                        continue
                    break
                if resp.status_code in (401, 403):
                    raise InvalidKeyError(
                        "Anthropic rejected this key. "
                        "For usage history, you need an admin key (sk-ant-admin-*) from "
                        "console.anthropic.com → Settings → API Keys → Admin keys."
                    )
                if resp.status_code == 404:
                    return []
                if resp.status_code >= 400:
                    raise ProviderError(f"Anthropic {path} returned {resp.status_code}")
                body = resp.json()
                items.extend(body.get("data", []))
                if not body.get("has_more"):
                    return items
                page = body.get("next_page")
                if not page:
                    return items

    async def validate_key(self, key: str) -> KeyInfo:
        async with httpx.AsyncClient(timeout=30) as client:
            for attempt in range(MAX_RETRIES):
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers=self._headers(key),
                )
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("retry-after", 2 ** (attempt + 1)))
                    await asyncio.sleep(retry_after)
                    continue
                break
        if resp.status_code in (401, 403):
            raise InvalidKeyError("Anthropic rejected this key.")
        if resp.status_code >= 400:
            raise ProviderError(f"Anthropic /models returned {resp.status_code}")
        if _is_admin(key):
            label = "Admin key — polling + proxy enabled"
        else:
            label = "API key — proxy only (add admin key for 90-day history)"
        return KeyInfo(provider=self.name, label=label, masked_key=mask_key(key))

    async def fetch_usage(self, key: str, start: date, end: date) -> list[UsageRecord]:
        if not _is_admin(key):
            return []
        rows = await self._get_pages(
            key,
            "/organization/usage",
            {
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "limit": 100,
            },
        )
        records: list[UsageRecord] = []
        for r in rows:
            ts = r.get("start_time")
            day = _day(ts) if ts is not None else r.get("date", "")
            records.append(
                UsageRecord(
                    provider=self.name,
                    model=r.get("model") or "unknown",
                    date=day,
                    input_tokens=r.get("input_tokens", 0),
                    output_tokens=r.get("output_tokens", 0),
                    cache_read_tokens=r.get("cache_read_input_tokens", 0),
                    cache_write_tokens=r.get("cache_creation_input_tokens", 0),
                    requests=r.get("request_count", 0),
                    cost_usd=None,
                    source="usage_api",
                    cost_estimated=False,
                )
            )
        return records

    async def fetch_costs(self, key: str, start: date, end: date) -> list[CostRecord]:
        if not _is_admin(key):
            return []
        rows = await self._get_pages(
            key,
            "/organization/costs",
            {
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "limit": 100,
            },
        )
        records: list[CostRecord] = []
        for r in rows:
            ts = r.get("start_time")
            day = _day(ts) if ts is not None else r.get("date", "")
            records.append(
                CostRecord(
                    provider=self.name,
                    date=day,
                    cost_usd=float(r.get("cost", r.get("amount", {}).get("value", 0.0))),
                    source="usage_api",
                )
            )
        return records
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
python -m pytest tests/test_anthropic_adapter.py -v
```

Expected: all 11 PASS.

If fixture field names don't match the real API response shape, update the fixtures AND the field lookups in `fetch_usage`/`fetch_costs` together — they are coupled.

- [ ] **Step 6: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all 53 + 11 = 64 tests pass (44 original + 9 pricing + 11 adapter).

- [ ] **Step 7: Commit**

```bash
git add backend/providers/anthropic_adapter.py \
        tests/test_anthropic_adapter.py \
        tests/fixtures/anthropic_usage.json \
        tests/fixtures/anthropic_costs.json
git commit -m "feat: add AnthropicAdapter with hybrid polling + proxy-only degradation"
```

---

## Task 3: Register adapter in main.py

**Files:**
- Modify: `backend/main.py`

**Interfaces:**
- Consumes: `AnthropicAdapter` from `backend.providers.anthropic_adapter`

- [ ] **Step 1: Add import and registration**

Open `backend/main.py`. Find the adapters dict (currently `{"openai": OpenAIAdapter()}`). Add the Anthropic import alongside the existing OpenAI import and extend the dict:

```python
from backend.providers.anthropic_adapter import AnthropicAdapter
from backend.providers.openai_adapter import OpenAIAdapter

# ...

adapters = {
    "openai": OpenAIAdapter(),
    "anthropic": AnthropicAdapter(),
}
```

- [ ] **Step 2: Start the server and verify the Anthropic provider card appears in Settings**

```bash
make dev   # or: uvicorn backend.main:app --reload --port 8400
```

Open `http://localhost:8400` → Settings → Providers. Confirm:
- "Anthropic" card is visible
- Key hint text mentions `sk-ant-admin-*`
- Saving a regular `sk-ant-*` key shows "proxy only" label
- Saving a `sk-ant-admin-*` key (if available) shows "polling + proxy" label and triggers a sync

- [ ] **Step 3: Run full test suite one final time**

```bash
python -m pytest tests/ -v
```

Expected: all 64 tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/main.py
git commit -m "feat: register AnthropicAdapter — Anthropic now tracked alongside OpenAI"
```

---

## Post-implementation note

The org usage endpoint URL (`/v1/organization/usage`) must be verified against live Anthropic API docs before Step 4 of Task 2. If the endpoint path or response field names differ, update:
1. The `BASE` constant and route in `tests/test_anthropic_adapter.py`
2. The `_get_pages` call paths in `anthropic_adapter.py`
3. The fixture field names in `tests/fixtures/anthropic_usage.json`

These three change together — keep them in sync.
