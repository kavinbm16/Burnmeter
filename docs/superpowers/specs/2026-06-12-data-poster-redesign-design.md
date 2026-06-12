# Burnmeter "Data Poster" Redesign — Design Spec

Approved 2026-06-12 via visual companion session (.superpowers/brainstorm/2444-1781241282).

## Goal

Lift the dashboard to award-site quality with a unique tokenization-native visual identity. User chose **Data Poster (Swiss brutalist)** direction and **bento grid** layout from mockups.

## Visual language

- Canvas ink `#0c0c0e`; text `#f2f2f0`; muted `#6a6a70`; hairline `#2a2a2e`; single accent red `#ff4d29`. No other hues except data-required ones.
- Bento grid: CSS grid, `gap: 1px`, hairline color as grid background. No border-radius, no shadows.
- Type: Space Grotesk (self-hosted, `@fontsource-variable/space-grotesk` — preserves no-external-calls guarantee). Numerals 700–900 weight, letter-spacing −0.02em to −0.04em. Micro-labels: 10–11px uppercase, 2–3px tracking, red.
- Motion: odometer digit rolls on number change; brief red pulse on live cell update; 150–250ms ease-out; `prefers-reduced-motion` respected.

## Features (all user-selected)

1. **Odometer numerals** — digits roll vertically on load/update. `Odometer.svelte`.
2. **Budget + burn pace** — monthly budget (global USD), gauge cell: spent vs budget bar, dotted pace projection ("ON PACE FOR $X BY JUL 1"). Backend `budgets` table, `GET/PUT /api/budget`.
3. **Calendar heatmap** — ~17 weeks daily spend, black→red 5-step scale, click day → dashboard filters to that day, click again clears. `GET /api/heatmap?days=120`.
4. **Model leaderboard** — all models across providers ranked by spend: tokens, $/1M effective rate, in:out ratio bar. `GET /api/models?period=`.
5. **Tokenizer playground** — page: textarea → `gpt-tokenizer` (o200k_base, client-side) → colored token chips + per-model cost table from `GET /api/pricing` + static OpenAI price entries; Gemini costs marked ≈ (token counts are OpenAI-BPE approximations for non-OpenAI models — labeled as such).
6. **Poster export** — current period rendered as hidden 1200×1600 poster node → PNG via `html-to-image`.
7. **Live ticker** — masthead strip; `WS /ws/live` broadcasts each proxy capture `{model, input_tokens, output_tokens, cost_usd, ts}`; frontend rolls last N events horizontally.

## Architecture

Backend (FastAPI):
- `store.py`: `budgets` table (`scope TEXT PRIMARY KEY DEFAULT 'global', monthly_usd REAL`), `heatmap()`, `models_leaderboard()` queries.
- `main.py`: endpoints above + `/ws/live` WebSocket with connection registry; `gemini_proxy._record` publishes events via injected callback.
- `pricing.py`: expose `PRICES` + add OpenAI display rates for playground (estimates only, marked).

Frontend (Svelte 5):
- `lib/theme` utilities in `app.css` (`cell`, `microlabel`, `numeral`).
- Components: `Odometer.svelte`, `Heatmap.svelte`, `BurnGauge.svelte`, `Leaderboard.svelte`, `LiveTicker.svelte`, `Poster.svelte`, `BarStrip.svelte`.
- Views: `Dashboard.svelte` (replaces Overview), `Playground.svelte`, `ProviderDetail`/`Settings` restyled.
- Delete: `Donut.svelte`, `StackedBars.svelte`, `Overview.svelte`.

## Testing

- pytest: budget CRUD, heatmap aggregates, models leaderboard, WS broadcast on proxy capture.
- `npm run check` + `npm run build` clean.
- Manual visual pass via dev server.

## Out of scope

Command palette (declined), light mode, mobile-first optimization (desktop-first; grid collapses to single column under 900px).
