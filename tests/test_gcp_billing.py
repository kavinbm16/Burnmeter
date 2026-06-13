"""Tests for gcp_billing — mock BigQuery, never hit real GCP."""

from __future__ import annotations

import json
import sys
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from backend.providers.base import CostRecord, ProviderError

# Mock the google cloud libraries before importing gcp_billing
sys.modules['google'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.bigquery'] = MagicMock()
sys.modules['google.oauth2'] = MagicMock()
sys.modules['google.oauth2.service_account'] = MagicMock()


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

    with patch("backend.providers.gcp_billing.service_account.Credentials.from_service_account_info", return_value=MagicMock()), \
         patch("backend.providers.gcp_billing.bigquery.Client", return_value=mock_client), \
         patch("backend.providers.gcp_billing.bigquery.QueryJobConfig", return_value=MagicMock()), \
         patch("backend.providers.gcp_billing.bigquery.ArrayQueryParameter", return_value=MagicMock()), \
         patch("backend.providers.gcp_billing.bigquery.ScalarQueryParameter", return_value=MagicMock()):
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

    with patch("backend.providers.gcp_billing.service_account.Credentials.from_service_account_info", return_value=MagicMock()), \
         patch("backend.providers.gcp_billing.bigquery.Client", return_value=mock_client), \
         patch("backend.providers.gcp_billing.bigquery.QueryJobConfig", return_value=MagicMock()), \
         patch("backend.providers.gcp_billing.bigquery.ArrayQueryParameter", return_value=MagicMock()), \
         patch("backend.providers.gcp_billing.bigquery.ScalarQueryParameter", return_value=MagicMock()):
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

    with patch("backend.providers.gcp_billing.service_account.Credentials.from_service_account_info", return_value=MagicMock()), \
         patch("backend.providers.gcp_billing.bigquery.Client", return_value=mock_client):
        from backend.providers.gcp_billing import discover_tables
        tables = await discover_tables(VALID_SA_JSON)

    assert tables == ["test-project.billing_data.gcp_billing_export_v1_ABCDEF"]
