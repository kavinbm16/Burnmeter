<script lang="ts">
  // Rolling digit display: each digit is a vertical strip of 0-9 translated
  // to the current value. Non-digits (.,$≈MKB) render as static glyphs.
  let { value, class: cls = '' }: { value: string; class?: string } = $props()

  const chars = $derived(value.split(''))
</script>

<span class="numeral inline-flex overflow-hidden {cls}" aria-label={value}>
  {#each chars as ch, i (i)}
    {#if ch >= '0' && ch <= '9'}
      <span class="relative inline-block" style="height: 1em; width: 0.62em;" aria-hidden="true">
        <span
          class="absolute left-0 top-0 flex flex-col transition-transform duration-500 ease-out"
          style="transform: translateY({-Number(ch)}em);"
        >
          {#each Array(10) as _, d}
            <span style="height: 1em; line-height: 1;">{d}</span>
          {/each}
        </span>
      </span>
    {:else}
      <span style="line-height: 1;" aria-hidden="true">{ch}</span>
    {/if}
  {/each}
</span>
