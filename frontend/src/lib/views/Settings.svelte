<script lang="ts">
  import { ShieldCheck, Trash2, Copy, CheckCircle2, AlertTriangle, Loader2 } from '@lucide/svelte'
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

  const configured = $derived(new Set(data?.configured.map((c) => c.name) ?? []))
</script>

<div class="mx-auto max-w-3xl space-y-4">
  <div class="panel flex items-start gap-3 border-positive/30 p-4">
    <ShieldCheck class="mt-0.5 size-5 shrink-0 text-positive" />
    <div class="text-sm">
      <div class="font-semibold">Your keys stay on this machine.</div>
      <p class="mt-1 text-muted-foreground">
        Keys are stored in your OS keychain (or an encrypted local file), never in the database or
        logs, and are only ever sent to the provider's official API. The server listens on
        127.0.0.1 only. This app is open source — audit it.
      </p>
    </div>
  </div>

  {#if data}
    {#each Object.entries(data.available) as [name, meta]}
      {@const cfg = data.configured.find((c) => c.name === name)}
      <div class="panel p-4">
        <div class="flex items-center gap-3">
          <h2 class="font-semibold">{meta.display_name}</h2>
          <span class="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
            {meta.mode === 'proxy' ? 'local proxy' : 'usage api'}
          </span>
          {#if cfg}
            <span class="ml-auto flex items-center gap-1.5 text-xs text-positive">
              <CheckCircle2 class="size-3.5" /> {cfg.masked_key}
              {#if cfg.sync_status === 'syncing'}· syncing…{/if}
              {#if cfg.last_synced_at}· synced {cfg.last_synced_at}Z{/if}
            </span>
            <button
              class="text-muted-foreground hover:text-destructive"
              onclick={() => remove(name)}
              title="Remove provider"
            >
              <Trash2 class="size-4" />
            </button>
          {/if}
        </div>

        <p class="mt-2 text-sm text-muted-foreground">{meta.key_hint}</p>

        {#if cfg?.sync_status === 'invalid_key' || cfg?.sync_status === 'error'}
          <div class="mt-2 flex items-center gap-2 text-sm text-destructive">
            <AlertTriangle class="size-4" /> {cfg.sync_error ?? 'sync failed'}
          </div>
        {/if}

        {#if !cfg}
          <div class="mt-3 flex gap-2">
            <input
              type="password"
              placeholder={name === 'openai' ? 'sk-admin-…' : 'AIza…'}
              bind:value={keyInput[name]}
              class="flex-1 rounded-md border border-border bg-surface-2 px-3 py-2 text-sm mono
                     placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary"
            />
            <button
              class="flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-semibold
                     text-primary-foreground disabled:opacity-50"
              disabled={busy === name || !(keyInput[name] ?? '').trim()}
              onclick={() => add(name)}
            >
              {#if busy === name}<Loader2 class="size-4 animate-spin" />{/if}
              Add
            </button>
          </div>
          {#if errors[name]}
            <div class="mt-2 flex items-center gap-2 text-sm text-destructive">
              <AlertTriangle class="size-4" /> {errors[name]}
            </div>
          {/if}
        {/if}

        {#if name === 'gemini'}
          <div class="mt-3 rounded-md border border-border bg-surface-2 p-3 text-sm">
            <div class="panel-title mb-2">Point your apps at the local proxy</div>
            <div class="flex items-center gap-2">
              <code class="mono flex-1 truncate text-xs">{proxyUrl}</code>
              <button class="text-muted-foreground hover:text-foreground" onclick={copyProxy}>
                {#if copied}<CheckCircle2 class="size-4 text-positive" />{:else}<Copy class="size-4" />{/if}
              </button>
            </div>
            <pre class="mt-2 overflow-x-auto text-xs text-muted-foreground">{`# python (google-genai)
client = genai.Client(
    api_key=...,  # optional if key stored above
    http_options={"base_url": "${proxyUrl}"},
)`}</pre>
            <p class="mt-2 text-xs text-muted-foreground">
              Gemini has no usage API, so burnmeter counts tokens from each response passing
              through. Only traffic routed via the proxy is tracked; costs are ≈ estimates from a
              local price table.
            </p>
          </div>
        {/if}
      </div>
    {/each}
  {:else}
    <div class="panel h-40 animate-pulse"></div>
  {/if}
</div>
