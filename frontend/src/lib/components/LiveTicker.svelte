<script lang="ts">
  import { fmtTokens, fmtUsd } from '$lib/api'

  interface LiveEvent {
    provider: string
    model: string
    input_tokens: number
    output_tokens: number
    audio_input_tokens?: number
    audio_output_tokens?: number
    source?: string
    key_id?: string
    cost_usd: number | null
    ts: string
  }

  let { onevent }: { onevent?: () => void } = $props()

  let events = $state<LiveEvent[]>([])
  let connected = $state(false)

  $effect(() => {
    let ws: WebSocket | null = null
    let retry: ReturnType<typeof setTimeout>
    let ping: ReturnType<typeof setInterval>
    let closed = false

    function connect() {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws/live`)
      ws.onopen = () => {
        connected = true
        ping = setInterval(() => ws?.readyState === 1 && ws.send('ping'), 25000)
      }
      ws.onmessage = (msg) => {
        try {
          const e = JSON.parse(msg.data) as LiveEvent
          events = [e, ...events].slice(0, 12)
          onevent?.()
        } catch (err) {
          console.error('[LiveTicker] Failed to parse WebSocket message:', msg.data, err)
        }
      }
      ws.onclose = () => {
        connected = false
        clearInterval(ping)
        if (!closed) retry = setTimeout(connect, 5000)
      }
    }
    connect()
    return () => {
      closed = true
      clearTimeout(retry)
      clearInterval(ping)
      ws?.close()
    }
  })
</script>

<div class="flex min-w-0 items-center gap-3 overflow-hidden">
  <span class="flex shrink-0 items-center gap-1.5">
    <span
      class="size-1.5 rounded-full"
      style="background: {connected ? 'var(--red)' : 'var(--muted)'};
             {connected ? 'box-shadow: 0 0 6px var(--red);' : ''}"
    ></span>
    <span class="microlabel-dim">{connected ? 'live' : 'offline'}</span>
  </span>
  {#if events.length === 0}
    <span class="microlabel-dim truncate">awaiting proxy traffic…</span>
  {:else}
    <div class="flex min-w-0 gap-5 overflow-hidden whitespace-nowrap">
      {#each events as e (e.ts)}
        <span
          class="numeral inline-flex shrink-0 items-baseline gap-1.5 text-xs"
          style="animation: ticker-in 0.25s ease-out;"
        >
          <span class="text-paper">{e.model}</span>
          {#if e.source === 'live_proxy'}<span class="text-red">●LIVE</span>{/if}
          <span class="text-muted">+{fmtTokens(e.input_tokens + e.output_tokens)}</span>
          {#if (e.audio_input_tokens ?? 0) + (e.audio_output_tokens ?? 0) > 0}
            <span class="text-muted">({fmtTokens((e.audio_input_tokens ?? 0) + (e.audio_output_tokens ?? 0))} aud)</span>
          {/if}
          {#if e.key_id}<span class="text-muted">{e.key_id}</span>{/if}
          <span class="text-red">{fmtUsd(e.cost_usd, true)}</span>
        </span>
      {/each}
    </div>
  {/if}
</div>
