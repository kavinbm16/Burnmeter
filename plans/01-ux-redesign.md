# Plan: UX Redesign — Burnmeter Dashboard & Chrome

**Source:** Dieter Rams audit, 2026-06-12. Score 16/30. REDESIGN verdict.
**Audit files:** `DESIGN-IS-2026-06-12/`

## Preserve (DO NOT TOUCH)

- oklch color tokens in `app.css:1-60` (`--ink`, `--paper`, `--red`, `--heat-1..4`, etc.)
- Space Grotesk font + 116% root font-size (`app.css:30-40`)
- `prefers-reduced-motion` override (`app.css:107-111`)
- Odometer 500ms ease-out digit scroll (`src/lib/components/Odometer.svelte:14`)
- LiveTicker WebSocket logic (`src/lib/components/LiveTicker.svelte:22-55`)
- All API endpoints in `src/lib/api.ts` — backend untouched
- Honest copy conventions: `≈` estimates, `Z` timestamps, masked keys

## Anti-patterns to guard

- Do NOT port the 12-widget simultaneous Dashboard layout under new styling
- Do NOT use feature flags — ship the new layout directly
- Do NOT add dark/light theme toggle — dark is intentional

---

## Phase 0 — Discovered State (reference before each phase)

**Phase 0 read from actual code (2026-06-12):**

### Key input block — Settings only (NOT ProviderDetail)

```svelte
<!-- Settings.svelte:106-119 — the only key input form -->
<input
  type="password"
  placeholder={name === 'openai' ? 'sk-admin-…' : 'AIza…'}
  bind:value={keyInput[name]}
  class="numeral flex-1 border border-hairline bg-ink-2 px-3 py-2 text-sm text-paper
         placeholder:text-muted/70 focus:border-red focus:outline-none"
  onkeydown={(e) => e.key === 'Enter' && add(name)}
/>
<button
  class="bg-red px-5 text-xs font-bold tracking-widest text-ink disabled:opacity-40"
  disabled={busy === name || !(keyInput[name] ?? '').trim()}
  onclick={() => add(name)}
>{busy === name ? '…' : 'ADD'}</button>
```

### Provider card — Dashboard (target for Phase 4 drill fix)

```svelte
<!-- Dashboard.svelte:137-154 -->
<div
  class="cell group cursor-pointer transition-colors hover:bg-ink-2"
  role="button" tabindex="0"
  onclick={() => ondrill(p.provider)}
  onkeydown={(e) => e.key === 'Enter' && ondrill(p.provider)}
>
  <div class="flex items-baseline justify-between">
    <span class="microlabel">{p.provider}</span>
    <span class="microlabel-dim opacity-0 transition-opacity group-hover:opacity-100">open →</span>
  </div>
  ...
</div>
```

### Sort headers — ProviderDetail (no focus at all)

```svelte
<!-- ProviderDetail.svelte:79-84 -->
<button
  class="microlabel-dim hover:text-paper"
  style={sortBy === c.key ? 'color: var(--red);' : ''}
  onclick={() => (sortBy = c.key)}
>{c.label}{sortBy === c.key ? ' ▾' : ''}</button>
```

### Heatmap day button (no focus-visible)

```svelte
<!-- Heatmap.svelte:63-71 -->
<button
  role="option"
  aria-selected={selected === d.date}
  class="aspect-square w-full min-w-[8px] transition-transform hover:scale-125"
  style="background: {selected === d.date ? 'var(--red)' : level(d.cost)};
         outline: {selected === d.date ? '1px solid var(--paper)' : 'none'};"
  title={`${d.date} · ${fmtUsd(d.cost)}`}
  onclick={() => onselect(selected === d.date ? null : d.date)}
></button>
```

### Focus state inventory (Phase 0 findings)

| Element | Current | Missing |
|---------|---------|---------|
| `<select>` (App.svelte:73) | `focus:border-red focus:outline-none` | — |
| `<input>` in Settings (line 110) | `focus:border-red focus:outline-none` | — |
| Nav `<button>`s (App.svelte:63-67) | none | `:focus-visible` ring |
| Sync `<button>` (App.svelte:83) | none | `:focus-visible` ring |
| Provider card div (Dashboard:137) | none | `:focus-visible` ring |
| Sort header `<button>`s (PD:79) | none | `:focus-visible` ring |
| ADD `<button>` (Settings:117) | none | `:focus-visible` ring |
| SET `<button>` (BurnGauge:63) | none | `:focus-visible` ring |
| Heatmap `<button>` 120x (H:63) | none | `:focus-visible` ring |

