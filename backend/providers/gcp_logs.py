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

# Lazy imports for BigQuery (optional dependency)
try:
    from google.cloud import bigquery
    from google.oauth2 import service_account
except ImportError:
    bigquery = None
    service_account = None


def _fetch_logs_sync(
    credentials_json: str, logs_table: str, since_timestamp: str
) -> list[UsageRecord]:
    if bigquery is None or service_account is None:
        raise ImportError("google-cloud-bigquery not installed")

    try:
        info = json.loads(credentials_json)
    except json.JSONDecodeError as e:
        raise ProviderError("invalid credentials JSON") from e

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
