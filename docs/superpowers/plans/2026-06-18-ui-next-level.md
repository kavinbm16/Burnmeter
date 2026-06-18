# UI Next-Level Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a top-driver insight strip, a full live-burn ambient experience, and a shareable weekly card + committable SVG badge to burnmeter.

**Architecture:** Backend gains pure compute functions (`insights`, `badge`) exposed as FastAPI endpoints with pytest TDD. Frontend gains a single shared `liveStore` that owns the one `/ws/live` WebSocket and a derived burn-rate; new Svelte components subscribe to it. Optimistic UI corrects against authoritative fetches.

**Tech Stack:** FastAPI + aiosqlite (backend), Svelte 5 runes + Tailwind (frontend), pytest (backend tests), svelte-check (frontend typecheck — no vitest in project).

## Global Constraints

- Local-first: no public server; keys never leave the machine — verbatim from spec.
- Badge output contains ONLY the dollar figure — never provider/key/secret data.
- Backend dollar amounts: USD float; format to 2 decimals for display.
- Period names supported by `_period_range`: `today, yesterday, 7d, mtd, 30d, 90d`.
- Existing WebSocket event shape (do not change): `{provider, model, input_tokens, output_tokens, audio_input_tokens?, audio_output_tokens?, source?, key_id?, cost_usd, ts}`.
- Frontend reduced-motion: pulse/flash disabled under `prefers-reduced-motion`; counters still update.
- Run backend tests with `python -m pytest`; frontend check with `npm run check` (in `frontend/`), expect `0 ERRORS`.

---

### Task 1: Prior-window range helper (backend)

**Files:**
- Modify: `backend/main.py` (add `_prior_range` near `_period_range`, ~line 127)
- Test: `tests/test_insights.py` (create)

**Interfaces:**
- Produces: `_prior_range(start: str, end: str) -> tuple[str, str]` — given an inclusive `[start, end]` window, returns the immediately-preceding window of equal length (also inclusive). For a 1-day window `(d, d)` returns `(d-1, d-1)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_insights.py
from backend.main import _prior_range


def test_prior_range_multi_day():
    # 2026-06-11..2026-06-17 is 7 days inclusive; prior is 2026-06-04..2026-06-10
    assert _prior_range("2026-06-11", "2026-06-17") == ("2026-06-04", "2026-06-10")


def test_prior_range_single_day():
    assert _prior_range("2026-06-18", "2026-06-18") == ("2026-06-17", "2026-06-17")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_insights.py -v`
Expected: FAIL — `ImportError: cannot import name '_prior_range'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/main.py — add directly below _period_range
def _prior_range(start: str, end: str) -> tuple[str, str]:
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    length = (e - s).days + 1  # inclusive day count
    prior_end = s - timedelta(days=1)
    prior_start = prior_end - timedelta(days=length - 1)
    return prior_start.isoformat(), prior_end.isoformat()
```