### Sidebar bug discovered

`PROVIDER_COLORS` in `api.ts` references CSS vars `--chart-openai` and `--chart-gemini` that are **not defined in `app.css`**. Fix in Phase 1 or note as out-of-scope.

---

## Phase 1 — Jargon Copy Fixes

**Principle addressed:** #4 Understandable (1/3 → target 2/3)  
**Risk:** Low — text-only changes  
**Files:** 5 files, 7 surgical replacements

### Task 1.1 — App.svelte:77 — "MTD" → "This month"

File: `frontend/src/App.svelte`

```svelte
<!-- BEFORE line 77 -->
<option value="mtd">MTD</option>

<!-- AFTER -->
<option value="mtd">This month</option>
```

### Task 1.2 — App.svelte:81 — "POSTER ↓" → "EXPORT POSTER"

File: `frontend/src/App.svelte`

```svelte
<!-- BEFORE line 81 -->
<button ... onclick={exportPoster}>POSTER ↓</button>

<!-- AFTER -->
<button ... onclick={exportPoster}>EXPORT POSTER</button>
```

### Task 1.3 — BurnGauge.svelte:41 — "Burn" → "Spending pace"

File: `frontend/src/lib/components/BurnGauge.svelte`

```svelte
<!-- BEFORE line 41 -->
<span class="microlabel">Burn</span>

<!-- AFTER -->
<span class="microlabel">Spending pace</span>
```

### Task 1.4 — Playground.svelte:52 — "o200k_base" label

File: `frontend/src/lib/views/Playground.svelte`

Find the line containing `o200k_base · runs locally` and replace:
```
<!-- BEFORE -->
o200k_base · runs locally, text never leaves this page

<!-- AFTER -->
OpenAI token encoding · runs locally, text never leaves this page
```

### Task 1.5 — ProviderDetail.svelte:74-75 — "AUD IN" / "AUD OUT"

File: `frontend/src/lib/views/ProviderDetail.svelte`

```svelte
<!-- BEFORE lines 74-75 (column headers) -->
<th>AUD IN</th>
<th>AUD OUT</th>

<!-- AFTER -->
<th>Audio In</th>
<th>Audio Out</th>
```

Also find matching header in the "By API key" table (line ~120) and apply same fix.

### Task 1.6 — Settings.svelte:156 — "Ground-truth cost" → "Actual billed cost"

File: `frontend/src/lib/views/Settings.svelte`

```svelte
<!-- BEFORE line 156 -->
<span class="microlabel">Ground-truth cost · GCP billing export</span>

<!-- AFTER -->
<span class="microlabel">Actual billed cost · GCP billing export</span>
```

### Task 1.7 — ProviderDetail.svelte:115 — "proxy-captured traffic"

File: `frontend/src/lib/views/ProviderDetail.svelte`

```svelte
<!-- BEFORE line 115 -->
proxy-captured traffic · masked hints only

<!-- AFTER -->
traffic via local proxy · masked hints only
```

### Phase 1 Verification

```bash
# Confirm all 7 jargon strings are gone
grep -r "MTD\|POSTER ↓\|o200k_base\|AUD IN\|AUD OUT\|Ground-truth\|proxy-captured\|\"Burn\"" frontend/src/
# Should return 0 matches
```

---

## Phase 2 — Focus Accessibility

**Principle addressed:** #8 Thorough (1/3 → target 2/3)  
**Risk:** Low — CSS-only changes  
**Files:** `app.css`, `App.svelte`, `Dashboard.svelte`, `ProviderDetail.svelte`, `Heatmap.svelte`, `BurnGauge.svelte`

### Task 2.1 — Define focus-ring utility in app.css

Add after line 92 (before the `pulse-red` utility):

```css
/* app.css — add after line 92 */
@utility focus-ring {
  &:focus-visible {
    outline: 2px solid var(--red);
    outline-offset: 2px;
  }
}
```

This single utility will be applied to all interactive elements below.

### Task 2.2 — App.svelte nav buttons (lines 63-67)

```svelte
<!-- BEFORE -->
<button class="microlabel-dim pb-0.5 transition-colors ...">

<!-- AFTER — add focus-ring -->
<button class="microlabel-dim pb-0.5 transition-colors focus-ring ...">
```

