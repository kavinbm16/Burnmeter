# AI Providers Accordion + Guided Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pin the global footer to the viewport bottom (device-agnostic) and rebuild the AI Providers tab as accordion rows with a guided, copy-paste integration flow per provider.

**Architecture:** Two files change. `App.svelte` gets a flex-column shell so `<main>` absorbs slack and the footer sinks to the bottom. `Settings.svelte` gets a script tweak (language-tab + snippet state) and a providers-tab template rewrite from card-grid to full-width accordion rows with a Gemini 1-2-3 proxy guide. No backend changes.

**Tech Stack:** Svelte 5 (runes: `$state`, `$derived`), Tailwind v4, TypeScript. Verification: `cd frontend && npm run check` (svelte-check), then `npm run build`. No unit-test harness exists for the frontend; verification is type-check + build + manual smoke test.

---

## File Scope

| File | Change |
|------|--------|
| `frontend/src/App.svelte` | Root → flex column; `<main>` → `flex-1`. Footer pins to bottom. |
| `frontend/src/lib/views/Settings.svelte` | Script: add `proxyLang` + `snippetCopied` + `proxySnippet()`, remove `geminiProxyOpen`. Template: providers tab grid → accordion rows. |

No new files. No backend changes. Billing & GCP tab untouched.

---

## Task 1: Device-Agnostic Footer in App.svelte

**Files:**
- Modify: `frontend/src/App.svelte:49` (root div), `frontend/src/App.svelte:100` (`<main>`)

- [ ] **Step 1: Make the root a flex column**

Find this line (the root wrapper, line 49):

```svelte
<div class="mx-auto min-h-screen max-w-7xl px-6">
```

Replace with:

```svelte
<div class="mx-auto flex min-h-screen max-w-7xl flex-col px-6">
```

- [ ] **Step 2: Let `<main>` absorb the slack**

Find this line (line 100):

```svelte
  <main class="py-6">
```

Replace with:

```svelte
  <main class="flex-1 py-6">
```

The `<footer>` markup is unchanged — `flex-1` on main now pushes it to the viewport bottom on short pages.

- [ ] **Step 3: Verify TypeScript**

Run: `cd /Users/kavin/Projects/machanirobotics/burnmeter/frontend && npm run check`
Expected: 0 errors, 0 warnings.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.svelte
git commit -m "fix: pin footer to viewport bottom via flex-column shell"
```

---

## Task 2: Settings.svelte — Script: language tabs + snippet state

**Files:**
- Modify: `frontend/src/lib/views/Settings.svelte` (script block)

- [ ] **Step 1: Replace `geminiProxyOpen` with `proxyLang` + snippet copy state**

Find this line (line 8):

```svelte
  let geminiProxyOpen = $state(false)
```

Replace with:

```svelte
  let proxyLang = $state<'python' | 'node' | 'curl'>('python')
```

- [ ] **Step 2: Add `snippetCopied` next to the other copy states**

Find this block (lines 28-30):

```svelte
  // ── Copy states ──────────────────────────────────────────────────────
  let proxyCopied = $state(false)
  let cmdCopied = $state(false)
```

Replace with:

```svelte
  // ── Copy states ──────────────────────────────────────────────────────
  let proxyCopied = $state(false)
  let cmdCopied = $state(false)
  let snippetCopied = $state(false)
```

- [ ] **Step 3: Add the snippet builder and copy function**

Find the `copyProxy` function (lines 124-128):

```svelte
  function copyProxy() {
    navigator.clipboard.writeText(proxyUrl)
    proxyCopied = true
    setTimeout(() => (proxyCopied = false), 1500)
  }
```

Insert this immediately AFTER that function (before `copyCmd`):

```svelte
  function proxySnippet(lang: 'python' | 'node' | 'curl'): string {
    if (lang === 'node') {
      return `import { GoogleGenAI } from "@google/genai";

const ai = new GoogleGenAI({
  apiKey: "YOUR_KEY",
  httpOptions: { baseUrl: "${proxyUrl}" },
});`
    }
    if (lang === 'curl') {
      return `curl ${proxyUrl}/v1beta/models/gemini-2.0-flash:generateContent \\
  -H "x-goog-api-key: YOUR_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"contents":[{"parts":[{"text":"Hello"}]}]}'`
    }
    return `from google import genai

client = genai.Client(
    api_key="YOUR_KEY",
    http_options={"base_url": "${proxyUrl}"},
)`
  }

  function copySnippet() {
    navigator.clipboard.writeText(proxySnippet(proxyLang))
    snippetCopied = true
    setTimeout(() => (snippetCopied = false), 1500)
  }
