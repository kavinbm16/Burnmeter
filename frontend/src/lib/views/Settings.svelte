<script lang="ts">
  import { api } from '$lib/api'
  import type { ProvidersResponse } from '$lib/api'

  let data = $state<ProvidersResponse | null>(null)
  let keyInput = $state<Record<string, string>>({})
  let busy = $state<string | null>(null)
  let errors = $state<Record<string, string>>({})
  let copied = $state(false)

  const proxyUrl = `${location.protocol}//${location.hostname}:8400/proxy/gemini`

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
            </div>
          {/if}
        </div>
      {/each}
    {:else}
      <div class="cell h-40 animate-pulse"></div>
    {/if}
  </div>
</div>
