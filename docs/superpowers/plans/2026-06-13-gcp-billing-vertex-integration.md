# GCP Billing + Vertex AI Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the manual Gemini-only BigQuery billing setup with a unified GCP connection that covers Gemini API billing reconciliation, Vertex AI costs, and near-real-time Vertex AI token ingestion via Cloud Logging — with a completely redesigned provider onboarding UX.

**Architecture:** Single service account JSON authenticates all GCP data sources. Three independent sync loops run inside `SyncEngine`: hourly OpenAI usage API (existing), 30-min GCP billing export (new), 5-min Vertex AI Cloud Logging (new, optional). BigQuery calls run in a thread-pool executor to avoid blocking the async event loop. `cost_records` table receives billing actuals; `usage_records` receives Cloud Logging token counts and proxy estimates. No schema migrations required.

**Tech Stack:** Python 3.11+, FastAPI, `google-cloud-bigquery>=3.25` (already in billing extra), `google-auth` (explicit dep), aiosqlite, Svelte 5

---

## File Map

**Create:**
- `backend/providers/gcp_billing.py` — replaces `gemini_billing.py`; queries billing export for Gemini API + Vertex AI; table auto-discovery
- `backend/providers/gcp_logs.py` — queries Vertex AI request-response log sink table; returns `UsageRecord` list
- `tests/test_gcp_billing.py`
- `tests/test_gcp_logs.py`

**Modify:**
- `backend/store.py` — add `get_sync_state()`, `ensure_provider()`, `reconciliation_summary()`
- `backend/sync.py` — add billing loop (30 min), logs loop (5 min), `restart_gcp_loops()`, `stop_gcp_loops()`; update `sync_all()`
- `backend/main.py` — add `/api/gcp/*` endpoints + `/api/providers/{name}/reconciliation`; update backward-compat `/api/billing/gemini` routes
- `pyproject.toml` — add explicit `google-auth>=2.30` to billing extra
- `frontend/src/lib/api.ts` — add GCP methods + reconciliation fetch
- `frontend/src/lib/views/Settings.svelte` — GCP card (setup + connected states), Vertex AI auto-card
- `frontend/src/lib/views/Dashboard.svelte` — reconciliation badge on total
- `frontend/src/lib/views/ProviderDetail.svelte` — estimated vs actual cost row
- `frontend/src/lib/components/Heatmap.svelte` — reconciliation dot on cells

**Delete:**
- `backend/providers/gemini_billing.py` — superseded by `gcp_billing.py` (remove in Task 4 after sync.py is updated)

---

## Task 1: gcp_billing.py — Billing Export Ingestion

**Files:**
- Create: `backend/providers/gcp_billing.py`
- Create: `tests/test_gcp_billing.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gcp_billing.py`:

```python
"""Tests for gcp_billing — mock BigQuery, never hit real GCP."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from backend.providers.base import CostRecord, ProviderError


VALID_SA_JSON = json.dumps({
    "type": "service_account",
    "project_id": "test-project",
    "private_key_id": "key123",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n-----END RSA PRIVATE KEY-----\n",
    "client_email": "burnmeter@test-project.iam.gserviceaccount.com",
    "client_id": "123",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
})


def _make_row(day, service, sku, cost_usd):
    r = MagicMock()
    r.day = day
    r.service = service
    r.sku = sku
    r.cost_usd = cost_usd
    return r


@pytest.mark.asyncio
async def test_fetch_billing_costs_gemini_and_vertex():
    rows = [
        _make_row(date(2026, 6, 10), "Generative Language API", "Gemini 2.0 Flash Input Tokens", 1.20),
        _make_row(date(2026, 6, 10), "Vertex AI", "Gemini 1.5 Pro Input Characters", 0.50),
    ]
    mock_job = MagicMock()
    mock_job.result.return_value = rows
    mock_client = MagicMock()
    mock_client.query.return_value = mock_job

    with patch("google.oauth2.service_account.Credentials.from_service_account_info", return_value=MagicMock()), \
         patch("google.cloud.bigquery.Client", return_value=mock_client), \
         patch("google.cloud.bigquery.QueryJobConfig", return_value=MagicMock()), \
         patch("google.cloud.bigquery.ArrayQueryParameter", return_value=MagicMock()), \
         patch("google.cloud.bigquery.ScalarQueryParameter", return_value=MagicMock()):
        from backend.providers.gcp_billing import fetch_billing_costs
        result = await fetch_billing_costs(
            VALID_SA_JSON, "p.d.t", date(2026, 6, 1), date(2026, 6, 10)
        )

    assert len(result) == 2
    gemini = next(r for r in result if r.provider == "gemini")
    vertex = next(r for r in result if r.provider == "vertex_ai")
    assert gemini.cost_usd == 1.20
    assert gemini.source == "billing_export"
    assert vertex.cost_usd == 0.50
    assert vertex.line_item == "Gemini 1.5 Pro Input Characters"
    assert vertex.source == "billing_export"


@pytest.mark.asyncio
async def test_fetch_billing_costs_skips_unknown_service():
    rows = [
        _make_row(date(2026, 6, 10), "Cloud Storage", "Standard Storage", 0.01),
    ]
    mock_job = MagicMock()
    mock_job.result.return_value = rows
    mock_client = MagicMock()
    mock_client.query.return_value = mock_job

    with patch("google.oauth2.service_account.Credentials.from_service_account_info", return_value=MagicMock()), \
         patch("google.cloud.bigquery.Client", return_value=mock_client), \
         patch("google.cloud.bigquery.QueryJobConfig", return_value=MagicMock()), \
         patch("google.cloud.bigquery.ArrayQueryParameter", return_value=MagicMock()), \
         patch("google.cloud.bigquery.ScalarQueryParameter", return_value=MagicMock()):
        from backend.providers.gcp_billing import fetch_billing_costs
        result = await fetch_billing_costs(
            VALID_SA_JSON, "p.d.t", date(2026, 6, 1), date(2026, 6, 10)
        )

    assert result == []


def test_validate_credentials_ok():
    from backend.providers.gcp_billing import validate_credentials
    project_id = validate_credentials(VALID_SA_JSON)
    assert project_id == "test-project"


def test_validate_credentials_bad_type():
    bad = json.dumps({"type": "authorized_user", "project_id": "x"})
    from backend.providers.gcp_billing import validate_credentials
    with pytest.raises(ProviderError, match="service-account"):
        validate_credentials(bad)


def test_validate_credentials_bad_json():
    from backend.providers.gcp_billing import validate_credentials
    with pytest.raises(ProviderError):
        validate_credentials("not json")


@pytest.mark.asyncio
async def test_discover_tables_returns_matching():
    mock_dataset = MagicMock()
    mock_dataset.dataset_id = "billing_data"
    mock_table = MagicMock()
    mock_table.table_id = "gcp_billing_export_v1_ABCDEF"
    mock_client = MagicMock()
    mock_client.list_datasets.return_value = [mock_dataset]
    mock_client.list_tables.return_value = [mock_table]

    with patch("google.oauth2.service_account.Credentials.from_service_account_info", return_value=MagicMock()), \
         patch("google.cloud.bigquery.Client", return_value=mock_client):
        from backend.providers.gcp_billing import discover_tables
        tables = await discover_tables(VALID_SA_JSON)

    assert tables == ["test-project.billing_data.gcp_billing_export_v1_ABCDEF"]
```

