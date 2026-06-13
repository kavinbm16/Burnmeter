"""Tests for gcp_logs — mock BigQuery."""

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock the google cloud libraries before importing gcp_logs
sys.modules['google'] = MagicMock()
sys.modules['google.cloud'] = MagicMock()
sys.modules['google.cloud.bigquery'] = MagicMock()
sys.modules['google.oauth2'] = MagicMock()
sys.modules['google.oauth2.service_account'] = MagicMock()

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

    with patch("backend.providers.gcp_logs.service_account.Credentials.from_service_account_info", return_value=MagicMock()), \
         patch("backend.providers.gcp_logs.bigquery.Client", return_value=mock_client), \
         patch("backend.providers.gcp_logs.bigquery.QueryJobConfig", return_value=MagicMock()), \
         patch("backend.providers.gcp_logs.bigquery.ScalarQueryParameter", return_value=MagicMock()):
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

    with patch("backend.providers.gcp_logs.service_account.Credentials.from_service_account_info", return_value=MagicMock()), \
         patch("backend.providers.gcp_logs.bigquery.Client", return_value=mock_client), \
         patch("backend.providers.gcp_logs.bigquery.QueryJobConfig", return_value=MagicMock()), \
         patch("backend.providers.gcp_logs.bigquery.ScalarQueryParameter", return_value=MagicMock()):
        from backend.providers.gcp_logs import fetch_log_usage
        result = await fetch_log_usage(VALID_SA_JSON, "p.d.t", "2026-06-13T00:00:00Z")

    assert result == []
