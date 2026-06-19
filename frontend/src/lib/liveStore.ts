import { writable, derived, type Readable } from 'svelte/store'

export interface LiveEvent {
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

export function computeBurnRate(evts: LiveEvent[], now: number): number {
  return evts
    .filter((e) => Date.parse(e.ts) >= now - 60_000)
    .reduce((sum, e) => sum + (e.cost_usd ?? 0), 0)
}

const _events = writable<LiveEvent[]>([])
const _connected = writable(false)
const _lastEventAt = writable(0)

export const events: Readable<LiveEvent[]> = _events
export const connected: Readable<boolean> = _connected
export const lastEventAt: Readable<number> = _lastEventAt
export const burnRatePerMin: Readable<number> = derived(_events, ($e) =>
  computeBurnRate($e, Date.now()),
)

let ws: WebSocket | null = null
let refcount = 0
let retry: ReturnType<typeof setTimeout>
let ping: ReturnType<typeof setInterval>
let closed = false

function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/ws/live`)
  ws.onopen = () => {
    _connected.set(true)
    ping = setInterval(() => ws?.readyState === 1 && ws.send('ping'), 25_000)
  }
  ws.onmessage = (msg) => {
    try {
      const e = JSON.parse(msg.data) as LiveEvent
      _events.update((cur) => [e, ...cur].slice(0, 12))
      _lastEventAt.set(Date.now())
    } catch (err) {
      console.error('[liveStore] parse failed:', msg.data, err)
    }
  }
  ws.onclose = () => {
    _connected.set(false)
    clearInterval(ping)
    if (!closed) retry = setTimeout(connect, 5000)
  }
}

export function startLive(): () => void {
  refcount++
  if (!ws) {
    closed = false
    connect()
  }
  return () => {
    refcount--
    if (refcount <= 0) {
      closed = true
      clearTimeout(retry)
      clearInterval(ping)
      ws?.close()
      ws = null
    }
  }
}
