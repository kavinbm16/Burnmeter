<script lang="ts">
  import { ArrowLeft } from '@lucide/svelte'
  import { api, fmtTokens, fmtUsd } from '$lib/api'
  import type { Breakdown } from '$lib/api'

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
  const maxDailyCost = $derived(
    Math.max(0.0001, ...(data?.daily ?? []).map((d) => d.cost_usd ?? 0))
  )
  const billedTotal = $derived(
    (data?.billed_costs ?? []).reduce((a, b) => a + b.cost_usd, 0)
  )
</script>

<div class="space-y-4">
  <button class="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground" onclick={onback}>
    <ArrowLeft class="size-4" /> Dashboard
  </button>

  <h1 class="text-xl font-bold capitalize">{provider}</h1>

  {#if error}
    <div class="panel border-destructive/50 p-4 text-sm text-destructive">{error}</div>
  {:else if !data}
    <div class="panel h-48 animate-pulse"></div>
  {:else if rows.length === 0}
    <div class="panel p-8 text-center text-sm text-muted-foreground">
      No data for this period.
    </div>
  {:else}
    <div class="panel p-4">
      <div class="panel-title mb-3">Daily cost</div>
      <div class="flex h-32 items-end gap-[2px]">
        {#each data.daily as d}
          <div
            class="flex-1 rounded-t-sm bg-primary/80 transition-colors hover:bg-primary"
            style="height: {((d.cost_usd ?? 0) / maxDailyCost) * 112 + 2}px"
            title={`${d.date} · ${fmtUsd(d.cost_usd)} · ${fmtTokens(d.input_tokens + d.output_tokens)} tokens`}
          ></div>
        {/each}
      </div>
    </div>

    <div class="panel overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-border text-left text-xs uppercase tracking-wider text-muted-foreground">
            <th class="px-4 py-2.5">Model</th>
            <th class="px-2 py-2.5">Source</th>
            <th class="cursor-pointer px-2 py-2.5 text-right" onclick={() => (sortBy = 'input_tokens')}>Input</th>
            <th class="cursor-pointer px-2 py-2.5 text-right" onclick={() => (sortBy = 'output_tokens')}>Output</th>
            <th class="px-2 py-2.5 text-right">Cached</th>
            <th class="cursor-pointer px-2 py-2.5 text-right" onclick={() => (sortBy = 'requests')}>Reqs</th>
            <th class="cursor-pointer px-4 py-2.5 text-right" onclick={() => (sortBy = 'cost_usd')}>Cost</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border">
          {#each rows as r}
            <tr class="hover:bg-surface-2">
              <td class="px-4 py-2.5 font-medium">{r.model}</td>
              <td class="px-2 py-2.5">
                <span class="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                  {r.source}
                </span>
              </td>
              <td class="mono px-2 py-2.5 text-right">{fmtTokens(r.input_tokens)}</td>
              <td class="mono px-2 py-2.5 text-right">{fmtTokens(r.output_tokens)}</td>
              <td class="mono px-2 py-2.5 text-right">{fmtTokens(r.cache_read_tokens)}</td>
              <td class="mono px-2 py-2.5 text-right">{fmtTokens(r.requests)}</td>
              <td class="mono px-4 py-2.5 text-right font-semibold">
                {fmtUsd(r.cost_usd, !!r.cost_estimated)}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    {#if data.billed_costs.length > 0}
      <div class="panel p-4">
        <div class="panel-title mb-2">Provider-billed cost (ground truth)</div>
        <div class="mono text-lg font-bold">{fmtUsd(billedTotal)}</div>
        <p class="mt-1 text-xs text-muted-foreground">
          From {data.billed_costs[0].source.replace('_', ' ')} · {data.billed_costs.length} daily records.
          Token-level rows above may lag or be estimates; this number is what the provider billed.
        </p>
      </div>
    {/if}
  {/if}
</div>
