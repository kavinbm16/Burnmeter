<script lang="ts">
  import { api } from '$lib/api'
  import type { GCPStatus, ProvidersResponse } from '$lib/api'

  let data = $state<ProvidersResponse | null>(null)
  let keyInput = $state<Record<string, string>>({})
  let busy = $state<string | null>(null)
  let errors = $state<Record<string, string>>({})
  let copied = $state(false)

  // GCP connection state
  let gcp = $state<GCPStatus | null>(null)
  let gcpCreds = $state('')
  let gcpProjectId = $state<string | null>(null)  // extracted client-side on paste
  let gcpTables = $state<string[]>([])
  let gcpSelectedTable = $state('')
  let gcpLogsTable = $state('')
  let gcpShowLogs = $state(false)
  let gcpValidating = $state(false)
  let gcpConnecting = $state(false)
  let gcpError = $state('')

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

  let cmdCopied = $state(false)

  const proxyUrl = `${location.protocol}//${location.hostname}:8400/proxy/gemini`
  const liveProxyUrl = `ws://${location.hostname}:8400/proxy/gemini`
  let proxyCopied = $state(false)

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
</script>

<div class="mx-auto max-w-3xl">
  <div class="bento grid-cols-1">

    <!-- Key custody notice -->
    <div class="cell">
      <div class="microlabel">Key custody</div>
      <p class="mt-2 text-sm" style="color: var(--muted)">
        Keys live in your OS keychain (or an encrypted local file), never in the database or logs,
        and are only sent to the provider's official API. Server binds 127.0.0.1.
        Open source — <a class="underline hover:text-paper" href="https://github.com/kavinbm16/burnmeter/blob/master/SECURITY.md" target="_blank" rel="noreferrer">audit the guarantees</a>.
      </p>
    </div>

    <!-- GCP connection card -->
    <div class="cell">
      <div class="flex items-baseline gap-3">
        <h2 class="text-sm font-bold uppercase tracking-widest">Google Cloud Platform</h2>
        <span class="microlabel-dim">billing export · vertex ai</span>
        {#if gcp?.configured}
          <span class="numeral ml-auto text-xs" style="color: var(--red)">● {gcp.project_id}</span>
          <button class="focus-ring microlabel-dim hover:text-paper" onclick={disconnectGCP}>REMOVE</button>
        {/if}
      </div>

      {#if gcp?.configured}
        <div class="mt-3 grid grid-cols-2 gap-px text-xs" style="color: var(--muted)">
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
        <p class="microlabel-dim mt-2">Billing table: <code class="numeral text-xs">{gcp.billing_table}</code></p>
        <button
          class="focus-ring mt-3 border border-hairline px-3 py-1 text-xs tracking-widest hover:text-paper"
          onclick={() => api.gcpSync()}
        >SYNC NOW</button>
      {:else}
        <!-- Setup flow -->
        <p class="mt-2 text-sm" style="color: var(--muted)">
          One service account connects Gemini API billing reconciliation and Vertex AI cost tracking.
        </p>

        <div class="mt-3 flex items-center justify-between">
          <span class="microlabel">Create service account</span>
          <button class="focus-ring microlabel-dim hover:text-paper" onclick={copyCmd}>
            {cmdCopied ? 'COPIED ✓' : 'COPY COMMAND'}
          </button>
        </div>
        <p class="mt-1 text-xs" style="color: var(--muted)">Replace PROJECT_ID with your GCP project. Then paste the generated JSON below.</p>

        <textarea
          placeholder="Paste service-account JSON here…"
          bind:value={gcpCreds}
          oninput={() => extractProjectId(gcpCreds)}
          rows="4"
          class="numeral mt-3 w-full resize-y border border-hairline bg-ink px-3 py-2 text-xs
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
        {:else}
          <div class="mt-3">
            <span class="microlabel">Billing export table</span>
            <select
              bind:value={gcpSelectedTable}
              class="numeral mt-1 w-full border border-hairline bg-ink px-3 py-2 text-xs text-paper focus:border-red focus:outline-none"
            >
              <option value="" disabled>Select table…</option>
              {#each gcpTables as t}
                <option value={t}>{t}</option>
              {/each}
            </select>
          </div>

          <div class="mt-3">
            <button
              class="microlabel-dim hover:text-paper"
              onclick={() => (gcpShowLogs = !gcpShowLogs)}
            >▸ Advanced: Vertex AI live logs (optional)</button>
            {#if gcpShowLogs}
              <p class="mt-2 text-xs" style="color: var(--muted)">
                Enable request-response logging on each Vertex AI endpoint and route to BigQuery.
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
            class="focus-ring mt-3 bg-red px-5 py-1.5 text-xs font-bold tracking-widest text-ink disabled:opacity-40"
            disabled={gcpConnecting || !gcpSelectedTable}
            onclick={connectGCP}
          >{gcpConnecting ? '…' : 'CONNECT'}</button>
        {/if}

        {#if gcpError}
          <p class="mt-2 text-sm" style="color: var(--red)">▲ {gcpError}</p>
        {/if}
      {/if}
    </div>

    <!-- Provider cards (OpenAI, Gemini) — skip vertex_ai here, it has its own card below -->
    {#if data}
      {#each Object.entries(data.available) as [name, meta] (name)}
        {@const cfg = data.configured.find((c) => c.name === name)}
        <div class="cell">
          <div class="flex items-baseline gap-3">
            <h2 class="text-sm font-bold uppercase tracking-widest">{meta.display_name}</h2>
            <span class="microlabel-dim">{meta.mode === 'proxy' ? 'local proxy' : 'usage api'}</span>
            {#if cfg}
              <span class="numeral ml-auto text-xs" style="color: var(--red)">
                ● {cfg.masked_key}
                {#if cfg.sync_status === 'syncing'} · SYNCING{/if}
              </span>
              <button class="focus-ring microlabel-dim hover:text-paper" onclick={() => remove(name)}>REMOVE</button>
            {/if}
          </div>

          <p class="mt-2 text-sm" style="color: var(--muted)">{meta.key_hint}</p>

          {#if cfg?.sync_status === 'invalid_key' || cfg?.sync_status === 'error'}
            <p class="mt-2 text-sm" style="color: var(--red)">▲ {cfg.sync_error ?? 'sync failed'}</p>
          {/if}
          {#if cfg?.last_synced_at}
            <p class="microlabel-dim mt-2">last sync {cfg.last_synced_at}Z</p>
          {/if}

          {#if !cfg}
            <div class="mt-4 flex gap-px">
              <input
                type="password"
                placeholder={name === 'openai' ? 'sk-admin-…' : 'AIza…'}
                bind:value={keyInput[name]}
                class="numeral flex-1 border border-hairline bg-ink-2 px-3 py-2 text-sm text-paper
                       placeholder:text-muted/70 focus:border-red focus:outline-none"
                onkeydown={(e) => e.key === 'Enter' && add(name)}
              />
              <button
                class="focus-ring bg-red px-5 text-xs font-bold tracking-widest text-ink disabled:opacity-40"
                disabled={busy === name || !(keyInput[name] ?? '').trim()}
                onclick={() => add(name)}
              >{busy === name ? '…' : 'ADD'}</button>
            </div>
            {#if errors[name]}
              <p class="mt-2 text-sm" style="color: var(--red)">▲ {errors[name]}</p>
            {/if}
          {/if}

          {#if name === 'gemini'}
            <div class="mt-4 border border-hairline bg-ink-2 p-4">
              <div class="flex items-center justify-between">
                <span class="microlabel">Proxy endpoint</span>
                <button class="focus-ring microlabel-dim hover:text-paper" onclick={copyProxy}>
                  {proxyCopied ? 'COPIED ✓' : 'COPY'}
                </button>
              </div>
              <code class="numeral mt-2 block truncate text-xs">{proxyUrl}</code>
              <pre class="mt-3 overflow-x-auto text-xs" style="color: var(--muted)">{`client = genai.Client(
    api_key=...,
    http_options={"base_url": "${proxyUrl}"},
)`}</pre>
              <p class="microlabel-dim mt-2">
                {gcp?.configured
                  ? 'traffic via proxy is estimated — GCP billing reconciliation active ✓'
                  : 'costs are estimated — connect GCP above for actual billed amounts'}
              </p>

              <div class="mt-4 border-t border-hairline pt-3">
                <span class="microlabel">Live API (websocket) sessions</span>
                <code class="numeral mt-2 block truncate text-xs">{liveProxyUrl}</code>
                <pre class="mt-2 overflow-x-auto text-xs" style="color: var(--muted)">{`client = genai.Client(
    api_key=...,
    http_options={"base_url": "${liveProxyUrl}"},
)`}</pre>
              </div>
            </div>
          {/if}
        </div>
      {/each}

      <!-- Vertex AI auto-card — appears when GCP billing finds Vertex AI costs -->
      {#if data.configured.find((c) => c.name === 'vertex_ai')}
        {@const vtx = data.configured.find((c) => c.name === 'vertex_ai')!}
        <div class="cell">
          <div class="flex items-baseline gap-3">
            <h2 class="text-sm font-bold uppercase tracking-widest">Google Vertex AI</h2>
            <span class="microlabel-dim">billing export</span>
            <span class="numeral ml-auto text-xs" style="color: var(--red)">● via GCP billing</span>
          </div>
          <p class="mt-2 text-sm" style="color: var(--muted)">
            Cost data sourced from GCP billing export. No proxy — all Vertex AI traffic is captured
            regardless of where it runs.
            {#if !gcp?.logs_table}
              Token counts require Vertex AI request-response logging (configure in GCP card above).
            {:else}
              Token counts via request-response logs ✓
            {/if}
          </p>
          {#if vtx.last_synced_at}
            <p class="microlabel-dim mt-2">last sync {vtx.last_synced_at}Z</p>
          {/if}
        </div>
      {/if}
    {:else}
      <div class="cell h-40 animate-pulse"></div>
    {/if}

  </div>
</div>
