"""Anthropic adapter — Usage Report API + Cost Report API (admin key) or proxy-only (regular key).

Admin key (sk-ant-admin*): polls /v1/organizations/usage_report/messages and
/v1/organizations/cost_report hourly via SyncEngine.
Regular key (sk-ant-api03-* etc.): fetch_usage + fetch_costs return []
immediately; data accumulates via proxy capture only.

Endpoints (verified against platform.claude.com/docs, 2026-06-17):
  GET /v1/organizations/usage_report/messages
    ?starting_at=<RFC3339>&ending_at=<RFC3339>&bucket_width=1d&group_by[]=model&limit&page
  GET /v1/organizations/cost_report
    ?starting_at=<RFC3339>&ending_at=<RFC3339>&bucket_width=1d&limit&page
  GET /v1/models  — key validation (any valid key)

Cost amounts are in cents as decimal strings; divide by 100 for USD.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
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
        """Fetch all pages of a paginated endpoint with 429 backoff.

        Returns a flat list of bucket dicts (each with starting_at, ending_at, results).
        """
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
                buckets.extend(body.get("data", []))
                if not body.get("has_more"):
                    return buckets
                page = body.get("next_page")
                if not page:
                    return buckets

    async def validate_key(self, key: str) -> KeyInfo:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = httpx.Response(500)
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
        buckets = await self._get_pages(
            key,
            "/organizations/usage_report/messages",
            {
                "starting_at": f"{start.isoformat()}T00:00:00Z",
                "ending_at": f"{end.isoformat()}T00:00:00Z",
                "bucket_width": "1d",
                "group_by[]": "model",
                "limit": 31,
            },
        )
        records: list[UsageRecord] = []
        for bucket in buckets:
            day = bucket["starting_at"][:10]
            for r in bucket.get("results", []):
                cache_creation = r.get("cache_creation") or {}
                cache_write = (
                    cache_creation.get("ephemeral_1h_input_tokens", 0)
                    + cache_creation.get("ephemeral_5m_input_tokens", 0)
                )
                cache_read = r.get("cache_read_input_tokens", 0)
                uncached = r.get("uncached_input_tokens", 0)
                records.append(
                    UsageRecord(
                        provider=self.name,
                        model=r.get("model") or "unknown",
                        date=day,
                        input_tokens=uncached + cache_read + cache_write,
                        output_tokens=r.get("output_tokens", 0),
                        cache_read_tokens=cache_read,
                        cache_write_tokens=cache_write,
                        requests=0,
                        cost_usd=None,
                        source="usage_api",
                        cost_estimated=False,
                    )
                )
        return records

    async def fetch_costs(self, key: str, start: date, end: date) -> list[CostRecord]:
        if not _is_admin(key):
            return []
        buckets = await self._get_pages(
            key,
            "/organizations/cost_report",
            {
                "starting_at": f"{start.isoformat()}T00:00:00Z",
                "ending_at": f"{end.isoformat()}T00:00:00Z",
                "bucket_width": "1d",
                "limit": 31,
            },
        )
        # amount is cents as decimal string; sum per day, convert to USD
        day_cents: dict[str, float] = defaultdict(float)
        for bucket in buckets:
            day = bucket["starting_at"][:10]
            for r in bucket.get("results", []):
                day_cents[day] += float(r.get("amount", "0"))
        return [
            CostRecord(
                provider=self.name,
                date=day,
                cost_usd=cents / 100,
                source="usage_api",
            )
            for day, cents in sorted(day_cents.items())
        ]
