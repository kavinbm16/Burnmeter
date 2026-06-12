<script lang="ts">
  import { api, fmtTokens, fmtUsd } from '$lib/api'
  import type { Breakdown } from '$lib/api'
  import BarStrip from '$lib/components/BarStrip.svelte'

  let {
    provider,
    period,
    refreshTick,
    onback,
  }: { provider: string; period: string; refreshTick: number; onback: () => void } = $props()

  let data = $state<Breakdown | null>(null)
  let error = $state<string | null>(null)
  let sortBy = $state<'cost_usd' | 'input_tokens' | 'output_tokens' | 'requests'>('cost_usd')

  $effect(() => {
    void refreshTick
    api.breakdown(provider, period).then(
      (d) => { data = d; error = null },
      (e) => (error = String(e))
    )
  })

  const rows = $derived(
    [...(data?.by_model ?? [])].sort((a, b) => (b[sortBy] ?? 0) - (a[sortBy] ?? 0))
  )
  const bars = $derived(
    (data?.daily ?? []).map((d) => ({
      date: d.date,
      cost: d.cost_usd ?? 0,
      tokens: d.input_tokens + d.output_tokens,
    }))
  )
  const billedTotal = $derived((data?.billed_costs ?? []).reduce((a, b) => a + b.cost_usd, 0))

  const COLS: { key: typeof sortBy; label: string }[] = [
    { key: 'input_tokens', label: 'INPUT' },
    { key: 'output_tokens', label: 'OUTPUT' },
    { key: 'requests', label: 'REQS' },
    { key: 'cost_usd', label: 'COST' },
  ]
</script>

<button class="microlabel-dim mb-4 hover:text-paper" onclick={onback}>← DASHBOARD</button>

<h1 class="numeral mb-4 text-3xl uppercase">{provider}</h1>

{#if error}
  <div class="bento grid-cols-1"><div class="cell text-sm" style="color: var(--red)">{error}</div></div>
{:else if !data}
  <div class="bento grid-cols-1"><div class="cell h-48 animate-pulse"></div></div>
{:else if rows.length === 0}
  <div class="bento grid-cols-1"><div class="cell py-12 text-center"><span class="microlabel-dim">no data in period</span></div></div>
{:else}
  <div class="bento grid-cols-1">
    <div class="cell">
      <div class="microlabel mb-3">Daily cost</div>
      <BarStrip {bars} height={110} />
    </div>

    <div class="cell !p-0">
      <table class="w-full text-sm">
        <thead>
          <tr class="hairline-b">
            <th class="microlabel-dim px-5 py-3 text-left">MODEL</th>
            <th class="microlabel-dim px-2 py-3 text-left">SOURCE</th>
            {#each COLS as c (c.key)}
              <th class="px-3 py-3 text-right">
                <button
                  class="microlabel-dim hover:text-paper"
                  style={sortBy === c.key ? 'color: var(--red);' : ''}
                  onclick={() => (sortBy = c.key)}
                >{c.label}{sortBy === c.key ? ' ▾' : ''}</button>
              </th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each rows as r (r.model + r.source)}
            <tr class="hairline-b transition-colors last:border-b-0 hover:bg-ink-2">
              <td class="px-5 py-3 font-bold">{r.model}</td>
              <td class="microlabel-dim px-2 py-3">{r.source}</td>
              <td class="numeral px-3 py-3 text-right">{fmtTokens(r.input_tokens)}</td>
              <td class="numeral px-3 py-3 text-right">{fmtTokens(r.output_tokens)}</td>
              <td class="numeral px-3 py-3 text-right">{fmtTokens(r.requests)}</td>
              <td class="numeral px-3 py-3 text-right font-bold">{fmtUsd(r.cost_usd, !!r.cost_estimated)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    {#if data.billed_costs.length > 0}
      <div class="cell">
        <div class="microlabel">Provider-billed (ground truth)</div>
        <div class="numeral mt-2 text-2xl">{fmtUsd(billedTotal)}</div>
        <p class="microlabel-dim mt-1">
          {data.billed_costs.length} daily records via {data.billed_costs[0].source.replace('_', ' ')}
        </p>
      </div>
    {/if}
  </div>
{/if}