- [ ] **Step 2: Run tests — expect failure (module not found)**

```bash
cd /Users/kavin/Projects/machanirobotics/burnmeter
.venv/bin/pytest tests/test_gcp_billing.py -v
```

Expected: `ImportError: cannot import name 'fetch_billing_costs' from 'backend.providers.gcp_billing'`

- [ ] **Step 3: Create `backend/providers/gcp_billing.py`**

```python
"""GCP billing export ingestion — covers Gemini API and Vertex AI.

Queries the standard Cloud Billing export table (gcp_billing_export_v1_*)
for both 'Generative Language API' and 'Vertex AI' service rows.
All BigQuery calls run in a thread-pool executor (client is sync).

Requires: pip install 'burnmeter[billing]'
"""

from __future__ import annotations

import asyncio
import json
from datetime import date

from backend.providers.base import CostRecord, ProviderError

SERVICES: dict[str, str] = {
    "Generative Language API": "gemini",
    "Vertex AI": "vertex_ai",
}

_BILLING_QUERY = """
    SELECT DATE(usage_start_time) AS day,
           service.description AS service,
           sku.description AS sku,
           SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS cost_usd
    FROM `{table}`
    WHERE service.description IN UNNEST(@services)
      AND DATE(usage_start_time) BETWEEN @start AND @end
    GROUP BY day, service, sku
    ORDER BY day
"""


def _make_client(credentials_json: str):
    from google.cloud import bigquery
    from google.oauth2 import service_account

    info = json.loads(credentials_json)
    creds = service_account.Credentials.from_service_account_info(info)
    return bigquery.Client(credentials=creds, project=info.get("project_id")), info.get("project_id", "")


def _fetch_billing_sync(credentials_json: str, table: str, start: date, end: date) -> list[CostRecord]:
    from google.cloud import bigquery

    client, _ = _make_client(credentials_json)
    job = client.query(
        _BILLING_QUERY.format(table=table),
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("services", "STRING", list(SERVICES.keys())),
                bigquery.ScalarQueryParameter("start", "DATE", start.isoformat()),
                bigquery.ScalarQueryParameter("end", "DATE", end.isoformat()),
            ]
        ),
    )
    records: list[CostRecord] = []
    for row in job.result():
        provider = SERVICES.get(row.service)
        if not provider:
            continue
        records.append(
            CostRecord(
                provider=provider,
                date=row.day.isoformat(),
                cost_usd=float(row.cost_usd or 0),
                line_item=row.sku or row.service,
                source="billing_export",
            )
        )
    return records


async def fetch_billing_costs(
    credentials_json: str, table: str, start: date, end: date
) -> list[CostRecord]:
    """Async wrapper — runs blocking BigQuery query in thread pool."""
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _fetch_billing_sync, credentials_json, table, start, end
        )
    except ImportError as e:
        raise ProviderError(
            "BigQuery support not installed. Run: pip install 'burnmeter[billing]'"
        ) from e


def _discover_tables_sync(credentials_json: str) -> list[str]:
    from google.cloud import bigquery

    client, project_id = _make_client(credentials_json)
    tables: list[str] = []
    for dataset in client.list_datasets():
        for table in client.list_tables(dataset.dataset_id):
            if "gcp_billing_export" in table.table_id:
                tables.append(f"{project_id}.{dataset.dataset_id}.{table.table_id}")
    return tables


async def discover_tables(credentials_json: str) -> list[str]:
    """List billing export tables in the project for dropdown population."""
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _discover_tables_sync, credentials_json)
    except ImportError as e:
        raise ProviderError(
            "BigQuery support not installed. Run: pip install 'burnmeter[billing]'"
        ) from e


def validate_credentials(credentials_json: str) -> str:
    """Validate service-account JSON shape. Returns project_id. Raises ProviderError."""
    try:
        info = json.loads(credentials_json)
    except json.JSONDecodeError as e:
        raise ProviderError("invalid JSON") from e
    if info.get("type") != "service_account":
        raise ProviderError("not a service-account JSON (type must be 'service_account')")
    return info.get("project_id", "")
```

- [ ] **Step 4: Run tests — expect pass**

```bash
.venv/bin/pytest tests/test_gcp_billing.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/providers/gcp_billing.py tests/test_gcp_billing.py
git commit -m "feat: gcp_billing — billing export ingestion for Gemini API + Vertex AI"
```

---

## Task 2: gcp_logs.py — Vertex AI Cloud Logging Ingestion

**Files:**
- Create: `backend/providers/gcp_logs.py`
- Create: `tests/test_gcp_logs.py`

**Context:** Requires a Cloud Logging → BigQuery log sink configured on the Vertex AI project. Enable **request-response logging** on each Vertex AI endpoint:
```python
endpoint.update(request_response_logging_config={
    "enabled": True,
    "bigquery_destination": {"output_uri": "bq://PROJECT/DATASET/TABLE"}
})
```
The BQ log table has columns: `timestamp`, `endpoint_id`, `deployed_model_id`, `request` (JSON string), `response` (JSON string). Token counts are in `response.usageMetadata`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gcp_logs.py`:

```python
"""Tests for gcp_logs — mock BigQuery."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

VALID_SA_JSON = json.dumps({
    "type": "service_account",
    "project_id": "test-project",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----\n",
    "client_email": "burnmeter@test-project.iam.gserviceaccount.com",
})


def _make_log_row(timestamp_str, model, input_tokens, output_tokens):
    r = MagicMock()
    r.timestamp = MagicMock()
    r.timestamp.isoformat.return_value = timestamp_str
    r.day = MagicMock()
    r.day.isoformat.return_value = timestamp_str[:10]
    r.model = model
    r.input_tokens = input_tokens
    r.output_tokens = output_tokens
    return r


@pytest.mark.asyncio
async def test_fetch_log_usage_aggregates_by_day_and_model():
    rows = [
        _make_log_row("2026-06-13T10:00:00Z", "gemini-2.0-flash-001", 1000, 200),
        _make_log_row("2026-06-13T11:00:00Z", "gemini-2.0-flash-001", 500, 100),
        _make_log_row("2026-06-13T12:00:00Z", "gemini-1.5-pro-001", 2000, 400),
    ]
    mock_job = MagicMock()
    mock_job.result.return_value = rows
    mock_client = MagicMock()
    mock_client.query.return_value = mock_job

    with patch("google.oauth2.service_account.Credentials.from_service_account_info", return_value=MagicMock()), \
         patch("google.cloud.bigquery.Client", return_value=mock_client), \
         patch("google.cloud.bigquery.QueryJobConfig", return_value=MagicMock()), \
         patch("google.cloud.bigquery.ScalarQueryParameter", return_value=MagicMock()):
        from backend.providers.gcp_logs import fetch_log_usage
        result = await fetch_log_usage(VALID_SA_JSON, "p.d.t", "2026-06-13T00:00:00Z")

    assert len(result) == 2
    flash = next(r for r in result if r.model == "gemini-2.0-flash-001")
    pro = next(r for r in result if r.model == "gemini-1.5-pro-001")
    assert flash.input_tokens == 1500
    assert flash.output_tokens == 300
    assert flash.requests == 2
    assert flash.provider == "vertex_ai"
    assert flash.source == "cloud_logging"
    assert flash.cost_estimated is False
    assert pro.input_tokens == 2000


@pytest.mark.asyncio
async def test_fetch_log_usage_skips_null_token_rows():
    rows = [
        _make_log_row("2026-06-13T10:00:00Z", "gemini-2.0-flash-001", None, None),
    ]
    mock_job = MagicMock()
    mock_job.result.return_value = rows
    mock_client = MagicMock()
    mock_client.query.return_value = mock_job

    with patch("google.oauth2.service_account.Credentials.from_service_account_info", return_value=MagicMock()), \
         patch("google.cloud.bigquery.Client", return_value=mock_client), \
         patch("google.cloud.bigquery.QueryJobConfig", return_value=MagicMock()), \
         patch("google.cloud.bigquery.ScalarQueryParameter", return_value=MagicMock()):
        from backend.providers.gcp_logs import fetch_log_usage
        result = await fetch_log_usage(VALID_SA_JSON, "p.d.t", "2026-06-13T00:00:00Z")

    assert result == []
```

- [ ] **Step 2: Run tests — expect failure**

```bash
.venv/bin/pytest tests/test_gcp_logs.py -v
```

Expected: `ImportError: cannot import name 'fetch_log_usage'`

- [ ] **Step 3: Create `backend/providers/gcp_logs.py`**

```python
"""Vertex AI request-response log sink ingestion.

