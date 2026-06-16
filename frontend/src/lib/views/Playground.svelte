<script lang="ts">
  import { encode, decode } from 'gpt-tokenizer'
  import { api, fmtUsd } from '$lib/api'

  let text = $state(
    'Burnmeter splits this sentence into tokens — the unit every provider bills you for.'
  )
  let pricing = $state<Record<string, { input_per_m: number; output_per_m: number }>>({})
  let tokenizerError = $state<string | null>(null)

  api.pricing().then((p) => (pricing = p))

  // OpenAI display rates for comparison (estimates; real OpenAI cost comes from
  // the Costs API — this table only powers the playground what-if).
  const OPENAI_RATES: Record<string, { input_per_m: number; output_per_m: number }> = {
    'gpt-4o': { input_per_m: 2.5, output_per_m: 10 },
    'gpt-4o-mini': { input_per_m: 0.15, output_per_m: 0.6 },
    'gpt-4.1': { input_per_m: 2.0, output_per_m: 8 },
  }

  const tokens = $derived.by(() => {
    try {
      tokenizerError = null
      return encode(text).map((id) => ({ id, str: decode([id]) }))
    } catch (err) {
      console.error('[Playground] Tokenization failed:', err)
      tokenizerError = 'Unable to tokenize text. Try different input.'
      return []
    }
  })

  const allRates = $derived({ ...OPENAI_RATES, ...pricing })

  // chip palette: muted reds/greys cycling — stays inside the poster language
  const CHIP = [
    'background: var(--heat-1); color: var(--paper);',
    'background: var(--ink-2); color: var(--paper);',
    'background: var(--heat-2); color: var(--paper);',
    'background: var(--hairline); color: var(--paper);',
  ]
</script>

<div class="bento grid-cols-1 lg:grid-cols-3">
  <div class="cell lg:col-span-2">
    <div class="microlabel">Input text</div>
    <textarea
      bind:value={text}
      rows="5"
      class="numeral mt-3 w-full resize-y border border-hairline bg-ink-2 p-3 text-sm leading-relaxed
             text-paper focus:border-red focus:outline-none"
      placeholder="paste anything…"
    ></textarea>

    <div class="mt-5 flex items-baseline justify-between">
      <span class="microlabel">Tokenized</span>
      <span class="microlabel-dim">OpenAI token encoding · runs locally, text never leaves this page</span>
    </div>
    {#if tokenizerError}
      <div class="mt-3 rounded border border-red/30 bg-red/5 px-3 py-2 text-xs text-red">
        {tokenizerError}
      </div>
    {:else}
      <div class="mt-3 flex flex-wrap gap-1 leading-relaxed">
        {#each tokens as t, i (i)}
          <span
            class="numeral px-1.5 py-0.5 text-xs"
            style={CHIP[i % CHIP.length]}
            title={`token #${i} · id ${t.id}`}
          >{t.str.replace(/ /g, '␣').replace(/\n/g, '⏎')}</span>
        {/each}
      </div>
    {/if}
  </div>

  <div class="cell">
    <div class="numeral text-6xl">
      {tokens.length}<span style="color: var(--red)">.</span>
    </div>
    <div class="microlabel mt-1">tokens</div>
    <div class="microlabel-dim mt-1">{text.length} chars · {(text.length / Math.max(1, tokens.length)).toFixed(1)} chars/token</div>

    <div class="microlabel mt-8 hairline-b pb-2">cost as input, per model</div>
    <table class="w-full text-sm">
      <tbody>
        {#each Object.entries(allRates) as [model, rate] (model)}
          <tr class="hairline-b last:border-b-0">
            <td class="py-2 pr-2 text-xs font-bold">{model}</td>
            <td class="numeral py-2 text-right text-xs" style="color: var(--muted)">
              ≈{fmtUsd((tokens.length * rate.input_per_m) / 1_000_000)}
            </td>
            <td class="numeral py-2 pl-2 text-right text-xs">
              ×1K = ≈{fmtUsd((tokens.length * 1000 * rate.input_per_m) / 1_000_000)}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
    <p class="microlabel-dim mt-3">
      counts use OpenAI's o200k BPE; other providers tokenize differently — treat non-OpenAI rows
      as close approximations.
    </p>
  </div>
</div>
