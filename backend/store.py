"""SQLite persistence. Usage rows are upserted on (provider, model, date, source).

API keys are NEVER stored here — see keys.py.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite

from backend.providers.base import CostRecord, UsageRecord

DEFAULT_DB_PATH = Path(os.environ.get("BURNMETER_DB", "~/.burnmeter/burnmeter.db")).expanduser()

SCHEMA = """
CREATE TABLE IF NOT EXISTS providers (
    name TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    masked_key TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS usage_records (
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    date TEXT NOT NULL,
    source TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    requests INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL,
    cost_estimated INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (provider, model, date, source)
);

CREATE TABLE IF NOT EXISTS cost_records (
    provider TEXT NOT NULL,
    date TEXT NOT NULL,
    source TEXT NOT NULL,
    line_item TEXT NOT NULL DEFAULT '',
    cost_usd REAL NOT NULL,
    PRIMARY KEY (provider, date, source, line_item)
);

CREATE TABLE IF NOT EXISTS sync_state (
    provider TEXT PRIMARY KEY,
    last_synced_at TEXT,
    watermark_date TEXT,
    status TEXT NOT NULL DEFAULT 'idle',
    error TEXT
);
"""


class Store:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)

    async def init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    @asynccontextmanager
    async def _conn(self) -> AsyncIterator[aiosqlite.Connection]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            yield db

    # -- providers -----------------------------------------------------------

    async def add_provider(self, name: str, display_name: str, masked_key: str, label: str) -> None:
        async with self._conn() as db:
            await db.execute(
                "INSERT INTO providers(name, display_name, masked_key, label) VALUES(?,?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET masked_key=excluded.masked_key, label=excluded.label",
                (name, display_name, masked_key, label),
            )
            await db.commit()

    async def remove_provider(self, name: str) -> None:
        async with self._conn() as db:
            await db.execute("DELETE FROM providers WHERE name=?", (name,))
            await db.execute("DELETE FROM usage_records WHERE provider=?", (name,))
            await db.execute("DELETE FROM cost_records WHERE provider=?", (name,))
            await db.execute("DELETE FROM sync_state WHERE provider=?", (name,))
            await db.commit()

    async def list_providers(self) -> list[dict[str, Any]]:
        async with self._conn() as db:
            cur = await db.execute(
                """SELECT p.*, s.last_synced_at, s.watermark_date,
                          s.status AS sync_status, s.error AS sync_error
                   FROM providers p LEFT JOIN sync_state s ON s.provider = p.name
                   ORDER BY p.name"""
            )
            return [dict(r) for r in await cur.fetchall()]

    # -- usage ---------------------------------------------------------------

    async def upsert_usage(self, records: list[UsageRecord]) -> None:
        if not records:
            return
        async with self._conn() as db:
            await db.executemany(
                """INSERT INTO usage_records
                   (provider, model, date, source, input_tokens, output_tokens,
                    cache_read_tokens, cache_write_tokens, requests, cost_usd, cost_estimated)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(provider, model, date, source) DO UPDATE SET
                     input_tokens=excluded.input_tokens,
                     output_tokens=excluded.output_tokens,
                     cache_read_tokens=excluded.cache_read_tokens,
                     cache_write_tokens=excluded.cache_write_tokens,
                     requests=excluded.requests,
                     cost_usd=excluded.cost_usd,
                     cost_estimated=excluded.cost_estimated""",
                [
                    (
                        r.provider, r.model, r.date, r.source,
                        r.input_tokens, r.output_tokens,
                        r.cache_read_tokens, r.cache_write_tokens,
                        r.requests, r.cost_usd, int(r.cost_estimated),
                    )
                    for r in records
                ],
            )
            await db.commit()

    async def increment_usage(self, r: UsageRecord) -> None:
        """Additive upsert for proxy capture (one call at a time)."""
        async with self._conn() as db:
            await db.execute(
                """INSERT INTO usage_records
                   (provider, model, date, source, input_tokens, output_tokens,
                    cache_read_tokens, cache_write_tokens, requests, cost_usd, cost_estimated)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(provider, model, date, source) DO UPDATE SET
                     input_tokens = input_tokens + excluded.input_tokens,
                     output_tokens = output_tokens + excluded.output_tokens,
                     cache_read_tokens = cache_read_tokens + excluded.cache_read_tokens,
                     cache_write_tokens = cache_write_tokens + excluded.cache_write_tokens,
                     requests = requests + excluded.requests,
                     cost_usd = COALESCE(cost_usd, 0) + COALESCE(excluded.cost_usd, 0),
                     cost_estimated = MAX(cost_estimated, excluded.cost_estimated)""",
                (
                    r.provider, r.model, r.date, r.source,
                    r.input_tokens, r.output_tokens,
                    r.cache_read_tokens, r.cache_write_tokens,
                    r.requests, r.cost_usd, int(r.cost_estimated),
                ),
            )
            await db.commit()

    async def upsert_costs(self, records: list[CostRecord]) -> None:
        if not records:
            return
        async with self._conn() as db:
            await db.executemany(
                """INSERT INTO cost_records (provider, date, source, line_item, cost_usd)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(provider, date, source, line_item) DO UPDATE SET
                     cost_usd=excluded.cost_usd""",
                [(r.provider, r.date, r.source, r.line_item or "", r.cost_usd) for r in records],
            )
            await db.commit()

    # -- sync state ------------------------------------------------------------

    async def set_sync_state(
        self, provider: str, status: str, error: str | None = None, watermark: str | None = None
    ) -> None:
        async with self._conn() as db:
            await db.execute(
                """INSERT INTO sync_state(provider, last_synced_at, watermark_date, status, error)
                   VALUES (?, datetime('now'), ?, ?, ?)
                   ON CONFLICT(provider) DO UPDATE SET
                     last_synced_at=datetime('now'),
                     watermark_date=COALESCE(excluded.watermark_date, watermark_date),
                     status=excluded.status, error=excluded.error""",
                (provider, watermark, status, error),
            )
            await db.commit()

    # -- aggregates ------------------------------------------------------------

    async def overview(self, start: str, end: str) -> dict[str, Any]:
        async with self._conn() as db:
            cur = await db.execute(
                """SELECT provider,
                          SUM(input_tokens) AS input_tokens,
                          SUM(output_tokens) AS output_tokens,
                          SUM(cache_read_tokens) AS cache_read_tokens,
                          SUM(cache_write_tokens) AS cache_write_tokens,
                          SUM(requests) AS requests,
                          SUM(cost_usd) AS cost_usd,
                          MAX(cost_estimated) AS cost_estimated
                   FROM usage_records WHERE date BETWEEN ? AND ?
                   GROUP BY provider ORDER BY cost_usd DESC""",
                (start, end),
            )
            by_provider = [dict(r) for r in await cur.fetchall()]

            cur = await db.execute(
                """SELECT date, provider, SUM(cost_usd) AS cost_usd,
                          SUM(input_tokens + output_tokens) AS total_tokens
                   FROM usage_records WHERE date BETWEEN ? AND ?
                   GROUP BY date, provider ORDER BY date""",
                (start, end),
            )
            daily = [dict(r) for r in await cur.fetchall()]

        totals = {
            "cost_usd": sum(p["cost_usd"] or 0 for p in by_provider),
            "input_tokens": sum(p["input_tokens"] or 0 for p in by_provider),
            "output_tokens": sum(p["output_tokens"] or 0 for p in by_provider),
            "requests": sum(p["requests"] or 0 for p in by_provider),
        }
        return {"totals": totals, "by_provider": by_provider, "daily": daily}

    async def breakdown(self, provider: str, start: str, end: str) -> dict[str, Any]:
        async with self._conn() as db:
            cur = await db.execute(
                """SELECT model, source,
                          SUM(input_tokens) AS input_tokens,
                          SUM(output_tokens) AS output_tokens,
                          SUM(cache_read_tokens) AS cache_read_tokens,
                          SUM(cache_write_tokens) AS cache_write_tokens,
                          SUM(requests) AS requests,
                          SUM(cost_usd) AS cost_usd,
                          MAX(cost_estimated) AS cost_estimated
                   FROM usage_records WHERE provider=? AND date BETWEEN ? AND ?
                   GROUP BY model, source ORDER BY cost_usd DESC""",
                (provider, start, end),
            )
            by_model = [dict(r) for r in await cur.fetchall()]

            cur = await db.execute(
                """SELECT date,
                          SUM(input_tokens) AS input_tokens,
                          SUM(output_tokens) AS output_tokens,
                          SUM(cost_usd) AS cost_usd,
                          SUM(requests) AS requests
                   FROM usage_records WHERE provider=? AND date BETWEEN ? AND ?
                   GROUP BY date ORDER BY date""",
                (provider, start, end),
            )
            daily = [dict(r) for r in await cur.fetchall()]

            cur = await db.execute(
                """SELECT date, source, line_item, cost_usd FROM cost_records
                   WHERE provider=? AND date BETWEEN ? AND ? ORDER BY date""",
                (provider, start, end),
            )
            billed = [dict(r) for r in await cur.fetchall()]

        return {"by_model": by_model, "daily": daily, "billed_costs": billed}
