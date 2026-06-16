<script lang="ts">
  import { api, fmtUsd } from '$lib/api'
  import type { Budget } from '$lib/api'

  let budget = $state<Budget | null>(null)
  let error = $state<string | null>(null)
  let editing = $state(false)
  let inputVal = $state('')
  let saving = $state(false)

  async function load() {
    try {
      budget = await api.budget()
      error = null
    } catch (e) {
      console.error('[Budget] load failed:', e)
      error = 'Failed to load budget data.'
    }
  }

  load()

  function startEdit() {
    inputVal = budget?.monthly_usd != null ? String(budget.monthly_usd) : ''
    editing = true
  }

  async function saveLimit() {
    const val = inputVal.trim()
    const num = val === '' ? null : parseFloat(val)
    if (val !== '' && (isNaN(num!) || num! < 0)) return
    saving = true
    try {
      await api.setBudget(num ?? null)
      await load()
      editing = false
    } catch (e) {
      console.error('[Budget] save failed:', e)
      error = 'Failed to save budget limit.'
    } finally {
      saving = false
    }
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') saveLimit()
    if (e.key === 'Escape') editing = false
  }

  const burnPct = $derived.by(() => {
    if (!budget || !budget.monthly_usd) return null
    return Math.min(100, (budget.projected_eom / budget.monthly_usd) * 100)
  })

  const overBudget = $derived.by(() => {
    if (!budget || !budget.monthly_usd) return false
    return budget.projected_eom > budget.monthly_usd
  })

  const remaining = $derived.by(() => {
    if (!budget || !budget.monthly_usd) return null
    return budget.monthly_usd - budget.spent_mtd
  })

  const daysLeft = $derived.by(() => {
    if (!budget) return null
    return budget.days_in_month - budget.days_elapsed
  })
</script>

{#if error}
  <div class="bento grid-cols-1">
    <div class="cell text-xs" style="color: var(--red)">{error}</div>
  </div>
{:else if !budget}
  <div class="bento grid-cols-1">
    <div class="cell h-48 animate-pulse"></div>
  </div>
{:else}
  <div class="bento lg:grid-cols-3">
    <!-- left: big numerals -->
    <div class="cell flex flex-col gap-6 lg:col-span-1">
      <div>
        <div class="numeral text-5xl">{fmtUsd(budget.spent_mtd)}</div>
        <div class="microlabel mt-1">spent month-to-date</div>
        <div class="microlabel-dim mt-0.5">{budget.days_elapsed} of {budget.days_in_month} days</div>
      </div>

      <div>
        <div class="numeral text-5xl" style={overBudget ? 'color: var(--red)' : ''}>{fmtUsd(budget.projected_eom)}</div>
        <div class="microlabel mt-1">projected end-of-month</div>
      </div>

      {#if remaining !== null}
        <div>
          <div class="numeral text-5xl" style={remaining < 0 ? 'color: var(--red)' : ''}>{fmtUsd(Math.abs(remaining))}</div>
          <div class="microlabel mt-1">{remaining < 0 ? 'over budget' : 'remaining'}</div>
        </div>
      {/if}
    </div>

    <!-- right: budget control + burn bar -->
    <div class="cell lg:col-span-2">
      <div class="microlabel mb-4">Monthly Budget Limit</div>

      {#if editing}
        <div class="flex items-center gap-3">
          <span class="microlabel-dim text-lg">$</span>
          <input
            type="number"
            min="0"
            step="1"
            bind:value={inputVal}
            onkeydown={onKeydown}
            class="numeral w-40 border border-hairline bg-ink-2 px-3 py-2 text-xl focus:border-red focus:outline-none"
            placeholder="0"
          />
          <button
            class="focus-ring microlabel border border-hairline px-3 py-2 transition-colors hover:border-red disabled:opacity-40"
            onclick={saveLimit}
            disabled={saving}
          >{saving ? 'SAVING…' : 'SET'}</button>
          <button
            class="focus-ring microlabel-dim px-2 py-2 hover:text-paper"
            onclick={() => (editing = false)}
          >CANCEL</button>
        </div>
      {:else}
        <div class="flex items-baseline gap-4">
          <div class="numeral text-4xl">
            {budget.monthly_usd != null ? fmtUsd(budget.monthly_usd) : '—'}
          </div>
          <button
            class="focus-ring microlabel-dim hover:text-paper"
            onclick={startEdit}
          >{budget.monthly_usd != null ? 'CHANGE' : 'SET LIMIT'}</button>
        </div>
      {/if}

      {#if burnPct !== null}
        <div class="mt-8">
          <div class="mb-2 flex items-baseline justify-between">
            <span class="microlabel">Burn rate</span>
            <span class="numeral text-sm" style={overBudget ? 'color: var(--red)' : 'color: var(--muted)'}>{burnPct.toFixed(0)}% of budget</span>
          </div>
          <div class="h-3 w-full overflow-hidden border border-hairline" style="background: var(--ink-2)">
            <div
              class="h-full transition-all duration-500"
              style="width: {burnPct}%; background: {overBudget ? 'var(--red)' : 'var(--heat-2)'};"
            ></div>
          </div>
          <div class="microlabel-dim mt-2">
            {#if overBudget}
              OVER BUDGET · {daysLeft} days left in month
            {:else if burnPct > 80}
              WARNING · {daysLeft} days left · on pace to exceed limit
            {:else}
              {daysLeft} days left · on track
            {/if}
          </div>
        </div>
      {:else}
        <div class="mt-8">
          <div class="microlabel-dim">Set a monthly limit to see burn rate.</div>
        </div>
      {/if}

      {#if !budget.monthly_usd}
        <div class="mt-6 border-t border-hairline pt-4">
          <div class="microlabel-dim text-xs leading-relaxed">
            Set a monthly limit to track burn rate and get over-budget warnings. Limits are stored locally and never sent to any provider.
          </div>
        </div>
      {/if}
    </div>
  </div>
{/if}
