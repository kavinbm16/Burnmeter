export interface ProviderUsage {
  provider: string
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  requests: number
  cost_usd: number | null
  cost_estimated: number
}

export interface DailyPoint {
  date: string
  provider: string
  cost_usd: number | null
  total_tokens: number
}

export interface Overview {
  totals: { cost_usd: number; input_tokens: number; output_tokens: number; requests: number }
  by_provider: ProviderUsage[]
  daily: DailyPoint[]
  period: { start: string; end: string }
}

export interface ConfiguredProvider {
  name: string
  display_name: string
  masked_key: string
  label: string
  created_at: string
  last_synced_at: string | null
  watermark_date: string | null
  sync_status: string | null
  sync_error: string | null
}

export interface AvailableProvider {
  display_name: string
  key_hint: string
  mode: 'usage_api' | 'proxy'
}

export interface ProvidersResponse {
  configured: ConfiguredProvider[]
  available: Record<string, AvailableProvider>
}

export interface ModelRow {
  model: string
  source: string
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  requests: number
  cost_usd: number | null
  cost_estimated: number
}

export interface Breakdown {
  by_model: ModelRow[]
  daily: { date: string; input_tokens: number; output_tokens: number; cost_usd: number | null; requests: number }[]
  billed_costs: { date: string; source: string; line_item: string; cost_usd: number }[]
  period: { start: string; end: string }
}

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${url} → ${res.status}`)
  return res.json()
}

export const api = {
  overview: (period: string) => get<Overview>(`/api/overview?period=${period}`),
  providers: () => get<ProvidersResponse>('/api/providers'),
  breakdown: (name: string, period: string) =>
    get<Breakdown>(`/api/providers/${name}/breakdown?period=${period}`),
  addProvider: async (name: string, key: string) => {
    const res = await fetch('/api/providers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, key }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
      throw new Error(body.detail ?? `HTTP ${res.status}`)
    }
    return res.json()
  },
  removeProvider: (name: string) => fetch(`/api/providers/${name}`, { method: 'DELETE' }),
  sync: (provider?: string) =>
    fetch(`/api/sync${provider ? `?provider=${provider}` : ''}`, { method: 'POST' }),
}

export function fmtUsd(v: number | null | undefined, estimated = false): string {
  if (v == null) return '—'
  const s = v >= 100 ? v.toFixed(0) : v >= 1 ? v.toFixed(2) : v.toFixed(4)
  return `${estimated ? '≈' : ''}$${s}`
}

export function fmtTokens(v: number | null | undefined): string {
  if (v == null) return '—'
  if (v >= 1e9) return (v / 1e9).toFixed(2) + 'B'
  if (v >= 1e6) return (v / 1e6).toFixed(2) + 'M'
  if (v >= 1e3) return (v / 1e3).toFixed(1) + 'K'
  return String(v)
}

export const PROVIDER_COLORS: Record<string, string> = {
  openai: 'var(--chart-openai)',
  gemini: 'var(--chart-gemini)',
}
