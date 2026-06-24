const TOKEN_KEY = 'gobus_admin_token'
const CUSTOMER_TOKEN_KEY = 'gobus_customer_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

// --- End-customer auth (separate from admin) ---
export function getCustomerToken(): string | null {
  return localStorage.getItem(CUSTOMER_TOKEN_KEY)
}

export function setCustomerToken(token: string) {
  localStorage.setItem(CUSTOMER_TOKEN_KEY, token)
}

export function clearCustomerToken() {
  localStorage.removeItem(CUSTOMER_TOKEN_KEY)
}

// Single-source hotline: fetched once from the backend (BotSettings.hotline) and
// shared so the header + message bolding stay in sync with the admin-set value.
export let runtimeHotline = '19567'
export function setRuntimeHotline(h: string) {
  if (h) runtimeHotline = h
}
export async function fetchPublicInfo(): Promise<{ greeting: string; hotline: string }> {
  const res = await fetch('/api/bot-settings/public/info')
  if (!res.ok) throw new Error('Failed to load bot info')
  const data = (await res.json()) as { greeting: string; hotline: string }
  if (data.hotline) setRuntimeHotline(data.hotline)
  return data
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
  getAdminMe: () => request<{ email: string; id: number }>('/api/auth/me'),

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
  getMetricsUsers: (params?: Record<string, string>) =>
    request<Paginated<MetricsUserStat>>(`/api/metrics/users?${new URLSearchParams(params || '')}`),
  getMetricsUserDetail: (customerId: number) =>
    request<MetricsUserDetail>(`/api/metrics/users/${customerId}`),

  // Admin CRM / tickets
  getAdminTickets: (params?: Record<string, string>) =>
    request<Paginated<TicketAdminSummary>>(`/api/admin/tickets?${new URLSearchParams(params || '')}`),
  getAdminTicket: (id: number) => request<TicketDetail>(`/api/admin/tickets/${id}`),
  updateAdminTicket: (id: number, data: Partial<TicketUpdate>) =>
    request<TicketDetail>(`/api/admin/tickets/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  replyAdminTicket: (id: number, body: string) =>
    request<TicketDetail>(`/api/admin/tickets/${id}/messages`, {
      method: 'POST',
      body: JSON.stringify({ body }),
    }),
}

export interface TicketAdminSummary {
  id: number
  ref_number: string
  subject: string
  category: string
  status: string
  priority: string
  priority_auto: string | null
  channel: string
  customer_id: number | null
  guest_name: string | null
  guest_email: string | null
  assigned_admin_id: number | null
  created_at: string
  updated_at: string
}

export interface TicketUpdate {
  status: string
  priority: string
  assigned_admin_id: number | null
}

// --- Customer + ticket API (public chat side; uses the customer token, never
//     redirects to the admin login on 401) ---
async function customerRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getCustomerToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(path, { ...options, headers })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    if (res.status === 401 && token) clearCustomerToken()
    throw new ApiError(formatDetail(err.detail), res.status)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export const customerApi = {
  register: (data: CustomerRegisterData) =>
    customerRequest<{ access_token: string }>('/api/customer/register', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  login: (email: string, password: string) =>
    customerRequest<{ access_token: string }>('/api/customer/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  me: () => customerRequest<CustomerProfile>('/api/customer/me'),
  updateProfile: (data: { full_name: string; phone: string; email: string }) =>
    customerRequest<CustomerProfile>('/api/customer/me', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  changePassword: (data: { old_password: string; new_password: string; confirm_password: string }) =>
    customerRequest<{ ok: boolean }>('/api/customer/password', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  requestOtp: (email: string, purpose = 'ticket_create') =>
    customerRequest<{ sent: boolean }>('/api/tickets/otp/request', {
      method: 'POST',
      body: JSON.stringify({ email, purpose }),
    }),
  verifyOtp: (email: string, code: string, purpose = 'ticket_create') =>
    customerRequest<{ verified_token: string }>('/api/tickets/otp/verify', {
      method: 'POST',
      body: JSON.stringify({ email, code, purpose }),
    }),
  createTicket: (data: TicketCreatePayload) =>
    customerRequest<TicketDetail>('/api/tickets', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  listMyTickets: () => customerRequest<TicketSummary[]>('/api/tickets'),
  getTicket: (ref: string, verifiedToken?: string) => {
    const q = verifiedToken ? `?verified_token=${encodeURIComponent(verifiedToken)}` : ''
    return customerRequest<TicketDetail>(`/api/tickets/${ref}${q}`)
  },
}

export interface CustomerRegisterData {
  full_name: string
  phone: string
  email: string
  password: string
  confirm_password: string
}

export interface CustomerProfile {
  id: number
  full_name: string
  phone: string
  email: string
}

export interface TicketDraft {
  category: string
  priority: string
  subject: string
  description: string
}

export interface TicketCreatePayload {
  subject: string
  description: string
  category: string
  priority?: string
  priority_auto?: string
  channel?: string
  session_id?: string | null
  guest_name?: string
  guest_email?: string
  guest_phone?: string
  verified_token?: string
}

export interface TicketSummary {
  ref_number: string
  subject: string
  category: string
  status: string
  priority: string
  created_at: string
}

export interface TicketMessageItem {
  id: number
  author_type: string
  author_id: number | null
  body: string
  attachment_url: string | null
  created_at: string
}

export interface TicketDetail extends TicketSummary {
  id: number
  customer_id: number | null
  guest_name: string | null
  guest_email: string | null
  guest_phone: string | null
  channel: string
  description: string
  priority_auto: string | null
  assigned_admin_id: number | null
  session_id: string | null
  updated_at: string
  resolved_at: string | null
  messages: TicketMessageItem[]
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

export const DASHBOARD_CHANNELS = [...CHAT_CHANNELS] as const

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
  departure_station_id?: number | null
  arrival_station_id?: number | null
  route?: Route
  departure_station_name?: string | null
  arrival_station_name?: string | null
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
  customer_id: number | null
  customer_email: string | null
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

export interface MetricsUserStat {
  customer_id: number
  customer_email: string | null
  full_name: string | null
  chat_turns: number
  total_tokens: number
  tickets: number
  last_seen: string | null
}

export interface MetricsUserDetail {
  customer: {
    id: number
    full_name: string | null
    email: string | null
    phone: string | null
    created_at: string | null
    last_login_at: string | null
  }
  chat_turns: number
  total_tokens: number
  sessions: number
  first_seen: string | null
  last_seen: string | null
  tickets_total: number
  tickets_by_status: Record<string, number>
  recent_chats: {
    created_at: string | null
    channel: string | null
    user_message: string
    ai_response: string
    total_tokens: number
    success: boolean
  }[]
  recent_tickets: {
    ref_number: string
    subject: string
    status: string
    priority: string
    created_at: string | null
  }[]
}