Queries a BigQuery table populated by a Cloud Logging sink on a Vertex AI
endpoint with request-response logging enabled. Provides near-real-time
(~5 min lag) per-request token counts — the only granular usage path for
Vertex AI since there is no proxy.

Log sink table schema (from Vertex AI online prediction logging):
  timestamp TIMESTAMP
  endpoint_id STRING
  deployed_model_id STRING
  request STRING (JSON)
  response STRING (JSON — contains usageMetadata.promptTokenCount etc.)
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace

from backend.providers.base import ProviderError, UsageRecord

_LOGS_QUERY = """
    SELECT
        DATE(timestamp) AS day,
        JSON_VALUE(response, '$.modelVersion') AS model,
        CAST(JSON_VALUE(response, '$.usageMetadata.promptTokenCount') AS INT64) AS input_tokens,
        CAST(JSON_VALUE(response, '$.usageMetadata.candidatesTokenCount') AS INT64) AS output_tokens
    FROM `{table}`
    WHERE timestamp > @since
      AND response IS NOT NULL
"""


def _fetch_logs_sync(
    credentials_json: str, logs_table: str, since_timestamp: str
) -> list[UsageRecord]:
    from google.cloud import bigquery
    from google.oauth2 import service_account

    info = json.loads(credentials_json)
    creds = service_account.Credentials.from_service_account_info(info)
    client = bigquery.Client(credentials=creds, project=info.get("project_id"))

    job = client.query(
        _LOGS_QUERY.format(table=logs_table),
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("since", "TIMESTAMP", since_timestamp),
            ]
        ),
    )

    # Accumulate per (day, model) to produce one UsageRecord per bucket
    buckets: dict[tuple[str, str], UsageRecord] = {}
    for row in job.result():
        if not row.model or row.input_tokens is None:
            continue
        day = row.day.isoformat()
        key = (day, row.model)
        if key not in buckets:
            buckets[key] = UsageRecord(
                provider="vertex_ai",
                model=row.model,
                date=day,
                source="cloud_logging",
                key_id="",
                input_tokens=0,
                output_tokens=0,
                requests=0,
                cost_estimated=False,
            )
        r = buckets[key]
        buckets[key] = UsageRecord(
            provider=r.provider,
            model=r.model,
            date=r.date,
            source=r.source,
            key_id=r.key_id,
            input_tokens=r.input_tokens + (row.input_tokens or 0),
            output_tokens=r.output_tokens + (row.output_tokens or 0),
            requests=r.requests + 1,
            cost_estimated=False,
        )

    return list(buckets.values())


async def fetch_log_usage(
    credentials_json: str, logs_table: str, since_timestamp: str
) -> list[UsageRecord]:
    """Async wrapper — runs blocking BigQuery query in thread pool."""
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _fetch_logs_sync, credentials_json, logs_table, since_timestamp
        )
    except ImportError as e:
        raise ProviderError(
            "BigQuery support not installed. Run: pip install 'burnmeter[billing]'"
        ) from e
```

- [ ] **Step 4: Run tests — expect pass**

```bash
.venv/bin/pytest tests/test_gcp_logs.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/providers/gcp_logs.py tests/test_gcp_logs.py
git commit -m "feat: gcp_logs — Vertex AI Cloud Logging near-real-time token ingestion"
```

---

## Task 3: Store Additions — get_sync_state, ensure_provider, reconciliation_summary

**Files:**
- Modify: `backend/store.py`
- Modify: `tests/test_store.py`

Read `tests/test_store.py` first to understand existing fixture pattern before writing new tests.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_store.py`:

```python
# ---- append these to the existing test file ----

@pytest.mark.asyncio
async def test_get_sync_state_returns_none_when_missing(tmp_store):
    result = await tmp_store.get_sync_state("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_get_sync_state_returns_dict_after_set(tmp_store):
    await tmp_store.set_sync_state("__gcp_billing__", "ok", watermark="2026-06-12")
    result = await tmp_store.get_sync_state("__gcp_billing__")
    assert result is not None
    assert result["status"] == "ok"
    assert result["watermark_date"] == "2026-06-12"


@pytest.mark.asyncio
async def test_ensure_provider_inserts_if_absent(tmp_store):
    await tmp_store.ensure_provider("vertex_ai", "Google Vertex AI", "via GCP billing", "billing export")
    rows = await tmp_store.list_providers()
    assert any(r["name"] == "vertex_ai" for r in rows)


@pytest.mark.asyncio
async def test_ensure_provider_does_not_overwrite_existing(tmp_store):
    await tmp_store.add_provider("vertex_ai", "Google Vertex AI", "via GCP billing", "billing export")
    # Calling ensure again should not raise or change anything
    await tmp_store.ensure_provider("vertex_ai", "CHANGED", "x", "y")
    rows = await tmp_store.list_providers()
    row = next(r for r in rows if r["name"] == "vertex_ai")
    assert row["display_name"] == "Google Vertex AI"


@pytest.mark.asyncio
async def test_reconciliation_summary_empty(tmp_store):
    result = await tmp_store.reconciliation_summary("gemini", "2026-06-01", "2026-06-30")
    assert result == []


@pytest.mark.asyncio
async def test_reconciliation_summary_with_proxy_and_billing(tmp_store):
    from backend.providers.base import CostRecord, UsageRecord

    # Proxy estimate
    await tmp_store.upsert_usage([UsageRecord(
        provider="gemini", model="gemini-2.0-flash", date="2026-06-10",
        source="proxy", cost_usd=1.00, cost_estimated=True
    )])
    # Billing actual
    await tmp_store.upsert_costs([CostRecord(
        provider="gemini", date="2026-06-10", cost_usd=1.05,
        line_item="Flash Input Tokens", source="billing_export"
    )])

    result = await tmp_store.reconciliation_summary("gemini", "2026-06-01", "2026-06-30")
    assert len(result) == 1
    row = result[0]
    assert row["date"] == "2026-06-10"
    assert row["estimated_cost"] == pytest.approx(1.00)
    assert row["actual_cost"] == pytest.approx(1.05)
    assert row["reconciled"] is True
    assert row["delta_pct"] == pytest.approx(5.0)
```