```

- [ ] **Step 4: Verify TypeScript**

Run: `cd /Users/kavin/Projects/machanirobotics/burnmeter/frontend && npm run check`
Expected: 0 errors. (A warning that `proxyLang` / `copySnippet` / `snippetCopied` are unused is acceptable here — Task 3 wires them into the template. If `npm run check` treats unused as an error, proceed directly to Task 3 and re-run check there.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/views/Settings.svelte
git commit -m "refactor: Settings.svelte script — add proxyLang tabs + snippet builder"
```

---

## Task 3: Settings.svelte — AI Providers tab → accordion rows

**Files:**
- Modify: `frontend/src/lib/views/Settings.svelte` (providers tab template block)

- [ ] **Step 1: Replace the entire providers tab block**

Find the providers tab block. It starts with `{#if activeTab === 'providers'}` and the `{#if data}` immediately after, and ends at the `{:else}` line that begins the Billing & GCP tab (the line `<!-- Billing & GCP tab -->`). Replace everything from `{#if activeTab === 'providers'}` up to **but not including** `{:else}` / `<!-- Billing & GCP tab -->` with the block below.

```svelte
  {#if activeTab === 'providers'}
    {#if data}
      <!-- Provider accordion rows -->
      <div class="border border-hairline">
        {#each Object.entries(data.available) as [name, meta] (name)}
          {@const cfg = data.configured.find((c) => c.name === name)}
          <div class="border-b border-hairline last:border-b-0">
            <!-- Row header (click toggles) -->
            <button
              class="focus-ring flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-ink-2"
              onclick={() => selectProvider(name)}
            >
              <div>
                <div class="microlabel">{meta.display_name}</div>
                <div class="microlabel-dim mt-0.5">{meta.mode === 'proxy' ? 'local proxy' : 'usage api'}</div>
              </div>
              <div class="flex items-center gap-3">
                {#if cfg}
                  {#if cfg.sync_status === 'invalid_key' || cfg.sync_status === 'error'}
                    <span class="text-xs" style="color: var(--red)">▲ key error</span>
                  {:else}
                    <span class="flex items-center gap-2">
                      <span style="color: var(--red); font-size: 0.6rem;">●</span>
                      {#if cfg.last_synced_at}
                        <span class="microlabel-dim">synced {cfg.last_synced_at}Z</span>
                      {/if}
                    </span>
                  {/if}
                {:else}
                  <span class="microlabel-dim" style="color: var(--red);">connect →</span>
                {/if}
                <span class="microlabel-dim">{selectedProvider === name ? '▴' : '▾'}</span>
              </div>
            </button>

            <!-- Expanded body -->
            {#if selectedProvider === name}
              <div class="border-t border-hairline bg-ink-2 px-4 py-4">

                {#if meta.mode === 'proxy'}
                  <!-- Gemini-style guided 1-2-3 -->
                  {#if cfg}
                    <!-- Manage strip -->
                    <div class="mb-4 flex items-center gap-3 border-b border-hairline pb-3">
                      <span style="color: var(--red); font-size: 0.6rem;">●</span>
                      <code class="numeral text-xs">{cfg.masked_key}</code>
                      {#if cfg.last_synced_at}
                        <span class="microlabel-dim">· last sync {cfg.last_synced_at}Z</span>
                      {/if}
                      <div class="ml-auto flex gap-3">
                        <button class="focus-ring microlabel border border-hairline px-3 py-1 hover:border-red" onclick={() => api.sync()}>SYNC NOW</button>
                        <button class="focus-ring microlabel-dim hover:text-paper" onclick={() => remove(name)}>REMOVE</button>
                      </div>
                    </div>
                  {/if}

                  <!-- Step 1: add key (optional) -->
                  <div class="flex items-center gap-2">
                    <span class="microlabel shrink-0" style="background: var(--red); color: var(--ink); padding: 1px 6px;">1</span>
                    <span class="microlabel">ADD KEY (OPTIONAL)</span>
                  </div>
                  {#if !cfg}
                    <div class="mt-2 flex gap-px">
                      <input
                        type="password"
                        placeholder="AIza…"
                        bind:value={keyInput[name]}
                        class="numeral flex-1 border border-hairline bg-ink px-3 py-2 text-sm text-paper placeholder:text-muted/70 focus:border-red focus:outline-none"
                        onkeydown={(e) => e.key === 'Enter' && add(name)}
                      />
                      <button
                        class="focus-ring bg-red px-5 text-xs font-bold tracking-widest text-ink disabled:opacity-40"
                        disabled={busy === name || !(keyInput[name] ?? '').trim()}
                        onclick={() => add(name)}
                      >{busy === name ? '…' : 'ADD KEY'}</button>
                    </div>
                    <p class="microlabel-dim mt-1">or skip — pass your own key per request</p>
                    {#if errors[name]}
                      <p class="mt-2 text-sm" style="color: var(--red)">▲ {errors[name]}</p>
                    {/if}
                  {/if}

                  <!-- Step 2: point app at proxy -->
                  <div class="mt-5 flex items-center gap-2">
                    <span class="microlabel shrink-0" style="background: var(--red); color: var(--ink); padding: 1px 6px;">2</span>
                    <span class="microlabel">POINT YOUR APP AT THE PROXY</span>
                  </div>
                  <div class="mt-2 flex gap-px">
                    {#each ['python', 'node', 'curl'] as const as lang}
                      <button
                        class="focus-ring microlabel border border-hairline px-3 py-1.5 transition-colors hover:text-paper"
                        style={proxyLang === lang ? 'color: var(--paper); border-color: var(--red);' : ''}
                        onclick={() => (proxyLang = lang)}
                      >{lang === 'curl' ? 'cURL' : lang === 'node' ? 'NODE' : 'PYTHON'}</button>
                    {/each}
                  </div>
                  <div class="relative mt-2">
                    <button class="focus-ring microlabel-dim absolute right-2 top-2 hover:text-paper" onclick={copySnippet}>
                      {snippetCopied ? 'COPIED ✓' : 'COPY'}
                    </button>
                    <pre class="overflow-x-auto border border-hairline bg-ink px-3 py-2 text-xs" style="color: var(--muted)">{proxySnippet(proxyLang)}</pre>
                  </div>
                  <p class="microlabel-dim mt-2">Live / streaming? Use <code class="numeral">{liveProxyUrl}</code></p>

                  <!-- Step 3: run -->
                  <div class="mt-5 flex items-center gap-2">
                    <span class="microlabel shrink-0" style="background: var(--red); color: var(--ink); padding: 1px 6px;">3</span>
                    <span class="microlabel">RUN — USAGE COUNTS AUTOMATICALLY</span>
                  </div>
                  <p class="microlabel-dim mt-2">
                    {gcp?.configured
                      ? 'traffic via proxy is estimated — GCP billing reconciliation active ✓'
                      : 'costs are estimated — connect GCP billing for actual billed amounts'}
                  </p>

                {:else}
                  <!-- usage_api provider (OpenAI) -->
                  {#if cfg}
                    <div class="flex items-center gap-3">
                      <span style="color: var(--red); font-size: 0.6rem;">●</span>
                      <code class="numeral text-xs">{cfg.masked_key}</code>
                      {#if cfg.last_synced_at}
                        <span class="microlabel-dim">· last sync {cfg.last_synced_at}Z</span>
                      {/if}
                    </div>
                    {#if cfg.sync_status === 'invalid_key' || cfg.sync_status === 'error'}
                      <p class="mt-2 text-sm" style="color: var(--red)">▲ {cfg.sync_error ?? 'sync failed'}</p>
                    {/if}
                    <div class="mt-3 flex gap-3">
                      <button class="focus-ring microlabel border border-hairline px-3 py-1.5 hover:border-red" onclick={() => api.sync()}>SYNC NOW</button>
                      <button class="focus-ring microlabel-dim hover:text-paper" onclick={() => remove(name)}>REMOVE</button>
                    </div>
                  {:else}
                    <p class="mb-3 text-sm" style="color: var(--muted)">{meta.key_hint}</p>
                    <div class="microlabel mb-1">API KEY</div>
                    <div class="flex gap-px">
                      <input
                        type="password"
                        placeholder="sk-admin-…"
                        bind:value={keyInput[name]}
                        class="numeral flex-1 border border-hairline bg-ink px-3 py-2 text-sm text-paper placeholder:text-muted/70 focus:border-red focus:outline-none"
                        onkeydown={(e) => e.key === 'Enter' && add(name)}
                      />
                      <button
                        class="focus-ring bg-red px-5 text-xs font-bold tracking-widest text-ink disabled:opacity-40"
                        disabled={busy === name || !(keyInput[name] ?? '').trim()}
                        onclick={() => add(name)}
                      >{busy === name ? '…' : 'ADD KEY'}</button>
                    </div>
                    {#if errors[name]}
                      <p class="mt-2 text-sm" style="color: var(--red)">▲ {errors[name]}</p>
                    {/if}
                  {/if}
                {/if}

              </div>
            {/if}
          </div>
        {/each}

        <!-- Vertex AI read-only row -->
        {#if data.configured.find((c) => c.name === 'vertex_ai')}
          {@const vtx = data.configured.find((c) => c.name === 'vertex_ai')!}
          <div class="flex items-center justify-between border-b border-hairline px-4 py-3 last:border-b-0">
            <div>
              <div class="microlabel">Google Vertex AI</div>
              <div class="microlabel-dim mt-0.5">via GCP billing</div>
            </div>
            <span class="flex items-center gap-2">
              <span style="color: var(--red); font-size: 0.6rem;">●</span>
              {#if vtx.last_synced_at}
                <span class="microlabel-dim">synced {vtx.last_synced_at}Z</span>
              {/if}
            </span>
          </div>
        {/if}
      </div>

      <!-- Non-interactive add hint -->
      <div class="mt-px border border-dashed border-hairline px-4 py-3 text-center">
        <span class="microlabel-dim">+ ADD ANOTHER PROVIDER</span>
      </div>

    {:else}
      <div class="bento grid-cols-1"><div class="cell h-40 animate-pulse"></div></div>
    {/if}
```

