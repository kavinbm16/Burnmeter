<script lang="ts">
  import { api, fmtUsd, fmtTokens } from '$lib/api'
  import type { LeaderboardModel } from '$lib/api'

  let period = $state('mtd')
  let models = $state<LeaderboardModel[]>([])
  let loading = $state(true)
  let error = $state<string | null>(null)

  // Comprehensive pricing: input_per_m, output_per_m (USD per 1M tokens)
  // Sources: provider pricing pages, June 2026
  const BASE_PRICING: Record<string, { input_per_m: number; output_per_m: number }> = {
    // Claude (Anthropic)
    'claude-opus-4':            { input_per_m: 15.00, output_per_m: 75.00 },
    'claude-opus-4-5':          { input_per_m: 15.00, output_per_m: 75.00 },
    'claude-sonnet-4':          { input_per_m: 3.00,  output_per_m: 15.00 },
    'claude-sonnet-4-6':        { input_per_m: 3.00,  output_per_m: 15.00 },
    'claude-sonnet-4-5':        { input_per_m: 3.00,  output_per_m: 15.00 },
    'claude-haiku-4-5':         { input_per_m: 0.80,  output_per_m: 4.00  },
    'claude-haiku-3-5':         { input_per_m: 0.80,  output_per_m: 4.00  },
    'claude-haiku-3':           { input_per_m: 0.25,  output_per_m: 1.25  },
    // OpenAI
    'gpt-4o':                   { input_per_m: 2.50,  output_per_m: 10.00 },
    'gpt-4o-mini':              { input_per_m: 0.15,  output_per_m: 0.60  },
    'gpt-4.1':                  { input_per_m: 2.00,  output_per_m: 8.00  },
    'gpt-4.1-mini':             { input_per_m: 0.40,  output_per_m: 1.60  },
    'gpt-4.1-nano':             { input_per_m: 0.10,  output_per_m: 0.40  },
    'o3':                       { input_per_m: 10.00, output_per_m: 40.00 },
    'o4-mini':                  { input_per_m: 1.10,  output_per_m: 4.40  },
    'o3-mini':                  { input_per_m: 1.10,  output_per_m: 4.40  },
    // Gemini
    'gemini-2.5-pro':           { input_per_m: 1.25,  output_per_m: 10.00 },
    'gemini-2.5-flash':         { input_per_m: 0.30,  output_per_m: 2.50  },
    'gemini-2.5-flash-lite':    { input_per_m: 0.10,  output_per_m: 0.40  },
    'gemini-2.0-flash':         { input_per_m: 0.10,  output_per_m: 0.40  },
    'gemini-2.0-flash-lite':    { input_per_m: 0.075, output_per_m: 0.30  },
  }

  // For each model prefix: ordered list of cheaper alternatives to suggest
  const DOWNGRADES: Record<string, string[]> = {
    'claude-opus-4':         ['claude-sonnet-4-6', 'claude-haiku-4-5'],
    'claude-sonnet-4':       ['claude-haiku-4-5'],
    'claude-sonnet-4-6':     ['claude-haiku-4-5'],
    'claude-sonnet-4-5':     ['claude-haiku-4-5'],
    'gpt-4o':                ['gpt-4o-mini'],
    'gpt-4.1':               ['gpt-4.1-mini', 'gpt-4.1-nano'],
    'o3':                    ['o4-mini'],
    'gemini-2.5-pro':        ['gemini-2.5-flash', 'gemini-2.0-flash'],
    'gemini-2.5-flash':      ['gemini-2.5-flash-lite', 'gemini-2.0-flash'],
  }

  function lookupPricing(model: string) {
    // exact match first, then longest prefix match
    if (BASE_PRICING[model]) return BASE_PRICING[model]
    const candidates = Object.keys(BASE_PRICING).filter(k => model.startsWith(k))
    if (!candidates.length) return null
    return BASE_PRICING[candidates.sort((a, b) => b.length - a.length)[0]]
  }

  function lookupDowngrades(model: string): string[] {
    const key = Object.keys(DOWNGRADES).find(k => model.startsWith(k))
    return key ? DOWNGRADES[key] : []
  }

  function computeCost(m: LeaderboardModel, rates: { input_per_m: number; output_per_m: number }) {
    return (m.input_tokens * rates.input_per_m + m.output_tokens * rates.output_per_m) / 1_000_000
  }

  interface Suggestion {
    model: LeaderboardModel
    currentCost: number
    actualCost: number | null
    alternatives: { name: string; cost: number; savings: number }[]
    topSavings: number
  }

  const suggestions = $derived.by((): Suggestion[] => {
    return models
      .map((m) => {
        const rates = lookupPricing(m.model)
        const currentCost = rates ? computeCost(m, rates) : 0
        const actualCost = m.cost_usd ?? (m.cost_estimated > 0 ? m.cost_estimated : null)
        const alternatives = lookupDowngrades(m.model)
          .map((alt) => {
            const altRates = lookupPricing(alt)
            if (!altRates) return null
            const altCost = (m.input_tokens * altRates.input_per_m + m.output_tokens * altRates.output_per_m) / 1_000_000
            return { name: alt, cost: altCost, savings: currentCost - altCost }
          })
          .filter((a): a is { name: string; cost: number; savings: number } => a !== null && a.savings > 0)
        return { model: m, currentCost, actualCost, alternatives, topSavings: alternatives[0]?.savings ?? 0 }
      })
      .filter((s) => s.alternatives.length > 0 && s.currentCost > 0)
      .sort((a, b) => b.topSavings - a.topSavings)
  })

  const totalSavings = $derived(suggestions.reduce((sum, s) => sum + s.topSavings, 0))

  async function load() {
    loading = true
    error = null
    try {
      const res = await api.models(period)
      models = res.models
    } catch (e) {
      console.error('[Optimizer] load failed:', e)
      error = 'Failed to load model usage.'
    } finally {
      loading = false
    }
  }

  $effect(() => { period; load() })