- [ ] **Step 2: Run tests — expect failure**

```bash
.venv/bin/pytest tests/test_store.py -v -k "get_sync_state or ensure_provider or reconciliation"
```

Expected: `AttributeError: 'Store' object has no attribute 'get_sync_state'`

- [ ] **Step 3: Add methods to `backend/store.py`**

Add these three methods to the `Store` class after the `set_sync_state` method (around line 254):

```python
    async def get_sync_state(self, provider: str) -> dict[str, Any] | None:
        async with self._conn() as db:
            cur = await db.execute(
                "SELECT * FROM sync_state WHERE provider=?", (provider,)
            )
            row = await cur.fetchone()
            return dict(row) if row else None

    async def ensure_provider(
        self, name: str, display_name: str, masked_key: str, label: str
    ) -> None:
        """Insert provider only if it doesn't already exist. Safe to call repeatedly."""
        async with self._conn() as db:
            await db.execute(
                """INSERT INTO providers(name, display_name, masked_key, label)
                   VALUES(?,?,?,?)
                   ON CONFLICT(name) DO NOTHING""",
                (name, display_name, masked_key, label),
            )
            await db.commit()

    async def reconciliation_summary(
        self, provider: str, start: str, end: str
    ) -> list[dict[str, Any]]:
        """Per-day estimated vs actual cost for a provider. Used for reconciliation UI."""
        async with self._conn() as db:
            cur = await db.execute(
                """SELECT date, SUM(cost_usd) AS estimated_cost
                   FROM usage_records
                   WHERE provider=? AND date BETWEEN ? AND ? AND source='proxy'
                   GROUP BY date""",
                (provider, start, end),
            )
            estimated = {r["date"]: r["estimated_cost"] or 0.0 for r in await cur.fetchall()}

            cur = await db.execute(
                """SELECT date, SUM(cost_usd) AS actual_cost
                   FROM cost_records
                   WHERE provider=? AND date BETWEEN ? AND ? AND source='billing_export'
                   GROUP BY date""",
                (provider, start, end),
            )
            actual = {r["date"]: r["actual_cost"] or 0.0 for r in await cur.fetchall()}

        all_dates = sorted(set(list(estimated.keys()) + list(actual.keys())))
        result = []
        for d in all_dates:
            est = estimated.get(d, 0.0)
            act = actual.get(d)
            delta_pct: float | None = None
            if act is not None and est > 0:
                delta_pct = round((act - est) / est * 100, 2)
            result.append(
                {
                    "date": d,
                    "estimated_cost": est,
                    "actual_cost": act,
                    "delta_pct": delta_pct,
                    "reconciled": act is not None,
                }
            )
        return result
```

- [ ] **Step 4: Run tests — expect pass**

```bash
.venv/bin/pytest tests/test_store.py -v
```

Expected: all tests pass (existing + new).

- [ ] **Step 5: Commit**

```bash
git add backend/store.py tests/test_store.py
git commit -m "feat: store — get_sync_state, ensure_provider, reconciliation_summary"
```

---

## Task 4: sync.py — Three Independent Loops

**Files:**
- Modify: `backend/sync.py`
- Delete: `backend/providers/gemini_billing.py`

- [ ] **Step 1: Replace `backend/sync.py` entirely**

```python
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
```

- [ ] **Step 2: Delete the old gemini_billing.py**

```bash
git rm backend/providers/gemini_billing.py
```

- [ ] **Step 3: Run existing tests — verify nothing broken**

```bash
.venv/bin/pytest tests/ -v --ignore=tests/test_gcp_billing.py --ignore=tests/test_gcp_logs.py
```

Expected: all existing tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/sync.py
git commit -m "feat: sync — billing loop (30min), logs loop (5min), dynamic restart_gcp_loops"
```

---

## Task 5: main.py — /api/gcp/* Endpoints

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Add GCP Pydantic models and imports**

At the top of `main.py`, after the existing imports, add:

```python
from backend.providers.gcp_billing import validate_credentials  # noqa: E402 (added below lifespan)
```

This import must be lazy (inside the endpoint) to avoid ImportError if billing extra isn't installed. Add these models near the other Pydantic models:

```python
class GCPConnectRequest(BaseModel):
    credentials_json: str
    billing_table: str
    logs_table: str | None = None
```

- [ ] **Step 2: Add all /api/gcp/* endpoints**

Add these endpoints to `main.py` after the `/api/budget` PUT endpoint:

```python
@app.get("/api/gcp/auth-check")
async def gcp_auth_check():
    """Detect if Application Default Credentials are available with billing scope."""
    try:
        import google.auth  # noqa: PLC0415

        _, project = google.auth.default(
            scopes=[
                "https://www.googleapis.com/auth/cloud-billing.readonly",
                "https://www.googleapis.com/auth/bigquery.readonly",
            ]
        )
        return {"adc": True, "project_id": project}
    except Exception:
        return {"adc": False, "project_id": None}


@app.get("/api/gcp/status")
async def gcp_status():
    creds = keystore.get_key("gcp_credentials_json")
    return {
        "configured": creds is not None,
        "project_id": keystore.get_key("gcp_project_id"),
        "billing_table": keystore.get_key("gcp_billing_table"),
        "logs_table": keystore.get_key("gcp_logs_table"),
        "billing_sync": await store.get_sync_state("__gcp_billing__"),
        "logs_sync": await store.get_sync_state("__gcp_logs__"),
    }


class GCPTablesRequest(BaseModel):
    credentials_json: str


@app.post("/api/gcp/tables")
async def gcp_tables(req: GCPTablesRequest):
    """Validate credentials and return list of billing export tables."""
    from backend.providers.gcp_billing import discover_tables, validate_credentials  # noqa: PLC0415

    try:
        validate_credentials(req.credentials_json)
        tables = await discover_tables(req.credentials_json)
        return {"tables": tables}
    except ProviderError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/gcp/connect")
async def gcp_connect(req: GCPConnectRequest):
    """Store GCP credentials, start billing + logs sync loops, trigger immediate sync."""
    from backend.providers.gcp_billing import validate_credentials  # noqa: PLC0415

    try:
        project_id = validate_credentials(req.credentials_json)
    except ProviderError as e:
        raise HTTPException(status_code=400, detail=str(e))

    keystore.set_key("gcp_credentials_json", req.credentials_json)
    keystore.set_key("gcp_billing_table", req.billing_table)
    keystore.set_key("gcp_project_id", project_id)
    if req.logs_table:
        keystore.set_key("gcp_logs_table", req.logs_table)

    sync_engine.restart_gcp_loops()

    import asyncio as _asyncio  # noqa: PLC0415

    _asyncio.create_task(sync_engine.sync_gcp_billing())

    return {"ok": True, "project_id": project_id}


