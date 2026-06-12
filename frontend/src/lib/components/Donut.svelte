<script lang="ts">
  import { arc, pie } from 'd3-shape'
  import { PROVIDER_COLORS, fmtUsd } from '$lib/api'

  let { slices }: { slices: { name: string; value: number }[] } = $props()

  const arcs = $derived.by(() => {
    const gen = pie<{ name: string; value: number }>().value((d) => d.value).sort(null)
    const a = arc<any>().innerRadius(52).outerRadius(78).cornerRadius(3).padAngle(0.02)
    return gen(slices.filter((s) => s.value > 0)).map((p) => ({
      d: a(p)!,
      name: p.data.name,
      value: p.data.value,
    }))
  })

  const total = $derived(slices.reduce((a, s) => a + s.value, 0))
</script>

{#if total === 0}
  <div class="flex h-44 items-center justify-center text-sm text-muted-foreground">No spend yet.</div>
{:else}
  <div class="flex items-center gap-6">
    <svg viewBox="-85 -85 170 170" class="size-44">
      {#each arcs as a}
        <path d={a.d} fill={PROVIDER_COLORS[a.name] ?? 'var(--chart-3)'} opacity="0.9">
          <title>{a.name}: {fmtUsd(a.value)}</title>
        </path>
      {/each}
      <text text-anchor="middle" dy="-2" class="fill-[var(--foreground)] mono" font-size="15" font-weight="700">
        {fmtUsd(total)}
      </text>
      <text text-anchor="middle" dy="14" class="fill-[var(--muted-foreground)]" font-size="9">
        total spend
      </text>
    </svg>
    <ul class="space-y-1.5 text-sm">
      {#each arcs as a}
        <li class="flex items-center gap-2">
          <span class="size-2.5 rounded-sm" style="background: {PROVIDER_COLORS[a.name] ?? 'var(--chart-3)'}"></span>
          <span class="capitalize">{a.name}</span>
          <span class="mono text-muted-foreground">{fmtUsd(a.value)}</span>
          <span class="text-xs text-muted-foreground">({((a.value / total) * 100).toFixed(0)}%)</span>
        </li>
      {/each}
    </ul>
  </div>
{/if}
