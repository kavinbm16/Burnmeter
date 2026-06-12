<script lang="ts">
  import { api, fmtTokens, fmtUsd } from '$lib/api'
  import type { Breakdown, KeyRow } from '$lib/api'
  import BarStrip from '$lib/components/BarStrip.svelte'

  let {
    provider,
    period,
    refreshTick,
    onback,
  }: { provider: string; period: string; refreshTick: number; onback: () => void } = $props()

  let data = $state<Breakdown | null>(null)
  let keys = $state<KeyRow[]>([])
  let error = $state<string | null>(null)
  let sortBy = $state<'cost_usd' | 'input_tokens' | 'output_tokens' | 'requests'>('cost_usd')

  $effect(() => {
    void refreshTick
    Promise.all([api.breakdown(provider, period), api.keys(provider, period)]).then(
      ([d, k]) => { data = d; keys = k.keys; error = null },
      (e) => (error = String(e))
    )
  })

  const hasAudio = $derived(
    (data?.by_model ?? []).some((m) => m.audio_input_tokens || m.audio_output_tokens)
  )

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
            {#if hasAudio}
              <th class="microlabel-dim px-3 py-3 text-right">AUD IN</th>
              <th class="microlabel-dim px-3 py-3 text-right">AUD OUT</th>
            {/if}
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
              {#if hasAudio}
                <td class="numeral px-3 py-3 text-right" style="color: var(--red)">
                  {r.audio_input_tokens ? fmtTokens(r.audio_input_tokens) : '—'}
                </td>
                <td class="numeral px-3 py-3 text-right" style="color: var(--red)">
                  {r.audio_output_tokens ? fmtTokens(r.audio_output_tokens) : '—'}
                </td>
              {/if}
              <td class="numeral px-3 py-3 text-right">{fmtTokens(r.input_tokens)}</td>
              <td class="numeral px-3 py-3 text-right">{fmtTokens(r.output_tokens)}</td>
              <td class="numeral px-3 py-3 text-right">{fmtTokens(r.requests)}</td>
              <td class="numeral px-3 py-3 text-right font-bold">{fmtUsd(r.cost_usd, !!r.cost_estimated)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    {#if keys.length > 0}
      <div class="cell !p-0">
        <div class="flex items-baseline justify-between px-5 pt-4">
          <span class="microlabel">By API key</span>
          <span class="microlabel-dim">proxy-captured traffic · masked hints only</span>
        </div>
        <table class="mt-2 w-full text-sm">
          <thead>
            <tr class="hairline-b">
              <th class="microlabel-dim px-5 py-2.5 text-left">KEY</th>
              <th class="microlabel-dim px-3 py-2.5 text-right">MODELS</th>
              <th class="microlabel-dim px-3 py-2.5 text-right">INPUT</th>
              <th class="microlabel-dim px-3 py-2.5 text-right">OUTPUT</th>
              <th class="microlabel-dim px-3 py-2.5 text-right">AUD IN</th>
              <th class="microlabel-dim px-3 py-2.5 text-right">AUD OUT</th>
              <th class="microlabel-dim px-3 py-2.5 text-right">REQS</th>
              <th class="microlabel-dim px-5 py-2.5 text-right">COST</th>
            </tr>
          </thead>
          <tbody>
            {#each keys as k (k.key_id)}
              <tr class="hairline-b transition-colors last:border-b-0 hover:bg-ink-2">
                <td class="numeral px-5 py-3 font-bold">{k.key_id}</td>
                <td class="numeral px-3 py-3 text-right">{k.model_count}</td>
                <td class="numeral px-3 py-3 text-right">{fmtTokens(k.input_tokens)}</td>
                <td class="numeral px-3 py-3 text-right">{fmtTokens(k.output_tokens)}</td>
                <td class="numeral px-3 py-3 text-right" style="color: var(--red)">
                  {k.audio_input_tokens ? fmtTokens(k.audio_input_tokens) : '—'}
                </td>
                <td class="numeral px-3 py-3 text-right" style="color: var(--red)">
                  {k.audio_output_tokens ? fmtTokens(k.audio_output_tokens) : '—'}
                </td>
                <td class="numeral px-3 py-3 text-right">{fmtTokens(k.requests)}</td>
                <td class="numeral px-5 py-3 text-right font-bold">{fmtUsd(k.cost_usd, !!k.cost_estimated)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}

    {#if data.billed_costs.length > 0}
      {@const bySku = [...data.billed_costs
        .reduce((m, b) => m.set(b.line_item, (m.get(b.line_item) ?? 0) + b.cost_usd), new Map<string, number>())
        .entries()].sort((a, b) => b[1] - a[1])}
      <div class="cell">
        <div class="flex items-baseline justify-between">
          <span class="microlabel">Provider-billed (ground truth)</span>
          <span class="microlabel-dim">via {data.billed_costs[0].source.replace('_', ' ')}</span>
        </div>
        <div class="numeral mt-2 text-2xl">{fmtUsd(billedTotal)}</div>
        <div class="mt-3">
          {#each bySku as [sku, cost] (sku)}
            <div class="hairline-b flex items-baseline justify-between py-1.5 text-xs last:border-b-0">
              <span style="color: var(--muted)">{sku || 'unattributed'}</span>
              <span class="numeral">{fmtUsd(cost)}</span>
            </div>
          {/each}
        </div>
      </div>
    {/if}
  </div>
{/if}
