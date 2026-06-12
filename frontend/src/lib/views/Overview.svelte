<script lang="ts">
  import { DollarSign, ArrowDownToLine, ArrowUpFromLine, Activity, ChevronRight } from '@lucide/svelte'
  import { api, fmtTokens, fmtUsd, PROVIDER_COLORS } from '$lib/api'
  import type { Overview } from '$lib/api'
  import Donut from '$lib/components/Donut.svelte'
  import StackedBars from '$lib/components/StackedBars.svelte'

  let {
    period,
    refreshTick,
    ondrill,
  }: { period: string; refreshTick: number; ondrill: (p: string) => void } = $props()

  let data = $state<Overview | null>(null)
  let error = $state<string | null>(null)

  $effect(() => {
    void refreshTick
    api.overview(period).then(
      (d) => { data = d; error = null },
      (e) => (error = String(e))
    )
  })

  const anyEstimated = $derived(data?.by_provider.some((p) => p.cost_estimated) ?? false)
</script>

{#if error}
  <div class="panel border-destructive/50 p-4 text-sm text-destructive">{error}</div>
{:else if !data}
  <div class="grid grid-cols-4 gap-4">
    {#each Array(4) as _}
      <div class="panel h-24 animate-pulse"></div>
    {/each}
  </div>
{:else if data.by_provider.length === 0}
  <div class="panel flex flex-col items-center gap-3 p-12 text-center">
    <DollarSign class="size-8 text-muted-foreground" />
    <h2 class="text-lg font-semibold">No usage data yet</h2>
    <p class="max-w-md text-sm text-muted-foreground">
      Add a provider key in the Providers tab. OpenAI backfills the last 90 days automatically;
      Gemini usage appears as soon as traffic flows through the local proxy.
    </p>
  </div>
{:else}
  <div class="space-y-4">
    <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <div class="panel p-4">
        <div class="panel-title flex items-center gap-1.5"><DollarSign class="size-3.5" /> Spend</div>
        <div class="mono mt-2 text-2xl font-bold">
          {fmtUsd(data.totals.cost_usd, anyEstimated)}
        </div>
        <div class="text-xs text-muted-foreground">{data.period.start} → {data.period.end}</div>
      </div>
      <div class="panel p-4">
        <div class="panel-title flex items-center gap-1.5"><ArrowDownToLine class="size-3.5" /> Input tokens</div>
        <div class="mono mt-2 text-2xl font-bold">{fmtTokens(data.totals.input_tokens)}</div>
      </div>
      <div class="panel p-4">
        <div class="panel-title flex items-center gap-1.5"><ArrowUpFromLine class="size-3.5" /> Output tokens</div>
        <div class="mono mt-2 text-2xl font-bold">{fmtTokens(data.totals.output_tokens)}</div>
      </div>
      <div class="panel p-4">
        <div class="panel-title flex items-center gap-1.5"><Activity class="size-3.5" /> Requests</div>
        <div class="mono mt-2 text-2xl font-bold">{fmtTokens(data.totals.requests)}</div>
      </div>
    </div>

    <div class="grid gap-4 lg:grid-cols-5">
      <div class="panel p-4 lg:col-span-3">
        <div class="panel-title mb-3">Daily spend</div>
        <StackedBars daily={data.daily} />
      </div>
      <div class="panel p-4 lg:col-span-2">
        <div class="panel-title mb-3">Provider share</div>
        <Donut
          slices={data.by_provider.map((p) => ({ name: p.provider, value: p.cost_usd ?? 0 }))}
        />
      </div>
    </div>

    <div class="panel divide-y divide-border">
      {#each data.by_provider as p}
        <button
          class="flex w-full items-center gap-4 px-4 py-3 text-left transition-colors hover:bg-surface-2"
          onclick={() => ondrill(p.provider)}
        >
          <span class="size-2.5 rounded-sm" style="background: {PROVIDER_COLORS[p.provider] ?? 'var(--chart-3)'}"></span>
          <span class="w-28 font-medium capitalize">{p.provider}</span>
          <span class="mono text-sm text-muted-foreground">
            {fmtTokens(p.input_tokens)} in · {fmtTokens(p.output_tokens)} out
            {#if p.cache_read_tokens}· {fmtTokens(p.cache_read_tokens)} cached{/if}
          </span>
          <span class="mono ml-auto font-semibold">{fmtUsd(p.cost_usd, !!p.cost_estimated)}</span>
          <ChevronRight class="size-4 text-muted-foreground" />
        </button>
      {/each}
    </div>

    {#if anyEstimated}
      <p class="text-xs text-muted-foreground">
        ≈ values are estimated from the local price table (proxy-captured traffic). Provider-billed
        figures may differ slightly.
      </p>
    {/if}
  </div>
{/if}
