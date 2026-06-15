<script lang="ts">
  import { api } from '$lib/api'
  import type { GCPStatus, ProvidersResponse } from '$lib/api'

  // ── Tab + selection state ────────────────────────────────────────────
  let activeTab = $state<'providers' | 'billing'>('providers')
  let selectedProvider = $state<string | null>(null)
  let proxyLang = $state<'python' | 'node' | 'curl'>('python')

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
  let cmdCopied = $state(false)
  let snippetCopied = $state(false)

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

  <!-- Footer: key custody notice -->
  <p class="mt-8 microlabel-dim">
    Keys stored in OS keychain — never in database or logs —
    <a class="underline hover:text-paper" href="https://github.com/kavinbm16/burnmeter/blob/master/SECURITY.md" target="_blank" rel="noreferrer">audit the guarantees</a>
  </p>

</div>
