---
name: scope
description: Audit scope for burnmeter UX/UI design-is review
metadata:
  type: project
---

# Scope

**Product:** Burnmeter — local-first LLM token & cost dashboard

**Surfaces audited:**
- Dashboard (`src/lib/views/Dashboard.svelte`)
- Settings (`src/lib/views/Settings.svelte`)
- ProviderDetail (`src/lib/views/ProviderDetail.svelte`)
- Playground / Tokenizer (`src/lib/views/Playground.svelte`)
- Shared components: BurnGauge, Heatmap, Odometer, BarStrip, Leaderboard, LiveTicker, Poster
- Global chrome: `App.svelte`, `app.css`

**Primary user:** Developer/engineer using OpenAI or Gemini APIs who wants to track and control LLM spend.

**Primary task:** View aggregate LLM spend for a period, drill into per-provider / per-model breakdown, and configure budget.

**Stack:** Svelte + TypeScript (Vite), FastAPI Python backend, Tailwind v4, oklch color system, Space Grotesk font.

**Constraints:** Local-first (keys never leave machine), dark theme, no backend DB for keys.

**Reference designs:** None specified. Comparable products: Usage.ai, OpenAI billing dashboard, Helicone.

**Date:** 2026-06-12