Note: the closing `{:else}` and Billing & GCP tab that follow this block are unchanged — they stay exactly as they are in the current file.

- [ ] **Step 2: Verify TypeScript**

Run: `cd /Users/kavin/Projects/machanirobotics/burnmeter/frontend && npm run check`
Expected: 0 errors, 0 warnings.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/views/Settings.svelte
git commit -m "feat: AI Providers tab — accordion rows + guided proxy integration"
```

---

## Task 4: Build Verification

**Files:** None — verification only.

- [ ] **Step 1: Full build**

Run: `cd /Users/kavin/Projects/machanirobotics/burnmeter/frontend && npm run build`
Expected: build succeeds. The gpt-tokenizer chunk-size warning (>500 kB on `Playground`) is pre-existing and acceptable — not a failure.

- [ ] **Step 2: Manual smoke-test**

Run: `cd /Users/kavin/Projects/machanirobotics/burnmeter/frontend && npm run dev`

| Check | Expected |
|------|---------|
| Short Providers page | Footer sits at viewport bottom, no mid-page float. |
| Tall page (Dashboard with data) | Footer flows below content normally. |
| AI Providers tab | Provider rows stacked full-width inside one bordered container. |
| Collapsed row | Name + mode label left; status (`● synced` / red `connect →` / red `▲ key error`) + chevron right. |
| Click OpenAI row | Expands. Unconfigured: key hint + API KEY input + ADD KEY. Configured: masked key + SYNC NOW + REMOVE. |
| Click Gemini row | Expands to 1-2-3 guide. Step 2 has PYTHON/NODE/cURL tabs; switching tabs swaps the snippet; COPY copies it. Live proxy URL shown. |
| Click expanded row again | Collapses. |
| Vertex AI row (if GCP connected) | Read-only, no chevron, no expand. |
| `+ ADD ANOTHER PROVIDER` | Dashed, non-interactive. |
| Billing & GCP tab | Unchanged from prior redesign. |

---

## Self-Review

| Spec requirement | Task |
|-----------------|------|
| Footer pinned bottom, device-agnostic (flex-col + flex-1) | Task 1 |
| Accordion rows replace grid | Task 3 |
| Collapsed row: name / mode / status states | Task 3 |
| Vertex read-only row | Task 3 |
| Non-interactive add hint | Task 3 |
| OpenAI connect + manage | Task 3 (usage_api branch) |
| Gemini guided 1-2-3 | Task 3 (proxy branch) |
| Optional key + passthrough note | Task 3 (step 1) |
| Language tabs Python/Node/cURL + copy | Task 2 (state/builder) + Task 3 (step 2) |
| Live proxy URL in snippets + WebSocket note | Task 2 (`proxySnippet`) + Task 3 (step 2) |
| Reconciliation note | Task 3 (step 3) |
| `proxyLang` added, `geminiProxyOpen` removed | Task 2 |
| No backend changes | All — confirmed |

**Type consistency:** `proxyLang` (`'python'|'node'|'curl'`) defined in Task 2, consumed in Task 3 tabs/snippet. `proxySnippet(lang)` and `copySnippet()` defined in Task 2, called in Task 3. `snippetCopied` defined in Task 2, read in Task 3. `selectProvider`, `add`, `remove`, `keyInput`, `busy`, `errors`, `gcp`, `liveProxyUrl` all pre-existing in the current script — unchanged. No mismatches found.

**Placeholder scan:** No TBD/TODO/"handle edge cases" — all steps contain literal code. No gaps.