Ensure `from datetime import date` is imported in `backend/main.py` (it imports `datetime, timezone, timedelta` — add `date`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_insights.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_insights.py
git commit -m "feat: add _prior_range helper for period-over-period insights"
```

---

### Task 2: Insight computation + `/api/insights` endpoint (backend)

**Files:**
- Modify: `backend/main.py` (add `_compute_insight` + `@app.get("/api/insights")` after the `/api/models` endpoint, ~line 258)
- Test: `tests/test_insights.py` (extend)

**Interfaces:**
- Consumes: `store.overview(start, end) -> dict` with `["totals"]["cost_usd"]`; `store.models_leaderboard(start, end) -> list[dict]` each having `model: str`, `cost_usd: float | None`.
- Produces: `async def _compute_insight(store, cur_start, cur_end, prior_start, prior_end) -> dict | None` returning either `None` (no prior data) or:
  ```python
  {
    "current_usd": float, "prior_usd": float,
    "delta_usd": float, "delta_pct": float | None,
    "direction": "up" | "down" | "flat",
    "driver": {"label": str, "delta_usd": float} | None,
  }
  ```
  Endpoint `GET /api/insights?period=` returns `{"insight": <that dict or None>}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_insights.py — append
# (pyproject sets asyncio_mode = "auto" → no @pytest.mark.asyncio needed)
from backend.main import _compute_insight


class _FakeStore:
    def __init__(self, totals, models):
        # totals: {(start,end): cost}; models: {(start,end): [ {model, cost_usd}, ... ]}
        self._totals = totals
        self._models = models

    async def overview(self, start, end):
        return {"totals": {"cost_usd": self._totals.get((start, end), 0.0)}}

    async def models_leaderboard(self, start, end):
        return self._models.get((start, end), [])


async def test_insight_top_driver_up():
    store = _FakeStore(
        totals={("c0", "c1"): 71.4, ("p0", "p1"): 50.2},
        models={
            ("c0", "c1"): [{"model": "gpt-4o", "cost_usd": 51.0}, {"model": "haiku", "cost_usd": 20.4}],
            ("p0", "p1"): [{"model": "gpt-4o", "cost_usd": 20.0}, {"model": "haiku", "cost_usd": 30.2}],
        },
    )
    out = await _compute_insight(store, "c0", "c1", "p0", "p1")
    assert out["direction"] == "up"
    assert round(out["delta_usd"], 2) == 21.2
    assert round(out["delta_pct"], 3) == 0.422
    # gpt-4o rose +31 (largest signed change); haiku fell -9.8
    assert out["driver"]["label"] == "gpt-4o"
    assert round(out["driver"]["delta_usd"], 1) == 31.0


async def test_insight_none_when_no_prior():
    store = _FakeStore(totals={("c0", "c1"): 10.0}, models={("c0", "c1"): [{"model": "x", "cost_usd": 10.0}]})
    out = await _compute_insight(store, "c0", "c1", "p0", "p1")
    assert out is None


async def test_insight_delta_pct_null_on_zero_prior_with_data():
    # prior total is zero but there is at least one prior model row → still no prior baseline
    store = _FakeStore(totals={("c0", "c1"): 10.0, ("p0", "p1"): 0.0}, models={("c0", "c1"): [], ("p0", "p1"): []})
    out = await _compute_insight(store, "c0", "c1", "p0", "p1")
    assert out is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_insights.py -v`
Expected: FAIL — `ImportError: cannot import name '_compute_insight'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/main.py — add above the /api/models endpoint
async def _compute_insight(store, cur_start, cur_end, prior_start, prior_end):
    prior_total = (await store.overview(prior_start, prior_end))["totals"]["cost_usd"] or 0.0
    if prior_total <= 0:
        return None  # no baseline → no honest insight
    cur_total = (await store.overview(cur_start, cur_end))["totals"]["cost_usd"] or 0.0

    cur_models = {m["model"]: (m.get("cost_usd") or 0.0) for m in await store.models_leaderboard(cur_start, cur_end)}
    prior_models = {m["model"]: (m.get("cost_usd") or 0.0) for m in await store.models_leaderboard(prior_start, prior_end)}
    driver = None
    if cur_models or prior_models:
        best = max(
            (cur_models.keys() | prior_models.keys()),
            key=lambda k: abs(cur_models.get(k, 0.0) - prior_models.get(k, 0.0)),
        )
        driver = {"label": best, "delta_usd": cur_models.get(best, 0.0) - prior_models.get(best, 0.0)}

    delta = cur_total - prior_total
    return {
        "current_usd": cur_total,
        "prior_usd": prior_total,
        "delta_usd": delta,
        "delta_pct": delta / prior_total,
        "direction": "up" if delta > 0.005 else "down" if delta < -0.005 else "flat",
        "driver": driver,
    }


@app.get("/api/insights")
async def insights(period: str = "7d"):
    start, end = _period_range(period)
    prior_start, prior_end = _prior_range(start, end)
    return {"insight": await _compute_insight(store, start, end, prior_start, prior_end)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_insights.py -v`
Expected: PASS (5 passed total)

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_insights.py
git commit -m "feat: add /api/insights top-driver endpoint"
```

---

### Task 3: Badge SVG renderer + `/api/badge.svg` endpoint (backend)

**Files:**
- Create: `backend/badge.py`
- Modify: `backend/main.py` (add `@app.get("/api/badge.svg")` after `/api/insights`)
- Test: `tests/test_badge.py` (create)

**Interfaces:**
- Produces: `render_badge_svg(amount_usd: float) -> str` — returns a self-contained shields-style SVG string with label `burnmeter` and value `$<amount, 2dp>`.
- Endpoint `GET /api/badge.svg` returns the SVG with `media_type="image/svg+xml"`, value = month-to-date total from `store.overview(month_start, today)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_badge.py
from backend.badge import render_badge_svg


def test_badge_is_valid_svg_with_amount():
    svg = render_badge_svg(42.5)
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "burnmeter" in svg
    assert "$42.50" in svg


def test_badge_formats_two_decimals():
    assert "$0.00" in render_badge_svg(0)
    assert "$1234.60" in render_badge_svg(1234.6)


def test_badge_contains_no_secret_inputs():
    # Only the dollar figure is ever rendered; pass a junk "key-like" amount path is impossible
    svg = render_badge_svg(7.0)
    for needle in ("sk-", "AIza", "api", "key"):
        assert needle.lower() not in svg.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_badge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.badge'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/badge.py
"""Render a shields-style SVG badge. Input is ONLY a dollar figure — never any
key, provider, or secret material."""
from __future__ import annotations


def render_badge_svg(amount_usd: float) -> str:
    value = f"${amount_usd:.2f}"
    label = "burnmeter"
    # crude but stable widths (6px/char + padding) so the badge renders standalone
    lw = 8 + len(label) * 6
    vw = 8 + len(value) * 7
    w = lw + vw
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="20" role="img" '
        f'aria-label="{label}: {value}">'
        f'<rect width="{lw}" height="20" fill="#2a2a2e"/>'
        f'<rect x="{lw}" width="{vw}" height="20" fill="#e5484d"/>'
        f'<g fill="#fff" font-family="Verdana,Geneva,sans-serif" font-size="11">'
        f'<text x="{lw/2:.0f}" y="14" text-anchor="middle">{label}</text>'
        f'<text x="{lw + vw/2:.0f}" y="14" text-anchor="middle">{value}</text>'
        f'</g></svg>'
    )
```

```python
# backend/main.py — add import at top with the other backend imports
from backend.badge import render_badge_svg

# add endpoint after /api/insights
@app.get("/api/badge.svg")
async def badge_svg():
    today = datetime.now(tz=timezone.utc).date()
    month_start = today.replace(day=1).isoformat()
    total = (await store.overview(month_start, today.isoformat()))["totals"]["cost_usd"] or 0.0
    return Response(content=render_badge_svg(total), media_type="image/svg+xml")
```

Ensure `from fastapi.responses import Response` (or `from starlette.responses import Response`) is available in `backend/main.py`; add if missing.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_badge.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/badge.py backend/main.py tests/test_badge.py
git commit -m "feat: add SVG burn badge renderer and /api/badge.svg"
```

---

### Task 4: Write badge file on sync (backend)

**Files:**
- Modify: `backend/main.py` (`trigger_sync`, ~line 192; add a `_write_badge_file` helper)
- Test: `tests/test_badge.py` (extend)

**Interfaces:**
- Produces: `async def _write_badge_file() -> None` — computes MTD total, renders SVG, writes to `os.environ.get("BURNMETER_BADGE_PATH", "burn-badge.svg")`. Called at the end of `trigger_sync`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_badge.py — append
import os
from backend import badge as badge_mod


def test_badge_file_written(tmp_path):
    path = tmp_path / "burn-badge.svg"
    badge_mod.write_badge(str(path), 12.3)
    assert path.read_text().startswith("<svg")
    assert "$12.30" in path.read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_badge.py::test_badge_file_written -v`
Expected: FAIL — `AttributeError: module 'backend.badge' has no attribute 'write_badge'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/badge.py — append
def write_badge(path: str, amount_usd: float) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_badge_svg(amount_usd))
```

```python
# backend/main.py — add helper near badge endpoint, call from trigger_sync
import os  # ensure imported (it is — used by run())

from backend.badge import render_badge_svg, write_badge  # extend existing import


async def _write_badge_file() -> None:
    today = datetime.now(tz=timezone.utc).date()
    month_start = today.replace(day=1).isoformat()
    total = (await store.overview(month_start, today.isoformat()))["totals"]["cost_usd"] or 0.0
    write_badge(os.environ.get("BURNMETER_BADGE_PATH", "burn-badge.svg"), total)
```

Then in `trigger_sync`, after the sync calls and before `return {"ok": True}`:

```python
    await _write_badge_file()
    return {"ok": True}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_badge.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/badge.py backend/main.py tests/test_badge.py
git commit -m "feat: write burn-badge.svg to disk on sync"
```

---

### Task 5: Shared `liveStore` + LiveTicker refactor (frontend)

**Files:**
- Create: `frontend/src/lib/liveStore.ts`
- Modify: `frontend/src/lib/components/LiveTicker.svelte`

**Interfaces:**
- Produces (module `liveStore`):
  - `export interface LiveEvent { provider: string; model: string; input_tokens: number; output_tokens: number; audio_input_tokens?: number; audio_output_tokens?: number; source?: string; key_id?: string; cost_usd: number | null; ts: string }`
  - `export const events: Readable<LiveEvent[]>` — last 12, newest first.
  - `export const connected: Readable<boolean>`
  - `export const burnRatePerMin: Readable<number>` — sum of `cost_usd` over events within the last 60s, as $/min.
  - `export const lastEventAt: Readable<number>` — epoch ms of latest event (0 if none).
  - `export function computeBurnRate(evts: LiveEvent[], now: number): number` — pure; sum `cost_usd` of events with `Date.parse(ts) >= now - 60000`.
  - `export function startLive(): () => void` — idempotent; opens the single WS, returns a no-op-safe stop fn. Safe to call from multiple components (ref-counted).

- [ ] **Step 1: Write `liveStore.ts`**

```ts
// frontend/src/lib/liveStore.ts
import { writable, derived, type Readable } from 'svelte/store'

export interface LiveEvent {
  provider: string
  model: string
  input_tokens: number
  output_tokens: number
  audio_input_tokens?: number
  audio_output_tokens?: number
  source?: string
  key_id?: string
  cost_usd: number | null
  ts: string
}

export function computeBurnRate(evts: LiveEvent[], now: number): number {
  return evts
    .filter((e) => Date.parse(e.ts) >= now - 60_000)
    .reduce((sum, e) => sum + (e.cost_usd ?? 0), 0)
}

const _events = writable<LiveEvent[]>([])
const _connected = writable(false)
const _lastEventAt = writable(0)

export const events: Readable<LiveEvent[]> = _events
export const connected: Readable<boolean> = _connected
export const lastEventAt: Readable<number> = _lastEventAt
export const burnRatePerMin: Readable<number> = derived(_events, ($e) => computeBurnRate($e, Date.now()))

let ws: WebSocket | null = null
let refcount = 0
let retry: ReturnType<typeof setTimeout>
let ping: ReturnType<typeof setInterval>
let closed = false

function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/ws/live`)
  ws.onopen = () => {
    _connected.set(true)
    ping = setInterval(() => ws?.readyState === 1 && ws.send('ping'), 25_000)
  }
  ws.onmessage = (msg) => {
    try {
      const e = JSON.parse(msg.data) as LiveEvent
      _events.update((cur) => [e, ...cur].slice(0, 12))
      _lastEventAt.set(Date.now())
    } catch (err) {
      console.error('[liveStore] parse failed:', msg.data, err)
    }
  }
  ws.onclose = () => {
    _connected.set(false)
    clearInterval(ping)
    if (!closed) retry = setTimeout(connect, 5000)
  }
}

