# Verdict

## REDESIGN

**Score 16/30 falls below the REFINE threshold (20), triggering REDESIGN.**

The design's color system, honesty, and core data model are strong foundations — but the Dashboard overloads every visit with 12+ simultaneous widget blocks, jargon fills every view, focus accessibility is broken across the primary interactive surface (120 heatmap cells), and key management is copy-pasted rather than componentized. The bones of the data model are sound; the information architecture and surface density need to be rebuilt from purpose.

---

## Top 5 Highest-Leverage Moves

**1. #4 Understandable — Demystify 7 jargon labels across all 4 views.**
Every view contains at least 1 term that requires domain expertise: "MTD" (App.svelte:77), "AUD IN/OUT" (ProviderDetail.svelte:74-75), "o200k_base" (Playground.svelte:52), "Ground-truth cost" (Settings.svelte:156), "proxy-captured traffic" (ProviderDetail.svelte:115), "Burn" (BurnGauge.svelte:41), "POSTER ↓" mismatch (App.svelte:81).

**2. #5 Unobtrusive + #10 As little design as possible — Reduce Dashboard to a primary view and secondary detail.**
Dashboard currently surfaces BurnGauge + 3 Odometers + BarStrip + 6+ provider cards + 120-cell Heatmap + Leaderboard + LiveTicker simultaneously. Redesign: primary view = spend total + single period bar + provider list. Secondary view = heatmap + leaderboard on demand (tab or scroll section), not competing on the same screen.

**3. #8 Thorough — Add focus rings to all 120 Heatmap cells and the App nav bar.**
Heatmap.svelte:66 has `hover:scale-125` but no `:focus-visible` ring. App.svelte:63-67 nav buttons have no focus styling. ProviderDetail.svelte:79-83 sort headers have no focus state. This breaks keyboard navigation entirely.

**4. #10 As little design as possible — Componentize the duplicated key management UI.**
Settings.svelte:106-118 and ProviderDetail.svelte:106-118 are identical key-input+button+error blocks. Extract to a `<KeyInput>` component. This will also surface whether Settings and ProviderDetail should remain separate views or merge.

**5. #2 Useful — Make the provider drilldown affordance always visible.**
Dashboard.svelte:147 "open →" text is hover-only. The whole card is clickable but nothing signals this until hover. Replace with a persistent `›` icon or arrow that stays visible, especially critical on touch/keyboard.
