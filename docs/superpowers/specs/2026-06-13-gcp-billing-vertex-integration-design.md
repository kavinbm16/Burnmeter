# GCP Billing Integration + Vertex AI Support — Design Spec

**Date:** 2026-06-13  
**Status:** Approved  
**Scope:** Backend ingestion pipeline, Vertex AI as first-class provider, BigQuery reconciliation, Cloud Logging near-real-time ingestion, provider onboarding UX redesign

---

## Problem

Current Gemini cost tracking is proxy-only: estimated, not billed amounts, and only captures traffic routed through the local proxy. Vertex AI is completely unsupported. The BigQuery billing setup is a buried advanced option with a raw JSON textarea — too manual, too fragile, not integrated into the main provider flow.

Goal: make GCP billing export the primary accuracy layer for all Google providers, add Vertex AI as a first-class provider, and make onboarding feel like a product not a config file.

---

## Architecture Overview

Three ingestion layers, each with a distinct role:

| Layer | Provider(s) | Latency | What it gives |
|---|---|---|---|
| Local proxy | Gemini API | Real-time | Per-key, per-request tokens + estimated cost |
| Cloud Logging → BQ | Vertex AI | ~5 min | Per-request model + actual token counts |
| Billing export → BQ | Gemini API + Vertex AI | T+hours | Actual billed cost per SKU |

Proxy remains the live feed for Gemini API. For Vertex AI, Cloud Logging is the real-time path (minutes lag). Billing export is the ground-truth reconciliation layer for both — it arrives hours after usage but is the authoritative number Google charges.

Single GCP connection (one service account) covers all three layers. Setting it up once activates billing reconciliation for Gemini API AND Vertex AI cost + usage tracking.

---

## Section 1 — GCP Connection Model & Auth

### Auth Strategy

Primary path: **service account JSON**. Most reliable across all environments (local dev, CI, servers). No gcloud required.

Secondary path: **ADC** (`google.auth.default()`). Detected opportunistically on connect attempt. Offered as a shortcut if available with correct billing scope. Not the default — billing scope is not included in standard `gcloud auth application-default login` and the failure is confusing.

### Connection Scope

One GCP connection covers:
- `service.description = 'Generative Language API'` → `provider='gemini'` in cost_records
- `service.description = 'Vertex AI'` → `provider='vertex_ai'` in cost_records
- Vertex AI Cloud Logging table (if log sink configured)

The billing export table lives at billing-account level, not project level. It aggregates across all projects in the billing account. This means one table covers all Vertex AI and Gemini API spend regardless of which project the code ran in.

### Stored Credentials

All stored in KeyStore (OS keychain / encrypted file), never in SQLite:

| Key | Value |
|---|---|
| `gcp_credentials_json` | Service account JSON string |
| `gcp_billing_table` | Fully-qualified billing export table |
| `gcp_logs_table` | Fully-qualified Vertex AI log sink table (optional) |
| `gcp_project_id` | Extracted from credentials JSON for display |

### Permissions Required (service account)

Minimum roles:
- `roles/bigquery.dataViewer` on the billing export dataset
- `roles/bigquery.dataViewer` on the log sink dataset (if using Cloud Logging path)
- `roles/bigquery.jobUser` on the project to run queries

One-liner to generate (shown in UI with copy button):
```bash
gcloud iam service-accounts create burnmeter-reader \
  --display-name="Burnmeter read-only" --project=PROJECT_ID && \
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:burnmeter-reader@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataViewer" && \
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:burnmeter-reader@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser" && \
gcloud iam service-accounts keys create burnmeter-key.json \
  --iam-account="burnmeter-reader@PROJECT_ID.iam.gserviceaccount.com"
```

---

## Section 2 — Ingestion Pipeline

### New Backend Files

**`backend/providers/gcp_billing.py`** — replaces `gemini_billing.py`

Queries billing export for both services:
```sql
SELECT DATE(usage_start_time) AS day,
       service.description AS service,
       sku.description AS sku,
       SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS cost_usd
FROM `{table}`
WHERE service.description IN ('Generative Language API', 'Vertex AI')
  AND DATE(usage_start_time) BETWEEN @start AND @end
GROUP BY day, service, sku
ORDER BY day
```

Maps service to provider:
- `'Generative Language API'` → `provider='gemini'`
- `'Vertex AI'` → `provider='vertex_ai'`

BigQuery client is synchronous (`google-cloud-bigquery`). All calls wrapped in `asyncio.get_event_loop().run_in_executor(None, fn)` to avoid blocking the event loop.

Table auto-discovery: on credential validation, list BigQuery datasets in the project and filter tables matching `gcp_billing_export_v1_*`. Returns list to frontend as a dropdown.

**`backend/providers/gcp_logs.py`** — new, Vertex AI real-time path

