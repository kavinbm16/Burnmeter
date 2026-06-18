<script lang="ts">
  import { api, fmtTokens, fmtUsd } from '$lib/api'
  import type { Budget, HeatmapDay, LeaderboardModel, Overview, ReconciliationRow } from '$lib/api'
  import Odometer from '$lib/components/Odometer.svelte'
  import Heatmap from '$lib/components/Heatmap.svelte'
  import BurnGauge from '$lib/components/BurnGauge.svelte'
  import Leaderboard from '$lib/components/Leaderboard.svelte'
  import BarStrip from '$lib/components/BarStrip.svelte'
  import LiveTicker from '$lib/components/LiveTicker.svelte'

  let {
    period,
    refreshTick,
    ondrill,
    onsetup,
  }: {
    period: string
    refreshTick: number
    ondrill: (p: string) => void
    onsetup: () => void
  } = $props()

  let data = $state<Overview | null>(null)
  let budget = $state<Budget | null>(null)
  let heat = $state<{ start: string; end: string; days: HeatmapDay[] } | null>(null)
  let models = $state<LeaderboardModel[]>([])
  let error = $state<string | null>(null)
  let dayFilter = $state<string | null>(null)
  let secondaryView: 'calendar' | 'leaderboard' = $state('calendar')

  $effect(() => {
    void refreshTick
    void dayFilter
    Promise.all([
      api.overview(period, dayFilter),
      api.budget(),
      api.heatmap(120),
      api.models(period, dayFilter),
    ]).then(
      ([o, b, h, m]) => {
        data = o
        budget = b
        heat = h
        models = m.models
        error = null
      },
      (e) => (error = String(e))
    )
    api.reconciliation('gemini', period).then(
      (res) => (reconciliation = res.reconciliation),
      () => (reconciliation = [])
    )
  })

  async function saveBudget(v: number | null) {
    await api.setBudget(v)
    budget = await api.budget()
  }

  const dailyBars = $derived.by(() => {
    if (!data) return []
    const byDay = new Map<string, { cost: number; tokens: number }>()
    for (const p of data.daily) {
      const d = byDay.get(p.date) ?? { cost: 0, tokens: 0 }
      d.cost += p.cost_usd ?? 0
      d.tokens += p.total_tokens
      byDay.set(p.date, d)
    }
    return [...byDay.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, v]) => ({ date, cost: v.cost, tokens: v.tokens }))
  })

  const anyEstimated = $derived(data?.by_provider.some((p) => p.cost_estimated) ?? false)
  let reconciliation = $state<ReconciliationRow[]>([])
  const reconciledDays = $derived(reconciliation.filter(r => r.reconciled).length)
  const totalDays = $derived(reconciliation.length)
  const reconciledDatesSet = $derived(new Set(reconciliation.filter(r => r.reconciled).map(r => r.date)))
</script>

