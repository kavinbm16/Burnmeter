<script lang="ts">
  import { PROVIDER_COLORS, fmtUsd } from '$lib/api'
  import type { DailyPoint } from '$lib/api'

  let { daily }: { daily: DailyPoint[] } = $props()

  const days = $derived.by(() => {
    const map = new Map<string, Record<string, number>>()
    for (const p of daily) {
      const d = map.get(p.date) ?? {}
      d[p.provider] = (d[p.provider] ?? 0) + (p.cost_usd ?? 0)
      map.set(p.date, d)
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b))
  })

  const maxDay = $derived(
    Math.max(0.0001, ...days.map(([, v]) => Object.values(v).reduce((a, b) => a + b, 0)))
  )
</script>

{#if days.length === 0}
  <div class="flex h-44 items-center justify-center text-sm text-muted-foreground">
    No usage data yet for this period.
  </div>
{:else}
  <div class="flex h-44 items-end gap-[2px]">
    {#each days as [date, byProvider]}
      {@const total = Object.values(byProvider).reduce((a, b) => a + b, 0)}
      <div
        class="group relative flex flex-1 flex-col-reverse rounded-t-sm"
        title={`${date} · ${fmtUsd(total)}`}
      >
        {#each Object.entries(byProvider) as [provider, cost]}
          <div
            style="height: {(cost / maxDay) * 160}px; background: {PROVIDER_COLORS[provider] ?? 'var(--chart-3)'}"
            class="w-full opacity-85 transition-opacity group-hover:opacity-100"
          ></div>
        {/each}
      </div>
    {/each}
  </div>
  <div class="mt-1 flex justify-between text-[10px] text-muted-foreground mono">
    <span>{days[0][0]}</span>
    <span>{days[days.length - 1][0]}</span>
  </div>
{/if}
