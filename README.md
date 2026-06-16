![burnmeter](assests/image.png)

> Local-first dashboard for LLM token usage and spend — across providers, on your machine.

Add your API keys and get a live breakdown of token usage and cost: per provider, per model, per day. Nothing leaves your machine.

---

## What it does

- **Tracks spend** across OpenAI and Gemini (more coming)
- **Shows breakdowns** by provider, model, and day
- **Reconciles estimates vs actuals** — proxy counts vs billed cost
- **Runs entirely local** — no cloud, no telemetry, no account

---

## Providers

| Provider | Data source | What you need |
|---|---|---|
| **OpenAI** | Official Usage & Costs API — backfills 90 days, syncs hourly | Admin API key (Settings → Organization → Admin keys) — regular project keys won't work |
| **Gemini** | Local proxy — burnmeter counts tokens from every response | Your Gemini API key + one base-URL change in your apps |
| **GCP Billing** | BigQuery billing export — ground-truth billed cost for Gemini | GCP project with billing export enabled *(optional, for exact dollar reconciliation)* |

---

## Quickstart

```bash
git clone https://github.com/kavinbm16/burnmeter && cd burnmeter

make install     # uv venv + deps, npm install
make start       # build frontend, serve everything → http://127.0.0.1:8400
```

That's it — one command, one server, one port. Open the dashboard → **Providers** → add a key.

### One startup point

The backend serves the built frontend, so the whole app runs from a single process on `:8400` — there is no separate frontend server to run in production. Two commands cover the two modes:

| Command | What runs | URL |
|---|---|---|
| `make start` | Builds the frontend, then the backend serves it. One process. | http://127.0.0.1:8400 |
| `make dev` | Backend **and** Vite hot-reload together (Ctrl-C stops both). | http://localhost:5173 |

Use `make dev` while hacking on the UI (instant reload); use `make start` to just run it. Prefer raw commands? See the [Makefile](Makefile) — each target is one line.

---

## Routing Gemini through the proxy

Gemini has no usage API, so burnmeter intercepts responses locally to count tokens.

Change one line in your app:

```python
from google import genai

client = genai.Client(
    api_key="...",  # optional if you stored it in burnmeter
    http_options={"base_url": "http://127.0.0.1:8400/proxy/gemini"},
)
```

The proxy forwards requests verbatim to `generativelanguage.googleapis.com`. Only token counts are recorded — request and response bodies are never stored.

---

## Understanding the numbers

| Badge | Meaning |
|---|---|
| `usage_api` | Provider-reported, authoritative. May lag up to ~24 h. |
| `proxy` + **≈ cost** | Locally counted tokens, priced from a static table (`backend/pricing.py`). Tokens are exact; dollars are estimated. |
| `billing_export` | Ground-truth billed cost from GCP BigQuery. Optional. |

---

## Security

- Keys stored in your **OS keychain** (or Fernet-encrypted file as fallback) — never in the database, logs, or API responses
- Keys sent **only** to the provider's official API host (hardcoded allowlist)
- Server binds **127.0.0.1** — not exposed to your network
- **Zero telemetry** — no analytics, no phone-home

Enforced by tests and documented in [SECURITY.md](SECURITY.md). The codebase is small — audit it.

---

## Development

```bash
make test        # backend tests  (.venv/bin/python -m pytest)
make check       # svelte type check
```

PRs welcome — especially new provider adapters. An adapter is one file implementing `ProviderAdapter` (`backend/providers/base.py`) plus a fixture-based test.

---

## License

MIT
