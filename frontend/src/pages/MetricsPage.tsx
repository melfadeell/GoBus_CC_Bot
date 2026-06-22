import { useCallback, useEffect, useState } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  api,
  ApiRequestLog,
  AuthLogEntry,
  ChatLogEntry,
  ErrorLogEntry,
  LlmCallLog,
  MetricsCharts,
  MetricsOverview,
} from '@/api/client'
import ChartCard from '@/components/dashboard/ChartCard'
import { EmptyState, ErrorState, LoadingState, PageHeader } from '@/components/admin/Shared'
import { useLanguage } from '@/i18n/LanguageProvider'

type TabId = 'overview' | 'requests' | 'chat' | 'llm' | 'auth' | 'errors'

function formatTime(value: string) {
  return new Date(value).toLocaleString()
}

function truncate(value: string | null | undefined, max = 80) {
  if (!value) return '—'
  return value.length <= max ? value : `${value.slice(0, max)}…`
}

const PAGE_SIZE = 50

function isoDaysAgo(n: number): string {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

export default function MetricsPage() {
  const { t } = useLanguage()
  const m = t.metrics
  const [tab, setTab] = useState<TabId>('overview')
  const [days, setDays] = useState(30)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [overview, setOverview] = useState<MetricsOverview | null>(null)
  const [charts, setCharts] = useState<MetricsCharts | null>(null)
  const [requests, setRequests] = useState<ApiRequestLog[]>([])
  const [chatLogs, setChatLogs] = useState<ChatLogEntry[]>([])
  const [llmCalls, setLlmCalls] = useState<LlmCallLog[]>([])
  const [authLogs, setAuthLogs] = useState<AuthLogEntry[]>([])
  const [errors, setErrors] = useState<ErrorLogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Effective date window: explicit range wins, else derived from the day preset.
  const effFrom = dateFrom || isoDaysAgo(days - 1)
  const effTo = dateTo || isoDaysAgo(0)

  // Reset to first page whenever the filter or tab changes.
  useEffect(() => {
    setPage(1)
  }, [tab, days, dateFrom, dateTo])

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    const dateParams = { date_from: effFrom, date_to: effTo }
    const pageParams = { ...dateParams, page: String(page), page_size: String(PAGE_SIZE) }

    if (tab === 'overview') {
      Promise.all([api.getMetricsOverview(dateParams), api.getMetricsCharts(dateParams)])
        .then(([o, c]) => {
          setOverview(o)
          setCharts(c)
        })
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false))
      return
    }

    const fetchers: Record<Exclude<TabId, 'overview'>, () => Promise<void>> = {
      requests: () =>
        api.getMetricsRequests(pageParams).then((r) => { setRequests(r.items); setTotal(r.total) }),
      chat: () => api.getMetricsChatLogs(pageParams).then((r) => { setChatLogs(r.items); setTotal(r.total) }),
      llm: () => api.getMetricsLlmCalls(pageParams).then((r) => { setLlmCalls(r.items); setTotal(r.total) }),
      auth: () => api.getMetricsAuthLogs(pageParams).then((r) => { setAuthLogs(r.items); setTotal(r.total) }),
      errors: () => api.getMetricsErrors(pageParams).then((r) => { setErrors(r.items); setTotal(r.total) }),
    }

    fetchers[tab]()
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [tab, effFrom, effTo, page])

  useEffect(() => {
    load()
  }, [load])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const tabs: { id: TabId; label: string }[] = [
    { id: 'overview', label: m.tabs.overview },
    { id: 'requests', label: m.tabs.requests },
    { id: 'chat', label: m.tabs.chat },
    { id: 'llm', label: m.tabs.llm },
    { id: 'auth', label: m.tabs.auth },
    { id: 'errors', label: m.tabs.errors },
  ]

  const chartData =
    charts?.daily.map((d) => ({
      ...d,
      label: d.date.slice(5),
    })) ?? []

  if (loading && !overview && tab === 'overview') return <LoadingState />
  if (error && tab === 'overview' && !overview) return <ErrorState message={error} onRetry={load} />

  return (
    <div className="fade-in space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <PageHeader title={m.title} subtitle={m.subtitle} />
        <div className="flex flex-wrap items-end gap-2 shrink-0">
          <button
            type="button"
            className={`px-3 py-1.5 rounded-lg text-sm border ${!dateFrom && !dateTo && days === 7 ? 'bg-[var(--color-brand-primary)] text-white border-transparent' : 'border-[var(--color-border-default)]'}`}
            onClick={() => { setDays(7); setDateFrom(''); setDateTo('') }}
          >
            {m.days7}
          </button>
          <button
            type="button"
            className={`px-3 py-1.5 rounded-lg text-sm border ${!dateFrom && !dateTo && days === 30 ? 'bg-[var(--color-brand-primary)] text-white border-transparent' : 'border-[var(--color-border-default)]'}`}
            onClick={() => { setDays(30); setDateFrom(''); setDateTo('') }}
          >
            {m.days30}
          </button>
          <div>
            <label className="block text-[10px] text-[var(--color-text-muted)] mb-0.5">{m.dateFrom}</label>
            <input type="date" className="input-field ltr py-1 text-sm" value={dateFrom} max={dateTo || undefined}
              onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div>
            <label className="block text-[10px] text-[var(--color-text-muted)] mb-0.5">{m.dateTo}</label>
            <input type="date" className="input-field ltr py-1 text-sm" value={dateTo} min={dateFrom || undefined}
              onChange={(e) => setDateTo(e.target.value)} />
          </div>
          {(dateFrom || dateTo) && (
            <button type="button" className="btn-ghost text-sm" onClick={() => { setDateFrom(''); setDateTo('') }}>
              {m.clearDates}
            </button>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 border-b border-[var(--color-border-default)] pb-2">
        {tabs.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
              tab === id
                ? 'bg-[var(--color-brand-primary)] text-white'
                : 'hover:bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {loading && tab !== 'overview' ? <LoadingState /> : null}
      {error && tab !== 'overview' ? <ErrorState message={error} onRetry={load} /> : null}

      {tab === 'overview' && overview && charts ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3">
            {[
              { label: m.totalRequests, value: overview.total_requests },
              { label: m.chatTurns, value: overview.chat_turns },
              { label: m.llmCalls, value: overview.llm_calls },
              { label: m.errors, value: overview.errors },
              { label: m.rateLimits, value: overview.rate_limit_hits },
              { label: m.avgLatency, value: overview.avg_latency_sec },
              { label: m.totalTokens, value: overview.total_tokens },
            ].map((card) => (
              <div key={card.label} className="card p-3">
                <div className="text-xs text-[var(--color-text-muted)] truncate">{card.label}</div>
                <div className="text-xl font-bold mt-0.5" style={{ color: 'var(--color-brand-primary)' }}>
                  {typeof card.value === 'number' && card.label === m.avgLatency
                    ? card.value.toFixed(3)
                    : Number(card.value).toLocaleString()}
                </div>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <ChartCard title={m.requestsChart}>
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-default)" />
                  <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} width={32} allowDecimals={false} />
                  <Tooltip />
                  <Area type="monotone" dataKey="requests" stroke="var(--color-brand-primary)" fill="var(--color-brand-primary)" fillOpacity={0.2} />
                </AreaChart>
              </ResponsiveContainer>
            </ChartCard>
            <ChartCard title={m.chatChart}>
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-default)" />
                  <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} width={32} allowDecimals={false} />
                  <Tooltip />
                  <Area type="monotone" dataKey="chat_turns" stroke="var(--color-brand-accent)" fill="var(--color-brand-accent)" fillOpacity={0.2} />
                </AreaChart>
              </ResponsiveContainer>
            </ChartCard>
            <ChartCard title={m.tokensChart}>
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-default)" />
                  <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} width={40} allowDecimals={false} />
                  <Tooltip />
                  <Area type="monotone" dataKey="tokens" stroke="#6366f1" fill="#6366f1" fillOpacity={0.2} />
                </AreaChart>
              </ResponsiveContainer>
            </ChartCard>
            <ChartCard title={m.errorsChart}>
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-default)" />
                  <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} width={32} allowDecimals={false} />
                  <Tooltip />
                  <Area type="monotone" dataKey="errors" stroke="#ef4444" fill="#ef4444" fillOpacity={0.2} />
                </AreaChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>
        </>
      ) : null}

      {tab === 'requests' && !loading ? (
        requests.length === 0 ? (
          <EmptyState message={t.common.noData} />
        ) : (
          <LogTable
            headers={[m.time, m.method, m.path, m.status, m.latency, m.ip]}
            rows={requests.map((r) => [
              formatTime(r.created_at),
              r.api_method,
              truncate(r.api_path, 60),
              String(r.status_code ?? '—'),
              r.response_time_sec?.toFixed(3) ?? '—',
              r.client_ip ?? '—',
            ])}
          />
        )
      ) : null}

      {tab === 'chat' && !loading ? (
        chatLogs.length === 0 ? (
          <EmptyState message={t.common.noData} />
        ) : (
          <LogTable
            headers={[m.time, m.session, m.channel, m.tokens, m.latency, m.success]}
            rows={chatLogs.map((r) => [
              formatTime(r.created_at),
              truncate(r.session_id, 12),
              r.channel ?? '—',
              String(r.total_tokens),
              r.response_time_sec?.toFixed(2) ?? '—',
              r.success ? t.common.yes : t.common.no,
            ])}
          />
        )
      ) : null}

      {tab === 'llm' && !loading ? (
        llmCalls.length === 0 ? (
          <EmptyState message={t.common.noData} />
        ) : (
          <LogTable
            headers={[m.time, m.model, m.tokens, m.latency, m.success]}
            rows={llmCalls.map((r) => [
              formatTime(r.created_at),
              r.model ?? '—',
              String(r.total_tokens),
              r.response_time_sec?.toFixed(2) ?? '—',
              r.success ? t.common.yes : t.common.no,
            ])}
          />
        )
      ) : null}

      {tab === 'auth' && !loading ? (
        authLogs.length === 0 ? (
          <EmptyState message={t.common.noData} />
        ) : (
          <LogTable
            headers={[m.time, m.email, m.action, m.status, m.ip]}
            rows={authLogs.map((r) => [
              formatTime(r.created_at),
              r.email,
              r.action,
              String(r.status_code),
              r.client_ip ?? '—',
            ])}
          />
        )
      ) : null}

      {tab === 'errors' && !loading ? (
        errors.length === 0 ? (
          <EmptyState message={t.common.noData} />
        ) : (
          <LogTable
            headers={[m.time, m.errorType, m.message]}
            rows={errors.map((r) => [
              formatTime(r.created_at),
              r.error_type,
              truncate(r.message, 120),
            ])}
          />
        )
      ) : null}

      {tab !== 'overview' && !loading && total > PAGE_SIZE ? (
        <div className="flex items-center justify-end gap-3 text-sm">
          <button
            type="button"
            className="btn-ghost px-3 disabled:opacity-40"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            {m.prev}
          </button>
          <span className="text-[var(--color-text-muted)]">
            {m.page} {page} / {totalPages}
          </span>
          <button
            type="button"
            className="btn-ghost px-3 disabled:opacity-40"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            {m.next}
          </button>
        </div>
      ) : null}
    </div>
  )
}

function LogTable({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--color-border-default)] text-left">
            {headers.map((h) => (
              <th key={h} className="px-3 py-2 font-medium text-[var(--color-text-muted)] whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-[var(--color-border-default)] last:border-0">
              {row.map((cell, j) => (
                <td key={j} className="px-3 py-2 align-top whitespace-nowrap">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