export function startLive(): () => void {
  refcount++
  if (!ws) {
    closed = false
    connect()
  }
  return () => {
    refcount--
    if (refcount <= 0) {
      closed = true
      clearTimeout(retry)
      clearInterval(ping)
      ws?.close()
      ws = null
    }
  }
}
```

- [ ] **Step 2: Refactor LiveTicker to consume the store**

Replace the `<script>` body of `LiveTicker.svelte` so it no longer opens its own WS — subscribe to `liveStore` instead. Keep the `onevent` callback and the existing markup unchanged.

```svelte
<script lang="ts">
  import { fmtTokens, fmtUsd } from '$lib/api'
  import { events as liveEvents, connected as liveConnected, startLive, type LiveEvent } from '$lib/liveStore'

  let { onevent }: { onevent?: () => void } = $props()

  let events = $state<LiveEvent[]>([])
  let connected = $state(false)

  $effect(() => {
    const stop = startLive()
    const unEvents = liveEvents.subscribe((e) => {
      events = e
      onevent?.()
    })
    const unConn = liveConnected.subscribe((c) => (connected = c))
    return () => {
      unEvents()
      unConn()
      stop()
    }
  })
</script>
```

Leave the existing `<div class="flex min-w-0 ...">…</div>` markup (lines 60-90) exactly as-is.

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run check`
Expected: `0 ERRORS 0 WARNINGS`

