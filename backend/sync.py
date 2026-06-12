"""Background sync: pulls usage + costs from provider APIs into SQLite.

Each provider keeps a watermark (last fully-synced date). Every cycle we
re-fetch from watermark-3 days (usage APIs are eventually consistent for up to
~24-48h) through today, then advance the watermark to yesterday.
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
SYNC_INTERVAL_SECONDS = 3600


class SyncEngine:
    def __init__(self, store: Store, keystore: KeyStore, adapters: dict[str, ProviderAdapter]):
        self.store = store
        self.keystore = keystore
        self.adapters = adapters
        self._task: asyncio.Task | None = None
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, provider: str) -> asyncio.Lock:
        return self._locks.setdefault(provider, asyncio.Lock())

    async def sync_provider(self, provider: str, backfill: bool = False) -> None:
        adapter = self.adapters.get(provider)
        if adapter is None:
            return  # proxy-only providers (gemini) have nothing to poll
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
                logger.info(
                    "synced %s: %d usage rows, %d cost rows", provider, len(usage), len(costs)
                )
            except InvalidKeyError as e:
                await self.store.set_sync_state(provider, "invalid_key", error=str(e))
            except ProviderError as e:
                await self.store.set_sync_state(provider, "error", error=str(e))
            except Exception as e:  # never let one provider kill the loop
                logger.exception("sync failed for %s", provider)
                await self.store.set_sync_state(provider, "error", error=type(e).__name__)

    async def sync_all(self, backfill: bool = False) -> None:
        rows = await self.store.list_providers()
        await asyncio.gather(*(self.sync_provider(r["name"], backfill) for r in rows))

    async def _loop(self) -> None:
        while True:
            await self.sync_all()
            await asyncio.sleep(SYNC_INTERVAL_SECONDS)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
