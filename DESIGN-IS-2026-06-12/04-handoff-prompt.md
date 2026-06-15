# Handoff Prompt

Copy-paste this into `/make-plan` to begin the redesign:

---

```
/make-plan Redesign burnmeter's Dashboard view and shared chrome. Current design scored 16/30 on a Dieter Rams audit with critical gaps in principles #4 (understandable: 1/3), #5 (unobtrusive: 1/3), #8 (thorough: 1/3), and #10 (as little design as possible: 1/3).

Verdict paragraph (from audit 03-verdict.md):
> The design's color system, honesty, and core data model are strong foundations — but the Dashboard overloads every visit with 12+ simultaneous widget blocks, jargon fills every view, focus accessibility is broken across the primary interactive surface (120 heatmap cells), and key management is copy-pasted rather than componentized. The bones of the data model are sound; the information architecture and surface density need to be rebuilt from purpose.

Why redesign and not refine: Total score 16/30 < 20 threshold; principles #4 (understandable), #5 (unobtrusive), and #10 (as little design as possible) all scored 1/3, meaning multiple load-bearing UX dimensions are simultaneously degraded, not just one isolated issue.

Preserve from current design:
- oklch color token system (--ink, --ink-2, --paper, --muted, --hairline, --red, --red-dim, --heat-1..4) in app.css:1-60 — scored well on aesthetic (#3: 2/3) and honesty (#6: 2/3)
- Space Grotesk font and 116% root font-size system (app.css:30-40)
- prefers-reduced-motion override (app.css:107-111) — accessibility win
- Odometer digit scroll mechanic (Odometer.svelte:14, 500ms ease-out) — the one animation that earns its place
- LiveTicker WebSocket architecture (LiveTicker.svelte:22-55) — keep the data connection; revisit where it surfaces
- All API endpoints and data model (api.ts — no changes to backend)
- Honest copy conventions: ≈ prefix for estimates, Z suffix timestamps, masked key display

Discard:
- Simultaneously-visible widget stack on Dashboard (BurnGauge + 3 Odometers + BarStrip + 6+ provider cards + Heatmap + Leaderboard + LiveTicker all on one scroll). Caused failure on #5 (unobtrusive) and #10 (as little design as possible).
- Hover-only "open →" affordance on provider cards (Dashboard.svelte:147). Caused failure on #2 (useful).
- Duplicated key management block in both Settings.svelte:106-118 and ProviderDetail.svelte:106-118. Caused failure on #10 (as little design as possible).
- All 7 jargon labels: "MTD", "AUD IN/OUT", "o200k_base", "Ground-truth cost", "proxy-captured traffic", "Burn", "POSTER ↓" (see evidence anchors below). Caused failure on #4 (understandable).

Top 5 moves from the audit (implement in priority order):

1. #4 Understandable: Replace all 7 jargon labels with plain language.
   - "MTD" → "This month" (App.svelte:77)
   - "AUD IN" / "AUD OUT" → "Audio In" / "Audio Out" (ProviderDetail.svelte:74-75)
   - "o200k_base" → "OpenAI token encoding" (Playground.svelte:52)
   - "Ground-truth cost" → "Actual billed cost" (Settings.svelte:156)
   - "proxy-captured traffic" → "traffic via local proxy" (ProviderDetail.svelte:115)
   - "Burn" → "Spending pace" (BurnGauge.svelte:41)
   - "POSTER ↓" → "EXPORT POSTER" and update button to open modal explicitly (App.svelte:81)

2. #5 Unobtrusive + #10 As little design as possible: Redesign Dashboard information architecture.
   - Primary view: spend total (Odometer, one) + period selector + provider list (cards with always-visible › icon).
   - Secondary section (collapsed by default or tab-switched): Heatmap + Leaderboard + LiveTicker.
   - BarStrip bar chart: keep as the primary visual between spend total and provider list.
   - BurnGauge: keep inline with spend total (it earns its place as the budget context).
   - Remove 2 of the 3 satellite Odometers (Input tokens, Output tokens, Requests) from primary view — surface in ProviderDetail drilldown instead.

3. #8 Thorough: Add focus-visible rings to all interactive elements missing them.
   - Heatmap.svelte:66 — add `:focus-visible` ring (currently only hover:scale-125, no focus style)
   - App.svelte:63-67 — nav buttons need focus ring
   - ProviderDetail.svelte:79-83 — sort header buttons need focus ring
   - BurnGauge.svelte: add loading skeleton and error state (currently MISSING per evidence)
   - Verify: run Tab key through entire Dashboard, Settings, ProviderDetail flows.

4. #10 As little design as possible: Extract shared KeyInput component.
   - Create src/lib/components/KeyInput.svelte
   - Replace Settings.svelte:106-118 and ProviderDetail.svelte:106-118 with <KeyInput>
   - Simultaneously evaluate: does ProviderDetail need to exist as a separate route, or can its key management live entirely in Settings with a provider-scoped accordion?

5. #2 Useful: Make provider drilldown affordance always visible.
   - Dashboard.svelte:142-148 — replace hover-only "open →" text with a persistent small arrow icon (›) that's always visible in the card's right edge
   - Ensure the entire card has role="button" and keyboard activation (currently has onkeydown but focus state is missing)

Redesign principles in priority order:
1. #4 Understandable — every label must be interpretable by a developer who has never used a cost dashboard
2. #5 Unobtrusive — primary task (see total spend) must complete in <3 seconds without visual noise
3. #10 As little design as possible — every UI element on the primary view must have a reason; secondary features get secondary placement

Deliverables for the plan:
- New Dashboard information architecture (primary view vs. secondary/progressive-disclosure)
- Plain-language copy replacement list (all 7 jargon fixes, one file each with line numbers)
- Focus ring implementation spec (which CSS class, which Tailwind variant, test procedure)
- KeyInput component extraction (interface, file path, migration of 2 call sites)
- Drilldown affordance fix (Dashboard.svelte:142-148, persistent icon spec)
- States checklist completion: BurnGauge loading/error, Heatmap loading/error/focus/disabled

Anti-patterns to guard against:
- Porting the current 12-widget simultaneous layout under new styling — this is the root cause of #5 and #10 failures
- Keeping both old and new Dashboard behind a feature flag indefinitely
- Treating the Preserve list as optional — the color system and typography are NOT being redesigned
- Redesigning to follow a different trend (e.g., switching to a light theme or card-heavy layout) — the redesign should follow the principles above, not aesthetic fashion
```
