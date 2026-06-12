# 🔥 burnmeter

**Local-first dashboard for LLM token usage and spend, across providers.**

Add your API keys, get a token-wise and dollar-wise breakdown — per provider, per model, per day. Everything runs on your machine; your keys and usage data never leave it.

## Providers (v1)

| Provider | How it works | What you need |
|---|---|---|
| **OpenAI** | Pulls historical usage + billed cost from the official Usage & Costs APIs. Backfills 90 days, then syncs hourly. | An **organization Admin API key** (Settings → Organization → Admin keys). Regular project keys cannot read usage. |
| **Google Gemini** | Gemini has no usage API. Burnmeter runs a local pass-through proxy — point your apps at it and every response's `usageMetadata` is counted and priced. Optional: ground-truth cost via GCP billing export to BigQuery. | Your regular Gemini API key. One base-URL change in your apps. |

Anthropic and OpenRouter adapters are next on the roadmap.

## Quickstart

```bash
git clone https://github.com/kavinbm16/burnmeter && cd burnmeter

# backend
uv venv && uv pip install -e '.[dev]'
.venv/bin/python -m backend.main          # serves http://127.0.0.1:8400

# frontend (dev)
cd frontend && npm install && npm run dev # http://localhost:5173
# — or build once and let the backend serve it:
npm run build                             # then just use :8400
```

Open the dashboard → **Providers** → add a key.

### Routing Gemini traffic through the proxy

```python
from google import genai

client = genai.Client(
    api_key="...",  # optional if you stored the key in burnmeter
    http_options={"base_url": "http://127.0.0.1:8400/proxy/gemini"},
)
```

The proxy forwards requests verbatim to `generativelanguage.googleapis.com` and records only token counts — request/response bodies are never stored.

## Your keys are safe here

- Stored in your **OS keychain** (or a Fernet-encrypted file if no keychain exists) — never in the database, never in logs, never in API responses.
- Sent **only** to the provider's official API host (hardcoded allowlist).
- The server binds **127.0.0.1** — nothing is exposed to your network.
- **No telemetry.** Zero analytics, zero phone-home.

All of this is enforced by tests and documented in [SECURITY.md](SECURITY.md). The codebase is small — audit it.

## Reading the numbers

- **`usage_api`** badge — provider-reported, authoritative (may lag up to ~24 h).
- **`proxy`** badge with **≈ cost** — locally counted tokens, priced from a static table (`backend/pricing.py`). Accurate tokens, estimated dollars.
- **`billing_export`** — ground-truth billed cost from GCP (optional, advanced).

## Development

```bash
.venv/bin/python -m pytest        # backend tests
cd frontend && npm run check      # svelte-check
```

PRs welcome — especially new provider adapters. An adapter is one file implementing `ProviderAdapter` (`backend/providers/base.py`) plus a fixture-based test.

## License

MIT
