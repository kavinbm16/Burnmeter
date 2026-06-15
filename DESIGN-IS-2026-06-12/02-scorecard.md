# Scorecard

Scored by orchestrator from 01-evidence.md. Tie-breaker: lower score. Score worst instance, not mean.

---

**1. Good design is innovative — Score: 2/3**
Evidence: Live WebSocket ticker for real-time token events (LiveTicker.svelte:65-77), poster export, odometer display — combinations not standard in LLM cost tools. Core concept (cost dashboard) is established.
Justification: Refreshes the cost dashboard pattern with clear improvements (live feed, exportable poster); doesn't pioneer a genuinely new interaction pattern but improves on competitors with restraint.

---

**2. Good design makes a product useful — Score: 2/3**
Evidence: Primary task (view spend) succeeds in 0 clicks on Dashboard. But 120 heatmap buttons (Heatmap.svelte:63-71) as a day-filter mechanism adds cognitive overhead; hover-only "open →" affordance (Dashboard.svelte:147) hides drilldown from first-time users.
Justification: Primary task completes immediately; adjacent surface (heatmap as filter + invisible drill affordance) adds unnecessary steps for secondary tasks.

---

**3. Good design is aesthetic — Score: 2/3**
Evidence: oklch color system (12 tokens, consistent), Tailwind 4px base spacing, Space Grotesk. Orphan type values: 0.68rem and 0.72rem microlabels (app.css:66,74) sit outside the Tailwind scale; absolute heights 150px/110px in BarStrip outside the unit system.
Justification: ≤2 minor inconsistencies — the fixed-rem microlabel sizes and absolute BarStrip heights break from an otherwise clean system.

---

**4. Good design makes a product understandable — Score: 1/3**
Evidence: 7 jargon/unclear labels: "MTD" (App.svelte:77), "AUD IN/OUT" (ProviderDetail.svelte:74-75), "o200k_base" (Playground.svelte:52), "Ground-truth cost" (Settings.svelte:156), "proxy-captured traffic" (ProviderDetail.svelte:115), "local proxy / usage api" (Settings.svelte:85), "POSTER ↓" mismatch (App.svelte:81).
Justification: More than 2–3 controls require domain knowledge to interpret; jargon is present across all 4 views, not isolated.

---

**5. Good design is unobtrusive — Score: 1/3**
Evidence: Dashboard surfaces BurnGauge + 3 Odometers + BarStrip + 6+ provider cards + 120-cell Heatmap + Leaderboard + LiveTicker simultaneously. 5 idle animations (Odometer.svelte:14, digit transitions on refresh). Provider cards hover for drilldown text (Dashboard.svelte:147).
Justification: Chrome — the quantity of simultaneous data widgets and persistent animations — competes with the primary content (spend total) for attention.

---

**6. Good design is honest — Score: 2/3**
Evidence: 0 marketing superlatives, 0 dark patterns. Estimates labeled "≈" (Dashboard.svelte:183). One minor label mismatch: "POSTER ↓" implies immediate download; opens modal first (App.svelte:81, exportPoster handler).
Justification: ≤1 minor inflation/mismatch — the poster button label is the only divergence from 1:1 claim-to-behavior mapping.

---

**7. Good design is long-lasting — Score: 2/3**
Evidence: oklch color system and Space Grotesk are forward-looking choices. Bento grid dashboard layout is strongly associated with the 2024–2026 design trend wave; could date the product in 3 years.
Justification: 1 dated marker — the bento grid + all-caps monospace aesthetic is a specific current-moment trend; core data representations (tables, bar charts) are timeless.

---

**8. Good design is thorough down to the last detail — Score: 1/3**
Evidence: Focus ring missing from: Heatmap.svelte:66 (120 cells), ProviderDetail.svelte table headers (lines 79-83), App.svelte nav buttons (lines 63-67). Loading/error states missing from BurnGauge.svelte and Odometer.svelte. Odometer has no empty state.
Justification: 3+ states missing across primary interactive surfaces — Heatmap missing focus/disabled/loading/error (4 states), Odometer missing 5 of 6 states.

---

**9. Good design is environmentally friendly — Score: 2/3**
Evidence: Main bundle 34KB gzip (< 100KB ✓). prefers-reduced-motion honored (app.css:107-111 ✓). Playground lazy chunk: 1,034KB gzip (deferred, but large). 5 idle Odometer animations run continuously. WebSocket always-on on Dashboard.
Justification: <500KB initial load, motion gated — qualifies for 2; Playground lazy chunk is 1MB gzip which is heavy even deferred, and 5 persistent idle animations add unnecessary GPU work.

---

**10. Good design is as little design as possible — Score: 1/3**
Evidence: Dashboard contains 12+ simultaneous widget blocks. Key management duplicated verbatim in Settings.svelte:106-118 AND ProviderDetail.svelte:106-118 (not componentized). Hover-only "open →" (Dashboard.svelte:147) is a removable affordance (card is already clickable). REMOVE button appears 3 times across Settings without clear differentiation.
Justification: 5+ removable or consolidatable elements — the key management duplication, hover text redundancy, and triple REMOVE pattern are clear excess.

---

## Total: 16/30

| # | Principle | Score |
|---|-----------|-------|
| 1 | Innovative | 2 |
| 2 | Useful | 2 |
| 3 | Aesthetic | 2 |
| 4 | Understandable | 1 |
| 5 | Unobtrusive | 1 |
| 6 | Honest | 2 |
| 7 | Long-lasting | 2 |
| 8 | Thorough | 1 |
| 9 | Environmentally friendly | 2 |
| 10 | As little design as possible | 1 |
| | **TOTAL** | **16/30** |
