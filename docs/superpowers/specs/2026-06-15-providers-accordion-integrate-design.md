# AI Providers Accordion + Guided Integration — Design Spec

**Date:** 2026-06-15
**Status:** Approved
**Scope:** Two files — `frontend/src/App.svelte` (footer), `frontend/src/lib/views/Settings.svelte` (AI Providers tab). No backend changes.

## Problem

The just-shipped Providers redesign has two issues observed on a live screenshot:

1. **Footer floats mid-page.** The global footer (`LOCAL-FIRST — KEYS NEVER LEAVE THIS MACHINE — SOURCE`) sits directly under short content instead of at the viewport bottom, leaving a large dead gap below it. Not device-agnostic.
2. **Provider integration is not user-friendly.** The 3-column card grid + detail-panel-below pattern wastes horizontal space and, more importantly, gives no clear guidance on *how to actually integrate* a provider — especially Gemini, which requires routing app traffic through a local proxy.

## Goals

- Footer pins to viewport bottom on short pages, flows below content on tall pages. One implementation, all screen sizes.
- AI Providers tab reads top-to-bottom as a stack of provider rows. Clicking a row expands a guided integration flow.
- Gemini proxy integration is dead-simple: numbered steps, copy-paste code in the user's language (Python / Node / cURL), proxy URL front and center.

## Non-Goals

- No backend changes. Provider set, proxy endpoints, and API contracts are unchanged.
- No change to the Billing & GCP tab (Task 5 of prior redesign stays as-is).
- No new providers.

---

## Part 1 — Device-Agnostic Footer (`App.svelte`)

**Current:** Root is `<div class="mx-auto min-h-screen max-w-7xl px-6">` with `<header>`, `<main class="py-6">`, `<footer>` as static flow children. Footer position follows content height → floats mid-page when content is short.

**Change:** Make the root a flex column that fills viewport height; let `<main>` absorb slack.

- Root: `class="mx-auto flex min-h-screen max-w-7xl flex-col px-6"`
- Main: add `flex-1` → `class="flex-1 py-6"`
- Footer: unchanged markup; now naturally pinned to bottom when content is short.

**Footer copy:** Global footer line stays as-is. The Settings keychain microline ("Keys stored in OS keychain… audit the guarantees", links to SECURITY.md) stays — distinct message (custody guarantee), lives inside the providers content flow, not redundant with the global brand footer.

---

## Part 2 — AI Providers Tab: Accordion Rows (`Settings.svelte`)

Replace the 3-column bento grid + detail-panel-below with a vertical stack of full-width provider rows. Clicking a row toggles an inline expanded body. Reuses existing `selectProvider(name)` toggle logic (`selectedProvider` is the open row).

### Collapsed row

Full-width, clickable. Left: `display_name`. Below name: mode label — `usage api` (usage_api mode) or `local proxy` (proxy mode). Right edge: status + chevron (`▾`).

Status states:
- Configured, healthy: `● synced {last_synced_at}Z` (red dot + muted time).
- Configured, error (`sync_status` is `invalid_key` or `error`): red `▲ key error`.
- Not configured: red `connect →`.

### Vertex AI row (read-only)

Only rendered when `data.configured` contains `vertex_ai`. Non-clickable row: name `Google Vertex AI`, label `via GCP billing`, red `●` dot. No expand. (Vertex is configured through the Billing & GCP tab, not here.)

### Add-provider hint

Non-interactive dashed row at the bottom: `+ ADD ANOTHER PROVIDER` in muted text. No click handler (matches prior spec decision).

---

## Part 3 — Expanded Row Body (per provider type)

The expanded body branches on the provider's `mode`.

### usage_api providers (OpenAI)

- **Not configured:** key hint (`meta.key_hint`) + `API KEY` label + password input (placeholder `sk-admin-…`) + `ADD KEY` button. Enter key submits. Inline error on failure (`▲ {error}`).
- **Configured (manage):** red `●` + masked key, `Last sync {time}Z`, error line if failing, then `SYNC NOW` (calls `api.sync()`) + `REMOVE` (calls `remove(name)`).