@app.delete("/api/gcp/disconnect")
async def gcp_disconnect():
    for key in ["gcp_credentials_json", "gcp_billing_table", "gcp_logs_table", "gcp_project_id"]:
        keystore.delete_key(key)
    await sync_engine.stop_gcp_loops()
    return {"ok": True}


@app.post("/api/gcp/sync")
async def gcp_sync():
    import asyncio as _asyncio  # noqa: PLC0415

    _asyncio.create_task(sync_engine.sync_gcp_billing())
    if keystore.get_key("gcp_logs_table"):
        _asyncio.create_task(sync_engine.sync_gcp_logs())
    return {"ok": True}


@app.get("/api/providers/{name}/reconciliation")
async def reconciliation(name: str, period: str = "30d"):
    start, end = _period_range(period)
    data = await store.reconciliation_summary(name, start, end)
    return {"reconciliation": data, "period": {"start": start, "end": end}}
```

- [ ] **Step 3: Update backward-compat /api/billing/gemini endpoints**

Replace the existing `/api/billing/gemini` GET, POST, DELETE handlers with these passthrough versions:

```python
# Backward-compat: kept so existing configured setups don't break.
# Redirects to unified /api/gcp/* endpoints.

@app.get("/api/billing/gemini")
async def billing_status():
    status = await gcp_status()
    return {
        "configured": status["configured"],
        "table": status["billing_table"],
    }


class BillingConfig(BaseModel):
    credentials_json: str
    table: str


@app.post("/api/billing/gemini")
async def billing_configure(cfg: BillingConfig):
    req = GCPConnectRequest(credentials_json=cfg.credentials_json, billing_table=cfg.table)
    return await gcp_connect(req)


@app.delete("/api/billing/gemini")
async def billing_remove():
    return await gcp_disconnect()
```

- [ ] **Step 4: Run the test suite**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all tests pass. If `test_api.py` has tests for the old `/api/billing/gemini` endpoints, they should still pass via the backward-compat handlers.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py
git commit -m "feat: /api/gcp/* endpoints — connect, status, tables, sync, disconnect; backward-compat billing/gemini"
```

---

## Task 6: pyproject.toml — Explicit google-auth Dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add google-auth to billing extra**

In `pyproject.toml`, change:
```toml
billing = ["google-cloud-bigquery>=3.25"]
```
to:
```toml
billing = ["google-cloud-bigquery>=3.25", "google-auth>=2.30"]
```

- [ ] **Step 2: Reinstall**

```bash
.venv/bin/pip install -e '.[billing,dev]'
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add explicit google-auth>=2.30 to billing extra"
```

---

## Task 7: api.ts — GCP Frontend API Methods

**Files:**
- Modify: `frontend/src/lib/api.ts`

Read `frontend/src/lib/api.ts` in full before editing to understand the existing export shape.

- [ ] **Step 1: Add GCP types and methods**

Add these types and methods to `api.ts` alongside the existing ones:

```typescript
export interface GCPStatus {
  configured: boolean
  project_id: string | null
  billing_table: string | null
  logs_table: string | null
  billing_sync: { status: string; last_synced_at: string | null; error: string | null } | null
  logs_sync: { status: string; last_synced_at: string | null; error: string | null } | null
}

export interface ReconciliationRow {
  date: string
  estimated_cost: number
  actual_cost: number | null
  delta_pct: number | null
  reconciled: boolean
}
```

Add to the `api` object:

```typescript
gcpAuthCheck: async (): Promise<{ adc: boolean; project_id: string | null }> => {
  const r = await fetch('/api/gcp/auth-check')
  return r.json()
},

gcpStatus: async (): Promise<GCPStatus> => {
  const r = await fetch('/api/gcp/status')
  return r.json()
},

gcpTables: async (credentialsJson: string): Promise<{ tables: string[] }> => {
  const r = await fetch('/api/gcp/tables', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credentials_json: credentialsJson }),
  })
  if (!r.ok) throw new Error((await r.json()).detail ?? 'validation failed')
  return r.json()
},

gcpConnect: async (
  credentialsJson: string,
  billingTable: string,
  logsTable?: string
): Promise<{ ok: boolean; project_id: string }> => {
  const r = await fetch('/api/gcp/connect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      credentials_json: credentialsJson,
      billing_table: billingTable,
      logs_table: logsTable ?? null,
    }),
  })
  if (!r.ok) throw new Error((await r.json()).detail ?? 'connect failed')
  return r.json()
},

gcpDisconnect: async (): Promise<{ ok: boolean }> => {
  const r = await fetch('/api/gcp/disconnect', { method: 'DELETE' })
  return r.json()
},

gcpSync: async (): Promise<{ ok: boolean }> => {
  const r = await fetch('/api/gcp/sync', { method: 'POST' })
  return r.json()
},

reconciliation: async (
  provider: string,
  period = '30d'
): Promise<{ reconciliation: ReconciliationRow[]; period: { start: string; end: string } }> => {
  const r = await fetch(`/api/providers/${provider}/reconciliation?period=${period}`)
  return r.json()
},
```

