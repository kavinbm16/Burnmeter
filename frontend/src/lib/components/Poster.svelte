<script lang="ts">
  import { toPng } from 'html-to-image'
  import { fmtTokens, fmtUsd } from '$lib/api'
  import type { LeaderboardModel, Overview } from '$lib/api'

  let {
    data,
    models,
    onclose,
  }: { data: Overview; models: LeaderboardModel[]; onclose: () => void } = $props()

  let node = $state<HTMLElement | null>(null)
  let exporting = $state(false)

  const monthLabel = new Date()
    .toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
    .toUpperCase()

  const dailyMax = $derived.by(() => {
    const byDay = new Map<string, number>()
    for (const p of data.daily) byDay.set(p.date, (byDay.get(p.date) ?? 0) + (p.cost_usd ?? 0))
    return { byDay, max: Math.max(0.0001, ...byDay.values()) }
  })

  async function download() {
    if (!node) return
    exporting = true
    try {
      const png = await toPng(node, { pixelRatio: 2 })
      const a = document.createElement('a')
      a.download = `burnmeter-${data.period.start}-${data.period.end}.png`
      a.href = png
      a.click()
    } finally {
      exporting = false
    }
  }
</script>

<div
  class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/80 p-6 backdrop-blur-sm"
  role="dialog"
  aria-label="Poster export"
>
  <div class="w-full max-w-2xl">
    <div class="mb-3 flex justify-end gap-2">
      <button
        class="bg-red px-4 py-2 text-xs font-bold tracking-widest text-ink disabled:opacity-50"
        onclick={download}
        disabled={exporting}
      >{exporting ? 'RENDERING…' : 'DOWNLOAD PNG'}</button>
      <button
        class="border border-hairline px-4 py-2 text-xs font-bold tracking-widest"
        onclick={onclose}
      >CLOSE</button>
    </div>

    <!-- the poster itself: fixed aspect, pure inline-safe styles -->
    <div bind:this={node} class="aspect-[3/4] w-full p-10" style="background: var(--ink); border: 1px solid var(--hairline);">
      <div class="flex justify-between hairline-b pb-3">
        <span class="text-xs font-bold" style="letter-spacing: 0.3em;">BURNMETER®</span>
        <span class="text-xs font-bold" style="color: var(--red); letter-spacing: 0.2em;">{monthLabel}</span>
      </div>

      <div class="numeral mt-12 text-8xl">
        {(data.totals.cost_usd ?? 0).toFixed(2).split('.')[0]}<span style="color: var(--red)">.</span>{(data.totals.cost_usd ?? 0).toFixed(2).split('.')[1]}
      </div>
      <div class="microlabel-dim mt-3" style="letter-spacing: 0.25em;">
        USD SPENT / {fmtTokens(data.totals.input_tokens + data.totals.output_tokens).toUpperCase()} TOKENS / {fmtTokens(data.totals.requests).toUpperCase()} REQUESTS
      </div>

      <div class="mt-10 flex h-28 items-end gap-px">
        {#each [...dailyMax.byDay.entries()].sort(([a], [b]) => a.localeCompare(b)) as [date, cost] (date)}
          <div
            class="flex-1"
            style="height: {Math.max(2, (cost / dailyMax.max) * 112)}px; background: var(--hairline);"
          ></div>
        {/each}
      </div>

      <div class="mt-10 bento grid-cols-3">
        {#each data.by_provider.slice(0, 3) as p (p.provider)}
          <div class="cell !p-4">
            <div class="microlabel">{p.provider}</div>
            <div class="numeral mt-1 text-xl">{fmtUsd(p.cost_usd, !!p.cost_estimated)}</div>
          </div>
        {/each}
      </div>

      <div class="mt-10">
        {#each models.slice(0, 5) as m, i (m.model + m.provider)}
          <div class="flex items-baseline gap-3 py-1.5 hairline-b text-xs">
            <span class="numeral" style="color: var(--muted)">{String(i + 1).padStart(2, '0')}</span>
            <span class="font-bold">{m.model}</span>
            <span class="numeral ml-auto">{fmtUsd(m.cost_usd, !!m.cost_estimated)}</span>
          </div>
        {/each}
      </div>

      <div class="microlabel-dim mt-10" style="letter-spacing: 0.25em;">
        {data.period.start} → {data.period.end} — GENERATED LOCALLY BY BURNMETER
      </div>
    </div>
  </div>
</div>
