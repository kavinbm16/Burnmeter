<script lang="ts">
  import { fmtUsd } from '$lib/api'

  interface Day {
    date: string
    cost_usd: number | null
    total_tokens: number
    requests: number
  }

  let {
    days,
    start,
    end,
    selected = null,
    onselect,
    loading = false,
    reconciledDates = new Set<string>(),
  }: {
    days: Day[]
    start: string
    end: string
    selected?: string | null
    onselect: (date: string | null) => void
    loading?: boolean
    reconciledDates?: Set<string>
  } = $props()

  const byDate = $derived(new Map(days.map((d) => [d.date, d])))

  // build full grid from start..end, aligned to weeks (columns = weeks, rows = weekday)
  const grid = $derived.by(() => {
    const out: { date: string; cost: number }[] = []
    const s = new Date(start + 'T00:00:00Z')
    const e = new Date(end + 'T00:00:00Z')
    for (let t = s.getTime(); t <= e.getTime(); t += 86400000) {
      const date = new Date(t).toISOString().slice(0, 10)
      out.push({ date, cost: byDate.get(date)?.cost_usd ?? 0 })
    }
    return out
  })

  const max = $derived(Math.max(0.0001, ...grid.map((d) => d.cost)))

  function level(cost: number): string {
    if (cost <= 0) return 'var(--ink-2)'
    const r = cost / max
    if (r < 0.25) return 'var(--heat-1)'
    if (r < 0.5) return 'var(--heat-2)'
    if (r < 0.75) return 'var(--heat-3)'
    return 'var(--heat-4)'
  }

  const startPad = $derived(new Date(start + 'T00:00:00Z').getUTCDay())
</script>

{#if loading}
  <div class="grid animate-pulse gap-px" style="grid-template-columns: repeat(17, 1fr)">
    {#each { length: 120 } as _}
      <div class="aspect-square w-full min-w-[8px] bg-ink-2"></div>
    {/each}
  </div>
{:else if days.every(d => d.cost_usd === 0 || d.cost_usd === null)}
  <p class="microlabel-dim py-4 text-center">no spend recorded in this period</p>
{:else}
  <div
    class="grid grid-flow-col gap-[2px]"
    style="grid-template-rows: repeat(7, 1fr);"
    role="listbox"
    aria-label="Daily spend heatmap"
  >
    {#each Array(startPad) as _}
      <span></span>
    {/each}
    {#each grid as d (d.date)}
      <button
        role="option"
        aria-selected={selected === d.date}
        class="focus-ring relative aspect-square w-full min-w-[8px] transition-transform hover:scale-125"
        style="background: {selected === d.date ? 'var(--red)' : level(d.cost)};"
        title={`${d.date} · ${fmtUsd(d.cost)}`}
        onclick={() => onselect(selected === d.date ? null : d.date)}
      >
        {#if reconciledDates.has(d.date)}
          <span class="absolute bottom-0.5 right-0.5 h-1 w-1 rounded-full bg-current opacity-60"></span>
        {/if}
      </button>
    {/each}
  </div>
  <div class="mt-2 flex items-center justify-between">
    <span class="microlabel-dim">{start} → {end}</span>
    <span class="flex items-center gap-[3px]">
      <span class="microlabel-dim mr-1">less</span>
      {#each ['var(--ink-2)', 'var(--heat-1)', 'var(--heat-2)', 'var(--heat-3)', 'var(--heat-4)'] as c}
        <span class="size-2" style="background: {c}"></span>
      {/each}
      <span class="microlabel-dim ml-1">more</span>
    </span>
  </div>
{/if}
