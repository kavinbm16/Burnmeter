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
  audio_input_tokens: number
  audio_output_tokens: number
  requests: number
  cost_usd: number | null
  cost_estimated: number
}

export interface KeyRow {
  key_id: string
  model_count: number
  input_tokens: number
  output_tokens: number
  audio_input_tokens: number
  audio_output_tokens: number
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

export interface Budget {
  monthly_usd: number | null
  spent_mtd: number
  projected_eom: number
  days_elapsed: number
  days_in_month: number
}

export interface HeatmapDay {
  date: string
  cost_usd: number | null
  total_tokens: number
  requests: number
}

export interface LeaderboardModel {
  model: string
  provider: string
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  requests: number
  cost_usd: number | null
  cost_estimated: number
}

export interface GCPStatus {
  configured: boolean
  project_id: string | null
  billing_table: string | null
  logs_table: string | null
  billing_sync: { status: string; last_synced_at: string | null; error: string | null } | null
  logs_sync: { status: string; last_synced_at: string | null; error: string | null } | null
}

export interface ReconciliationRow {
  date: string
  estimated_cost: number
  actual_cost: number | null
  delta_pct: number | null
  reconciled: boolean
}

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${url} → ${res.status}`)
  return res.json()
}

export const api = {
  overview: (period: string, date?: string | null) =>
    get<Overview>(`/api/overview?period=${period}${date ? `&date=${date}` : ''}`),
  budget: () => get<Budget>('/api/budget'),
  setBudget: (monthly_usd: number | null) =>
    fetch('/api/budget', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ monthly_usd }),
    }),
  heatmap: (days = 120) =>
    get<{ start: string; end: string; days: HeatmapDay[] }>(`/api/heatmap?days=${days}`),
  models: (period: string, date?: string | null) =>
    get<{ models: LeaderboardModel[] }>(
      `/api/models?period=${period}${date ? `&date=${date}` : ''}`
    ),
  pricing: () =>
    get<Record<string, { input_per_m: number; output_per_m: number }>>('/api/pricing'),
  keys: (name: string, period: string) =>
    get<{ keys: KeyRow[] }>(`/api/providers/${name}/keys?period=${period}`),
  billingStatus: () =>
    get<{ configured: boolean; table: string | null }>('/api/billing/gemini'),
  billingConfigure: async (credentials_json: string, table: string) => {
    const res = await fetch('/api/billing/gemini', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ credentials_json, table }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
      throw new Error(body.detail ?? `HTTP ${res.status}`)
    }
    return res.json()
  },
  billingRemove: () => fetch('/api/billing/gemini', { method: 'DELETE' }),
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
  gcpAuthCheck: async (): Promise<{ adc: boolean; project_id: string | null }> => {
    const r = await fetch('/api/gcp/auth-check')
    return r.json()
  },
  gcpStatus: async (): Promise<GCPStatus> => {
    const r = await fetch('/api/gcp/status')
    return r.json()
  },
  gcpTables: async (credentialsJson: string): Promise<{ tables: string[] }> => {
    const r = await fetch('/api/gcp/tables', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ credentials_json: credentialsJson }),
    })
    if (!r.ok) throw new Error((await r.json()).detail ?? 'validation failed')
    return r.json()
  },
  gcpConnect: async (
    credentialsJson: string,
    billingTable: string,
    logsTable?: string
  ): Promise<{ ok: boolean; project_id: string }> => {
    const r = await fetch('/api/gcp/connect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        credentials_json: credentialsJson,
        billing_table: billingTable,
        logs_table: logsTable ?? null,
      }),
    })
    if (!r.ok) throw new Error((await r.json()).detail ?? 'connect failed')
    return r.json()
  },
  gcpDisconnect: async (): Promise<{ ok: boolean }> => {
    const r = await fetch('/api/gcp/disconnect', { method: 'DELETE' })
    return r.json()
  },
  gcpSync: async (): Promise<{ ok: boolean }> => {
    const r = await fetch('/api/gcp/sync', { method: 'POST' })
    return r.json()
  },
  reconciliation: async (
    provider: string,
    period = '30d'
  ): Promise<{ reconciliation: ReconciliationRow[]; period: { start: string; end: string } }> => {
    const r = await fetch(`/api/providers/${provider}/reconciliation?period=${period}`)
    return r.json()
  },
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
