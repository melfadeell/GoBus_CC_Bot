const TOKEN_KEY = 'gobus_admin_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

function formatDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) =>
        typeof item === 'object' && item && 'msg' in item ? String(item.msg) : String(item)
      )
      .join('، ')
  }
  return 'Request failed'
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await fetch(path, { ...options, headers })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    if (res.status === 401 && token && !path.includes('/auth/login')) {
      clearToken()
      window.location.href = '/login'
    }
    throw new ApiError(formatDetail(err.detail), res.status)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  getStats: (params?: { channel?: string; date_from?: string; date_to?: string }) => {
    const q = new URLSearchParams()
    if (params?.channel) q.set('channel', params.channel)
    if (params?.date_from) q.set('date_from', params.date_from)
    if (params?.date_to) q.set('date_to', params.date_to)
    const qs = q.toString()
    return request<DashboardStats>(`/api/dashboard/stats${qs ? `?${qs}` : ''}`)
  },
  getAnalytics: (params?: { channel?: string; days?: number; date_from?: string; date_to?: string }) => {
    const q = new URLSearchParams()
    if (params?.channel) q.set('channel', params.channel)
    if (params?.days) q.set('days', String(params.days))
    if (params?.date_from) q.set('date_from', params.date_from)
    if (params?.date_to) q.set('date_to', params.date_to)
    const qs = q.toString()
    return request<DashboardAnalytics>(`/api/dashboard/analytics${qs ? `?${qs}` : ''}`)
  },

  getKbCategories: () => request<KbCategory[]>('/api/kb/categories'),
  getKbArticles: (params?: Record<string, string>) =>
    request<Paginated<KbArticle>>(`/api/kb?${new URLSearchParams(params || '')}`),
  getKbArticle: (id: number) => request<KbArticle>(`/api/kb/${id}`),
  createKbArticle: (data: Partial<KbArticle>) =>
    request<KbArticle>('/api/kb', { method: 'POST', body: JSON.stringify(data) }),
  updateKbArticle: (id: number, data: Partial<KbArticle>) =>
    request<KbArticle>(`/api/kb/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteKbArticle: (id: number) => request(`/api/kb/${id}`, { method: 'DELETE' }),
  enhanceText: (text: string) =>
    request<{ text: string }>('/api/kb/enhance', { method: 'POST', body: JSON.stringify({ text }) }),
  extractKbFile: async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    const token = getToken()
    const res = await fetch('/api/kb/extract-file', {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Extract failed' }))
      throw new Error(typeof err.detail === 'string' ? err.detail : 'Extract failed')
    }
    return res.json() as Promise<{ text: string }>
  },

  getStations: (params?: Record<string, string>) =>
    request<Paginated<Station>>(`/api/stations?${new URLSearchParams(params || '')}`),
  getStation: (id: number) => request<Station>(`/api/stations/${id}`),
  createStation: (data: Partial<Station>) =>
    request<Station>('/api/stations', { method: 'POST', body: JSON.stringify(data) }),
  updateStation: (id: number, data: Partial<Station>) =>
    request<Station>(`/api/stations/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteStation: (id: number) => request(`/api/stations/${id}`, { method: 'DELETE' }),

  getDestinations: (params?: Record<string, string>) =>
    request<Paginated<Destination>>(`/api/destinations?${new URLSearchParams(params || '')}`),
  getDestination: (id: number) => request<Destination>(`/api/destinations/${id}`),
  createDestination: (data: Partial<Destination>) =>
    request<Destination>('/api/destinations', { method: 'POST', body: JSON.stringify(data) }),
  updateDestination: (id: number, data: Partial<Destination>) =>
    request<Destination>(`/api/destinations/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteDestination: (id: number) => request(`/api/destinations/${id}`, { method: 'DELETE' }),

  getRoutes: () => request<Route[]>('/api/trips/routes'),
  getTrips: (params?: Record<string, string>) =>
    request<Paginated<Trip>>(`/api/trips?${new URLSearchParams(params || '')}`),
  getTrip: (id: number) => request<Trip>(`/api/trips/${id}`),
  createTrip: (data: Partial<Trip>) =>
    request<Trip>('/api/trips', { method: 'POST', body: JSON.stringify(data) }),
  updateTrip: (id: number, data: Partial<Trip>) =>
    request<Trip>(`/api/trips/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteTrip: (id: number) => request(`/api/trips/${id}`, { method: 'DELETE' }),

  getServices: () => request<Service[]>('/api/services'),
  updateService: (id: number, data: Partial<Service>) =>
    request<Service>(`/api/services/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  getBotSettings: () => request<BotSettings>('/api/bot-settings'),
  updateBotSettings: (data: Partial<BotSettings>) =>
    request<BotSettings>('/api/bot-settings', { method: 'PUT', body: JSON.stringify(data) }),
  getPromptVersions: () => request<PromptVersion[]>('/api/bot-settings/prompt-versions'),
  enhancePrompt: (instruction: string, basePrompt?: string) =>
    request<{ proposed_prompt: string }>('/api/bot-settings/prompt/enhance', {
      method: 'POST',
      body: JSON.stringify({ instruction, base_prompt: basePrompt }),
    }),
  savePrompt: (system_prompt: string, instruction_note?: string) =>
    request<BotSettings>('/api/bot-settings/prompt', {
      method: 'PUT',
      body: JSON.stringify({ system_prompt, instruction_note }),
    }),
  restorePromptVersion: (versionId: number) =>
    request<BotSettings>(`/api/bot-settings/prompt/restore/${versionId}`, { method: 'POST' }),
  getPublicGreeting: () => request<{ greeting: string }>('/api/bot-settings/public/greeting'),

  getConversations: (params?: Record<string, string>) =>
    request<Paginated<ChatSession>>(`/api/conversations?${new URLSearchParams(params || '')}`),
  getConversationMessages: (sessionId: string) =>
    request<ChatMessage[]>(`/api/conversations/${sessionId}/messages`),

  getMetricsOverview: (params?: { days?: number; date_from?: string; date_to?: string }) => {
    const q = new URLSearchParams()
    if (params?.days) q.set('days', String(params.days))
    if (params?.date_from) q.set('date_from', params.date_from)
    if (params?.date_to) q.set('date_to', params.date_to)
    const qs = q.toString()
    return request<MetricsOverview>(`/api/metrics/overview${qs ? `?${qs}` : ''}`)
  },
  getMetricsCharts: (params?: { days?: number; date_from?: string; date_to?: string }) => {
    const q = new URLSearchParams()
    if (params?.days) q.set('days', String(params.days))
    if (params?.date_from) q.set('date_from', params.date_from)
    if (params?.date_to) q.set('date_to', params.date_to)
    const qs = q.toString()
    return request<MetricsCharts>(`/api/metrics/charts${qs ? `?${qs}` : ''}`)
  },
  getMetricsRequests: (params?: Record<string, string>) =>
    request<Paginated<ApiRequestLog>>(`/api/metrics/requests?${new URLSearchParams(params || '')}`),
  getMetricsChatLogs: (params?: Record<string, string>) =>
    request<Paginated<ChatLogEntry>>(`/api/metrics/chat-logs?${new URLSearchParams(params || '')}`),
  getMetricsLlmCalls: (params?: Record<string, string>) =>
    request<Paginated<LlmCallLog>>(`/api/metrics/llm-calls?${new URLSearchParams(params || '')}`),
  getMetricsAuthLogs: (params?: Record<string, string>) =>
    request<Paginated<AuthLogEntry>>(`/api/metrics/auth-logs?${new URLSearchParams(params || '')}`),
  getMetricsErrors: (params?: Record<string, string>) =>
    request<Paginated<ErrorLogEntry>>(`/api/metrics/errors?${new URLSearchParams(params || '')}`),
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface DashboardStats {
  total_sessions: number
  total_messages: number
  total_tokens: number
  prompt_tokens: number
  completion_tokens: number
  total_cost_usd: number
  kb_articles: number
  stations: number
  destinations: number
  active_trips: number
}

export interface ChannelTokenStat {
  channel: string
  sessions: number
  messages: number
  total_tokens: number
  prompt_tokens: number
  completion_tokens: number
}

export interface DailyAnalyticsPoint {
  date: string
  messages: number
  tokens: number
  prompt_tokens: number
  completion_tokens: number
  cost_usd: number
}

export interface DashboardAnalytics {
  by_channel: ChannelTokenStat[]
  daily: DailyAnalyticsPoint[]
}

export const CHAT_CHANNELS = [
  'whatsapp',
  'instagram',
  'linkedin',
  'facebook',
  'tiktok',
  'website',
] as const

export const DASHBOARD_CHANNELS = ['poc', ...CHAT_CHANNELS] as const

export type ChatChannel = (typeof CHAT_CHANNELS)[number]

export interface KbCategory {
  id: number
  code: string
  name_ar: string
}

export interface KbArticle {
  id?: number
  category_id: number | null
  title: string
  slug?: string
  content: string
  service_scope: string
  source_file?: string | null
  is_active: boolean
  category?: KbCategory
}

export interface Station {
  id?: number
  name: string
  description: string
  working_hours?: string | null
  is_24_hours?: boolean
  opens_at?: string | null
  closes_at?: string | null
  map_url?: string | null
  map_text?: string | null
  city?: string | null
  is_active: boolean
}

export interface Destination {
  id?: number
  name_ar: string
  slug?: string
  content: string
  gobus_web_id?: number | null
  is_active: boolean
}

export interface Route {
  id: number
  origin: string
  destination: string
  service_code: string
  duration_minutes: number
  distance_km?: number | null
}

export interface Trip {
  id?: number
  route_id: number
  trip_date: string
  departure_time: string
  arrival_time: string
  bus_class: string
  total_seats: number
  available_seats: number
  price_egp: number
  is_bookable: boolean
  status: string
  route?: Route
}

export interface Service {
  id: number
  code: string
  name_ar: string
  name_en: string
  description: string
  has_detailed_data: boolean
  is_active: boolean
}

export interface BotSettings {
  id?: number
  system_prompt: string
  greeting_ar: string
}

export interface PromptVersion {
  id: number
  version_number: number
  system_prompt: string
  instruction_note: string | null
  created_at: string
}

export interface ChatSession {
  id: number
  session_id: string
  channel: string
  started_at: string
  message_count: number
}

export interface ChatMessage {
  id: number
  session_id: string
  role: string
  content: string
  image_url?: string | null
  created_at: string
}

export interface MetricsOverview {
  total_requests: number
  chat_turns: number
  llm_calls: number
  errors: number
  rate_limit_hits: number
  avg_latency_sec: number
  total_tokens: number
  date_from: string | null
  date_to: string | null
}

export interface MetricsDailyPoint {
  date: string
  requests: number
  chat_turns: number
  tokens: number
  errors: number
  rate_limit_hits: number
}

export interface MetricsCharts {
  daily: MetricsDailyPoint[]
}

export interface ApiRequestLog {
  id: number
  request_id: string
  api_method: string
  api_path: string
  client_ip: string | null
  status_code: number | null
  response_time_sec: number | null
  success: boolean
  error_message: string | null
  created_at: string
}

export interface ChatLogEntry {
  id: number
  request_id: string | null
  session_id: string
  channel: string | null
  client_ip: string | null
  user_message: string | null
  ai_response: string | null
  model: string | null
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  response_time_sec: number | null
  has_image: boolean
  success: boolean
  error_message: string | null
  created_at: string
}

export interface LlmCallLog {
  id: number
  request_id: string | null
  session_id: string | null
  model: string | null
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  response_time_sec: number | null
  success: boolean
  error_message: string | null
  created_at: string
}

export interface AuthLogEntry {
  id: number
  email: string
  action: string
  client_ip: string | null
  status_code: number
  success: boolean
  created_at: string
}

export interface ErrorLogEntry {
  id: number
  request_id: string | null
  error_type: string
  message: string | null
  stack_trace: string | null
  created_at: string
}