Apply to: logo button (line 53), all 3 nav buttons (lines 63-67), SYNC button (line 83), EXPORT POSTER button (line 81).

### Task 2.3 — Dashboard.svelte provider cards (line 137)

```svelte
<!-- BEFORE -->
<div class="cell group cursor-pointer transition-colors hover:bg-ink-2" role="button" tabindex="0" ...>

<!-- AFTER — add focus-ring -->
<div class="cell group cursor-pointer transition-colors hover:bg-ink-2 focus-ring" role="button" tabindex="0" ...>
```

### Task 2.4 — ProviderDetail.svelte sort header buttons (line 79)

```svelte
<!-- BEFORE -->
<button class="microlabel-dim hover:text-paper" ...>

<!-- AFTER -->
<button class="microlabel-dim hover:text-paper focus-ring" ...>
```

Also apply to the BACK button (line 50) and COPY / REMOVE / CONNECT buttons.

### Task 2.5 — Heatmap.svelte day buttons (line 63)

```svelte
<!-- BEFORE -->
<button
  class="aspect-square w-full min-w-[8px] transition-transform hover:scale-125"
  style="background: ...; outline: ..."
  ...

<!-- AFTER — add focus-ring, note: focus-visible outline overrides inline outline -->
<button
  class="aspect-square w-full min-w-[8px] transition-transform hover:scale-125 focus-ring"
  style="background: {selected === d.date ? 'var(--red)' : level(d.cost)};"
  aria-selected={selected === d.date}
  ...
```

Remove the inline `outline` style — the `aria-selected` + `focus-ring` combination handles both selected state (via background color) and focus state (via outline). If the selected outline is still needed visually, add a CSS rule in the utility targeting `[aria-selected="true"]`.

### Task 2.6 — BurnGauge.svelte buttons

```svelte
<!-- SET button (line 63) — add focus-ring -->
<button class="bg-red px-3 text-xs font-bold text-ink focus-ring" onclick={save}>SET</button>

<!-- Edit pencil button (line 45-47) — add focus-ring -->
<button class="microlabel-dim ... focus-ring" onclick={() => (editing = true)}>...</button>
```

### Task 2.7 — Settings.svelte buttons

Apply `focus-ring` to: ADD button (line 117), all REMOVE buttons (lines 91, 158), COPY button (line 130), CONNECT button (line 190).

### Phase 2 Verification

1. Open the app, Tab through Dashboard — every focusable element must show a 2px red outline
2. Tab through Settings — same
3. Tab through ProviderDetail — check sort headers and REMOVE/COPY buttons
4. Tab through 3 cells in Heatmap with keyboard — confirm outline appears, selected state still visually distinct

```bash
# Confirm focus-ring utility is defined
grep -n "focus-ring" frontend/src/app.css
# Confirm it's applied everywhere
grep -rn "focus-ring" frontend/src/
```

---

## Phase 3 — Dashboard Information Architecture Redesign

**Principle addressed:** #5 Unobtrusive (1/3 → target 2/3), #10 As little design as possible (1/3 → target 2/3)  
**Risk:** High — structural rewrite of Dashboard.svelte  
**Files:** `Dashboard.svelte`, `App.svelte`

### New Dashboard IA

```
PRIMARY VIEW (always visible, above fold)
├── [BurnGauge]                          — budget context, earns its place
├── [Odometer: Total spend]              — hero number, 1 only
├── [BarStrip: daily spend bars]         — single visual anchor
└── [Provider cards]                     — list, each with persistent › icon

SECONDARY SECTION (tab-switched or scrolled below a clear divider)
├── Spend calendar [Heatmap]
├── Model leaderboard [Leaderboard]
└── Live traffic [LiveTicker]
```

**Remove from primary view:**
- Input tokens Odometer
- Output tokens Odometer
- Requests Odometer

These 3 numbers move to ProviderDetail drilldown (already has them implicitly via model table).

### Task 3.1 — Add secondary section toggle to Dashboard

```svelte
<!-- Add to Dashboard.svelte $props interface -->
let {
  period,
  refreshTick,
  ondrill,
}: { period: string; refreshTick: number; ondrill: (p: string) => void } = $props()

<!-- Add local state -->
let view: 'overview' | 'detail' = $state('overview')
```

### Task 3.2 — Restructure Dashboard.svelte template

