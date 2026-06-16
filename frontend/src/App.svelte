<script lang="ts">
  import Dashboard from '$lib/views/Dashboard.svelte'
  import ProviderDetail from '$lib/views/ProviderDetail.svelte'
  import Settings from '$lib/views/Settings.svelte'

  // gpt-tokenizer ships multi-MB BPE ranks — load the playground on demand
  const playgroundImport = () => import('$lib/views/Playground.svelte')
  import LiveTicker from '$lib/components/LiveTicker.svelte'
  import Poster from '$lib/components/Poster.svelte'
  import { api } from '$lib/api'
  import type { LeaderboardModel, Overview } from '$lib/api'

  type Tab = 'dashboard' | 'playground' | 'providers'
  let tab = $state<Tab>('dashboard')
  let detailProvider = $state<string | null>(null)
  let period = $state('mtd')
  let syncing = $state(false)
  let refreshTick = $state(0)
  let poster = $state<{ data: Overview; models: LeaderboardModel[] } | null>(null)

  const NAV: { id: Tab; label: string }[] = [
    { id: 'dashboard', label: 'DASHBOARD' },
    { id: 'playground', label: 'TOKENIZER' },
    { id: 'providers', label: 'PROVIDERS' },
  ]

  async function syncNow() {
    syncing = true
    try {
      await api.sync()
      refreshTick++
    } finally {
      syncing = false
    }
  }

  async function exportPoster() {
    const [o, m] = await Promise.all([api.overview(period), api.models(period)])
    poster = { data: o, models: m.models }
  }

  let liveDebounce: ReturnType<typeof setTimeout>
  function onLiveEvent() {
    clearTimeout(liveDebounce)
    liveDebounce = setTimeout(() => refreshTick++, 800)
  }
</script>

<div class="mx-auto flex min-h-screen max-w-[110rem] flex-col px-8">
  <!-- masthead -->
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

  <main class="flex-1 py-6">
    {#if tab === 'providers'}
      <Settings />
    {:else if tab === 'playground'}
      {#await playgroundImport()}
        <div class="bento grid-cols-1"><div class="cell h-48 animate-pulse"></div></div>
      {:then { default: Playground }}
        <Playground />
      {/await}
    {:else if detailProvider}
      <ProviderDetail
        provider={detailProvider}
        {period}
        {refreshTick}
        onback={() => (detailProvider = null)}
      />
    {:else}
      <Dashboard {period} {refreshTick} ondrill={(p) => (detailProvider = p)} />
    {/if}
  </main>

  <footer class="hairline-b border-t border-hairline py-4">
    <span class="microlabel-dim">
      LOCAL-FIRST — KEYS NEVER LEAVE THIS MACHINE —
      <a class="underline hover:text-paper" href="https://github.com/kavinbm16/burnmeter" target="_blank" rel="noreferrer">SOURCE</a>
    </span>
  </footer>
</div>

{#if poster}
  <Poster data={poster.data} models={poster.models} onclose={() => (poster = null)} />
{/if}
