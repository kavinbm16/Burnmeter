# Providers Page & Nav Bar Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the app header into two rows and replace the clutter-stack providers page with a tabbed layout (AI Providers / Billing & GCP) featuring a provider card grid and slide-in detail panel.

**Architecture:** Two files change — `App.svelte` gets a two-row header, `Settings.svelte` gets a full layout rewrite with inner tab state, bento provider grid, and a detail panel that opens below the grid. No backend changes.

**Tech Stack:** Svelte 5 (runes: `$state`, `$derived`), Tailwind v4, TypeScript. Verification: `cd frontend && npm run check` (svelte-check) then `npm run build`.

---

## File Scope

| File | Change |
|------|--------|
| `frontend/src/App.svelte` | Restructure `<header>` into three rows; move period/export to row 2, SYNC to row 1 |
| `frontend/src/lib/views/Settings.svelte` | Full rewrite — inner tabs, provider grid, detail panel, stepped GCP setup |

No new files. No backend changes. No CSS changes.

---

## Task 1: Two-Row Header in App.svelte

**Files:**
- Modify: `frontend/src/App.svelte:49-94`

- [ ] **Step 1: Replace the `<header>` block**

The current header is a single `<div class="flex items-center gap-8 py-4">` row with everything jammed in. Replace lines 49–94 (the entire `<header>` element) with the three-row structure below.