Current structure (lines 59-184): BurnGauge → Odometers (3) → BarStrip → provider loop → Heatmap → Leaderboard → LiveTicker

New structure:

```svelte
<!-- PRIMARY: always visible -->
<section class="flex flex-col gap-4">
  <!-- hero row: spend total + budget pace side by side -->
  <div class="flex items-start gap-4">
    <Odometer ... />      <!-- total spend only -->
    <BurnGauge ... />
  </div>
  <BarStrip ... />
  <!-- provider list -->
  <div class="flex flex-col gap-1">
    {#each data.providers as p}
      <div
        class="cell group cursor-pointer transition-colors hover:bg-ink-2 focus-ring"
        role="button" tabindex="0"
        onclick={() => ondrill(p.provider)}
        onkeydown={(e) => e.key === 'Enter' && ondrill(p.provider)}
      >
        <div class="flex items-baseline justify-between">
          <span class="microlabel">{p.provider}</span>
          <!-- PERSISTENT › icon — always visible, no group-hover trick -->
          <span class="microlabel-dim" aria-hidden="true">›</span>
        </div>
        <div class="numeral mt-3 text-3xl">{fmtUsd(p.cost_usd, !!p.cost_estimated)}</div>
        <div class="microlabel-dim mt-2">
          {fmtTokens(p.input_tokens)} in / {fmtTokens(p.output_tokens)} out
        </div>
      </div>
    {/each}
  </div>
</section>

<!-- SECONDARY: tab toggle -->
<div class="mt-6 flex gap-4 border-t border-hairline pt-4">
  <button
    class="microlabel-dim transition-colors focus-ring"
    class:text-paper={view === 'overview'}
    onclick={() => (view = 'overview')}
  >Calendar</button>
  <button
    class="microlabel-dim transition-colors focus-ring"
    class:text-paper={view === 'detail'}
    onclick={() => (view = 'detail')}
  >Leaderboard</button>
</div>

{#if view === 'overview'}
  <Heatmap ... />
  <LiveTicker ... />
{:else}
  <Leaderboard ... />
{/if}
```

### Task 3.3 — Remove the 3 satellite Odometers from Dashboard

Delete the Input, Output, Requests Odometer blocks (current Dashboard.svelte approximately lines 106-132 — the `grid-cols-4` satellite stats section).

These numbers are already visible in ProviderDetail model table and per-provider breakdown. They don't need to be on the primary view.

### Phase 3 Verification

1. Launch dev server: `cd frontend && npm run dev`
2. Open browser, confirm:
   - Above fold: spend total + BurnGauge + BarStrip + provider list
   - Provider card shows `›` icon always (not on hover only)
   - Tab key focuses provider cards with red outline ring
   - Secondary section toggle switches between Calendar and Leaderboard
   - LiveTicker is in Calendar tab
3. Confirm 3 satellite Odometers are gone from primary view
4. Check that ProviderDetail still shows per-model breakdowns intact

---

## Phase 4 — BurnGauge & Heatmap State Completion

**Principle addressed:** #8 Thorough (continue from Phase 2)  
**Risk:** Low — additive only  
**Files:** `BurnGauge.svelte`, `Heatmap.svelte`

### Task 4.1 — BurnGauge: add loading state

```svelte
<!-- BurnGauge.svelte — add loading prop -->
let { budget, onsave, loading = false }: {
  budget: Budget;
  onsave: (v: number | null) => void;
  loading?: boolean
} = $props()

<!-- Wrap display with loading check -->
{#if loading}
  <div class="h-8 animate-pulse rounded bg-ink-2 w-24"></div>
{:else}
  <!-- existing display content -->
{/if}
```

Pass `loading={!data}` from Dashboard.svelte when data is still fetching.

### Task 4.2 — BurnGauge: add error state

```svelte
<!-- BurnGauge.svelte — add error prop -->
let { budget, onsave, loading = false, error = null }: {
  budget: Budget;
  onsave: (v: number | null) => void;
  loading?: boolean;
  error?: string | null
} = $props()

{#if error}
  <span class="microlabel-dim text-red-dim">▲ budget unavailable</span>
{/if}
```

### Task 4.3 — Heatmap: add empty state

```svelte
<!-- Heatmap.svelte — when all days have cost === 0 -->
{#if days.every(d => d.cost === 0)}
  <p class="microlabel-dim py-4 text-center">no spend recorded in this period</p>
{:else}
  <!-- existing grid -->
{/if}
```