- [ ] **Step 4: Manual verify**

Start backend + frontend, send proxy traffic; confirm the ticker still shows `live`/`offline` and rolls events. Open two tabs/components later (Task 7) and confirm only one WS connects (Network tab → one `/ws/live`).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/liveStore.ts frontend/src/lib/components/LiveTicker.svelte
git commit -m "feat: add shared liveStore; LiveTicker consumes it (single WS)"
```

---

### Task 6: Insight strip — api method + component + Dashboard mount (frontend)

**Files:**
- Modify: `frontend/src/lib/api.ts` (add `Insight` interface + `insights` method)
- Create: `frontend/src/lib/components/InsightStrip.svelte`
- Modify: `frontend/src/lib/views/Dashboard.svelte` (mount under hero, above BarStrip)

**Interfaces:**
- Consumes: `GET /api/insights?period=` → `{ insight: Insight | null }`.
- Produces: `api.insights(period: string): Promise<{ insight: Insight | null }>` and an `Insight` type matching Task 2's response dict.

- [ ] **Step 1: Add the API type + method**

```ts
// frontend/src/lib/api.ts — add interface near Overview
export interface Insight {
  current_usd: number
  prior_usd: number
  delta_usd: number
  delta_pct: number | null
  direction: 'up' | 'down' | 'flat'
  driver: { label: string; delta_usd: number } | null
}
```

```ts
// add inside the `api` object, next to `overview`
  insights: (period: string) =>
    get<{ insight: Insight | null }>(`/api/insights?period=${period}`),