```svelte
<header class="sticky top-0 z-10 backdrop-blur" style="background: color-mix(in oklch, var(--ink) 88%, transparent);">
  <!-- Row 1: brand + global sync -->
  <div class="flex items-center justify-between px-0 py-3 border-b border-hairline">
    <button
      class="focus-ring text-lg font-bold"
      style="letter-spacing: 0.25em;"
      onclick={() => { tab = 'dashboard'; detailProvider = null }}
    >
      BURNMETER<span style="color: var(--red)">®</span>
    </button>
    <button
      class="focus-ring microlabel border border-hairline px-3 py-1.5 transition-colors hover:border-red disabled:opacity-40"
      onclick={syncNow}
      disabled={syncing}
    >{syncing ? 'SYNCING…' : 'SYNC'}</button>
  </div>

  <!-- Row 2: tabs + view-specific actions -->
  <div class="flex items-center border-b border-hairline">
    <nav class="flex">
      {#each NAV as n (n.id)}
        <button
          class="focus-ring microlabel-dim px-5 py-2.5 transition-colors hover:text-paper"
          style={tab === n.id ? 'color: var(--paper); border-bottom: 1px solid var(--red);' : ''}
          onclick={() => { tab = n.id; detailProvider = null }}
        >{n.label}</button>
      {/each}
    </nav>
    {#if tab === 'dashboard'}
      <div class="ml-auto flex items-center gap-4">
        <select
          bind:value={period}
          class="microlabel-dim cursor-pointer border border-hairline bg-ink px-2 py-1.5 focus:border-red focus:outline-none"
        >
          <option value="mtd">This month</option>
          <option value="30d">30D</option>
          <option value="90d">90D</option>
        </select>
        <button class="focus-ring microlabel-dim hover:text-paper" onclick={exportPoster}>EXPORT POSTER</button>
      </div>
    {/if}
  </div>

  <!-- Row 3: live ticker (unchanged) -->
  <div class="flex items-center py-2 border-b border-hairline">
    <LiveTicker onevent={onLiveEvent} />
  </div>
</header>
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd /Users/kavin/Projects/machanirobotics/burnmeter/frontend && npm run check
```

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.svelte
git commit -m "feat: two-row header — brand+sync row 1, tabs+actions row 2"
```

---

## Task 2: Settings.svelte — Script Rewrite

**Files:**
- Modify: `frontend/src/lib/views/Settings.svelte` (entire `<script>` block, lines 1–127)

The existing script has all the right logic. Add `activeTab`, `selectedProvider`, and `geminiProxyOpen` state; add `selectProvider` helper; update `add()` and `remove()` to clear `selectedProvider` on success.

- [ ] **Step 1: Replace the entire `<script lang="ts">` block**

```svelte
<script lang="ts">
  import { api } from '$lib/api'
  import type { GCPStatus, ProvidersResponse } from '$lib/api'

  // ── Tab + selection state ────────────────────────────────────────────
  let activeTab = $state<'providers' | 'billing'>('providers')
  let selectedProvider = $state<string | null>(null)
  let geminiProxyOpen = $state(false)

  // ── Provider state ───────────────────────────────────────────────────
  let data = $state<ProvidersResponse | null>(null)
  let keyInput = $state<Record<string, string>>({})
  let busy = $state<string | null>(null)
  let errors = $state<Record<string, string>>({})

  // ── GCP state ────────────────────────────────────────────────────────
  let gcp = $state<GCPStatus | null>(null)
  let gcpCreds = $state('')
  let gcpProjectId = $state<string | null>(null)
  let gcpTables = $state<string[]>([])
  let gcpSelectedTable = $state('')
  let gcpLogsTable = $state('')
  let gcpShowLogs = $state(false)
  let gcpValidating = $state(false)
  let gcpConnecting = $state(false)
  let gcpError = $state('')

  // ── Copy states ──────────────────────────────────────────────────────
  let proxyCopied = $state(false)
  let cmdCopied = $state(false)

  const SERVICE_ACCOUNT_CMD = `gcloud iam service-accounts create burnmeter-reader \\
  --display-name="Burnmeter read-only" --project=PROJECT_ID && \\
gcloud projects add-iam-policy-binding PROJECT_ID \\
  --member="serviceAccount:burnmeter-reader@PROJECT_ID.iam.gserviceaccount.com" \\
  --role="roles/bigquery.dataViewer" && \\
gcloud projects add-iam-policy-binding PROJECT_ID \\
  --member="serviceAccount:burnmeter-reader@PROJECT_ID.iam.gserviceaccount.com" \\
  --role="roles/bigquery.jobUser" && \\
gcloud iam service-accounts keys create burnmeter-key.json \\
  --iam-account="burnmeter-reader@PROJECT_ID.iam.gserviceaccount.com"`

  const proxyUrl = `${location.protocol}//${location.hostname}:8400/proxy/gemini`
  const liveProxyUrl = `ws://${location.hostname}:8400/proxy/gemini`

  api.gcpStatus().then((s) => (gcp = s))

  async function load() {
    data = await api.providers()
  }
  load()

  function extractProjectId(json: string) {
    try {
      const info = JSON.parse(json)
      gcpProjectId = info.project_id ?? null
    } catch {
      gcpProjectId = null
    }
  }

  async function validateAndFetchTables() {
    gcpError = ''
    gcpTables = []
    gcpSelectedTable = ''
    gcpValidating = true
    try {
      const res = await api.gcpTables(gcpCreds)
      gcpTables = res.tables
      if (gcpTables.length === 1) gcpSelectedTable = gcpTables[0]
    } catch (e: any) {
      gcpError = e.message
    } finally {
      gcpValidating = false
    }
  }

  async function connectGCP() {
    gcpError = ''
    gcpConnecting = true
    try {
      await api.gcpConnect(gcpCreds, gcpSelectedTable, gcpShowLogs ? gcpLogsTable : undefined)
      gcpCreds = ''
      gcp = await api.gcpStatus()
    } catch (e: any) {
      gcpError = e.message
    } finally {
      gcpConnecting = false
    }
  }

  async function disconnectGCP() {
    if (!confirm('Remove GCP connection? Billing and Vertex AI sync will stop.')) return
    await api.gcpDisconnect()
    gcp = await api.gcpStatus()
    gcpCreds = ''
    gcpTables = []
    gcpSelectedTable = ''
    await load()
  }

  async function add(name: string) {
    busy = name
    errors = { ...errors, [name]: '' }
    try {
      await api.addProvider(name, keyInput[name] ?? '')
      keyInput = { ...keyInput, [name]: '' }
      selectedProvider = null
      await load()
    } catch (e: any) {
      errors = { ...errors, [name]: e.message }
    } finally {
      busy = null
    }
  }

  async function remove(name: string) {
    if (!confirm(`Remove ${name}? Its stored key and local usage history will be deleted.`)) return
    await api.removeProvider(name)
    selectedProvider = null
    await load()
  }

  function copyProxy() {
    navigator.clipboard.writeText(proxyUrl)
    proxyCopied = true
    setTimeout(() => (proxyCopied = false), 1500)
  }

  function copyCmd() {
    navigator.clipboard.writeText(SERVICE_ACCOUNT_CMD)
    cmdCopied = true
    setTimeout(() => (cmdCopied = false), 1500)
  }

  function selectProvider(name: string) {
    selectedProvider = selectedProvider === name ? null : name
    errors = { ...errors, [name]: '' }
  }
