# Anthropic Adapter Design

**Date:** 2026-06-17  
**Status:** Approved  
**Scope:** Add Anthropic/Claude as a tracked provider in burnmeter

---

## Summary

Add `AnthropicAdapter` following the existing `ProviderAdapter` ABC. Hybrid approach: poll Anthropic's org usage API when an admin key is present; fall back to proxy-captured data when only a regular API key is configured. Extend `pricing.py` with Claude model prices (including `cache_write_per_m`, which Claude bills at a 25% premium over standard input).

---

## Architecture

**Files changed:**

| File | Change |
|------|--------|
| `backend/providers/anthropic_adapter.py` | New — full adapter implementation |
| `backend/pricing.py` | Add `cache_write_per_m` to `ModelPrice`; add Claude model entries; update `estimate_cost_usd` |
| `backend/main.py` | Register `AnthropicAdapter` in `adapters` dict |

No changes to `SyncEngine`, `Store`, frontend, or any other file.

---

## `AnthropicAdapter`

### Class declaration

```python
class AnthropicAdapter(ProviderAdapter):
    name = "anthropic"
    display_name = "Anthropic"
    key_hint = (
        "Accepts any Anthropic API key (sk-ant-*). "
        "For 90-day usage history, use an admin key (sk-ant-admin-*) created at "
        "console.anthropic.com → Settings → API Keys → Admin keys. "
        "A regular API key enables proxy-captured data only."
    )
```

### Key validation

`validate_key(key: str) -> KeyInfo`:
- Call `GET https://api.anthropic.com/v1/models` — lightweight, works with any valid `sk-ant-*` key
- 401/403 → raise `InvalidKeyError`
- If `key.startswith("sk-ant-admin")` → `label = "Admin key — polling + proxy enabled"`
- Else → `label = "API key — proxy only (add admin key for history)"`
- Return `KeyInfo(provider="anthropic", label=label, masked_key=mask_key(key))`

### `fetch_usage`

```
fetch_usage(key, start, end) -> list[UsageRecord]
```

- Non-admin key (not `sk-ant-admin*`) → return `[]` immediately
- Admin key → paginate `GET /v1/organizations/usage` with `start_date`, `end_date`, `group_by=model`
- Per result row, emit one `UsageRecord`:
  - `provider = "anthropic"`
  - `model` = model id from response
  - `date` = bucket date (YYYY-MM-DD)
  - `input_tokens` = `input_tokens` from response
  - `output_tokens` = `output_tokens` from response
  - `cache_read_tokens` = `cache_read_input_tokens` from response
  - `cache_write_tokens` = `cache_creation_input_tokens` from response
  - `requests` = `request_count` from response
  - `cost_usd = None` (costs fetched separately)
  - `source = "usage_api"`
  - `cost_estimated = False`

### `fetch_costs`

```
fetch_costs(key, start, end) -> list[CostRecord]
```

- Non-admin key → return `[]`
- Admin key → `GET /v1/organizations/costs` with `start_date`, `end_date`
- If endpoint doesn't exist (404) → return `[]` silently; proxy path will use `estimate_cost_usd`
- Per result row, emit one `CostRecord`:
  - `provider = "anthropic"`
  - `date` = bucket date
  - `cost_usd` = amount from response
  - `source = "usage_api"`

### Endpoint URLs

Verify exact paths against Anthropic API docs during implementation — the org usage endpoint may be `/v1/organization/usage` (singular) or `/v1/organizations/usage` (plural). Use `GET /v1/models` for key validation (stable, documented).

### HTTP client pattern

Mirror `OpenAIAdapter._get_pages()`:
- `httpx.AsyncClient(timeout=30)`
- `MAX_RETRIES = 4`, 429 → exponential backoff from `retry-after` header or `2^(attempt+1)`
- Auth header: `x-api-key: {key}` + `anthropic-version: 2023-06-01`
- 401/403 → `InvalidKeyError`
- Other 4xx/5xx → `ProviderError(f"Anthropic {path} returned {status_code}")`

---

## `pricing.py` changes

### `ModelPrice` — new field

```python
@dataclass(frozen=True)
class ModelPrice:
    input_per_m: float
    output_per_m: float
    cache_read_per_m: float = 0.0
    cache_write_per_m: float = 0.0          # new: cache creation tokens (25% premium for Claude)
    audio_input_per_m: float | None = None
    audio_output_per_m: float | None = None
```

Existing Gemini entries are unaffected (`cache_write_per_m` defaults to `0.0`).

### `estimate_cost_usd` — update

Add `cache_write_tokens: int = 0` parameter, bill at `cache_write_per_m`:

```python
def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,            # new
    audio_input_tokens: int = 0,
    audio_output_tokens: int = 0,
) -> float | None:
    ...
    text_in = max(0, input_tokens - cache_read_tokens - cache_write_tokens - audio_input_tokens)
    return (
        text_in * p.input_per_m
        + cache_read_tokens * p.cache_read_per_m
        + cache_write_tokens * p.cache_write_per_m   # new line
        + audio_input_tokens * audio_in_rate
        + text_out * p.output_per_m
        + audio_output_tokens * audio_out_rate
    ) / 1_000_000
```

### Claude model prices (2026-06)

```python
# Anthropic Claude models — standard tier, verified 2026-06-17
"claude-fable-5":    ModelPrice(10.00, 50.00, cache_read_per_m=1.00,  cache_write_per_m=12.50),
"claude-opus-4-8":   ModelPrice(5.00,  25.00, cache_read_per_m=0.50,  cache_write_per_m=6.25),
"claude-opus-4-7":   ModelPrice(5.00,  25.00, cache_read_per_m=0.50,  cache_write_per_m=6.25),
"claude-opus-4-6":   ModelPrice(5.00,  25.00, cache_read_per_m=0.50,  cache_write_per_m=6.25),
"claude-sonnet-4-6": ModelPrice(3.00,  15.00, cache_read_per_m=0.30,  cache_write_per_m=3.75),
"claude-haiku-4-5":  ModelPrice(1.00,   5.00, cache_read_per_m=0.10,  cache_write_per_m=1.25),
```

Prefix matching in `_lookup()` handles versioned model IDs (e.g. `claude-opus-4-8-20260101`).

---

## Registration

`backend/main.py`:

```python
from backend.providers.anthropic_adapter import AnthropicAdapter

adapters = {
    "openai": OpenAIAdapter(),
    "anthropic": AnthropicAdapter(),
}
```

`SyncEngine` picks up `"anthropic"` automatically. Settings UI renders the provider card from `key_hint` via the existing `/api/providers` endpoint — no frontend changes.

---

## Error handling

| Condition | Behavior |
|-----------|----------|
| Non-admin key | `fetch_usage` + `fetch_costs` return `[]`; adapter still registered |
| Invalid key (401/403) | `InvalidKeyError` → `SyncEngine` sets `invalid_key` state in Settings |
| Rate limited (429) | Exponential backoff, up to `MAX_RETRIES` |
| Costs endpoint missing (404) | Return `[]`; proxy traffic estimated via pricing table |
| Unexpected 5xx | `ProviderError` → `SyncEngine` sets `error` state |

---

## Out of scope

- Proxy middleware changes (proxy-captured Claude traffic is future work)
- Frontend Settings card customization
- Extended cache pricing (treat as standard cache write rate)
- Batch API usage tracking
