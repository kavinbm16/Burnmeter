<script lang="ts">
  import { api } from '$lib/api'
  import type { ProvidersResponse } from '$lib/api'

  let data = $state<ProvidersResponse | null>(null)
  let keyInput = $state<Record<string, string>>({})
  let busy = $state<string | null>(null)
  let errors = $state<Record<string, string>>({})
  let copied = $state(false)
  let billing = $state<{ configured: boolean; table: string | null } | null>(null)
  let billingCreds = $state('')
  let billingTable = $state('')
  let billingError = $state('')

  const proxyUrl = `${location.protocol}//${location.hostname}:8400/proxy/gemini`
  const liveProxyUrl = `ws://${location.hostname}:8400/proxy/gemini`

  api.billingStatus().then((b) => (billing = b))

  async function saveBilling() {
    billingError = ''
    try {
      await api.billingConfigure(billingCreds, billingTable)
      billingCreds = ''
      billing = await api.billingStatus()
    } catch (e: any) {
      billingError = e.message
    }
  }

  async function removeBilling() {
    await api.billingRemove()
    billing = await api.billingStatus()
  }

  async function load() {
    data = await api.providers()
  }
  load()

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
    copied = true
    setTimeout(() => (copied = false), 1500)
  }
</script>

<div class="mx-auto max-w-3xl">
  <div class="bento grid-cols-1">
    <div class="cell">
      <div class="microlabel">Key custody</div>
      <p class="mt-2 text-sm" style="color: var(--muted)">
        Keys live in your OS keychain (or an encrypted local file), never in the database or logs,
        and are only sent to the provider's official API. Server binds 127.0.0.1.
        Open source — <a class="underline hover:text-paper" href="https://github.com/kavinbm16/burnmeter/blob/master/SECURITY.md" target="_blank" rel="noreferrer">audit the guarantees</a>.
      </p>
    </div>

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
              <button class="microlabel-dim hover:text-paper" onclick={() => remove(name)}>REMOVE</button>
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
                class="bg-red px-5 text-xs font-bold tracking-widest text-ink disabled:opacity-40"
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
                <button class="microlabel-dim hover:text-paper" onclick={copyProxy}>
                  {copied ? 'COPIED ✓' : 'COPY'}
                </button>
              </div>
              <code class="numeral mt-2 block truncate text-xs">{proxyUrl}</code>
              <pre class="mt-3 overflow-x-auto text-xs" style="color: var(--muted)">{`client = genai.Client(
    api_key=...,  # optional if stored above
    http_options={"base_url": "${proxyUrl}"},
)`}</pre>
              <p class="microlabel-dim mt-2">
                only traffic routed through the proxy is counted · costs are ≈ estimates
              </p>

              <div class="mt-4 border-t border-hairline pt-3">
                <span class="microlabel">Live API (websocket) sessions</span>
                <code class="numeral mt-2 block truncate text-xs">{liveProxyUrl}</code>
                <pre class="mt-2 overflow-x-auto text-xs" style="color: var(--muted)">{`client = genai.Client(
    api_key=...,
    http_options={"base_url": "${liveProxyUrl}"},
)
# live sessions (BidiGenerateContent) relay through the same host;
# audio + text tokens are split and priced at Live rates, per key`}</pre>
              </div>
            </div>

            <div class="mt-px border border-hairline bg-ink-2 p-4">
              <div class="flex items-baseline justify-between">
                <span class="microlabel">Ground-truth cost · GCP billing export</span>
                {#if billing?.configured}
                  <button class="microlabel-dim hover:text-paper" onclick={removeBilling}>REMOVE</button>
                {/if}
              </div>
              {#if billing?.configured}
                <p class="mt-2 text-sm" style="color: var(--muted)">
                  Connected to <code class="numeral text-xs">{billing.table}</code>. Daily SKU-level
                  costs (audio in / text out / live) sync hourly into the Gemini drilldown.
                </p>
              {:else}
                <p class="mt-2 text-sm" style="color: var(--muted)">
                  Advanced: enable Cloud Billing export to BigQuery, create a read-only service
                  account, paste its JSON + the export table. Gives billed (not estimated) Gemini
                  cost split by SKU. Note: Google's export has no per-key dimension — key-wise
                  numbers come from the proxy.
                </p>
                <input
                  placeholder="project.dataset.gcp_billing_export_v1_XXXXXX"
                  bind:value={billingTable}
                  class="numeral mt-3 w-full border border-hairline bg-ink px-3 py-2 text-xs text-paper
                         placeholder:text-muted/60 focus:border-red focus:outline-none"
                />
                <textarea
                  placeholder="service-account credentials JSON (stored encrypted, never in the DB)"
                  bind:value={billingCreds}
                  rows="3"
                  class="numeral mt-2 w-full resize-y border border-hairline bg-ink px-3 py-2 text-xs
                         text-paper placeholder:text-muted/60 focus:border-red focus:outline-none"
                ></textarea>
                <button
                  class="mt-2 bg-red px-4 py-1.5 text-xs font-bold tracking-widest text-ink disabled:opacity-40"
                  disabled={!billingCreds.trim() || !billingTable.trim()}
                  onclick={saveBilling}
                >CONNECT</button>
                {#if billingError}
                  <p class="mt-2 text-sm" style="color: var(--red)">▲ {billingError}</p>
                {/if}
              {/if}
            </div>
          {/if}
        </div>
      {/each}
    {:else}
      <div class="cell h-40 animate-pulse"></div>
    {/if}
  </div>
</div>