</script>
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd /Users/kavin/Projects/machanirobotics/burnmeter/frontend && npm run check
```

Expected: 0 errors. (Template is unchanged so far — only script changed.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/views/Settings.svelte
git commit -m "refactor: Settings.svelte script — add activeTab, selectedProvider state"
```

---

## Task 3: Settings.svelte — Outer Shell + Inner Tabs

**Files:**
- Modify: `frontend/src/lib/views/Settings.svelte` (template block, replace everything after `</script>`)

Replace the entire template (everything from `<div class="mx-auto max-w-3xl">` to end of file) with the shell below. Provider grid and GCP content are stubs — filled in Tasks 4 and 5.

- [ ] **Step 1: Replace the template with the tabbed shell**

```svelte
<div class="mx-auto max-w-3xl">

  <!-- Inner tab bar -->
  <div class="flex border-b border-hairline mb-6">
    <button
      class="focus-ring microlabel-dim px-5 py-2.5 transition-colors hover:text-paper"
      style={activeTab === 'providers' ? 'color: var(--paper); border-bottom: 1px solid var(--red);' : ''}
      onclick={() => { activeTab = 'providers'; selectedProvider = null }}
    >AI PROVIDERS</button>
    <button
      class="focus-ring microlabel-dim px-5 py-2.5 transition-colors hover:text-paper"
      style={activeTab === 'billing' ? 'color: var(--paper); border-bottom: 1px solid var(--red);' : ''}
      onclick={() => { activeTab = 'billing'; selectedProvider = null }}
    >BILLING &amp; GCP</button>
  </div>

  {#if activeTab === 'providers'}
    <!-- AI Providers tab — content added in Task 4 -->
    <div class="cell h-40 animate-pulse"></div>
  {:else}
    <!-- Billing & GCP tab — content added in Task 5 -->
    <div class="cell h-40 animate-pulse"></div>
  {/if}

  <!-- Footer: key custody notice -->
  <p class="mt-8 microlabel-dim">
    Keys stored in OS keychain — never in database or logs —
    <a class="underline hover:text-paper" href="https://github.com/kavinbm16/burnmeter/blob/master/SECURITY.md" target="_blank" rel="noreferrer">audit the guarantees</a>
  </p>

</div>
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd /Users/kavin/Projects/machanirobotics/burnmeter/frontend && npm run check
```

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/views/Settings.svelte
git commit -m "feat: Settings.svelte — inner tabs shell (AI Providers / Billing & GCP)"
```

---

## Task 4: AI Providers Tab — Grid + Detail Panel

**Files:**
- Modify: `frontend/src/lib/views/Settings.svelte` — replace the providers tab stub

- [ ] **Step 1: Replace the providers tab stub with the full grid + panel**

Find this block in the template:

```svelte
  {#if activeTab === 'providers'}
    <!-- AI Providers tab — content added in Task 4 -->
    <div class="cell h-40 animate-pulse"></div>
```

Replace it with:

```svelte
  {#if activeTab === 'providers'}
    {#if data}
      <!-- Provider card grid -->
      <div class="bento" style="grid-template-columns: repeat(3, 1fr);">
        {#each Object.entries(data.available) as [name, meta] (name)}
          {@const cfg = data.configured.find((c) => c.name === name)}
          <button
            class="cell focus-ring text-left transition-colors hover:bg-ink-2"
            style={selectedProvider === name ? 'outline: 1px solid var(--red); outline-offset: -1px;' : ''}
            onclick={() => selectProvider(name)}
          >
            <div class="microlabel">{meta.display_name}</div>
            <div class="microlabel-dim mt-1">{meta.mode === 'proxy' ? 'local proxy' : 'usage api'}</div>
            {#if cfg}
              <div class="mt-3 flex items-center gap-2">
                <span style="color: var(--red); font-size: 0.6rem;">●</span>
                <span class="numeral text-xs" style="color: var(--muted);">{cfg.masked_key}</span>
              </div>
              {#if cfg.sync_status === 'invalid_key' || cfg.sync_status === 'error'}
                <div class="mt-1 text-xs" style="color: var(--red)">▲ key error</div>
              {:else if cfg.last_synced_at}
                <div class="microlabel-dim mt-2">synced {cfg.last_synced_at}Z</div>
              {/if}
            {:else}
              <div class="mt-3">
                <span class="microlabel-dim" style="color: var(--red);">CONNECT →</span>
              </div>
            {/if}
          </button>
        {/each}

        <!-- Vertex AI auto-card (read-only, no click) -->
        {#if data.configured.find((c) => c.name === 'vertex_ai')}
          {@const vtx = data.configured.find((c) => c.name === 'vertex_ai')!}
          <div class="cell">
            <div class="microlabel">Google Vertex AI</div>
            <div class="microlabel-dim mt-1">billing export</div>
            <div class="mt-3 flex items-center gap-2">
              <span style="color: var(--red); font-size: 0.6rem;">●</span>
              <span class="microlabel-dim">via GCP billing</span>
            </div>
            {#if vtx.last_synced_at}
              <div class="microlabel-dim mt-2">synced {vtx.last_synced_at}Z</div>
            {/if}
          </div>
        {/if}
      </div>

      <!-- Non-interactive add hint -->
      <div class="mt-px border border-dashed border-hairline px-4 py-3 text-center">
        <span class="microlabel-dim">+ ADD ANOTHER PROVIDER</span>
      </div>

      <!-- Detail panel — appears when a provider card is selected -->
      {#if selectedProvider && data.available[selectedProvider]}
        {@const meta = data.available[selectedProvider]}
        {@const cfg = data.configured.find((c) => c.name === selectedProvider)}
        <div class="mt-1 border border-red bg-ink-2 p-5">
          <div class="flex items-center justify-between mb-4">
            <span class="microlabel">{cfg ? 'MANAGE' : 'CONNECT'} {meta.display_name}</span>
            <button
              class="focus-ring microlabel-dim hover:text-paper"
              onclick={() => (selectedProvider = null)}
            >✕</button>
          </div>

          {#if cfg}
            <!-- Manage mode -->
            <div class="flex items-center gap-2">
              <span style="color: var(--red); font-size: 0.6rem;">●</span>
              <code class="numeral text-xs">{cfg.masked_key}</code>
            </div>
            {#if cfg.last_synced_at}
              <div class="microlabel-dim mt-1">Last sync {cfg.last_synced_at}Z</div>
            {/if}
            {#if cfg.sync_status === 'invalid_key' || cfg.sync_status === 'error'}
              <p class="mt-2 text-sm" style="color: var(--red)">▲ {cfg.sync_error ?? 'sync failed'}</p>
            {/if}
            <div class="mt-4 flex gap-3">
              <button
                class="focus-ring microlabel border border-hairline px-3 py-1.5 hover:border-red"
                onclick={() => api.sync()}
              >SYNC NOW</button>
              <button
                class="focus-ring microlabel-dim hover:text-paper"
                onclick={() => remove(selectedProvider!)}
              >REMOVE</button>
            </div>

            <!-- Gemini proxy endpoints (toggle) -->
            {#if selectedProvider === 'gemini'}
              <div class="mt-5 border-t border-hairline pt-4">
                <button
                  class="focus-ring microlabel-dim hover:text-paper"
                  onclick={() => (geminiProxyOpen = !geminiProxyOpen)}
                >▸ Proxy endpoints</button>
                {#if geminiProxyOpen}
                  <div class="mt-3 space-y-3">
                    <div>
                      <div class="flex items-center justify-between">
                        <span class="microlabel">HTTP endpoint</span>
                        <button class="focus-ring microlabel-dim hover:text-paper" onclick={copyProxy}>
                          {proxyCopied ? 'COPIED ✓' : 'COPY'}
                        </button>
                      </div>
                      <code class="numeral mt-1 block truncate text-xs">{proxyUrl}</code>
                      <pre class="mt-2 overflow-x-auto text-xs" style="color: var(--muted)">{`client = genai.Client(
    api_key=...,
    http_options={"base_url": "${proxyUrl}"},
)`}</pre>
                    </div>
                    <div>
                      <span class="microlabel">WebSocket endpoint</span>
                      <code class="numeral mt-1 block truncate text-xs">{liveProxyUrl}</code>
                    </div>
                    <p class="microlabel-dim">
                      {gcp?.configured
                        ? 'traffic via proxy is estimated — GCP billing reconciliation active ✓'
                        : 'costs are estimated — connect GCP billing for actual billed amounts'}
                    </p>
                  </div>
                {/if}
              </div>
            {/if}

          {:else}
            <!-- Connect mode -->
            <p class="mb-4 text-sm" style="color: var(--muted)">{meta.key_hint}</p>
            <div class="microlabel mb-1">API KEY</div>
            <div class="flex gap-px">
              <input
                type="password"
                placeholder={selectedProvider === 'openai' ? 'sk-admin-…' : selectedProvider === 'gemini' ? 'AIza…' : '…'}
                bind:value={keyInput[selectedProvider]}
                class="numeral flex-1 border border-hairline bg-ink px-3 py-2 text-sm text-paper
                       placeholder:text-muted/70 focus:border-red focus:outline-none"
                onkeydown={(e) => e.key === 'Enter' && add(selectedProvider!)}
              />
              <button
                class="focus-ring bg-red px-5 text-xs font-bold tracking-widest text-ink disabled:opacity-40"
                disabled={busy === selectedProvider || !(keyInput[selectedProvider] ?? '').trim()}
                onclick={() => add(selectedProvider!)}
              >{busy === selectedProvider ? '…' : 'ADD KEY'}</button>
            </div>
            {#if errors[selectedProvider]}
              <p class="mt-2 text-sm" style="color: var(--red)">▲ {errors[selectedProvider]}</p>
            {/if}
          {/if}
        </div>
      {/if}

    {:else}
      <div class="bento grid-cols-1"><div class="cell h-40 animate-pulse"></div></div>
    {/if}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd /Users/kavin/Projects/machanirobotics/burnmeter/frontend && npm run check
```

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/views/Settings.svelte
git commit -m "feat: Settings.svelte — provider grid + slide-in detail panel"
```

---

## Task 5: Billing & GCP Tab

**Files:**
- Modify: `frontend/src/lib/views/Settings.svelte` — replace the billing tab stub

- [ ] **Step 1: Replace the billing tab stub**

Find this block:

```svelte
  {:else}
    <!-- Billing & GCP tab — content added in Task 5 -->
    <div class="cell h-40 animate-pulse"></div>
  {/if}
```

Replace it with:

```svelte
  {:else}
    <!-- Billing & GCP tab -->
    <div>
      <div class="flex items-baseline gap-3 mb-5">
        <h2 class="text-sm font-bold uppercase tracking-widest">Google Cloud Platform</h2>
        <span class="microlabel-dim">billing export · vertex ai</span>
        {#if gcp?.configured}
          <span class="numeral ml-auto text-xs" style="color: var(--red)">● {gcp.project_id}</span>
          <button class="focus-ring microlabel-dim hover:text-paper" onclick={disconnectGCP}>REMOVE</button>
        {/if}
      </div>

      {#if gcp?.configured}
        <!-- Connected status card -->
        <div class="bento grid-cols-1">
          <div class="cell">
            <div class="grid grid-cols-2 gap-6 text-xs" style="color: var(--muted)">
              <div>
                <span class="microlabel">Billing export</span>
                <p class="mt-1 numeral">
                  {gcp.billing_sync?.status === 'ok' ? '✓' : gcp.billing_sync?.status ?? '—'}
                  {#if gcp.billing_sync?.last_synced_at}
                    · {gcp.billing_sync.last_synced_at.slice(0, 16)}Z
                  {/if}
                </p>
                {#if gcp.billing_sync?.error}
                  <p class="mt-1" style="color: var(--red)">▲ {gcp.billing_sync.error}</p>
                {/if}
              </div>
              {#if gcp.logs_table}
                <div>
                  <span class="microlabel">Vertex AI logs</span>
                  <p class="mt-1 numeral">
                    {gcp.logs_sync?.status === 'ok' ? '✓' : gcp.logs_sync?.status ?? '—'}
                    {#if gcp.logs_sync?.last_synced_at}
                      · {gcp.logs_sync.last_synced_at.slice(0, 16)}Z
                    {/if}
                  </p>
                  {#if gcp.logs_sync?.error}
                    <p class="mt-1" style="color: var(--red)">▲ {gcp.logs_sync.error}</p>
                  {/if}
                </div>
              {/if}
            </div>
            <p class="microlabel-dim mt-4">Billing table: <code class="numeral text-xs">{gcp.billing_table}</code></p>
            <button
              class="focus-ring mt-3 border border-hairline px-3 py-1 text-xs tracking-widest hover:text-paper"
              onclick={() => api.gcpSync()}
            >SYNC NOW</button>
          </div>
        </div>

      {:else}
        <!-- Setup flow — stepped list -->
        <p class="mb-5 text-sm" style="color: var(--muted)">
          One service account connects Gemini API billing reconciliation and Vertex AI cost tracking.
        </p>
        <div class="bento grid-cols-1">

          <!-- Step 1: create service account -->
          <div class="cell flex items-start gap-4">
            <span class="microlabel mt-0.5 shrink-0" style="background: var(--red); color: var(--ink); padding: 1px 6px;">1</span>
            <div class="flex-1 min-w-0">
              <div class="microlabel-dim">CREATE SERVICE ACCOUNT</div>
              <p class="mt-1 text-xs" style="color: var(--muted)">Replace PROJECT_ID with your GCP project. Run in your terminal.</p>
            </div>
            <button class="focus-ring microlabel-dim hover:text-paper shrink-0" onclick={copyCmd}>
              {cmdCopied ? 'COPIED ✓' : 'COPY COMMAND'}
            </button>
          </div>

          <!-- Step 2: paste JSON -->
          <div class="cell">
            <div class="flex items-center gap-4 mb-3">
              <span class="microlabel shrink-0" style="background: var(--red); color: var(--ink); padding: 1px 6px;">2</span>
              <div class="microlabel-dim">PASTE SERVICE ACCOUNT JSON</div>
            </div>
            <textarea
              placeholder="Paste service-account JSON here…"
              bind:value={gcpCreds}
              oninput={() => extractProjectId(gcpCreds)}
              rows="4"
              class="numeral w-full resize-y border border-hairline bg-ink px-3 py-2 text-xs
                     text-paper placeholder:text-muted/60 focus:border-red focus:outline-none"
            ></textarea>
            {#if gcpProjectId}
              <p class="mt-1 text-xs" style="color: var(--muted)">Project: <code class="numeral">{gcpProjectId}</code> ✓</p>
            {/if}
            {#if gcpTables.length === 0}
              <button
                class="focus-ring mt-2 border border-hairline px-4 py-1.5 text-xs tracking-widest hover:text-paper disabled:opacity-40"
                disabled={gcpValidating || !gcpCreds.trim()}
                onclick={validateAndFetchTables}
              >{gcpValidating ? 'VALIDATING…' : 'VALIDATE & FIND TABLES'}</button>
            {/if}
          </div>

          <!-- Step 3: select table (only after tables discovered) -->
          {#if gcpTables.length > 0}
            <div class="cell">
              <div class="flex items-center gap-4 mb-3">
                <span class="microlabel shrink-0" style="background: var(--red); color: var(--ink); padding: 1px 6px;">3</span>
                <div class="microlabel-dim">SELECT BILLING TABLE</div>
              </div>
              <select
                bind:value={gcpSelectedTable}
                class="numeral w-full border border-hairline bg-ink px-3 py-2 text-xs text-paper focus:border-red focus:outline-none"
              >
                <option value="" disabled>Select table…</option>
                {#each gcpTables as t}
                  <option value={t}>{t}</option>
                {/each}
              </select>

              <div class="mt-4">
                <button
                  class="focus-ring microlabel-dim hover:text-paper"
                  onclick={() => (gcpShowLogs = !gcpShowLogs)}
                >▸ Advanced: Vertex AI live logs (optional)</button>
                {#if gcpShowLogs}
                  <p class="mt-2 text-xs" style="color: var(--muted)">
                    Enable request-response logging on Vertex AI endpoints and route to BigQuery.
                    Provides per-request token counts with ~5 min lag.
                  </p>
                  <input
                    placeholder="project.dataset.vertex_logs_table"
                    bind:value={gcpLogsTable}
                    class="numeral mt-2 w-full border border-hairline bg-ink px-3 py-2 text-xs text-paper
                           placeholder:text-muted/60 focus:border-red focus:outline-none"
                  />
                {/if}
              </div>

              <button
                class="focus-ring mt-5 bg-red px-5 py-1.5 text-xs font-bold tracking-widest text-ink disabled:opacity-40"
                disabled={gcpConnecting || !gcpSelectedTable}
                onclick={connectGCP}
              >{gcpConnecting ? '…' : 'CONNECT'}</button>

              {#if gcpError}
                <p class="mt-2 text-sm" style="color: var(--red)">▲ {gcpError}</p>
              {/if}
            </div>
          {/if}
        </div>
      {/if}
    </div>
  {/if}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd /Users/kavin/Projects/machanirobotics/burnmeter/frontend && npm run check
```

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/views/Settings.svelte
git commit -m "feat: Settings.svelte — Billing & GCP tab with stepped setup flow"
```

---

## Task 6: Build Verification

**Files:** None — verification only.

- [ ] **Step 1: Full build**

```bash
cd /Users/kavin/Projects/machanirobotics/burnmeter/frontend && npm run build
```

Expected: build succeeds (chunk size warning for gpt-tokenizer is pre-existing and acceptable — not a failure).

- [ ] **Step 2: Manual smoke-test checklist**

Start the dev server:

```bash
cd /Users/kavin/Projects/machanirobotics/burnmeter/frontend && npm run dev
```

Check these paths in the browser:

| Path | What to verify |
|------|---------------|
| Header — any tab | Row 1: logo left, SYNC right. Row 2: tabs left, period+export appear only on Dashboard tab. |
| Header — Tokenizer tab | Period select and EXPORT POSTER are hidden. |
| Header — Providers tab | Period select and EXPORT POSTER are hidden. |
| Providers → AI PROVIDERS tab | Provider cards in 3-col grid. Connected cards show masked key + sync time. Unconnected cards show red CONNECT →. |
| Click unconnected card | Red outline on card. Detail panel appears below grid with key input + ADD KEY button. |
| Click connected card | Detail panel appears in manage mode: masked key, SYNC NOW, REMOVE. |
| Gemini manage panel | ▸ Proxy endpoints toggle visible. Click reveals HTTP + WebSocket URLs. |
| Click ✕ on panel | Panel closes, card outline clears. |
| Click same card again | Panel toggles closed. |
| Providers → BILLING & GCP tab | Stepped list with steps 1/2. Step 3 hidden until tables discovered. Key custody footer line visible. |
| Footer | "Keys stored in OS keychain…" microlabel-dim line. |

- [ ] **Step 3: Commit build assets if any are tracked**

```bash
git status
# If frontend/dist is not gitignored, add it — but typically it is. No commit needed.
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| Two-row header (logo+sync / tabs+actions) | Task 1 |
| Period select + export only on Dashboard tab | Task 1 |
| Live ticker stays in row 3 | Task 1 |
| Inner tabs: AI PROVIDERS / BILLING & GCP | Task 3 |
| 3-col bento provider grid | Task 4 |
| Connected card: masked key, sync time, error state | Task 4 |
| Unconnected card: CONNECT →, dashed border | Task 4 |
| Vertex AI auto-card (read-only) | Task 4 |
| Non-interactive "+ ADD ANOTHER PROVIDER" | Task 4 |
| Detail panel with red border, ✕ close | Task 4 |
| Connect mode: key input + hint + ADD KEY | Task 4 |
| Manage mode: masked key + SYNC NOW + REMOVE | Task 4 |
| Gemini proxy section behind toggle | Task 4 |
| Errors inline in panel | Task 4 |
| GCP stepped list (3 steps, step 3 deferred) | Task 5 |
| GCP connected: status card + SYNC NOW + REMOVE | Task 5 |
| Key custody notice demoted to footer line | Task 3 |
| No backend changes | All tasks — confirmed |

No gaps found.