### Task 4.4 — Heatmap: add loading state

```svelte
<!-- Heatmap.svelte — add loading prop -->
let { days, start, end, selected = null, onselect, loading = false } = $props()

{#if loading}
  <div class="grid animate-pulse gap-px" style="grid-template-columns: repeat(12, 1fr)">
    {#each Array(120) as _}
      <div class="aspect-square w-full min-w-[8px] bg-ink-2"></div>
    {/each}
  </div>
{:else}
  <!-- existing grid -->
{/if}
```

### Phase 4 Verification

```bash
# Temporarily set backend offline, confirm:
# 1. BurnGauge shows loading skeleton while data is fetching
# 2. Heatmap shows loading skeleton while data is fetching
# 3. BurnGauge shows error text if budget endpoint fails
# 4. Heatmap shows "no spend recorded" if all days are 0
```

---

## Phase 5 — Verification & Regression Check

**Files:** No code changes — testing only

### Checklist

#### Copy (Phase 1)
- [ ] `grep -r "MTD" frontend/src/` → 0 results (only in `<option value="mtd">`)
- [ ] `grep -r "POSTER ↓" frontend/src/` → 0 results
- [ ] `grep -r "o200k_base" frontend/src/` → 0 results
- [ ] `grep -r "AUD IN\|AUD OUT" frontend/src/` → 0 results
- [ ] `grep -r "Ground-truth" frontend/src/` → 0 results
- [ ] `grep -r "proxy-captured" frontend/src/` → 0 results
- [ ] `grep -r '"Burn"' frontend/src/` → 0 results

#### Focus (Phase 2)
- [ ] Tab through Dashboard: logo → nav (3 tabs) → period select → EXPORT POSTER → SYNC → provider cards (all) → Calendar/Leaderboard toggle → heatmap cells → back to top
- [ ] Every focusable element shows 2px red outline
- [ ] No element is reachable by Tab but invisible when focused

#### Dashboard IA (Phase 3)
- [ ] Above fold on 1280px wide: spend total + BurnGauge visible without scroll
- [ ] Provider cards each show `›` icon without hovering
- [ ] Provider card keyboard activation (Enter) opens drilldown
- [ ] Calendar tab shows Heatmap + LiveTicker
- [ ] Leaderboard tab shows model table
- [ ] 3 satellite Odometers (Input, Output, Requests) are gone from primary view

#### States (Phase 4)
- [ ] BurnGauge renders loading skeleton before first data fetch resolves
- [ ] Heatmap renders loading skeleton before heatmap data resolves
- [ ] Heatmap renders empty state message when all costs are 0

#### Preserve list — regression check
- [ ] oklch token values in app.css unchanged (git diff app.css shows only focus-ring addition)
- [ ] Space Grotesk font still loading (check network tab)
- [ ] prefers-reduced-motion still overrides animations (toggle in devtools)
- [ ] Odometer digit scroll animation still fires on spend total
- [ ] LiveTicker WebSocket still connects (check Network → WS tab)
- [ ] All API endpoints still functional (no 404s in console)

---

## Execution Order

```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5
   ^           ^           ^          ^
 15 min      30 min      90 min    30 min
```

Total estimate: ~2.5 hours. Phases 1 and 2 are safe to ship independently before Phase 3.

## Files Changed

| File | Phase | Change type |
|------|-------|-------------|
| `frontend/src/App.svelte` | 1, 2 | Text + class edits |
| `frontend/src/lib/views/Dashboard.svelte` | 2, 3 | Structural rewrite |
| `frontend/src/lib/views/Settings.svelte` | 1, 2 | Text + class edits |
| `frontend/src/lib/views/ProviderDetail.svelte` | 1, 2 | Text + class edits |
| `frontend/src/lib/views/Playground.svelte` | 1 | Text edit |
| `frontend/src/lib/components/BurnGauge.svelte` | 1, 2, 4 | Props + states |
| `frontend/src/lib/components/Heatmap.svelte` | 2, 4 | Focus + states |
| `frontend/src/app.css` | 2 | Add focus-ring utility |

**No new files required.** The audit's "extract KeyInput component" recommendation was downgraded — Phase 0 confirmed the key input form only exists in Settings.svelte, not ProviderDetail, so the duplication was overstated. The other 7 changes above address the actual root causes.
