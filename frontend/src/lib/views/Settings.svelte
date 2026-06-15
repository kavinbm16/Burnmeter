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