{#if error}
  <div class="bento grid-cols-1"><div class="cell" style="color: var(--red)">{error}</div></div>
{:else if !data || !budget || !heat}
  <div class="bento grid-cols-2 md:grid-cols-4">
    {#each Array(4) as _}<div class="cell h-36 animate-pulse"></div>{/each}
  </div>
{:else if data.by_provider.length === 0 && !dayFilter}
  <div class="bento grid-cols-1">
    <div class="cell py-24 text-center">
      <div class="numeral text-6xl">000<span style="color: var(--red)">.</span>00</div>
      <p class="microlabel mt-5">no data recorded</p>
      <p class="mx-auto mt-4 max-w-md" style="color: var(--muted)">
        Add a provider key under PROVIDERS. OpenAI backfills 90 days of history;
        Gemini counts live through the local proxy.
      </p>
      <button
        class="focus-ring mt-6 bg-red px-6 py-2 text-xs font-bold tracking-widest text-ink"
        onclick={onsetup}
      >CONNECT YOUR FIRST PROVIDER →</button>
    </div>
  </div>
{:else}
  {#if dayFilter}
    <button
      class="microlabel mb-3 flex items-center gap-2 hover:text-paper"
      onclick={() => (dayFilter = null)}
    >
      ◼ filtered to {dayFilter} — clear ✕
    </button>
  {/if}

  <!-- PRIMARY: hero + budget -->
  <div class="flex flex-wrap items-start gap-6">
    <div class="flex-1">
      <div class="microlabel">Total spend</div>
      <div class="mt-4 flex items-baseline text-7xl lg:text-8xl">
        <Odometer value={(data.totals.cost_usd ?? 0).toFixed(2)} />
      </div>
      {#if totalDays > 0}
        <p class="microlabel-dim mt-1">
          {reconciledDays === totalDays
            ? 'reconciled against GCP billing'
            : reconciledDays > 0
              ? `${reconciledDays}/${totalDays} days reconciled`
              : 'estimated · connect GCP for actuals'}
        </p>
      {/if}
      <div class="microlabel-dim mt-2">
        {anyEstimated ? '≈ ' : ''}USD — {data.period.start} → {data.period.end}
      </div>
    </div>
    <BurnGauge budget={budget} onsave={saveBudget} loading={!data} />
  </div>

  <!-- PRIMARY: daily bar chart -->
  <div class="mt-6">
    <BarStrip bars={dailyBars} height={150} highlight={dayFilter} />
  </div>

  <!-- PRIMARY: provider list -->
  <div class="bento mt-6 grid-cols-2 md:grid-cols-4">
    {#each data.by_provider as p (p.provider)}
      <div
        class="focus-ring cell group cursor-pointer transition-colors hover:bg-ink-2"
        role="button"
        tabindex="0"
        onclick={() => ondrill(p.provider)}
        onkeydown={(e) => e.key === 'Enter' && ondrill(p.provider)}
      >
        <div class="flex items-baseline justify-between">
          <span class="microlabel">{p.provider}</span>
          <span class="microlabel-dim" aria-hidden="true">›</span>
        </div>
        <div class="numeral mt-3 text-3xl">{fmtUsd(p.cost_usd, !!p.cost_estimated)}</div>
        <div class="microlabel-dim mt-2">
          {fmtTokens(p.input_tokens)} in / {fmtTokens(p.output_tokens)} out
        </div>
      </div>
    {/each}
  </div>

  <!-- SECONDARY: tab toggle -->
  <div class="mt-6 flex gap-4 border-t border-hairline pt-4">
    <button
      class="microlabel-dim transition-colors focus-ring"
      class:text-paper={secondaryView === 'calendar'}
      onclick={() => (secondaryView = 'calendar')}
    >Calendar</button>
    <button
      class="microlabel-dim transition-colors focus-ring"
      class:text-paper={secondaryView === 'leaderboard'}
      onclick={() => (secondaryView = 'leaderboard')}
    >Leaderboard</button>
  </div>

  {#if secondaryView === 'calendar'}
    <div class="bento mt-px grid-cols-1">
      <div class="cell">
        <div class="microlabel mb-4">Spend calendar</div>
        <Heatmap
          days={heat.days}
          start={heat.start}
          end={heat.end}
          selected={dayFilter}
          onselect={(d) => (dayFilter = d)}
          loading={!data}
          reconciledDates={reconciledDatesSet}
        />
      </div>
    </div>
    <LiveTicker />
  {:else}
    <div class="bento mt-px grid-cols-1">
      <div class="cell">
        <div class="flex items-baseline justify-between">
          <span class="microlabel">Model leaderboard</span>
          <span class="microlabel-dim">spend · tokens · $/1M · in:out</span>
        </div>
        <div class="mt-4">
          <Leaderboard {models} />
        </div>
      </div>
    </div>
  {/if}

  {#if anyEstimated}
    <p class="microlabel-dim mt-4">≈ — estimated from local price table (proxy traffic). billed figures may differ.</p>
  {/if}
{/if}
