# Evidence

Consolidated from 4 subagent reports (structural, visual, copy & honesty, weight & friction).

---

## Structural Evidence

- **Interactive element count: 47** (28 buttons, 6 inputs, 1 select, 6 div[onclick], 1 textarea, 1 link) — App:53-87, Dashboard:84-165, Playground:42-84, ProviderDetail:50-190, Settings:91-190, Heatmap:63-71 (120 cells)
- **Max nesting depth: 5** — App → main → Dashboard → BarStrip → group div (App.svelte:49)
- **Repeated patterns (6):**
  - Key input+button: Settings.svelte:106-118 AND ProviderDetail.svelte:106-118 (identical structure, not componentized)
  - COPY button: Settings.svelte:129 (same action appears twice in same view for different contexts)
  - REMOVE button: Settings.svelte:91, Settings.svelte:158, ProviderDetail.svelte:158
  - Billing config section: Settings.svelte:173-195 and ProviderDetail
  - Error display: Settings.svelte:98,121,192 and ProviderDetail.svelte:22,55,98
  - Sort column headers: ProviderDetail.svelte:79-83 (4 buttons: INPUT, OUTPUT, REQS, COST)
- **Dead props/imports: 0**

---

## Visual Evidence

**Spacing scale:** Tailwind 4px base (0.5–8 units = 2–32px) with orphan values: `150px`, `110px` (BarStrip absolute heights). No custom scale deviations beyond these.

**Type scale (7 levels):**
- 10.9px (`microlabel-dim`, app.css:74)
- 11.5px (`microlabel`, app.css:66)
- 12px (`text-xs`)
- 14px (`text-sm`)
- 18px (`text-lg`)
- 24–36px (`text-2xl`–`text-4xl`)
- 48–64px (`text-6xl`–`text-8xl`)

Root is 116% (app.css:35), shifting all rem sizes. Microlabels use fixed rem orphan values (0.68rem, 0.72rem) outside the Tailwind scale.

**Color tokens (12 distinct):**
1. `--ink` oklch(0.16 0.004 280) — bg
2. `--ink-2` oklch(0.19 0.005 280) — hover cell bg
3. `--paper` oklch(0.96 0.002 90) — primary text
4. `--muted` oklch(0.52 0.008 280) — secondary text
5. `--hairline` oklch(0.27 0.006 280) — borders
6. `--red` oklch(0.66 0.23 32) — accent
7. `--red-dim` oklch(0.36 0.12 32) — dimmed accent
8–11. `--heat-1` through `--heat-4` — heatmap scale
12. `color-mix(in oklch, var(--ink) 88%, transparent)` — header blur (App.svelte:51)

**Contrast — lowest observed (INFERRED):**
- `--muted` on `--ink`: ~3.5:1 — fails WCAG AA (4.5:1) for normal text
- `microlabel-dim` (0.68rem, muted color) on ink: fails AA at small size

**States present checklist:**

| Component | empty | loading | error | success | focus | disabled |
|-----------|-------|---------|-------|---------|-------|----------|
| Dashboard.svelte | ✓ | ✓ | ✓ | ✓ | ✓ | MISSING |
| Settings.svelte | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| ProviderDetail.svelte | ✓ | ✓ | ✓ | ✓ | MISSING | MISSING |
| BurnGauge.svelte | ✓ | MISSING | MISSING | ✓ | ✓ | ✓ |
| Heatmap.svelte | INFERRED | MISSING | MISSING | ✓ | MISSING | MISSING |
| Odometer.svelte | MISSING | MISSING | MISSING | ✓ | MISSING | MISSING |
| App.svelte (nav) | n/a | ✓ | MISSING | ✓ | MISSING | ✓ |

**Motion inventory (8 entries):**
1. `pulse-red` — 0.6s ease-out box-shadow inset flash (app.css:94)
2. `ticker-in` — translateY(100%) → 0, opacity 0→1 (app.css:102-105)
3. Odometer digit scroll — 500ms ease-out transition-transform (Odometer.svelte:14)
4. `animate-pulse` — Tailwind loading skeletons (Dashboard:69, Settings:200, App:101)
5. `transition-colors` — nav/sync/row hover (App.svelte:64,84, Dashboard:139, ProviderDetail:90)
6. `transition-transform` — default 150ms
7. `hover:scale-125` — heatmap cell hover zoom (Heatmap.svelte:66)
8. `prefers-reduced-motion` override — 0.01ms duration (app.css:107-111) ✓

**Idle animations (data loaded, no interaction): 5** — Odometer digit roll transitions fire on each data fetch.

---

## Copy & Honesty Evidence

**Inflations: 0** — copy is uniformly factual.

**Dark patterns: 0**

**Jargon / unclear labels (6 flagged):**
1. `"o200k_base"` (Playground.svelte:52) — OpenAI encoder name; proposed: "OpenAI token encoding"
2. `"proxy-captured traffic"` (ProviderDetail.svelte:115) — proposed: "traffic routed through local proxy"
3. `"local proxy" / "usage api"` (Settings.svelte:85) — proposed: "local proxy (counts live)" / "usage API (backfilled)"
4. `"Ground-truth cost"` (Settings.svelte:156) — proposed: "Actual billed cost"
5. `"Burn"` (BurnGauge.svelte:41) — finance jargon; proposed: "Spending pace"
6. `"MTD"` (App.svelte:77) — abbreviation unexplained; proposed: "This month"
7. `"AUD IN" / "AUD OUT"` (ProviderDetail.svelte:74-75) — "Audio" abbreviated; proposed: "Audio In" / "Audio Out"

**Label→behavior mismatches (1):**
- `"POSTER ↓"` (App.svelte:81) label implies immediate download; actual behavior: opens modal first. Proposed: "EXPORT POSTER" or "POSTER…"

**Hover-only affordance (UX friction, not mismatch):**
- `"open →"` text (Dashboard.svelte:147) — visible only on hover; first-time users won't see drilldown affordance.

---

## Weight & Friction Evidence

- **Initial JS (main bundle):** 96,936 bytes raw | 34,236 bytes gzip — under 100KB ✓
- **Lazy chunk (Playground):** 2,037,606 bytes raw | 1,034,058 bytes gzip — 1MB gzip (tiktoken WASM)
- **Network requests on Dashboard load:** 4 HTTP (overview, budget, heatmap, models) + 1 WebSocket (/ws/live) = 5 total
- **TTI estimated:** 800–1,500ms (bundle parse ~500ms + API latency 200–800ms) — ESTIMATED
- **Idle animations:** 5 (Odometer digit transitions, fire on each data refresh)
- **Auto-appearing modals/badges on load:** 0 — Poster modal is user-triggered; LiveTicker dot is passive
- **prefers-reduced-motion:** HONORED (app.css:107-111, 0.01ms override) ✓
- **Dark mode:** Default dark theme; no `prefers-color-scheme` detection (no light mode)
