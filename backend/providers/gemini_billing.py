"""Optional Gemini ground-truth cost via GCP Cloud Billing BigQuery export.

Advanced path: the user enables the standard billing export to BigQuery in
their GCP project, creates a read-only service account, and uploads its JSON
credentials. We query daily cost rows for the Generative Language API service
and store them as CostRecords (source="billing_export").

Requires the optional `billing` extra: pip install 'burnmeter[billing]'.
Credentials JSON is stored through KeyStore (encrypted/keychain), never in the DB.
"""

from __future__ import annotations

import json
from datetime import date

from backend.providers.base import CostRecord, ProviderError

# Service display name used by the Gemini API in billing exports.
GEMINI_SERVICE = "Generative Language API"


async def fetch_billing_costs(
    credentials_json: str, table: str, start: date, end: date
) -> list[CostRecord]:
    """Query the billing export table for daily Gemini API costs.

    `table` is the fully-qualified billing export table, e.g.
    `myproject.billing_export.gcp_billing_export_v1_XXXXXX`.
    """
    try:
        from google.cloud import bigquery
        from google.oauth2 import service_account
    except ImportError as e:
        raise ProviderError(
            "BigQuery support not installed. Run: pip install 'burnmeter[billing]'"
        ) from e

    info = json.loads(credentials_json)
    creds = service_account.Credentials.from_service_account_info(info)
    client = bigquery.Client(credentials=creds, project=info.get("project_id"))

    # group by SKU so audio-input / text-output / live-session costs split out
    query = f"""
        SELECT DATE(usage_start_time) AS day,
               sku.description AS sku,
               SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS cost_usd
        FROM `{table}`
        WHERE service.description = @service
          AND DATE(usage_start_time) BETWEEN @start AND @end
        GROUP BY day, sku ORDER BY day
    """
    job = client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("service", "STRING", GEMINI_SERVICE),
                bigquery.ScalarQueryParameter("start", "DATE", start.isoformat()),
                bigquery.ScalarQueryParameter("end", "DATE", end.isoformat()),
            ]
        ),
    )
    return [
        CostRecord(
            provider="gemini",
            date=row.day.isoformat(),
            cost_usd=float(row.cost_usd),
            line_item=row.sku or GEMINI_SERVICE,
            source="billing_export",
        )
        for row in job.result()
    ]
