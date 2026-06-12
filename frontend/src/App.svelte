<script lang="ts">
  import { Flame, LayoutDashboard, Settings as SettingsIcon, RefreshCw } from '@lucide/svelte'
  import Overview from '$lib/views/Overview.svelte'
  import ProviderDetail from '$lib/views/ProviderDetail.svelte'
  import Settings from '$lib/views/Settings.svelte'
  import { api } from '$lib/api'

  let tab = $state<'overview' | 'settings'>('overview')
  let detailProvider = $state<string | null>(null)
  let period = $state('30d')
  let syncing = $state(false)
  let refreshTick = $state(0)

  async function syncNow() {
    syncing = true
    try {
      await api.sync()
      refreshTick++
    } finally {
      syncing = false
    }
  }
</script>

<div class="min-h-screen">
  <header class="border-b border-border bg-surface/60 backdrop-blur sticky top-0 z-10">
    <div class="mx-auto flex max-w-6xl items-center gap-6 px-6 py-3">
      <button
        class="flex items-center gap-2 text-lg font-bold tracking-tight"
        onclick={() => { tab = 'overview'; detailProvider = null }}
      >
        <Flame class="size-5 text-primary" />
        burnmeter
      </button>

      <nav class="flex items-center gap-1 text-sm">
        <button
          class="flex items-center gap-1.5 rounded-md px-3 py-1.5 transition-colors
                 {tab === 'overview' ? 'bg-surface-2 text-foreground' : 'text-muted-foreground hover:text-foreground'}"
          onclick={() => { tab = 'overview'; detailProvider = null }}
        >
          <LayoutDashboard class="size-4" /> Dashboard
        </button>
        <button
          class="flex items-center gap-1.5 rounded-md px-3 py-1.5 transition-colors
                 {tab === 'settings' ? 'bg-surface-2 text-foreground' : 'text-muted-foreground hover:text-foreground'}"
          onclick={() => { tab = 'settings'; detailProvider = null }}
        >
          <SettingsIcon class="size-4" /> Providers
        </button>
      </nav>

      <div class="ml-auto flex items-center gap-3">
        {#if tab === 'overview'}
          <select
            bind:value={period}
            class="rounded-md border border-border bg-surface-2 px-2 py-1.5 text-sm"
          >
            <option value="mtd">Month to date</option>
            <option value="30d">Last 30 days</option>
            <option value="90d">Last 90 days</option>
          </select>
        {/if}
        <button
          class="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm
                 text-muted-foreground hover:text-foreground disabled:opacity-50"
          onclick={syncNow}
          disabled={syncing}
        >
          <RefreshCw class="size-4 {syncing ? 'animate-spin' : ''}" /> Sync
        </button>
      </div>
    </div>
  </header>

  <main class="mx-auto max-w-6xl px-6 py-6">
    {#if tab === 'settings'}
      <Settings />
    {:else if detailProvider}
      <ProviderDetail
        provider={detailProvider}
        {period}
        {refreshTick}
        onback={() => (detailProvider = null)}
      />
    {:else}
      <Overview {period} {refreshTick} ondrill={(p) => (detailProvider = p)} />
    {/if}
  </main>

  <footer class="mx-auto max-w-6xl px-6 pb-6 text-xs text-muted-foreground">
    Local-first · your keys never leave this machine ·
    <a class="underline hover:text-foreground" href="https://github.com/kavinbm16/burnmeter" target="_blank" rel="noreferrer">
      source
    </a>
  </footer>
</div>