```

(Match the existing `get<T>(url)` helper used by sibling methods.)

- [ ] **Step 2: Create `InsightStrip.svelte`**

```svelte
<!-- frontend/src/lib/components/InsightStrip.svelte -->
<script lang="ts">
  import { api, fmtUsd, type Insight } from '$lib/api'

  let { period, refreshTick }: { period: string; refreshTick: number } = $props()
  let insight = $state<Insight | null>(null)

  $effect(() => {
    void refreshTick
    api.insights(period).then(
      (r) => (insight = r.insight),
      () => (insight = null),
    )
  })

  const arrow = $derived(insight?.direction === 'up' ? '↑' : insight?.direction === 'down' ? '↓' : '→')
  const pct = $derived(
    insight && insight.delta_pct != null ? `${Math.abs(insight.delta_pct * 100).toFixed(0)}%` : '',
  )
</script>

{#if insight}
  <div class="microlabel-dim mt-3 flex items-center gap-2">
    <span style={insight.direction === 'up' ? 'color: var(--red)' : ''}>{arrow} {pct}</span>
    <span>vs prior period</span>
    {#if insight.driver}
      <span>— driven by <span class="text-paper">{insight.driver.label}</span>
        ({insight.driver.delta_usd >= 0 ? '+' : ''}{fmtUsd(insight.driver.delta_usd, true)})</span>
    {/if}
  </div>
{/if}
```

- [ ] **Step 3: Mount in Dashboard**

In `Dashboard.svelte`, import the component and place it directly after the hero block (after the `</div>` that closes the `flex flex-wrap items-start gap-6` hero row, before the `<!-- PRIMARY: daily bar chart -->` block):

```svelte
  import InsightStrip from '$lib/components/InsightStrip.svelte'
```

```svelte
  <InsightStrip {period} {refreshTick} />
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npm run check`
Expected: `0 ERRORS`

- [ ] **Step 5: Manual verify**

With ≥2 periods of data, the strip shows e.g. `↑ 42% vs prior period — driven by gpt-4o (+$31)`. With no prior data, the strip is absent.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/components/InsightStrip.svelte frontend/src/lib/views/Dashboard.svelte
git commit -m "feat: add top-driver insight strip to dashboard"
```

---

### Task 7: Live burn-rate counter component (frontend)

**Files:**
- Create: `frontend/src/lib/components/BurnRate.svelte`
- Modify: `frontend/src/lib/views/Dashboard.svelte` (place beside hero total)

**Interfaces:**
- Consumes: `liveStore.burnRatePerMin`, `liveStore.lastEventAt`, `startLive()`.
- Produces: a self-contained component, no props required.

- [ ] **Step 1: Create `BurnRate.svelte`**

```svelte
<!-- frontend/src/lib/components/BurnRate.svelte -->
<script lang="ts">
  import { burnRatePerMin, lastEventAt, startLive } from '$lib/liveStore'

  let rate = $state(0)
  let last = $state(0)
  let now = $state(Date.now())

  $effect(() => {
    const stop = startLive()
    const unR = burnRatePerMin.subscribe((v) => (rate = v))
    const unL = lastEventAt.subscribe((v) => (last = v))
    const tick = setInterval(() => (now = Date.now()), 1000)
    return () => { unR(); unL(); clearInterval(tick); stop() }
  })

  const idle = $derived(last === 0 || now - last > 90_000)
</script>

<div class="text-right" style={idle ? 'opacity: 0.5' : ''}>
  <div class="microlabel">burn rate</div>
  <div class="numeral mt-1 text-2xl" style={idle ? '' : 'color: var(--red)'}>
    ${rate.toFixed(2)}<span class="microlabel-dim">/min</span>
  </div>
  <div class="microlabel-dim">{idle ? 'idle' : 'live'}</div>
</div>
```

- [ ] **Step 2: Mount beside hero**

In `Dashboard.svelte`, inside the hero `flex flex-wrap items-start gap-6` row, add `<BurnRate />` after `<BurnGauge .../>`. Import it:

```svelte
  import BurnRate from '$lib/components/BurnRate.svelte'
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run check`
Expected: `0 ERRORS`

- [ ] **Step 4: Manual verify**

Send proxy traffic → counter shows `$X.XX/min` in red + `live`. Stop traffic 90s → dims to `idle`. Network tab still shows a single `/ws/live` (shared with LiveTicker).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/components/BurnRate.svelte frontend/src/lib/views/Dashboard.svelte
git commit -m "feat: add live burn-rate counter with idle fallback"
```

---

### Task 8: Ambient motion — odometer roll, heatmap pulse, reduced-motion (frontend)

**Files:**
- Modify: `frontend/src/lib/views/Dashboard.svelte` (optimistic total + snap)
- Modify: `frontend/src/lib/components/Heatmap.svelte` (today-cell pulse on event)
- Modify: `frontend/src/app.css` (pulse/flash keyframes + reduced-motion guard)

**Interfaces:**
- Consumes: `liveStore.events` (subscribe for "new event arrived"), `liveStore.lastEventAt`.

- [ ] **Step 1: Add keyframes + reduced-motion guard to `app.css`**

```css
/* live ambient motion */
@keyframes burn-pulse { 0% { box-shadow: 0 0 0 0 var(--red); } 70% { box-shadow: 0 0 0 6px transparent; } 100% { box-shadow: 0 0 0 0 transparent; } }
@keyframes burn-flash { 0% { color: var(--red); } 100% { color: inherit; } }
.burn-pulse { animation: burn-pulse 0.8s ease-out; }
.burn-flash { animation: burn-flash 0.6s ease-out; }
@media (prefers-reduced-motion: reduce) {
  .burn-pulse, .burn-flash { animation: none; }
}
```

- [ ] **Step 2: Optimistic odometer roll + snap in Dashboard**

In `Dashboard.svelte` script, add a `displayCost` state that starts from the authoritative total and is bumped by live events, then snaps back on each fetch:

```svelte
  import { events as liveEvents } from '$lib/liveStore'

  let displayCost = $state(0)
  let flash = $state(false)

  // snap to authoritative value whenever data refetches
  $effect(() => {
    if (data) displayCost = data.totals.cost_usd ?? 0
  })

  // optimistic bump on each new live event
  $effect(() => {
    const un = liveEvents.subscribe((evts) => {
      const latest = evts[0]
      if (latest && latest.cost_usd) {
        displayCost += latest.cost_usd
        flash = true
        setTimeout(() => (flash = false), 600)
      }
    })
    return un
  })
```

Change the hero Odometer to use `displayCost` and the flash class:

```svelte
      <div class="mt-4 flex items-baseline text-7xl lg:text-8xl" class:burn-flash={flash}>
        <Odometer value={displayCost.toFixed(2)} />
      </div>
```

Note: the first `liveEvents.subscribe` fires immediately with the current buffer; guard so initial subscription does not double-count by tracking the latest seen `ts`:

```svelte
  let seenTs = ''
  $effect(() => {
    const un = liveEvents.subscribe((evts) => {
      const latest = evts[0]
      if (latest && latest.ts !== seenTs) {
        seenTs = latest.ts
        if (latest.cost_usd && displayCost) {
          displayCost += latest.cost_usd
          flash = true
          setTimeout(() => (flash = false), 600)
        }
      }
    })
    return un
  })
```

(Use only this guarded version; drop the unguarded one above.)

- [ ] **Step 3: Heatmap today-cell pulse**

In `Heatmap.svelte`, accept an optional `pulseDate: string | null` prop (the date to pulse). Add `class:burn-pulse={day.date === pulseDate}` to the cell element. In `Dashboard.svelte`, pass today's date as `pulseDate` only briefly when a live event arrives:

```svelte
  // Dashboard: derive a transient pulse date
  let pulseToday = $state<string | null>(null)
  // inside the guarded live-event effect, after seenTs update:
  pulseToday = new Date().toISOString().slice(0, 10)
  setTimeout(() => (pulseToday = null), 800)
```

```svelte
  <!-- Dashboard Heatmap usage: add prop -->
  <Heatmap ... pulseDate={pulseToday} />
```

```svelte
  <!-- Heatmap.svelte: add to $props() destructure -->
  pulseDate = null,
  ...
  // on the cell element:
  class:burn-pulse={day.date === pulseDate}
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npm run check`
Expected: `0 ERRORS`

- [ ] **Step 5: Manual verify**

Send proxy traffic: hero total ticks up + brief red flash; today's heatmap cell pulses. Enable OS reduce-motion → number still updates, no flash/pulse. After a manual SYNC, the total snaps to the server value (no permanent drift).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/views/Dashboard.svelte frontend/src/lib/components/Heatmap.svelte frontend/src/app.css
git commit -m "feat: live ambient — optimistic odometer, heatmap pulse, reduced-motion"
```

---

### Task 9: Weekly share card (frontend)

**Files:**
- Modify: `frontend/src/lib/components/Poster.svelte` (add `variant` prop)
- Modify: `frontend/src/App.svelte` (add EXPORT WEEKLY CARD action)

**Interfaces:**
- Consumes: existing `api.overview('7d')` and `api.models('7d')`.
- Produces: `Poster` accepts `variant?: 'poster' | 'weekly'` (default `'poster'`), and a "weekly" heading/range when `weekly`.

- [ ] **Step 1: Add `variant` to Poster**

In `Poster.svelte`, extend `$props()` with `variant = 'poster'` and switch the title/subtitle:

```svelte
  let { data, models, variant = 'poster', onclose }:
    { data: Overview; models: LeaderboardModel[]; variant?: 'poster' | 'weekly'; onclose: () => void } = $props()
```

```svelte
  <!-- where the heading renders -->
  <h2>{variant === 'weekly' ? 'WEEKLY BURN' : 'BURNMETER'}</h2>
  <p class="microlabel-dim">{data.period.start} → {data.period.end}</p>
```

(Adapt to Poster's actual heading markup; keep its existing styling.)

- [ ] **Step 2: Add export action in App**

In `App.svelte`, add a weekly export handler and a button next to EXPORT POSTER:

```svelte
  let posterVariant = $state<'poster' | 'weekly'>('poster')

  async function exportWeekly() {
    const [o, m] = await Promise.all([api.overview('7d'), api.models('7d')])
    posterVariant = 'weekly'
    poster = { data: o, models: m.models }
  }
```

Update the existing `exportPoster` to set `posterVariant = 'poster'`, and pass the variant to Poster:

```svelte
  <button class="focus-ring microlabel-dim hover:text-paper" onclick={exportWeekly}>EXPORT WEEKLY CARD</button>
```

```svelte
{#if poster}
  <Poster data={poster.data} models={poster.models} variant={posterVariant} onclose={() => (poster = null)} />
{/if}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run check`
Expected: `0 ERRORS`

- [ ] **Step 4: Manual verify**

Click EXPORT WEEKLY CARD → Poster opens titled "WEEKLY BURN" with the 7-day range and top models; existing EXPORT POSTER still renders the default poster.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/components/Poster.svelte frontend/src/App.svelte
git commit -m "feat: add weekly share card variant + export action"
```

---

### Task 10: Surface the badge in Settings (frontend)

**Files:**
- Modify: `frontend/src/lib/views/Settings.svelte` (add a "Share badge" block near the key-custody notice)

**Interfaces:**
- Consumes: `GET /api/badge.svg` (live preview), `burn-badge.svg` committed file (markdown snippet for README).

- [ ] **Step 1: Add badge block + copy handler**

In `Settings.svelte` script, add:

```ts
  const badgeUrl = `${location.protocol}//${location.host}/api/badge.svg`
  const badgeMarkdown = '![burnmeter](./burn-badge.svg)'
  let badgeCopied = $state(false)
  function copyBadge() {
    navigator.clipboard.writeText(badgeMarkdown)
    badgeCopied = true
    setTimeout(() => (badgeCopied = false), 1500)
  }
```

In the template, just above the "Key custody notice" `<p class="mt-10 microlabel-dim">`:

```svelte
  <div class="mt-10 border border-hairline p-4">
    <div class="microlabel mb-2">SHARE BADGE</div>
    <img src={badgeUrl} alt="burnmeter badge" class="mb-3" />
    <p class="microlabel-dim mb-2">
      A <code class="numeral">burn-badge.svg</code> is written to your repo on each sync. Paste this in your README:
    </p>
    <div class="flex items-center gap-3">
      <code class="numeral text-xs">{badgeMarkdown}</code>
      <button class="focus-ring microlabel-dim hover:text-paper" onclick={copyBadge}>
        {badgeCopied ? 'COPIED ✓' : 'COPY'}
      </button>
    </div>
  </div>
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run check`
Expected: `0 ERRORS`

- [ ] **Step 3: Manual verify**

Settings shows a live badge image rendering the MTD total + a copyable markdown snippet. After a sync, `burn-badge.svg` exists at repo root (or `BURNMETER_BADGE_PATH`).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/views/Settings.svelte
git commit -m "feat: surface share badge + README snippet in Settings"
```

---

## Final verification

- [ ] Backend: `python -m pytest` → all pass (incl. new `test_insights.py`, `test_badge.py`).
- [ ] Frontend: `cd frontend && npm run check` → `0 ERRORS`.
- [ ] Manual smoke: dashboard shows insight strip + burn-rate; live traffic animates total + heatmap; weekly card exports; badge renders in Settings.

## Spec coverage check

- liveStore shared WS → Task 5. ✔
- Insight strip (top driver, backend endpoint, hidden on no-prior) → Tasks 1, 2, 6. ✔
- Live burn full ambient (counter+idle, optimistic odometer+snap, heatmap pulse, flash, reduced-motion) → Tasks 5, 7, 8. ✔
- Share card (Poster weekly variant) → Task 9. ✔
- SVG badge (endpoint + file write on sync + Settings surface, no secrets) → Tasks 3, 4, 10. ✔
- Out of scope (sync counts, store-mode SDK fix, anomaly/pace insights) → not planned, per spec. ✔