### proxy providers (Gemini) — guided 1-2-3 (Version B)

Always shows the three-step guide (whether or not a key is stored). When configured, a manage strip (masked key + SYNC NOW + REMOVE) appears above the steps.

**① ADD KEY (OPTIONAL)**
- Red step badge `1` + label.
- Password input (placeholder `AIza…`) + `ADD KEY` button. Enter submits. Inline error.
- Helper line: `or skip — pass your own key per request` (the passthrough path).
- If already configured: show masked key + `Last sync` here instead of the input, with SYNC NOW / REMOVE.

**② POINT YOUR APP AT THE PROXY**
- Red step badge `2` + label.
- Language tabs: `PYTHON` · `NODE` · `cURL`. New state `proxyLang = $state<'python' | 'node' | 'curl'>('python')`. Active tab gets red underline/border.
- Code block for the selected language with a `COPY` button (reuses copy-state pattern; `setTimeout` reset to `COPY`).
- All snippets embed the dynamic `proxyUrl` (`${location.protocol}//${location.hostname}:8400/proxy/gemini`, already computed in script).
- WebSocket note below the snippet: `Live / streaming? Use {liveProxyUrl}` (already computed).

**③ RUN — USAGE COUNTS AUTOMATICALLY**
- Red step badge `3` + label.
- Reconciliation note (reuses prior logic):
  - GCP configured: `traffic via proxy is estimated — GCP billing reconciliation active ✓`
  - GCP not configured: `costs are estimated — connect GCP billing for actual billed amounts`

### Code snippets (embed `proxyUrl`)

**Python**
```python
from google import genai

client = genai.Client(
    api_key="YOUR_KEY",
    http_options={"base_url": "<proxyUrl>"},
)
```

**Node**
```javascript
import { GoogleGenAI } from "@google/genai";

const ai = new GoogleGenAI({
  apiKey: "YOUR_KEY",
  httpOptions: { baseUrl: "<proxyUrl>" },
});
```

**cURL**
```bash
curl <proxyUrl>/v1beta/models/gemini-2.0-flash:generateContent \
  -H "x-goog-api-key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"contents":[{"parts":[{"text":"Hello"}]}]}'
```

`<proxyUrl>` is interpolated live at render. `YOUR_KEY` stays literal (the user substitutes, or omits if they stored a key / use passthrough).

---

## State changes (`Settings.svelte` script)

- **Add:** `proxyLang = $state<'python' | 'node' | 'curl'>('python')`.
- **Add:** copy state for the snippet (e.g. `snippetCopied`), or reuse `proxyCopied`.
- **Remove:** `geminiProxyOpen` (the guide is always visible now; no toggle).
- Keep: `selectProvider`, `add`, `remove`, `keyInput`, `busy`, `errors`, all GCP state/functions, `proxyUrl`, `liveProxyUrl`, `copyProxy`/copy pattern.

## Verification

- `cd frontend && npm run check` → 0 errors.
- `npm run build` → succeeds (pre-existing gpt-tokenizer chunk-size warning is acceptable).
- Manual: short Providers page → footer at viewport bottom. Click each provider row → expands; click again → collapses. Gemini row → 1-2-3 visible, language tabs switch snippet, COPY copies live URL. OpenAI row → key box / manage. Vertex row (if present) → read-only, no expand.

## Self-Review

| Requirement | Covered |
|---|---|
| Footer pinned bottom, device-agnostic | Part 1 |
| No mid-page float on short content | Part 1 (flex-col + flex-1) |
| Accordion rows replace grid | Part 2 |
| Collapsed row: name/mode/status states | Part 2 |
| Vertex read-only row | Part 2 |
| Non-interactive add hint | Part 2 |
| OpenAI connect + manage | Part 3 |
| Gemini guided 1-2-3 | Part 3 |
| Optional key + passthrough note | Part 3 ① |
| Language tabs Python/Node/cURL + copy | Part 3 ② |
| Live proxy URL in snippets + WebSocket note | Part 3 ② |
| Reconciliation note | Part 3 ③ |
| No backend changes | All — confirmed |

No gaps found.
