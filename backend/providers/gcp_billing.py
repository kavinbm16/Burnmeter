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

# Lazy imports for BigQuery (optional dependency)
try:
    from google.cloud import bigquery
    from google.oauth2 import service_account
except ImportError:
    bigquery = None
    service_account = None

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
    if bigquery is None or service_account is None:
        raise ImportError("google-cloud-bigquery not installed")
    try:
        info = json.loads(credentials_json)
    except json.JSONDecodeError as e:
        raise ProviderError("invalid credentials JSON") from e
    creds = service_account.Credentials.from_service_account_info(info)
    return bigquery.Client(credentials=creds, project=info.get("project_id")), info.get("project_id", "")


def _fetch_billing_sync(credentials_json: str, table: str, start: date, end: date) -> list[CostRecord]:
    if bigquery is None:
        raise ImportError("google-cloud-bigquery not installed")
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
    if bigquery is None:
        raise ImportError("google-cloud-bigquery not installed")
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
