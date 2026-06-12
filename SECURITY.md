# Security Policy

Burnmeter handles your LLM provider API keys. This document explains exactly how, what we protect against, and how to report problems.

## How your keys are handled

| Guarantee | Enforcement |
|---|---|
| Keys never leave your machine, except to the provider's official API | Hardcoded upstream hosts: `api.openai.com`, `generativelanguage.googleapis.com`. No other outbound calls exist. |
| Keys are never stored in plaintext on disk | Stored in the OS keychain via [`keyring`](https://pypi.org/project/keyring/) (macOS Keychain, Windows Credential Manager, Linux Secret Service). If no keychain backend exists, fallback is a Fernet-encrypted file (`~/.burnmeter/keys.enc`). Covered by tests (`tests/test_keys.py::test_no_plaintext_on_disk`). |
| Keys never appear in the database | The SQLite schema has no key column; only a masked hint (`sk-…ab12`) is stored. |
| Keys never appear in logs | A logging filter redacts `sk-…` / `AIza…` shaped strings from every log record (`backend/keys.py::RedactionFilter`). |
| Keys are never returned by the API | All endpoints return only the masked hint. |
| The server is not reachable from your network | Binds `127.0.0.1` only. CORS restricted to the local frontend origin. |
| Proxy traffic is not stored | The Gemini proxy records only `usageMetadata` token counts. Request/response bodies are never persisted (covered by `tests/test_gemini_proxy.py::test_request_bodies_never_persisted`). |
| No telemetry | There is no analytics, crash reporting, or phone-home code. Grep the source. |

## Threat model

**In scope (we defend against):**
- Key exfiltration via logs, database files, API responses, or error traces.
- Keys being sent to any host other than the provider's official API.
- Plaintext keys at rest.

**Out of scope (we cannot defend against):**
- Malware or other users with access to your machine/OS account. The OS keychain is the boundary.
- Compromise of the provider's own API.
- Keys you paste somewhere else.

## Reporting a vulnerability

Open a GitHub security advisory (preferred) or email kavinbm16@gmail.com. Please do not open public issues for unpatched vulnerabilities. You can expect an initial response within 72 hours.

## Verifying the guarantees yourself

```bash
# 1. No plaintext keys at rest
pytest tests/test_keys.py -v

# 2. Proxy never persists bodies
pytest tests/test_gemini_proxy.py -v

# 3. No secrets in the repo
gitleaks detect

# 4. Outbound hosts (should only show the two provider hosts)
grep -rn "https://" backend/ --include="*.py" | grep -v test
```
