"""Background sync: pulls usage + costs from provider APIs and GCP billing into SQLite.

Three independent loops:
  1. Provider usage API (hourly) — OpenAI and any future usage-API providers
  2. GCP billing export (every 30 min) — Gemini API + Vertex AI actual costs
  3. GCP Cloud Logging (every 5 min) — Vertex AI near-real-time token counts

Loops 2 and 3 only run when GCP credentials are configured. They can be
started/stopped dynamically via restart_gcp_loops() / stop_gcp_loops()
without restarting the server.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from backend.keys import KeyStore
from backend.providers.base import InvalidKeyError, ProviderAdapter, ProviderError
from backend.store import Store

logger = logging.getLogger(__name__)

BACKFILL_DAYS = 90
REFETCH_OVERLAP_DAYS = 3
SYNC_INTERVAL_SECONDS = 3600        # provider usage API: 1 hour
BILLING_INTERVAL_SECONDS = 1800     # GCP billing export: 30 min
LOGS_INTERVAL_SECONDS = 300         # GCP Cloud Logging: 5 min
BILLING_REFETCH_DAYS = 5            # billing export can lag up to T+3


class SyncEngine:
    def __init__(self, store: Store, keystore: KeyStore, adapters: dict[str, ProviderAdapter]):
        self.store = store
        self.keystore = keystore
        self.adapters = adapters
        self._task: asyncio.Task | None = None
        self._billing_task: asyncio.Task | None = None
        self._logs_task: asyncio.Task | None = None
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, provider: str) -> asyncio.Lock:
        return self._locks.setdefault(provider, asyncio.Lock())

    # ── Provider usage API (loop 1) ──────────────────────────────────────────

    async def sync_provider(self, provider: str, backfill: bool = False) -> None:
        adapter = self.adapters.get(provider)
        if adapter is None:
            return
        key = self.keystore.get_key(provider)
        if not key:
            return
        async with self._lock(provider):
            today = datetime.now(tz=timezone.utc).date()
            start = today - timedelta(days=BACKFILL_DAYS)
            if not backfill:
                rows = await self.store.list_providers()
                state = next((r for r in rows if r["name"] == provider), None)
                watermark = state.get("watermark_date") if state else None
                if watermark:
                    start = max(
                        date.fromisoformat(watermark) - timedelta(days=REFETCH_OVERLAP_DAYS),
                        start,
                    )
            try:
                await self.store.set_sync_state(provider, "syncing")
                usage = await adapter.fetch_usage(key, start, today)
                costs = await adapter.fetch_costs(key, start, today)
                await self.store.upsert_usage(usage)
                await self.store.upsert_costs(costs)
                await self.store.set_sync_state(
                    provider, "ok", watermark=(today - timedelta(days=1)).isoformat()
                )
                logger.info("synced %s: %d usage, %d cost rows", provider, len(usage), len(costs))
            except InvalidKeyError as e:
                await self.store.set_sync_state(provider, "invalid_key", error=str(e))
            except ProviderError as e:
                await self.store.set_sync_state(provider, "error", error=str(e))
            except Exception:
                logger.exception("sync failed for %s", provider)
                await self.store.set_sync_state(provider, "error", error="unexpected error")

    async def sync_all(self, backfill: bool = False) -> None:
        rows = await self.store.list_providers()
        await asyncio.gather(
            *(self.sync_provider(r["name"], backfill) for r in rows),
        )

    async def _loop(self) -> None:
        while True:
            await self.sync_all()
            await asyncio.sleep(SYNC_INTERVAL_SECONDS)

    # ── GCP billing export (loop 2) ──────────────────────────────────────────

    async def sync_gcp_billing(self) -> None:
        creds = self.keystore.get_key("gcp_credentials_json")
        table = self.keystore.get_key("gcp_billing_table")
        if not creds or not table:
            return

        from backend.providers.gcp_billing import fetch_billing_costs

        today = datetime.now(tz=timezone.utc).date()
        state = await self.store.get_sync_state("__gcp_billing__")
        watermark = state.get("watermark_date") if state else None
        if watermark:
            start = max(
                date.fromisoformat(watermark) - timedelta(days=BILLING_REFETCH_DAYS),
                today - timedelta(days=BACKFILL_DAYS),
            )
        else:
            start = today - timedelta(days=BACKFILL_DAYS)

        try:
            await self.store.set_sync_state("__gcp_billing__", "syncing")
            costs = await fetch_billing_costs(creds, table, start, today)
            await self.store.upsert_costs(costs)

            if any(c.provider == "vertex_ai" for c in costs):
                await self.store.ensure_provider(
                    "vertex_ai", "Google Vertex AI", "via GCP billing", "billing export"
                )

            await self.store.set_sync_state(
                "__gcp_billing__", "ok",
                watermark=(today - timedelta(days=1)).isoformat(),
            )
            logger.info("GCP billing sync: %d cost rows", len(costs))
        except ProviderError as e:
            await self.store.set_sync_state("__gcp_billing__", "error", error=str(e))
        except Exception:
            logger.exception("GCP billing sync failed")
            await self.store.set_sync_state("__gcp_billing__", "error", error="unexpected error")

    async def _billing_loop(self) -> None:
        while True:
            await self.sync_gcp_billing()
            await asyncio.sleep(BILLING_INTERVAL_SECONDS)

    # ── GCP Cloud Logging (loop 3) ───────────────────────────────────────────

    async def sync_gcp_logs(self) -> None:
        creds = self.keystore.get_key("gcp_credentials_json")
        logs_table = self.keystore.get_key("gcp_logs_table")
        if not creds or not logs_table:
            return

        from backend.providers.gcp_logs import fetch_log_usage

        state = await self.store.get_sync_state("__gcp_logs__")
        watermark = state.get("watermark_date") if state else None
        if not watermark:
            watermark = (datetime.now(tz=timezone.utc) - timedelta(days=7)).isoformat()

        try:
            await self.store.set_sync_state("__gcp_logs__", "syncing")
            usage = await fetch_log_usage(creds, logs_table, watermark)
            await self.store.upsert_usage(usage)
            new_watermark = (
                datetime.now(tz=timezone.utc) - timedelta(minutes=30)
            ).isoformat()
            await self.store.set_sync_state("__gcp_logs__", "ok", watermark=new_watermark)
            logger.info("GCP logs sync: %d usage rows", len(usage))
        except ProviderError as e:
            await self.store.set_sync_state("__gcp_logs__", "error", error=str(e))
        except Exception:
            logger.exception("GCP logs sync failed")
            await self.store.set_sync_state("__gcp_logs__", "error", error="unexpected error")

    async def _logs_loop(self) -> None:
        while True:
            await self.sync_gcp_logs()
            await asyncio.sleep(LOGS_INTERVAL_SECONDS)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def restart_gcp_loops(self) -> None:
        """Start/restart GCP billing + logs loops. Called after /api/gcp/connect."""
        creds = self.keystore.get_key("gcp_credentials_json")
        if not creds:
            return
        if self._billing_task is None or self._billing_task.done():
            self._billing_task = asyncio.create_task(self._billing_loop())
        logs_table = self.keystore.get_key("gcp_logs_table")
        if logs_table and (self._logs_task is None or self._logs_task.done()):
            self._logs_task = asyncio.create_task(self._logs_loop())

    async def stop_gcp_loops(self) -> None:
        """Cancel GCP loops. Called after /api/gcp/disconnect."""
        for task in [self._billing_task, self._logs_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._billing_task = None
        self._logs_task = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
        self.restart_gcp_loops()

    async def stop(self) -> None:
        tasks = [t for t in [self._task, self._billing_task, self._logs_task] if t]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