Queries the Cloud Logging → BigQuery log sink table. Parses `protoPayload.response.usageMetadata` for token counts. Returns `UsageRecord` list with `provider='vertex_ai', source='cloud_logging', cost_estimated=0`.

Log filter for the sink (shown in UI, user creates this in GCP console):
```
resource.type="aiplatform.googleapis.com/Endpoint"
protoPayload.serviceName="aiplatform.googleapis.com"
protoPayload.methodName=~".*GenerateContent.*"
```

Query pattern (log sink table schema):
```sql
SELECT TIMESTAMP_TRUNC(timestamp, DAY) AS day,
       JSON_VALUE(protopayload_auditlog.requestMetadata.callerSuppliedUserAgent) AS caller,
       JSON_VALUE(protopayload_auditlog.resourceName) AS model,
       CAST(JSON_VALUE(protopayload_auditlog.response.usageMetadata.promptTokenCount) AS INT64) AS input_tokens,
CAST(JSON_VALUE(protopayload_auditlog.response.usageMetadata.candidatesTokenCount) AS INT64) AS output_tokens
FROM `{logs_table}`
WHERE timestamp >= @start
  AND timestamp < @end
```

This is best-effort — log schema can vary by model. Parse defensively, skip rows that don't match expected shape.

### Data Flows into Store

| Source | Target table | `source` value | `cost_estimated` |
|---|---|---|---|
| Gemini proxy | `usage_records` | `'proxy'` | `1` |
| Billing export | `cost_records` | `'billing_export'` | N/A |
| Cloud Logging | `usage_records` | `'cloud_logging'` | `0` |
| OpenAI usage API | `usage_records` | `'usage_api'` | `0` |

Vertex AI has NO usage_records from proxy (no proxy path). It gets usage_records from Cloud Logging (if configured) and cost_records from billing export.

---

## Section 3 — Sync Scheduling

Three independent sync loops in `SyncEngine`:

### Loop 1 — Provider usage API sync (existing, hourly)
OpenAI and any future usage-API providers. Unchanged.

### Loop 2 — GCP billing export sync (new, every 30 min)
- Watermark stored as `provider='__gcp_billing__'` in `sync_state`
- First run (no watermark): backfill 90 days
- Subsequent runs: re-fetch last 5 days from watermark (Vertex AI SKUs can appear up to T+3)
- After successful sync: upsert Vertex AI into `providers` table if rows found
- Advances watermark to yesterday

### Loop 3 — Vertex AI Cloud Logging sync (new, every 5 min)
- Only runs if `gcp_logs_table` is configured
- Watermark: last processed log timestamp (stored as `provider='__gcp_logs__'` in `sync_state`)
- Fetches logs newer than watermark
- Short window re-fetch: last 30 min from watermark (log delivery can be slightly delayed)
- Parses into `UsageRecord`, writes to `usage_records`

All three loops are independent tasks started in `SyncEngine.start()`. Loop 2 and 3 only start if GCP credentials are configured at startup. `POST /api/gcp/connect` calls `sync_engine.restart_gcp_loops()` to start them dynamically without restarting the server.

---

## Section 4 — Vertex AI Data Model

### In `providers` table

Auto-inserted when billing sync first finds Vertex AI rows:
```
name: 'vertex_ai'
display_name: 'Google Vertex AI'
masked_key: 'via GCP billing'
label: 'billing export'
```

User can remove it (deletes provider row + all associated records, same as any other provider).

### In `cost_records` table

No schema change needed:
```
provider: 'vertex_ai'
date: '2026-06-13'
source: 'billing_export'
line_item: 'Gemini 2.0 Flash Input Tokens'  -- SKU description
cost_usd: 0.0042
```

### In `usage_records` table (Cloud Logging path)

No schema change needed:
```
provider: 'vertex_ai'
model: 'gemini-2.0-flash-001'  -- parsed from resource name
date: '2026-06-13'
source: 'cloud_logging'
key_id: ''  -- no per-key dimension on Vertex
input_tokens: 14200
output_tokens: 830
cost_usd: NULL  -- no cost at this layer, comes from billing export
cost_estimated: 0
```

### What the dashboard shows for Vertex AI

- Cost: from `cost_records` (billing export) — actual billed
- Token usage: from `usage_records` (cloud logging) — if log sink configured
- If no log sink: token columns show 0, cost still shows from billing export
- Badge: `billing export` or `billing + live logs` depending on what's configured

---

## Section 5 — Reconciliation

### Logic

For any `(provider, date)` pair, truth priority:
1. `cost_records` billing export row → canonical cost, overrides estimated
2. `usage_records` cloud_logging → canonical token counts for Vertex
3. `usage_records` proxy → estimated cost, fills gap until billing lands

No new tables. The existing `store.breakdown()` already returns `billed_costs` separately from `by_model`. Extend it to compute delta.

### New `store.reconciliation_summary()` method