- [ ] **Step 2: Run TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat: api.ts — GCP connect/status/tables/sync/disconnect + reconciliation fetch"
```

---

## Task 8: Settings.svelte — GCP Card + Vertex AI Card

**Files:**
- Modify: `frontend/src/lib/views/Settings.svelte`

Read the full current `Settings.svelte` before editing. The existing billing section (lines 154–195) is being replaced by the new GCP card which is a sibling to, not nested inside, the Gemini provider card.

- [ ] **Step 1: Replace Settings.svelte**

```svelte
<script lang="ts">
  import { api } from '$lib/api'
  import type { GCPStatus, ProvidersResponse } from '$lib/api'

  let data = $state<ProvidersResponse | null>(null)
  let keyInput = $state<Record<string, string>>({})
  let busy = $state<string | null>(null)
  let errors = $state<Record<string, string>>({})
  let copied = $state(false)

  // GCP connection state
  let gcp = $state<GCPStatus | null>(null)
  let gcpCreds = $state('')
  let gcpProjectId = $state<string | null>(null)  // extracted client-side on paste
  let gcpTables = $state<string[]>([])
  let gcpSelectedTable = $state('')
  let gcpLogsTable = $state('')
  let gcpShowLogs = $state(false)
  let gcpValidating = $state(false)
  let gcpConnecting = $state(false)
  let gcpError = $state('')

  const SERVICE_ACCOUNT_CMD = `gcloud iam service-accounts create burnmeter-reader \\
  --display-name="Burnmeter read-only" --project=PROJECT_ID && \\
gcloud projects add-iam-policy-binding PROJECT_ID \\
  --member="serviceAccount:burnmeter-reader@PROJECT_ID.iam.gserviceaccount.com" \\
  --role="roles/bigquery.dataViewer" && \\
gcloud projects add-iam-policy-binding PROJECT_ID \\
  --member="serviceAccount:burnmeter-reader@PROJECT_ID.iam.gserviceaccount.com" \\
  --role="roles/bigquery.jobUser" && \\
gcloud iam service-accounts keys create burnmeter-key.json \\
  --iam-account="burnmeter-reader@PROJECT_ID.iam.gserviceaccount.com"`

  let cmdCopied = $state(false)

  const proxyUrl = `${location.protocol}//${location.hostname}:8400/proxy/gemini`
  const liveProxyUrl = `ws://${location.hostname}:8400/proxy/gemini`
  let proxyCopied = $state(false)

  api.gcpStatus().then((s) => (gcp = s))

  async function load() {
    data = await api.providers()
  }
  load()

  function extractProjectId(json: string) {
    try {
      const info = JSON.parse(json)
      gcpProjectId = info.project_id ?? null
    } catch {
      gcpProjectId = null
    }
  }

  async function validateAndFetchTables() {
    gcpError = ''
    gcpTables = []
    gcpSelectedTable = ''
    gcpValidating = true
    try {
      const res = await api.gcpTables(gcpCreds)
      gcpTables = res.tables
      if (gcpTables.length === 1) gcpSelectedTable = gcpTables[0]
    } catch (e: any) {
      gcpError = e.message
    } finally {
      gcpValidating = false
    }
  }

  async function connectGCP() {
    gcpError = ''
    gcpConnecting = true
    try {
      await api.gcpConnect(gcpCreds, gcpSelectedTable, gcpShowLogs ? gcpLogsTable : undefined)
      gcpCreds = ''
      gcp = await api.gcpStatus()
    } catch (e: any) {
      gcpError = e.message
    } finally {
      gcpConnecting = false
    }
  }

  async function disconnectGCP() {
    if (!confirm('Remove GCP connection? Billing and Vertex AI sync will stop.')) return
    await api.gcpDisconnect()
    gcp = await api.gcpStatus()
    gcpCreds = ''
    gcpTables = []
    gcpSelectedTable = ''
    await load()
  }

  async function add(name: string) {
    busy = name
    errors = { ...errors, [name]: '' }
    try {
      await api.addProvider(name, keyInput[name] ?? '')
      keyInput = { ...keyInput, [name]: '' }
      await load()
    } catch (e: any) {
      errors = { ...errors, [name]: e.message }
    } finally {
      busy = null
    }
  }

  async function remove(name: string) {
    if (!confirm(`Remove ${name}? Its stored key and local usage history will be deleted.`)) return
    await api.removeProvider(name)
    await load()
  }

  function copyProxy() {
    navigator.clipboard.writeText(proxyUrl)
    proxyCopied = true
    setTimeout(() => (proxyCopied = false), 1500)
  }

  function copyCmd() {
    navigator.clipboard.writeText(SERVICE_ACCOUNT_CMD)
    cmdCopied = true
    setTimeout(() => (cmdCopied = false), 1500)
  }
</script>

