<script lang="ts">
  import { fmtUsd, fmtTokens } from '$lib/api'

  interface Bar {
    date: string
    cost: number
    tokens?: number
  }

  let {
    bars,
    height = 120,
    highlight = null,
  }: { bars: Bar[]; height?: number; highlight?: string | null } = $props()

  const max = $derived(Math.max(0.0001, ...bars.map((b) => b.cost)))
</script>

{#if bars.length === 0}
  <div class="flex items-center justify-center" style="height: {height}px">
    <span class="microlabel-dim">no data in period</span>
  </div>
{:else}
  <div class="flex items-end gap-px" style="height: {height}px">
    {#each bars as b (b.date)}
      <div
        class="group relative flex-1 transition-colors"
        style="height: {Math.max(2, (b.cost / max) * height)}px;
               background: {highlight === b.date ? 'var(--red)' : 'var(--hairline)'};"
        title={`${b.date} · ${fmtUsd(b.cost)}${b.tokens != null ? ` · ${fmtTokens(b.tokens)} tkn` : ''}`}
      >
        <div class="absolute inset-0 opacity-0 transition-opacity group-hover:opacity-100" style="background: var(--red);"></div>
      </div>
    {/each}
  </div>
  <div class="mt-1.5 flex justify-between">
    <span class="microlabel-dim">{bars[0].date}</span>
    <span class="microlabel-dim">{bars[bars.length - 1].date}</span>
  </div>
{/if}
