# UI Next-Level: Insight Strip, Live Burn Ambient, Share Card + Badge

Date: 2026-06-18
Status: Approved — ready for implementation plan

## Goal

Move burnmeter's dashboard from *reporting* numbers to *acting* on them, and add
demo-wow + organic distribution. Three features over one shared live-data
foundation:

1. **Insight strip** — one-line "top driver" explanation of spend change.
2. **Live burn ambient** — real-time $/min counter plus ambient motion on live
   proxy traffic.
3. **Share card + badge** — downloadable weekly card and a committable SVG badge.

Local-first constraint holds: no public server, keys never leave the machine.

## Shared foundation: `liveStore`

New module `frontend/src/lib/liveStore.ts`. Owns the **single** `/ws/live`
WebSocket connection for the whole app (today LiveTicker owns its own; that moves
here).

Exposes:
- `events` — Svelte store, last 12 `LiveEvent` (existing shape: provider, model,
  input/output/audio tokens, source, key_id, cost_usd, ts).
- `burnRatePerMin` — derived store: sum of `cost_usd` over events in a rolling
  60-second window, extrapolated to $/min. `0` when window empty.
- `lastEventAt` — epoch ms of most recent event, for idle detection.
- `connected` — boolean.

Connection behavior identical to current LiveTicker: reconnect after 5s on close,
25s ping keepalive, parse-guard on messages.

`LiveTicker.svelte` is refactored to consume `liveStore` (subscribe to `events` +
`connected`) instead of opening its own WS. No visible behavior change.

**Why:** one connection, one source of truth; BurnRate, Heatmap pulse, and hero
odometer all subscribe to the same store. Components stay dumb and independently
reasoned about.

## Feature 1 — Insight strip (top driver)

### Backend: `GET /api/insights?period=`

- Resolve current window from `period` (reuse `_period_range`).
- Resolve **prior** window = immediately-preceding window of equal length.
- Pull per-model cost for both windows (reuse store/model aggregation).
- `delta_usd` = current_total − prior_total; `delta_pct` = delta / prior_total
  (null when prior_total == 0).
- Driver = model with the largest signed `cost_usd` change between windows;
  `driver.label` = model name, `driver.delta_usd` = its change.
- Response:
  ```json
  {
    "current_usd": 71.40,
    "prior_usd": 50.20,
    "delta_usd": 21.20,
    "delta_pct": 0.422,
    "direction": "up",
    "driver": { "label": "gpt-4o", "delta_usd": 31.0 }
  }
  ```
- When there is no prior data (prior window empty), return `{ "insight": null }`
  so the UI can hide the strip cleanly.

### Frontend: `InsightStrip.svelte`

- Mounted in Dashboard, directly under the hero total, above the BarStrip.
- Fetches `api.insights(period)` on period change / `refreshTick`.
- Renders one line: `Spend ↑42% vs prior 7d — driven by gpt-4o (+$31)`.
  - `↑` red for increase, `↓` muted for decrease.
  - Driver clause omitted if `driver` is null.
- Hidden entirely when `insight == null` or dashboard has no data.

## Feature 2 — Live burn ambient (full)

### `BurnRate.svelte`

- Placed beside the hero total (same flex row as Odometer / BurnGauge).
- Shows `liveStore.burnRatePerMin` formatted as `$X.XX/min` with a `microlabel`
  "burn rate".
- **Idle:** if `Date.now() - lastEventAt > 90_000` (or never), dim to `idle`
  state showing the last known rate greyed — no layout shift.

### Ambient motion (all `liveStore`-driven, no new WS)

- **Hero odometer optimistic roll:** on each new event, add `event.cost_usd` to
  the displayed total so it visibly ticks. Authoritative value is re-fetched on
  `refreshTick`; on each fetch, **snap** the displayed total to the server value
  to correct drift.
- **Heatmap today-cell pulse:** the cell for today's date + the live dot pulse
  via a CSS keyframe when a new event arrives.
- **Hero red flash:** subtle, short red flash on the total on each event.

### Constraints

- All motion respects reduced-motion (`@media (prefers-reduced-motion)` disables
  pulse/flash; counter still updates).

## Feature 3 — Share card + badge

### Weekly card

- Extend `Poster.svelte` with a `variant: 'weekly'` that frames the last-7d range
  and top models.
- Add an "EXPORT WEEKLY CARD" action (alongside existing EXPORT POSTER) that
  builds the weekly dataset (`api.overview('7d')` + `api.models('7d')`) and opens
  Poster in weekly variant → user saves the rendered image.

### SVG badge

- Backend `GET /api/badge.svg` renders a shields-style SVG:
  `burnmeter | $X this month` (month-to-date total, red accent). No key/secret
  ever in the output — only the dollar figure.
- On each sync, write `burn-badge.svg` to a configured path (default: repo root).
  Path is a setting; the writer only ever emits the dollar figure.
- Settings surfaces the badge: a copyable markdown snippet
  `![burnmeter](./burn-badge.svg)` plus the live `/api/badge.svg` URL.

## Testing

- **Backend (pytest):**
  - `test_insights.py` — delta and driver math; `delta_pct` null on zero prior;
    `insight: null` on empty prior window; driver picks largest signed change.
  - `test_badge.py` — SVG renders valid markup; dollar formatting; asserts no key
    material can appear.
- **Frontend:** no vitest in project → `npm run check` (svelte-check, 0 errors)
  plus manual verification. `liveStore` burn-rate window logic is written as a
  pure function so it can be unit-tested later if vitest is added.

## Risks & mitigations

- **Optimistic odometer drift** from authoritative total → snap to server value on
  every `refreshTick` fetch.
- **Badge file write** must never write secrets → writer takes only the computed
  dollar figure, not provider/key data; path is explicit and defaulted.
- **Insight on sparse data** → "top driver" requires a non-empty prior window;
  otherwise strip hides (no misleading insight).
- **liveStore refactor** could regress LiveTicker → keep LiveTicker markup
  unchanged, swap only the data source; verify `live`/`offline` + ticker render.

## Out of scope (flagged, not built)

- `/api/sync` returning record counts (separate backend task).
- Store-mode SDK keyless behavior fix (separate backend task).
- Anomaly/spike and budget-pace insight types (only "top driver" this round).
