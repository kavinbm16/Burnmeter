# Providers Page & Nav Bar Redesign

**Date:** 2026-06-15  
**Scope:** `frontend/src/App.svelte`, `frontend/src/lib/views/Settings.svelte`  
**Status:** Approved

---

## Problem

Current layout has two main issues:

1. **Nav bar** — logo, tabs, period select, export button, and SYNC all compete in one row. No visual hierarchy between global chrome and view-specific controls.
2. **Providers page** — one long vertical stack mixes GCP billing wizard, API key entry, proxy config snippet, and key custody notice. Everything is visible at once; nothing is in focus.

---

## Design Decisions

### 1. Two-Row Header

**Row 1 (branding + global action):**
- Left: `BURNMETER®` logo button (resets to dashboard, clears detail view)
- Right: `SYNC` button — always visible, always in the same place

**Row 2 (navigation + view-specific actions):**
- Left: `DASHBOARD` | `TOKENIZER` | `PROVIDERS` tab buttons, active tab underlined in red
- Right (only on Dashboard tab): period select dropdown + `EXPORT POSTER` button. Hidden on other tabs.

**Row 3 (unchanged):** Live ticker strip.

The ticker's `hairline-b` border beneath row 3 stays. No change to the sticky backdrop-blur behavior.

---

### 2. Providers Page — Two Inner Tabs

`Settings.svelte` renders two inner tabs at the top of the page:

- **AI PROVIDERS** (default)
- **BILLING & GCP**

#### AI Providers Tab

Provider grid: 3 columns, `gap:1px` with `background: var(--hairline)` (bento pattern).

**Connected card:**
- Provider name (microlabel), mode badge (microlabel-dim below name)
- Masked key + red dot indicator
- Last synced timestamp (microlabel-dim)
- Clicking a connected card opens the detail panel in manage mode (shows REMOVE + SYNC NOW)

**Unconnected card:**
- Provider name, mode badge
- `CONNECT →` link in red — clicking opens the detail panel in connect mode
- Dashed border (`border: 1px dashed var(--hairline)`) to signal "empty"

**Add card:**
- A dashed full-width row below the grid reading `+ ADD ANOTHER PROVIDER`. Non-interactive — visual hint only. No backend mechanism exists for arbitrary providers; this is a placeholder for future expansion. Renders statically with no click handler.

**Detail panel (slide-in below grid):**
- Appears when any card is clicked (connect or manage)
- Border: `1px solid var(--red)`, background `var(--ink-2)`
- Header: provider name in microlabel red + `✕` close button flush right
- One-line description of the connection method
- **Connect mode:** key input (type="password") + "Get key at [url]" hint line + `ADD KEY` button
- **Manage mode:** masked key display + `SYNC NOW` + `REMOVE` buttons + last synced time
- **Gemini only — extra section after key is added:** proxy endpoint block with copy button (HTTP + WebSocket URLs, code snippet). Always behind a `▸ Proxy endpoints` toggle — user expands manually. No session persistence required.
- Errors appear inline in the panel in red.

#### Billing & GCP Tab

Full-width single-column layout (no inner grid).

**Header:** `GOOGLE CLOUD PLATFORM` microlabel + one-line description ("One service account covers Gemini billing reconciliation and Vertex AI cost tracking.")

**When not connected — stepped list:**

Three steps rendered as a vertical list with `gap:1px` bento borders:

| Step | Label | Right side |
|------|-------|------------|
| 1 | CREATE SERVICE ACCOUNT | `COPY COMMAND` button |
| 2 | PASTE SERVICE ACCOUNT JSON | textarea always visible (same as current) |
| 3 | VALIDATE & SELECT TABLE | auto-opens after step 2 succeeds |

Step 1 is always expanded (just the copy button + brief instruction). Step 2 expands the textarea inline. After paste + `VALIDATE & FIND TABLES` succeeds, step 3 reveals the table dropdown + optional Vertex AI logs input + `CONNECT` button.

**When connected — status card:**
- Project ID with red dot
- Billing export sync status + last synced timestamp
- Vertex AI logs sync status (if logs table configured)
- `SYNC NOW` + `REMOVE` buttons
- Billing table name as code

**Footer (both tabs):** Small `microlabel-dim` line: "Keys stored in OS keychain — never in database or logs. [Audit →]". Replaces the current top-of-page key custody notice cell.

---

## What Stays Unchanged

- CSS design system (`app.css`) — no changes to tokens, utilities, or typography
- `bento` / `cell` pattern used throughout
- Live ticker component and behavior
- All backend API calls — this is purely a frontend restructuring
- `ProviderDetail.svelte` — not in scope
- `Dashboard.svelte` — not in scope (only the nav actions wiring changes in `App.svelte`)

---

## File Scope

| File | Changes |
|------|---------|
| `frontend/src/App.svelte` | Restructure header into two rows; move period select + export to row 2 conditional on `tab === 'dashboard'`; rename `providers` tab label if needed |
| `frontend/src/lib/views/Settings.svelte` | Full rewrite of layout: add inner tab state, AI Providers grid + detail panel, GCP tab with stepped setup |

---

## Open Questions (resolved)

- Gemini proxy config → lives in Gemini provider detail panel (manage mode), not in GCP tab
- Key custody notice → demoted to footer line, not a top-level card
- Vertex AI auto-card → stays in AI Providers tab as a read-only card (no key needed, sourced from GCP billing)
