"""OpenAI adapter — Usage API + Costs API.

Requires an org **Admin API key** (created at platform.openai.com/settings/organization/admin-keys).
A regular project key gets 401/403 from these endpoints; we turn that into an
actionable InvalidKeyError so the UI can explain.

Endpoints (verified against developers.openai.com, 2026-06):
  GET /v1/organization/usage/completions?start_time&end_time&bucket_width=1d&group_by[]=model&limit&page
  GET /v1/organization/costs?start_time&end_time&limit&page
Both return {"object":"page","data":[bucket...],"has_more":bool,"next_page":cursor}.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

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

BASE_URL = "https://api.openai.com/v1"
MAX_RETRIES = 4


def _day(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


class OpenAIAdapter(ProviderAdapter):
    name = "openai"
    display_name = "OpenAI"
    key_hint = (
        "Requires an organization Admin API key (sk-admin-…), created under "
        "Settings → Organization → Admin keys. Regular project keys cannot read usage."
    )

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url

    async def _get_pages(self, key: str, path: str, params: dict) -> list[dict]:
        """Fetch all pages of a bucketed usage/costs endpoint with 429 backoff."""
        buckets: list[dict] = []
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
                        headers={"Authorization": f"Bearer {key}"},
                    )
                    if resp.status_code == 429:
                        retry_after = float(resp.headers.get("retry-after", 2 ** (attempt + 1)))
                        await asyncio.sleep(retry_after)
                        continue
                    break
                if resp.status_code in (401, 403):
                    raise InvalidKeyError(
                        "OpenAI rejected this key for usage endpoints. "
                        "You need an organization Admin API key, not a project key."
                    )
                if resp.status_code >= 400:
                    raise ProviderError(f"OpenAI {path} returned {resp.status_code}")
                body = resp.json()
                buckets.extend(body.get("data", []))
                if not body.get("has_more"):
                    return buckets
                page = body.get("next_page")
                if not page:
                    return buckets

    async def validate_key(self, key: str) -> KeyInfo:
        now = int(datetime.now(tz=timezone.utc).timestamp())
        await self._get_pages(
            key,
            "/organization/usage/completions",
            {"start_time": now - 86400, "limit": 1},
        )
        return KeyInfo(provider=self.name, label="Admin key valid", masked_key=mask_key(key))

    async def fetch_usage(self, key: str, start: date, end: date) -> list[UsageRecord]:
        start_ts = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())
        end_ts = int(
            datetime(end.year, end.month, end.day, tzinfo=timezone.utc).timestamp()
        ) + 86400
        buckets = await self._get_pages(
            key,
            "/organization/usage/completions",
            {
                "start_time": start_ts,
                "end_time": end_ts,
                "bucket_width": "1d",
                "group_by[]": "model",
                "limit": 31,
            },
        )
        records: list[UsageRecord] = []
        for bucket in buckets:
            day = _day(bucket["start_time"])
            for r in bucket.get("results", []):
                records.append(
                    UsageRecord(
                        provider=self.name,
                        model=r.get("model") or "unknown",
                        date=day,
                        input_tokens=r.get("input_tokens", 0),
                        output_tokens=r.get("output_tokens", 0),
                        cache_read_tokens=r.get("input_cached_tokens", 0),
                        requests=r.get("num_model_requests", 0),
                        cost_usd=None,  # cost comes from fetch_costs (org grain)
                        source="usage_api",
                    )
                )
        return records

    async def fetch_costs(self, key: str, start: date, end: date) -> list[CostRecord]:
        start_ts = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())
        end_ts = int(
            datetime(end.year, end.month, end.day, tzinfo=timezone.utc).timestamp()
        ) + 86400
        buckets = await self._get_pages(
            key,
            "/organization/costs",
            {"start_time": start_ts, "end_time": end_ts, "limit": 31},
        )
        records: list[CostRecord] = []
        for bucket in buckets:
            day = _day(bucket["start_time"])
            for r in bucket.get("results", []):
                amount = (r.get("amount") or {}).get("value", 0.0)
                records.append(
                    CostRecord(
                        provider=self.name,
                        date=day,
                        cost_usd=float(amount),
                        line_item=r.get("line_item"),
                        source="usage_api",
                    )
                )
        return records