For a date range, returns per-day reconciliation state:
```python
{
  "date": "2026-06-13",
  "provider": "gemini",
  "estimated_cost": 1.24,      # sum from usage_records (proxy)
  "actual_cost": 1.31,         # from cost_records (billing export)
  "delta_pct": 5.6,            # (actual - estimated) / estimated * 100
  "reconciled": True
}
```

### UI signals

- Heatmap cells: small dot indicator — filled = reconciled, hollow = estimated
- Provider detail page: "estimated vs actual" row in cost breakdown when both exist
- Dashboard total: "(reconciled)" or "(estimated)" sub-label under spend total
- Per-provider card: last reconciliation timestamp

---

## Section 6 — API Changes

### New endpoints

```
GET  /api/gcp/auth-check          — detect ADC availability + scope; returns {adc: bool, project_id: str|null}
GET  /api/gcp/status              — credentials configured?, last billing sync, last log sync, providers found
POST /api/gcp/connect             — validate service account JSON, discover tables, store credentials, start loops
GET  /api/gcp/tables              — list billing export tables in project (dropdown population)
GET  /api/gcp/logs-tables         — list potential log sink tables in project
DELETE /api/gcp/disconnect        — remove all GCP credentials, stops billing + log sync loops
POST /api/gcp/sync                — manual trigger for billing + log sync
```

### Deprecated (backward-compatible, not removed immediately)

```
GET  /api/billing/gemini          — proxies to /api/gcp/status, filtered to billing fields
POST /api/billing/gemini          — proxies to /api/gcp/connect (billing table only)
DELETE /api/billing/gemini        — proxies to /api/gcp/disconnect
```

Keep old endpoints alive so existing setups don't break.

### Modified endpoints

```
GET /api/providers/{name}/breakdown — add reconciliation delta to response when both sources present
GET /api/overview                   — totals now note cost_reconciled: true/false
```

---

## Section 7 — Provider Onboarding UX (Settings.svelte)

### Card Structure

**OpenAI card** — unchanged.

**GCP card** (new, above Gemini proxy card)

Setup state (not configured):
```
┌─ GCP Billing Connection ─────────────────────────────────┐
│  microlabel: GOOGLE CLOUD PLATFORM                        │
│                                                           │
│  Connects Gemini API billing reconciliation + Vertex AI.  │
│  One service account covers both.                         │
│                                                           │
│  [copy icon] One-liner to create service account →        │
│                                                           │
│  [textarea: paste service-account JSON here]              │
│  ← on paste: extract + show project_id inline             │
│  Project: my-project-id ✓                                 │
│                                                           │
│  [VALIDATE] ← hits /api/gcp/tables, populates dropdown    │
│                                                           │
│  Billing export table: [dropdown ▾]                       │
│                                                           │
│  ▸ Advanced: Vertex AI live logs (optional)               │
│    [explain log sink setup with link to GCP console]      │
│    Log sink table: [dropdown ▾]                           │
│                                                           │
│  [CONNECT]                                                │
└───────────────────────────────────────────────────────────┘
```

Connected state:
```
┌─ GCP Billing Connection ─────────────────────────────────┐
│  ● my-project-id                          [REMOVE]        │
│  Billing export  ✓  last sync 14 min ago                  │
│  Vertex AI logs  ✓  last sync 2 min ago                   │
│  Found: Gemini API costs  ✓  Vertex AI costs  ✓           │
└───────────────────────────────────────────────────────────┘
```

**Gemini proxy card** — existing, kept. Shows "GCP reconciliation: connected ✓" if GCP card is done. Otherwise shows "costs are estimated — connect GCP for actuals".

**Vertex AI card** — auto-appears below Gemini card when GCP connect finds Vertex AI costs. No key input. Shows:
- Total cost this period (from billing export)
- Token usage (from cloud logging, if configured) or "token counts require Vertex AI log sink"
- Last sync time

### Key UX principles

- JSON paste → immediate inline extraction of `project_id`. No submit needed for this step.
- Table selection is a dropdown, never free-text.
- VALIDATE and CONNECT are separate steps — VALIDATE confirms permissions + lists tables, CONNECT stores and starts sync.
- Error messages are specific: "Missing roles/bigquery.dataViewer on dataset billing_data" not "permission denied".
- Vertex AI card never asks for a key — it only lights up when data exists.

---

## Section 8 — Dependencies

New Python packages (add to `pyproject.toml` `[billing]` extra):
- `google-cloud-bigquery` (already required for billing extra)
- `google-auth` (already a transitive dep, make explicit)

No new frontend dependencies.

---

## Out of Scope

- Pub/Sub push-based billing (too much GCP setup complexity)
- Multi-billing-account support (one connection per burnmeter instance)
- Vertex AI Model Monitoring (separate product, different setup)
- Anthropic / Azure cost reconciliation (different providers, future work)
- Token count derivation from Vertex billing SKU character counts (not reliable enough)
