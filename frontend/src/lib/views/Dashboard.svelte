<script lang="ts">
  import { api, fmtTokens, fmtUsd } from '$lib/api'
  import type { Budget, HeatmapDay, LeaderboardModel, Overview } from '$lib/api'
  import Odometer from '$lib/components/Odometer.svelte'
  import Heatmap from '$lib/components/Heatmap.svelte'
  import BurnGauge from '$lib/components/BurnGauge.svelte'
  import Leaderboard from '$lib/components/Leaderboard.svelte'
  import BarStrip from '$lib/components/BarStrip.svelte'

  let {
    period,
    refreshTick,
    ondrill,
  }: { period: string; refreshTick: number; ondrill: (p: string) => void } = $props()

  let data = $state<Overview | null>(null)
  let budget = $state<Budget | null>(null)
  let heat = $state<{ start: string; end: string; days: HeatmapDay[] } | null>(null)
  let models = $state<LeaderboardModel[]>([])
  let error = $state<string | null>(null)
  let dayFilter = $state<string | null>(null)

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
</script>

{#if error}
  <div class="bento grid-cols-1"><div class="cell text-sm" style="color: var(--red)">{error}</div></div>
{:else if !data || !budget || !heat}
  <div class="bento grid-cols-4">
    {#each Array(4) as _}<div class="cell h-32 animate-pulse"></div>{/each}
  </div>
{:else if data.by_provider.length === 0 && !dayFilter}
  <div class="bento grid-cols-1">
    <div class="cell py-20 text-center">
      <div class="numeral text-5xl">000<span style="color: var(--red)">.</span>00</div>
      <p class="microlabel mt-4">no data recorded</p>
      <p class="mx-auto mt-3 max-w-md text-sm" style="color: var(--muted)">
        Add a provider key under PROVIDERS. OpenAI backfills 90 days of history;
        Gemini counts live through the local proxy.
      </p>
    </div>
  </div>
{:else}
  {#if dayFilter}
    <button
      class="microlabel mb-2 flex items-center gap-2 hover:text-paper"
      onclick={() => (dayFilter = null)}
    >
      ◼ filtered to {dayFilter} — clear ✕
    </button>
  {/if}

  <div class="bento grid-cols-1 md:grid-cols-3 lg:grid-cols-5">
    <!-- dominant spend cell -->
    <div class="cell md:col-span-2 lg:col-span-2 lg:row-span-2">
      <div class="microlabel">Total spend</div>
      <div class="mt-3 flex items-baseline text-6xl lg:text-7xl">
        <Odometer value={(data.totals.cost_usd ?? 0).toFixed(2)} />
      </div>
      <div class="microlabel-dim mt-2">
        {anyEstimated ? '≈ ' : ''}USD — {data.period.start} → {data.period.end}
      </div>
      <div class="mt-6">
        <BarStrip bars={dailyBars} height={130} highlight={dayFilter} />
      </div>
    </div>

    <!-- satellite metrics -->
    <div class="cell">
      <div class="microlabel">Input</div>
      <div class="numeral mt-2 text-3xl"><Odometer value={fmtTokens(data.totals.input_tokens)} /></div>
      <div class="microlabel-dim mt-1">tokens</div>
    </div>
    <div class="cell">
      <div class="microlabel">Output</div>
      <div class="numeral mt-2 text-3xl"><Odometer value={fmtTokens(data.totals.output_tokens)} /></div>
      <div class="microlabel-dim mt-1">tokens</div>
    </div>
    <div class="cell">
      <div class="microlabel">Requests</div>
      <div class="numeral mt-2 text-3xl"><Odometer value={fmtTokens(data.totals.requests)} /></div>
      <div class="microlabel-dim mt-1">calls</div>
    </div>

    <!-- burn gauge -->
    <div class="cell md:col-span-2 lg:col-span-3">
      <BurnGauge budget={budget} onsave={saveBudget} />
    </div>

    <!-- providers -->
    {#each data.by_provider as p (p.provider)}
      <div
        class="cell group cursor-pointer transition-colors hover:bg-ink-2"
        role="button"
        tabindex="0"
        onclick={() => ondrill(p.provider)}
        onkeydown={(e) => e.key === 'Enter' && ondrill(p.provider)}
      >
        <div class="flex items-baseline justify-between">
          <span class="microlabel">{p.provider}</span>
          <span class="microlabel-dim opacity-0 transition-opacity group-hover:opacity-100">open →</span>
        </div>
        <div class="numeral mt-2 text-2xl">{fmtUsd(p.cost_usd, !!p.cost_estimated)}</div>
        <div class="microlabel-dim mt-1">
          {fmtTokens(p.input_tokens)} in / {fmtTokens(p.output_tokens)} out
        </div>
      </div>
    {/each}

    <!-- heatmap -->
    <div class="cell md:col-span-3 lg:col-span-3">
      <div class="microlabel mb-3">Spend calendar</div>
      <Heatmap
        days={heat.days}
        start={heat.start}
        end={heat.end}
        selected={dayFilter}
        onselect={(d) => (dayFilter = d)}
      />
    </div>

    <!-- leaderboard -->
    <div class="cell md:col-span-3 lg:col-span-5">
      <div class="flex items-baseline justify-between">
        <span class="microlabel">Model leaderboard</span>
        <span class="microlabel-dim">spend · tokens · $/1M · in:out</span>
      </div>
      <div class="mt-2">
        <Leaderboard {models} />
      </div>
    </div>
  </div>

  {#if anyEstimated}
    <p class="microlabel-dim mt-3">≈ — estimated from local price table (proxy traffic). billed figures may differ.</p>
  {/if}
{/if}