</script>

<div class="space-y-6">
  <!-- header row -->
  <div class="flex items-center justify-between">
    <div>
      <div class="microlabel-dim">potential savings if you downgrade models</div>
    </div>
    <select
      bind:value={period}
      class="microlabel-dim cursor-pointer border border-hairline bg-ink px-2 py-1.5 focus:border-red focus:outline-none"
    >
      <option value="today">Today</option>
      <option value="yesterday">Yesterday</option>
      <option value="7d">7D</option>
      <option value="mtd">This month</option>
      <option value="30d">30D</option>
      <option value="90d">90D</option>
    </select>
  </div>

  {#if error}
    <div class="bento grid-cols-1">
      <div class="cell text-xs" style="color: var(--red)">{error}</div>
    </div>
  {:else if loading}
    <div class="bento grid-cols-1"><div class="cell h-48 animate-pulse"></div></div>
  {:else if suggestions.length === 0}
    <div class="bento grid-cols-1">
      <div class="cell">
        <div class="numeral text-4xl">—</div>
        <div class="microlabel mt-2">no optimization opportunities found</div>
        <div class="microlabel-dim mt-1">
          {models.length === 0
            ? 'No model usage data for this period.'
            : 'All models in use are already the cheapest in their tier.'}
        </div>
      </div>
    </div>
  {:else}
    <!-- savings callout -->
    <div class="bento grid-cols-1 lg:grid-cols-3">
      <div class="cell">
        <div class="numeral text-5xl" style="color: var(--red)">{fmtUsd(totalSavings)}</div>
        <div class="microlabel mt-1">potential savings this period</div>
        <div class="microlabel-dim mt-1">if top cheaper model used for each request</div>
      </div>
      <div class="cell lg:col-span-2">
        <div class="microlabel mb-3">savings breakdown</div>
        <!-- mini bar chart -->
        {#each suggestions.slice(0, 5) as s}
          {@const pct = totalSavings > 0 ? (s.topSavings / totalSavings) * 100 : 0}
          <div class="mb-2 flex items-center gap-3">
            <div class="microlabel-dim w-44 truncate text-xs">{s.model.model}</div>
            <div class="h-2 flex-1 overflow-hidden border border-hairline" style="background: var(--ink-2)">
              <div class="h-full" style="width: {pct}%; background: var(--heat-2);"></div>
            </div>
            <div class="numeral w-16 text-right text-xs">{fmtUsd(s.topSavings)}</div>
          </div>
        {/each}
      </div>
    </div>

    <!-- per-model detail rows -->
    {#each suggestions as s}
      <div class="bento grid-cols-1">
        <div class="cell">
          <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:gap-8">
            <!-- model info -->
            <div class="min-w-48">
              <div class="numeral text-base font-bold">{s.model.model}</div>
              <div class="microlabel-dim mt-0.5">{fmtTokens(s.model.input_tokens + s.model.output_tokens)} tokens · {s.model.requests} req</div>
              <div class="numeral mt-2 text-2xl">{fmtUsd(s.currentCost)}</div>
              <div class="microlabel-dim">estimated cost</div>
            </div>

            <!-- arrow -->
            <div class="flex items-center pt-6 text-xl" style="color: var(--muted)">→</div>

            <!-- alternatives -->
            <div class="flex flex-1 flex-col gap-3 lg:flex-row lg:gap-6">
              {#each s.alternatives as alt}
                <div class="flex-1 border border-hairline p-4" style="background: var(--ink-2)">
                  <div class="numeral text-base font-bold">{alt.name}</div>
                  <div class="numeral mt-2 text-2xl">{fmtUsd(alt.cost)}</div>
                  <div class="microlabel-dim">same token count</div>
                  <div class="mt-2 inline-block border border-hairline px-2 py-0.5">
                    <span class="numeral text-xs" style="color: var(--red)">save {fmtUsd(alt.savings)}</span>
                    <span class="microlabel-dim ml-1 text-xs">({((alt.savings / s.currentCost) * 100).toFixed(0)}%)</span>
                  </div>
                </div>
              {/each}
            </div>
          </div>
        </div>
      </div>
    {/each}

    <div class="microlabel-dim px-1 text-xs">
      Savings assume same token volume at alternative model rates. Quality varies — test before switching production workloads.
    </div>
  {/if}
</div>
