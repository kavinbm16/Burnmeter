<script lang="ts">
  import { fmtTokens, fmtUsd } from '$lib/api'

  interface ModelRow {
    model: string
    provider: string
    input_tokens: number
    output_tokens: number
    cache_read_tokens: number
    requests: number
    cost_usd: number | null
    cost_estimated: number
  }

  let { models }: { models: ModelRow[] } = $props()

  const maxCost = $derived(Math.max(0.0001, ...models.map((m) => m.cost_usd ?? 0)))

  function perM(m: ModelRow): string {
    const tok = m.input_tokens + m.output_tokens
    if (!tok || m.cost_usd == null) return '—'
    return fmtUsd((m.cost_usd / tok) * 1_000_000, !!m.cost_estimated)
  }
</script>

{#if models.length === 0}
  <p class="microlabel-dim py-6 text-center">no model data in period</p>
{:else}
  <ol>
    {#each models as m, i (m.provider + m.model)}
      {@const total = m.input_tokens + m.output_tokens}
      <li class="hairline-b py-4 last:border-b-0">
        <div class="flex items-baseline gap-4">
          <span class="numeral w-8 text-base text-muted">{String(i + 1).padStart(2, '0')}</span>
          <span class="truncate text-base font-bold">{m.model}</span>
          <span class="microlabel-dim">{m.provider}</span>
          <span class="numeral ml-auto text-base">{fmtUsd(m.cost_usd, !!m.cost_estimated)}</span>
        </div>
        <div class="mt-2 flex items-center gap-4 pl-12">
          <div class="h-1.5 flex-1 bg-ink-2">
            <div class="h-full" style="width: {((m.cost_usd ?? 0) / maxCost) * 100}%; background: var(--red);"></div>
          </div>
          <span class="microlabel-dim w-24 text-right">{fmtTokens(total)} tkn</span>
          <span class="microlabel-dim w-28 text-right">{perM(m)}/1M</span>
          <span
            class="microlabel-dim w-20 text-right"
            title="input : output ratio"
          >{total ? Math.round((m.input_tokens / total) * 100) : 0}:{total ? Math.round((m.output_tokens / total) * 100) : 0}</span>
        </div>
      </li>
    {/each}
  </ol>
{/if}
