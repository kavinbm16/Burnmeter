<script lang="ts">
  import { fmtUsd } from '$lib/api'

  interface Budget {
    monthly_usd: number | null
    spent_mtd: number
    projected_eom: number
    days_elapsed: number
    days_in_month: number
  }

  let { budget, onsave, loading = false, error = null }: {
    budget: Budget | null;
    onsave: (v: number | null) => void;
    loading?: boolean;
    error?: string | null;
  } = $props()

  let editing = $state(false)
  let input = $state('')

  const pct = $derived(
    budget?.monthly_usd ? Math.min(100, (budget.spent_mtd / budget.monthly_usd) * 100) : 0
  )
  const projPct = $derived(
    budget?.monthly_usd ? Math.min(100, (budget.projected_eom / budget.monthly_usd) * 100) : 0
  )
  const over = $derived(budget?.monthly_usd != null && budget.projected_eom > budget.monthly_usd)
  const monthPct = $derived(budget ? (budget.days_elapsed / budget.days_in_month) * 100 : 0)

  const eomLabel = $derived.by(() => {
    const d = new Date()
    const next = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1))
    return next.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase()
  })

  function save() {
    const v = parseFloat(input)
    onsave(Number.isFinite(v) && v > 0 ? v : null)
    editing = false
  }
</script>

{#if loading}
  <div class="h-8 w-24 animate-pulse rounded bg-ink-2"></div>
{:else if error}
  <span class="microlabel-dim" style="color: var(--red-dim)">▲ budget unavailable</span>
{:else}
  <div class="flex h-full flex-col">
    <div class="flex items-baseline justify-between">
      <span class="microlabel">Spending pace</span>
      {#if budget?.monthly_usd != null}
        <button
          class="focus-ring microlabel-dim hover:text-paper"
          onclick={() => { input = String(budget?.monthly_usd); editing = true }}
        >
          budget {fmtUsd(budget.monthly_usd)} ✎
        </button>
      {/if}
    </div>

    {#if editing || budget?.monthly_usd == null}
      <div class="mt-3 flex gap-1">
        <input
          type="number"
          min="0"
          placeholder="monthly budget USD"
          bind:value={input}
          class="numeral w-full border border-hairline bg-ink-2 px-2 py-1.5 text-sm text-paper
                 placeholder:font-normal placeholder:text-muted focus:border-red focus:outline-none"
          onkeydown={(e) => e.key === 'Enter' && save()}
        />
        <button class="focus-ring bg-red px-3 text-xs font-bold text-ink" onclick={save}>SET</button>
      </div>
      {#if budget?.monthly_usd == null}
        <p class="microlabel-dim mt-2">set budget → pace projection</p>
      {/if}
    {:else}
      <div class="numeral mt-3 text-4xl" style:color={over ? 'var(--red)' : 'var(--paper)'}>
        {fmtUsd(budget.spent_mtd)}
      </div>

      <div class="relative mt-5 h-3 w-full bg-ink-2">
        <div class="absolute inset-y-0 left-0" style="width: {pct}%; background: var(--red);"></div>
        <div
          class="absolute inset-y-[-4px] border-l border-dashed border-paper/60"
          style="left: {projPct}%"
          title="projected end of month"
        ></div>
        <div
          class="absolute inset-y-0 border-l border-muted"
          style="left: {monthPct}%"
          title="today ({budget.days_elapsed}/{budget.days_in_month} days)"
        ></div>
      </div>

      <div class="mt-3 flex items-baseline justify-between">
        <span class="microlabel-dim">
          on pace for <span style:color={over ? 'var(--red)' : 'var(--paper)'} class="font-bold">
            {fmtUsd(budget.projected_eom)}
          </span> by {eomLabel}
        </span>
        <span class="numeral text-sm" style:color={over ? 'var(--red)' : 'var(--muted)'}>
          {pct.toFixed(0)}%
        </span>
      </div>
    {/if}
  </div>
{/if}
