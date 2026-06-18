<script lang="ts">
  import { api } from '$lib/api'
  import type { GCPStatus, ProvidersResponse } from '$lib/api'

  // ── Master–detail selection ──────────────────────────────────────────
  // `selected` is a provider name, 'vertex' (read-only), or 'billing'.
  let selected = $state<string>('')
  let proxyLang = $state<'python' | 'node' | 'curl'>('python')
  // How the proxy gets its key: 'store' = saved in keychain & injected
  // server-side; 'byok' = app passes its own key per request. Both count usage.
  let keyMode = $state<'store' | 'byok'>('store')

  // ── Provider state ───────────────────────────────────────────────────
  let data = $state<ProvidersResponse | null>(null)
  let keyInput = $state<Record<string, string>>({})
  let busy = $state<string | null>(null)
  let errors = $state<Record<string, string>>({})
  let syncBusy = $state(false)
  let syncDone = $state(false)

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
    // Default the selection to the first provider on first load.
    if (!selected && data) selected = Object.keys(data.available)[0] ?? 'billing'
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

  function select(name: string) {
    selected = name
    errors = { ...errors, [name]: '' }
  }

  // Sync only the selected provider (the SYNC NOW button used to sync all).
  async function syncProvider() {
    syncBusy = true
    errors = { ...errors, [selected]: '' }
    try {
      const res = await api.sync(selected)
      if (!res.ok) throw new Error('sync failed')
      await load()
      syncDone = true
      setTimeout(() => (syncDone = false), 1800)
    } catch (e: any) {
      errors = { ...errors, [selected]: e.message }
    } finally {
      syncBusy = false
    }
  }

  // "2026-06-18T09:58" (UTC, no zone) → "3m ago".
  function relTime(iso: string): string {
    const t = Date.parse(iso.endsWith('Z') ? iso : iso + 'Z')
    if (isNaN(t)) return iso
    const s = Math.max(0, (Date.now() - t) / 1000)
    if (s < 60) return 'just now'
    if (s < 3600) return `${Math.floor(s / 60)}m ago`
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`
    return `${Math.floor(s / 86400)}d ago`
  }
</script>

<div class="grid gap-px md:grid-cols-[16rem_1fr] md:gap-8">

  <!-- ── Left rail: master nav ──────────────────────────────────────── -->
  <aside class="md:border-r md:border-hairline md:pr-4">
    {#if data}
      <div class="microlabel-dim mb-2 px-3">AI PROVIDERS</div>
      {#each Object.entries(data.available) as [name, meta] (name)}
        {@const cfg = data.configured.find((c) => c.name === name)}
        <button
          class="focus-ring flex w-full items-center justify-between border-l-2 px-3 py-2 text-left transition-colors hover:text-paper"
          style={selected === name
            ? 'border-color: var(--red); color: var(--paper);'
            : 'border-color: transparent;'}
          onclick={() => select(name)}
        >
          <span class="text-sm font-medium uppercase tracking-wide">{meta.display_name}</span>
          {#if cfg}
            {#if cfg.sync_status === 'invalid_key' || cfg.sync_status === 'error'}
              <span class="text-xs" style="color: var(--red)">▲</span>
            {:else}
              <span style="color: var(--red); font-size: 0.6rem;">●</span>
            {/if}
          {:else}
            <span class="microlabel-dim" style="color: var(--red)">+</span>
          {/if}
        </button>
      {/each}

      {#if data.configured.find((c) => c.name === 'vertex_ai')}
        <button
          class="focus-ring flex w-full items-center justify-between border-l-2 px-3 py-2 text-left transition-colors hover:text-paper"
          style={selected === 'vertex'
            ? 'border-color: var(--red); color: var(--paper);'
            : 'border-color: transparent;'}
          onclick={() => select('vertex')}
        >
          <span class="text-sm font-medium uppercase tracking-wide">Google Vertex AI</span>
          <span style="color: var(--red); font-size: 0.6rem;">●</span>
        </button>
      {/if}

      <div class="microlabel-dim mb-2 mt-6 px-3">BILLING</div>
      <button
        class="focus-ring flex w-full items-center justify-between border-l-2 px-3 py-2 text-left transition-colors hover:text-paper"
        style={selected === 'billing'
          ? 'border-color: var(--red); color: var(--paper);'
          : 'border-color: transparent;'}
        onclick={() => select('billing')}
      >
        <span class="text-sm font-medium uppercase tracking-wide">Billing &amp; GCP</span>
        {#if gcp?.configured}
          <span style="color: var(--red); font-size: 0.6rem;">●</span>
        {/if}
      </button>
    {:else}
      <div class="cell h-32 animate-pulse"></div>
    {/if}
  </aside>

  <!-- ── Right pane: detail ─────────────────────────────────────────── -->
  <section class="min-h-[24rem] pt-6 md:pt-0">
    {#if data}

      {#if selected === 'billing'}
        <!-- Billing & GCP -->
        <div class="w-full">
          <div class="flex items-baseline gap-3 mb-1">
            <h2 class="text-xl font-bold uppercase tracking-widest">Google Cloud Platform</h2>
            {#if gcp?.configured}
              <span class="numeral ml-auto text-xs" style="color: var(--red)">● {gcp.project_id}</span>
              <button class="focus-ring microlabel-dim hover:text-paper" onclick={disconnectGCP}>REMOVE</button>
            {/if}
          </div>
          <p class="microlabel-dim mb-5">billing export · vertex ai</p>

          {#if gcp?.configured}
            <!-- Connected status -->
            <div class="border border-hairline p-5">
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

          {:else}
            <!-- Setup flow -->

            <!-- How it works -->
            <div class="mb-6 border border-hairline p-5">
              <div class="text-sm font-semibold uppercase tracking-widest" style="color: var(--paper)">How it works</div>
              <p class="mt-2 text-base" style="color: var(--muted)">
                Google exports your real Cloud Billing line-items to a BigQuery table. Burnmeter reads that
                table — read-only, through a service account — and reconciles the costs it estimates locally
                against what Google actually billed.
              </p>
              <ul class="mt-3 space-y-1.5 text-sm" style="color: var(--muted)">
                <li>· <span style="color: var(--paper)">Gemini API</span> — proxy-estimated cost is corrected to the billed amount.</li>
                <li>· <span style="color: var(--paper)">Vertex AI</span> — cost is read entirely from billing (no API key needed).</li>
                <li>· Burnmeter never writes to your project. The service account has read-only BigQuery access.</li>
              </ul>
              <p class="mt-3 text-sm" style="color: var(--red)">
                ▲ First-time billing export can take up to 24h before any data appears in BigQuery.
              </p>
            </div>

            <p class="mb-3 text-sm font-semibold uppercase tracking-widest" style="color: var(--muted)">What to do</p>
            <div class="space-y-px">

              <!-- Step 1: enable billing export -->
              <div class="flex items-start gap-4 border border-hairline p-4">
                <span class="microlabel mt-0.5 shrink-0" style="background: var(--red); color: var(--ink); padding: 1px 6px;">1</span>
                <div class="flex-1 min-w-0">
                  <div class="text-sm font-semibold uppercase tracking-widest" style="color: var(--muted)">ENABLE BILLING EXPORT TO BIGQUERY</div>
                  <p class="mt-1 text-sm" style="color: var(--muted)">
                    In the Google Cloud console, open <span style="color: var(--paper)">Billing → Billing export → BigQuery export</span>
                    and enable <span style="color: var(--paper)">Standard usage cost</span>. Pick or create a dataset to hold it.
                  </p>
                </div>
                <a
                  class="focus-ring microlabel-dim hover:text-paper shrink-0 underline"
                  href="https://console.cloud.google.com/billing/export"
                  target="_blank"
                  rel="noreferrer"
                >OPEN CONSOLE ↗</a>
              </div>

              <!-- Step 2: create service account -->
              <div class="flex items-start gap-4 border border-hairline p-4">
                <span class="microlabel mt-0.5 shrink-0" style="background: var(--red); color: var(--ink); padding: 1px 6px;">2</span>
                <div class="flex-1 min-w-0">
                  <div class="text-sm font-semibold uppercase tracking-widest" style="color: var(--muted)">CREATE A READ-ONLY SERVICE ACCOUNT</div>
                  <p class="mt-1 text-sm" style="color: var(--muted)">Replace PROJECT_ID with your GCP project, then run this in your terminal. It writes <code class="numeral">burnmeter-key.json</code>.</p>
                </div>
                <button class="focus-ring microlabel-dim hover:text-paper shrink-0" onclick={copyCmd}>
                  {cmdCopied ? 'COPIED ✓' : 'COPY COMMAND'}
                </button>
              </div>

              <!-- Step 3: paste JSON -->
              <div class="border border-hairline p-4">
                <div class="flex items-center gap-4 mb-3">
                  <span class="microlabel shrink-0" style="background: var(--red); color: var(--ink); padding: 1px 6px;">3</span>
                  <div class="text-sm font-semibold uppercase tracking-widest" style="color: var(--muted)">PASTE THE SERVICE ACCOUNT JSON</div>
                </div>
                <p class="mb-3 text-sm" style="color: var(--muted)">Open the <code class="numeral">burnmeter-key.json</code> file from step 2 and paste its full contents below. It stays on this machine.</p>
                <textarea
                  placeholder="Paste service-account JSON here…"
                  bind:value={gcpCreds}
                  oninput={() => extractProjectId(gcpCreds)}
                  rows="4"
                  class="numeral w-full resize-y border border-hairline bg-ink px-3 py-2 text-sm
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

              <!-- Step 4: select table -->
              {#if gcpTables.length > 0}
                <div class="border border-hairline p-4">
                  <div class="flex items-center gap-4 mb-1">
                    <span class="microlabel shrink-0" style="background: var(--red); color: var(--ink); padding: 1px 6px;">4</span>
                    <div class="text-sm font-semibold uppercase tracking-widest" style="color: var(--muted)">PICK YOUR BILLING TABLE & CONNECT</div>
                  </div>
                  <p class="mb-3 text-sm" style="color: var(--muted)">These are the BigQuery tables the service account can read. Choose the one holding your billing export.</p>
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

      {:else if selected === 'vertex'}
        <!-- Vertex AI: read-only, managed through Billing & GCP -->
        {@const vtx = data.configured.find((c) => c.name === 'vertex_ai')}
        <div class="w-full">
          <h2 class="text-xl font-bold uppercase tracking-widest">Google Vertex AI</h2>
          <p class="microlabel-dim mb-5 mt-1">billing export</p>
          <div class="border border-hairline p-5">
            <div class="flex items-center gap-2">
              <span style="color: var(--red); font-size: 0.6rem;">●</span>
              <span class="microlabel">Tracked via GCP billing export</span>
            </div>
            {#if vtx?.last_synced_at}
              <p class="microlabel-dim mt-2">Last sync {vtx.last_synced_at}Z</p>
            {/if}
            <p class="mt-4 text-base" style="color: var(--muted)">
              Vertex AI cost is sourced from the connected GCP billing export — there is no separate key.
            </p>
            <button
              class="focus-ring mt-3 microlabel border border-hairline px-3 py-1.5 hover:border-red"
              onclick={() => select('billing')}
            >MANAGE IN BILLING &amp; GCP →</button>
          </div>
        </div>

      {:else if data.available[selected]}
        <!-- Provider detail -->
        {@const meta = data.available[selected]}
        {@const cfg = data.configured.find((c) => c.name === selected)}
        <div class="w-full">
          <div class="flex items-baseline gap-3">
            <h2 class="text-xl font-bold uppercase tracking-widest">{meta.display_name}</h2>
            <span class="microlabel-dim">{meta.mode === 'proxy' ? 'local proxy' : 'usage api'}</span>
            {#if cfg}
              {#if cfg.sync_status === 'invalid_key' || cfg.sync_status === 'error'}
                <span class="ml-auto text-xs" style="color: var(--red)">▲ key error</span>
              {:else if cfg.last_synced_at}
                <span class="microlabel-dim ml-auto">synced {relTime(cfg.last_synced_at)}</span>
              {/if}
            {/if}
          </div>

          <div class="mt-5">
            {#if meta.mode === 'proxy'}
              <!-- Proxy provider (Gemini) — guided 1-2-3 -->
              {#if cfg}
                <div class="mb-5 flex items-center gap-3 border border-hairline p-3">
                  <span style="color: var(--red); font-size: 0.6rem;">●</span>
                  <code class="numeral text-xs">{cfg.masked_key}</code>
                  {#if cfg.last_synced_at}
                    <span class="microlabel-dim">· synced {relTime(cfg.last_synced_at)}</span>
                  {/if}
                  <div class="ml-auto flex gap-3">
                    <button
                      class="focus-ring microlabel border border-hairline px-3 py-1 hover:border-red disabled:opacity-40"
                      disabled={syncBusy}
                      onclick={syncProvider}
                    >{syncBusy ? 'SYNCING…' : syncDone ? 'SYNCED ✓' : 'SYNC NOW'}</button>
                    <button class="focus-ring microlabel-dim hover:text-paper" onclick={() => remove(selected)}>REMOVE</button>
                  </div>
                </div>
              {/if}

              <!-- Step 1 -->
              <div class="flex items-center gap-2">
                <span class="microlabel shrink-0" style="background: var(--red); color: var(--ink); padding: 1px 6px;">1</span>
                <span class="text-sm font-semibold uppercase tracking-widest">HOW THE PROXY GETS YOUR KEY</span>
              </div>
              {#if !cfg}
                <!-- Two ways to give the proxy a key — both count usage identically. -->
                <div class="mt-2 grid gap-px sm:grid-cols-2">
                  <button
                    class="focus-ring border p-3 text-left transition-colors"
                    style={keyMode === 'store'
                      ? 'border-color: var(--red); background: var(--ink-2);'
                      : 'border-color: var(--hairline);'}
                    onclick={() => (keyMode = 'store')}
                  >
                    <div class="text-sm font-semibold uppercase tracking-wide" style="color: var(--paper)">
                      Store key here <span class="microlabel-dim">· recommended</span>
                    </div>
                    <p class="mt-1 text-xs" style="color: var(--muted)">
                      Saved to your OS keychain. The proxy injects it server-side — your app code carries no key.
                    </p>
                  </button>
                  <button
                    class="focus-ring border p-3 text-left transition-colors"
                    style={keyMode === 'byok'
                      ? 'border-color: var(--red); background: var(--ink-2);'
                      : 'border-color: var(--hairline);'}
                    onclick={() => (keyMode = 'byok')}
                  >
                    <div class="text-sm font-semibold uppercase tracking-wide" style="color: var(--paper)">
                      Pass key in code
                    </div>
                    <p class="mt-1 text-xs" style="color: var(--muted)">
                      Nothing stored here. Your app sends its own key per request; the proxy forwards it untouched.
                    </p>
                  </button>
                </div>

                {#if keyMode === 'store'}
                  <div class="mt-3 flex gap-px">
                    <input
                      type="password"
                      placeholder="AIza…"
                      bind:value={keyInput[selected]}
                      class="numeral flex-1 border border-hairline bg-ink px-3 py-2.5 text-base text-paper placeholder:text-muted/70 focus:border-red focus:outline-none"
                      onkeydown={(e) => e.key === 'Enter' && add(selected)}
                    />
                    <button
                      class="focus-ring bg-red px-5 text-xs font-bold tracking-widest text-ink disabled:opacity-40"
                      disabled={busy === selected || !(keyInput[selected] ?? '').trim()}
                      onclick={() => add(selected)}
                    >{busy === selected ? '…' : 'STORE KEY'}</button>
                  </div>
                  {#if errors[selected]}
                    <p class="mt-2 text-sm" style="color: var(--red)">▲ {errors[selected]}</p>
                  {/if}
                {:else}
                  <p class="microlabel-dim mt-3">
                    Nothing to set up here — use the snippet below with your own key. Usage still counts automatically.
                  </p>
                {/if}
              {/if}

              <!-- Step 2 -->
              <div class="mt-6 flex items-center gap-2">
                <span class="microlabel shrink-0" style="background: var(--red); color: var(--ink); padding: 1px 6px;">2</span>
                <span class="text-sm font-semibold uppercase tracking-widest">POINT YOUR APP AT THE PROXY</span>
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
                <pre class="overflow-x-auto border border-hairline bg-ink px-4 py-3 text-sm leading-relaxed" style="color: var(--muted)">{proxySnippet(proxyLang)}</pre>
              </div>
              <p class="microlabel-dim mt-2">Live / streaming? Use <code class="numeral">{liveProxyUrl}</code></p>

              <!-- Step 3 -->
              <div class="mt-6 flex items-center gap-2">
                <span class="microlabel shrink-0" style="background: var(--red); color: var(--ink); padding: 1px 6px;">3</span>
                <span class="text-sm font-semibold uppercase tracking-widest">RUN — USAGE COUNTS AUTOMATICALLY</span>
              </div>
              <p class="microlabel-dim mt-2">
                {gcp?.configured
                  ? 'traffic via proxy is estimated — GCP billing reconciliation active ✓'
                  : 'costs are estimated — connect GCP billing for actual billed amounts'}
              </p>

            {:else}
              <!-- usage_api provider (OpenAI) -->
              {#if cfg}
                <div class="flex items-center gap-3 border border-hairline p-3">
                  <span style="color: var(--red); font-size: 0.6rem;">●</span>
                  <code class="numeral text-xs">{cfg.masked_key}</code>
                  {#if cfg.last_synced_at}
                    <span class="microlabel-dim">· synced {relTime(cfg.last_synced_at)}</span>
                  {/if}
                  <div class="ml-auto flex gap-3">
                    <button
                      class="focus-ring microlabel border border-hairline px-3 py-1 hover:border-red disabled:opacity-40"
                      disabled={syncBusy}
                      onclick={syncProvider}
                    >{syncBusy ? 'SYNCING…' : syncDone ? 'SYNCED ✓' : 'SYNC NOW'}</button>
                    <button class="focus-ring microlabel-dim hover:text-paper" onclick={() => remove(selected)}>REMOVE</button>
                  </div>
                </div>
                {#if cfg.sync_status === 'invalid_key' || cfg.sync_status === 'error'}
                  <p class="mt-2 text-sm" style="color: var(--red)">▲ {cfg.sync_error ?? 'sync failed'}</p>
                {/if}
              {:else}
                <p class="mb-3 text-base" style="color: var(--muted)">{meta.key_hint}</p>
                <div class="microlabel mb-1">API KEY</div>
                <div class="flex gap-px">
                  <input
                    type="password"
                    placeholder="sk-admin-…"
                    bind:value={keyInput[selected]}
                    class="numeral flex-1 border border-hairline bg-ink px-3 py-2.5 text-base text-paper placeholder:text-muted/70 focus:border-red focus:outline-none"
                    onkeydown={(e) => e.key === 'Enter' && add(selected)}
                  />
                  <button
                    class="focus-ring bg-red px-5 text-xs font-bold tracking-widest text-ink disabled:opacity-40"
                    disabled={busy === selected || !(keyInput[selected] ?? '').trim()}
                    onclick={() => add(selected)}
                  >{busy === selected ? '…' : 'ADD KEY'}</button>
                </div>
                {#if errors[selected]}
                  <p class="mt-2 text-sm" style="color: var(--red)">▲ {errors[selected]}</p>
                {/if}
              {/if}
            {/if}
          </div>
        </div>
      {/if}

      <!-- Key custody notice -->
      <p class="mt-10 microlabel-dim">
        Keys stored in OS keychain — never in database or logs —
        <a class="underline hover:text-paper" href="https://github.com/kavinbm16/burnmeter/blob/master/SECURITY.md" target="_blank" rel="noreferrer">audit the guarantees</a>
      </p>

    {:else}
      <div class="cell h-40 animate-pulse"></div>
    {/if}
  </section>

</div>