<div class="mx-auto max-w-3xl">
  <div class="bento grid-cols-1">

    <!-- Key custody notice -->
    <div class="cell">
      <div class="microlabel">Key custody</div>
      <p class="mt-2 text-sm" style="color: var(--muted)">
        Keys live in your OS keychain (or an encrypted local file), never in the database or logs,
        and are only sent to the provider's official API. Server binds 127.0.0.1.
        Open source — <a class="underline hover:text-paper" href="https://github.com/kavinbm16/burnmeter/blob/master/SECURITY.md" target="_blank" rel="noreferrer">audit the guarantees</a>.
      </p>
    </div>

    <!-- GCP connection card -->
    <div class="cell">
      <div class="flex items-baseline gap-3">
        <h2 class="text-sm font-bold uppercase tracking-widest">Google Cloud Platform</h2>
        <span class="microlabel-dim">billing export · vertex ai</span>
        {#if gcp?.configured}
          <span class="numeral ml-auto text-xs" style="color: var(--red)">● {gcp.project_id}</span>
          <button class="focus-ring microlabel-dim hover:text-paper" onclick={disconnectGCP}>REMOVE</button>
        {/if}
      </div>

      {#if gcp?.configured}
        <div class="mt-3 grid grid-cols-2 gap-px text-xs" style="color: var(--muted)">
          <div>
            <span class="microlabel">Billing export</span>
            <p class="mt-1 numeral">
              {gcp.billing_sync?.status === 'ok' ? '✓' : gcp.billing_sync?.status ?? '—'}
              {#if gcp.billing_sync?.last_synced_at}
                · {gcp.billing_sync.last_synced_at.slice(0, 16)}Z
              {/if}
            </p>
            {#if gcp.billing_sync?.error}
              <p class="mt-1" style="color: var(--red)">▲ {gcp.billing_sync.error}</p>
            {/if}
          </div>
          {#if gcp.logs_table}
            <div>
              <span class="microlabel">Vertex AI logs</span>
              <p class="mt-1 numeral">
                {gcp.logs_sync?.status === 'ok' ? '✓' : gcp.logs_sync?.status ?? '—'}
                {#if gcp.logs_sync?.last_synced_at}
                  · {gcp.logs_sync.last_synced_at.slice(0, 16)}Z
                {/if}
              </p>
              {#if gcp.logs_sync?.error}
                <p class="mt-1" style="color: var(--red)">▲ {gcp.logs_sync.error}</p>
              {/if}
            </div>
          {/if}
        </div>
        <p class="microlabel-dim mt-2">Billing table: <code class="numeral text-xs">{gcp.billing_table}</code></p>
        <button
          class="focus-ring mt-3 border border-hairline px-3 py-1 text-xs tracking-widest hover:text-paper"
          onclick={() => api.gcpSync()}
        >SYNC NOW</button>
      {:else}
        <!-- Setup flow -->
        <p class="mt-2 text-sm" style="color: var(--muted)">
          One service account connects Gemini API billing reconciliation and Vertex AI cost tracking.
        </p>

        <div class="mt-3 flex items-center justify-between">
          <span class="microlabel">Create service account</span>
          <button class="focus-ring microlabel-dim hover:text-paper" onclick={copyCmd}>
            {cmdCopied ? 'COPIED ✓' : 'COPY COMMAND'}
          </button>
        </div>
        <p class="mt-1 text-xs" style="color: var(--muted)">Replace PROJECT_ID with your GCP project. Then paste the generated JSON below.</p>

        <textarea
          placeholder="Paste service-account JSON here…"
          bind:value={gcpCreds}
          oninput={() => extractProjectId(gcpCreds)}
          rows="4"
          class="numeral mt-3 w-full resize-y border border-hairline bg-ink px-3 py-2 text-xs
                 text-paper placeholder:text-muted/60 focus:border-red focus:outline-none"
        ></textarea>

        {#if gcpProjectId}
          <p class="mt-1 text-xs" style="color: var(--muted)">Project: <code class="numeral">{gcpProjectId}</code> ✓</p>
        {/if}

        {#if gcpTables.length === 0}
          <button
            class="focus-ring mt-2 border border-hairline px-4 py-1.5 text-xs tracking-widest hover:text-paper disabled:opacity-40"
            disabled={gcpValidating || !gcpCreds.trim()}
            onclick={validateAndFetchTables}
          >{gcpValidating ? 'VALIDATING…' : 'VALIDATE & FIND TABLES'}</button>
        {:else}
          <div class="mt-3">
            <span class="microlabel">Billing export table</span>
            <select
              bind:value={gcpSelectedTable}
              class="numeral mt-1 w-full border border-hairline bg-ink px-3 py-2 text-xs text-paper focus:border-red focus:outline-none"
            >
              <option value="" disabled>Select table…</option>
              {#each gcpTables as t}
                <option value={t}>{t}</option>
              {/each}
            </select>
          </div>

          <div class="mt-3">
            <button
              class="microlabel-dim hover:text-paper"
              onclick={() => (gcpShowLogs = !gcpShowLogs)}
            >▸ Advanced: Vertex AI live logs (optional)</button>
            {#if gcpShowLogs}
              <p class="mt-2 text-xs" style="color: var(--muted)">
                Enable request-response logging on each Vertex AI endpoint and route to BigQuery.
                Provides per-request token counts with ~5 min lag.
              </p>
              <input
                placeholder="project.dataset.vertex_logs_table"
                bind:value={gcpLogsTable}
                class="numeral mt-2 w-full border border-hairline bg-ink px-3 py-2 text-xs text-paper
                       placeholder:text-muted/60 focus:border-red focus:outline-none"
              />
            {/if}
          </div>

          <button
            class="focus-ring mt-3 bg-red px-5 py-1.5 text-xs font-bold tracking-widest text-ink disabled:opacity-40"
            disabled={gcpConnecting || !gcpSelectedTable}
            onclick={connectGCP}
          >{gcpConnecting ? '…' : 'CONNECT'}</button>
        {/if}

        {#if gcpError}
          <p class="mt-2 text-sm" style="color: var(--red)">▲ {gcpError}</p>
        {/if}
      {/if}
    </div>

    <!-- Provider cards (OpenAI, Gemini) -->
    {#if data}
      {#each Object.entries(data.available) as [name, meta] (name)}
        {@const cfg = data.configured.find((c) => c.name === name)}
        <div class="cell">
          <div class="flex items-baseline gap-3">
            <h2 class="text-sm font-bold uppercase tracking-widest">{meta.display_name}</h2>
            <span class="microlabel-dim">{meta.mode === 'proxy' ? 'local proxy' : 'usage api'}</span>
            {#if cfg}
              <span class="numeral ml-auto text-xs" style="color: var(--red)">
                ● {cfg.masked_key}
                {#if cfg.sync_status === 'syncing'} · SYNCING{/if}
              </span>
              <button class="focus-ring microlabel-dim hover:text-paper" onclick={() => remove(name)}>REMOVE</button>
            {/if}
          </div>

          <p class="mt-2 text-sm" style="color: var(--muted)">{meta.key_hint}</p>

          {#if cfg?.sync_status === 'invalid_key' || cfg?.sync_status === 'error'}
            <p class="mt-2 text-sm" style="color: var(--red)">▲ {cfg.sync_error ?? 'sync failed'}</p>
          {/if}
          {#if cfg?.last_synced_at}
            <p class="microlabel-dim mt-2">last sync {cfg.last_synced_at}Z</p>
          {/if}

          {#if !cfg}
            <div class="mt-4 flex gap-px">
              <input
                type="password"
                placeholder={name === 'openai' ? 'sk-admin-…' : 'AIza…'}
                bind:value={keyInput[name]}
                class="numeral flex-1 border border-hairline bg-ink-2 px-3 py-2 text-sm text-paper
                       placeholder:text-muted/70 focus:border-red focus:outline-none"
                onkeydown={(e) => e.key === 'Enter' && add(name)}
              />
              <button
                class="focus-ring bg-red px-5 text-xs font-bold tracking-widest text-ink disabled:opacity-40"
                disabled={busy === name || !(keyInput[name] ?? '').trim()}
                onclick={() => add(name)}
              >{busy === name ? '…' : 'ADD'}</button>
            </div>
            {#if errors[name]}
              <p class="mt-2 text-sm" style="color: var(--red)">▲ {errors[name]}</p>
            {/if}
          {/if}

          {#if name === 'gemini'}
            <div class="mt-4 border border-hairline bg-ink-2 p-4">
              <div class="flex items-center justify-between">
                <span class="microlabel">Proxy endpoint</span>
                <button class="focus-ring microlabel-dim hover:text-paper" onclick={copyProxy}>
                  {proxyCopied ? 'COPIED ✓' : 'COPY'}
                </button>
              </div>
              <code class="numeral mt-2 block truncate text-xs">{proxyUrl}</code>
              <pre class="mt-3 overflow-x-auto text-xs" style="color: var(--muted)">{`client = genai.Client(
    api_key=...,
    http_options={"base_url": "${proxyUrl}"},
)`}</pre>
              <p class="microlabel-dim mt-2">
                {gcp?.configured
                  ? 'traffic via proxy is estimated — GCP billing reconciliation active ✓'
                  : 'costs are estimated — connect GCP above for actual billed amounts'}
              </p>

              <div class="mt-4 border-t border-hairline pt-3">
                <span class="microlabel">Live API (websocket) sessions</span>
                <code class="numeral mt-2 block truncate text-xs">{liveProxyUrl}</code>
                <pre class="mt-2 overflow-x-auto text-xs" style="color: var(--muted)">{`client = genai.Client(
    api_key=...,
    http_options={"base_url": "${liveProxyUrl}"},
)`}</pre>
              </div>
            </div>
          {/if}
        </div>
      {/each}

      <!-- Vertex AI auto-card — appears when GCP billing finds Vertex AI costs -->
      {#if data.configured.find((c) => c.name === 'vertex_ai')}
        {@const vtx = data.configured.find((c) => c.name === 'vertex_ai')!}
        <div class="cell">
          <div class="flex items-baseline gap-3">
            <h2 class="text-sm font-bold uppercase tracking-widest">Google Vertex AI</h2>
            <span class="microlabel-dim">billing export</span>
            <span class="numeral ml-auto text-xs" style="color: var(--red)">● via GCP billing</span>
          </div>
          <p class="mt-2 text-sm" style="color: var(--muted)">
            Cost data sourced from GCP billing export. No proxy — all Vertex AI traffic is captured
            regardless of where it runs.
            {#if !gcp?.logs_table}
              Token counts require Vertex AI request-response logging (configure in GCP card above).
            {:else}
              Token counts via request-response logs ✓
            {/if}
          </p>
          {#if vtx.last_synced_at}
            <p class="microlabel-dim mt-2">last sync {vtx.last_synced_at}Z</p>
          {/if}
        </div>
      {/if}
    {:else}
      <div class="cell h-40 animate-pulse"></div>
    {/if}

  </div>
</div>
```

- [ ] **Step 2: Run TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/views/Settings.svelte
git commit -m "feat: Settings — GCP connect card (setup/connected), Vertex AI auto-card, gemini proxy reconciliation hint"
```

---

## Task 9: Dashboard.svelte — Reconciliation Badge on Total

**Files:**
- Modify: `frontend/src/lib/views/Dashboard.svelte`

Read `frontend/src/lib/views/Dashboard.svelte` in full before editing. The total spend display is in the primary view. Add a small `(reconciled)` or `(estimated)` badge below the main cost figure.

- [ ] **Step 1: Add reconciliation state to Dashboard**

In the `<script>` section, add after existing data fetching:

```typescript
import type { ReconciliationRow } from '$lib/api'

let reconciliation = $state<ReconciliationRow[]>([])

// Fetch reconciliation for gemini (proxy vs billing)
async function loadReconciliation() {
  try {
    const res = await api.reconciliation('gemini', period)
    reconciliation = res.reconciliation
  } catch {
    reconciliation = []
  }
}
```

Call `loadReconciliation()` alongside the existing data load, and re-call it when period changes.

- [ ] **Step 2: Add badge to total cost display**

Find the total cost display in the template. Add a reconciliation sub-label below it:

```svelte
{@const reconciledDays = reconciliation.filter(r => r.reconciled).length}
{@const totalDays = reconciliation.length}
{#if totalDays > 0}
  <p class="microlabel-dim mt-1">
    {reconciledDays === totalDays
      ? 'reconciled against GCP billing'
      : reconciledDays > 0
        ? `${reconciledDays}/${totalDays} days reconciled`
        : 'estimated · connect GCP for actuals'}
  </p>
{/if}
```

- [ ] **Step 3: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/views/Dashboard.svelte
git commit -m "feat: Dashboard — reconciliation badge on total cost"
```

---

## Task 10: ProviderDetail.svelte — Estimated vs Actual Row

**Files:**
- Modify: `frontend/src/lib/views/ProviderDetail.svelte`

Read `frontend/src/lib/views/ProviderDetail.svelte` in full before editing. The breakdown view for a single provider is where reconciliation delta is most valuable.

- [ ] **Step 1: Add reconciliation fetch to ProviderDetail**

In the `<script>` section, add:

```typescript
import type { ReconciliationRow } from '$lib/api'

let reconciliation = $state<ReconciliationRow[]>([])

async function loadReconciliation() {
  if (provider === 'gemini') {
    const res = await api.reconciliation(provider, period)
    reconciliation = res.reconciliation
  }
}
```

Call `loadReconciliation()` when the component mounts and when period changes.

- [ ] **Step 2: Add reconciliation summary row to template**

Find the cost breakdown section and add after it:

```svelte
{#if reconciliation.some(r => r.reconciled)}
  {@const reconciled = reconciliation.filter(r => r.reconciled)}
  {@const totalActual = reconciled.reduce((s, r) => s + (r.actual_cost ?? 0), 0)}
  {@const totalEstimated = reconciled.reduce((s, r) => s + r.estimated_cost, 0)}
  {@const deltaPct = totalEstimated > 0
    ? ((totalActual - totalEstimated) / totalEstimated * 100).toFixed(1)
    : null}
  <div class="mt-4 border border-hairline bg-ink-2 p-4">
    <div class="microlabel mb-2">Billing reconciliation</div>
    <div class="grid grid-cols-3 gap-4 text-sm">
      <div>
        <p class="microlabel-dim">Proxy estimate</p>
        <p class="numeral">${totalEstimated.toFixed(4)}</p>
      </div>
      <div>
        <p class="microlabel-dim">GCP actual</p>
        <p class="numeral">${totalActual.toFixed(4)}</p>
      </div>
      <div>
        <p class="microlabel-dim">Delta</p>
        <p class="numeral" style="color: {deltaPct && parseFloat(deltaPct) > 0 ? 'var(--red)' : 'inherit'}">
          {deltaPct != null ? `${parseFloat(deltaPct) > 0 ? '+' : ''}${deltaPct}%` : '—'}
        </p>
      </div>
    </div>
    <p class="microlabel-dim mt-2">{reconciled.length} days reconciled against GCP billing export</p>
  </div>
{/if}
```

- [ ] **Step 3: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/views/ProviderDetail.svelte
git commit -m "feat: ProviderDetail — estimated vs actual reconciliation row for Gemini"
```

---

## Task 11: Heatmap.svelte — Reconciliation Dot on Cells

**Files:**
- Modify: `frontend/src/lib/components/Heatmap.svelte`

Read `frontend/src/lib/components/Heatmap.svelte` in full before editing. Each day cell is a `<button>` or `<div>`. Add a tiny indicator dot to show reconciled vs estimated state.

- [ ] **Step 1: Add reconciled prop**

In `Heatmap.svelte` `<script>` section, add prop:

```typescript
let { days = [], loading = false, reconciledDates = new Set<string>() }: {
  days: Array<{ date: string; cost_usd: number | null; total_tokens: number; requests: number }>
  loading?: boolean
  reconciledDates?: Set<string>
} = $props()
```

(Merge with existing props if the component already defines `days` and `loading`.)

- [ ] **Step 2: Add dot indicator to each cell**

Inside the cell render, add after the existing cell content:

```svelte
{#if reconciledDates.has(day.date)}
  <span class="absolute bottom-0.5 right-0.5 h-1 w-1 rounded-full bg-current opacity-60"></span>
{/if}
```

The cell needs `position: relative` (add `relative` Tailwind class to the cell element if not already present).

- [ ] **Step 3: Pass reconciledDates from Dashboard.svelte**

In `Dashboard.svelte`, compute and pass the set:

```svelte
{@const reconciledDatesSet = new Set(reconciliation.filter(r => r.reconciled).map(r => r.date))}

<Heatmap {days} reconciledDates={reconciledDatesSet} />
```

- [ ] **Step 4: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 5: Full test suite**

```bash
cd /Users/kavin/Projects/machanirobotics/burnmeter
.venv/bin/pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Build frontend**

```bash
cd frontend && npm run build
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/components/Heatmap.svelte frontend/src/lib/views/Dashboard.svelte
git commit -m "feat: Heatmap — reconciliation dot on reconciled day cells"
```

---

## Self-Review Checklist

After all tasks are complete:

- [ ] `gcp_billing.py` covers both `'Generative Language API'` and `'Vertex AI'` service names
- [ ] `gcp_billing.py` `fetch_billing_costs` runs in executor (not blocking event loop)
- [ ] `gcp_logs.py` skips rows where `input_tokens is None` (defensive parsing)
- [ ] `sync.py` `restart_gcp_loops()` is idempotent (won't create duplicate tasks)
- [ ] `sync.py` `stop()` cancels all three tasks
- [ ] `main.py` backward-compat `/api/billing/gemini` POST/GET/DELETE still work
- [ ] `main.py` `/api/gcp/connect` triggers immediate `sync_gcp_billing()` after storing credentials
- [ ] `Settings.svelte` VALIDATE and CONNECT are separate steps
- [ ] `Settings.svelte` Vertex AI card only shows when `data.configured` contains `vertex_ai`
- [ ] `Heatmap.svelte` reconciledDates prop has default value (no breaking change)
- [ ] All TypeScript checks pass
- [ ] All Python tests pass
- [ ] Frontend builds without error
