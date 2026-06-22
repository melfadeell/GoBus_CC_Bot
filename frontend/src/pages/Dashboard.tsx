import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, DASHBOARD_CHANNELS, DashboardAnalytics, DashboardStats } from '@/api/client'
import ChannelBreakdownChart from '@/components/dashboard/ChannelBreakdownChart'
import ChartCard from '@/components/dashboard/ChartCard'
import CostTrendChart from '@/components/dashboard/CostTrendChart'
import MessagesTrendChart from '@/components/dashboard/MessagesTrendChart'
import TokenSplitChart from '@/components/dashboard/TokenSplitChart'
import TokenUsageChart from '@/components/dashboard/TokenUsageChart'
import { ErrorState, LoadingState, PageHeader } from '@/components/admin/Shared'
import { useLanguage } from '@/i18n/LanguageProvider'

export default function DashboardPage() {
  const { t } = useLanguage()
  const d = t.dashboard
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [analytics, setAnalytics] = useState<DashboardAnalytics | null>(null)
  const [channel, setChannel] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const channelLabel = useCallback(
    (ch: string) => {
      const key = ch as keyof typeof t.dashboard.channels
      return t.dashboard.channels[key] ?? ch
    },
    [t.dashboard.channels]
  )

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    const params = {
      ...(channel ? { channel } : {}),
      ...(dateFrom ? { date_from: dateFrom } : {}),
      ...(dateTo ? { date_to: dateTo } : {}),
    }
    Promise.all([api.getStats(params), api.getAnalytics({ ...params, days: 30 })])
      .then(([s, a]) => {
        setStats(s)
        setAnalytics(a)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [channel, dateFrom, dateTo])

  useEffect(() => {
    load()
  }, [load])

  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} onRetry={load} />
  if (!stats || !analytics) return null

  const cards = [
    { label: d.conversations, value: stats.total_sessions, link: '/admin/conversations' },
    { label: d.messages, value: stats.total_messages, link: '/admin/conversations' },
    { label: d.kbArticles, value: stats.kb_articles, link: '/admin/kb', accent: true },
    { label: d.stations, value: stats.stations, link: '/admin/stations' },
    { label: d.destinations, value: stats.destinations, link: '/admin/kb?tab=destinations' },
    { label: d.activeTrips, value: stats.active_trips, link: '/admin/trips', accent: true },
  ]

  const tokenCards = [
    { label: d.totalTokens, value: stats.total_tokens.toLocaleString(), accent: true },
    { label: d.inputTokens, value: stats.prompt_tokens.toLocaleString() },
    { label: d.outputTokens, value: stats.completion_tokens.toLocaleString() },
    { label: d.costEstimate, value: `$${stats.total_cost_usd.toFixed(4)}`, accent: true },
  ]

  return (
    <div className="fade-in space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
        <PageHeader title={d.title} subtitle={d.subtitle} />
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">{d.dateFrom}</label>
            <input
              type="date"
              className="input-field ltr"
              value={dateFrom}
              max={dateTo || undefined}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">{d.dateTo}</label>
            <input
              type="date"
              className="input-field ltr"
              value={dateTo}
              min={dateFrom || undefined}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </div>
          {(dateFrom || dateTo) && (
            <button
              type="button"
              className="btn-ghost text-sm"
              onClick={() => {
                setDateFrom('')
                setDateTo('')
              }}
            >
              {d.clearDates}
            </button>
          )}
          <div>
            <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">{d.filterChannel}</label>
            <select
              className="input-field min-w-[160px]"
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
            >
              <option value="">{d.allChannels}</option>
              {DASHBOARD_CHANNELS.map((ch) => (
                <option key={ch} value={ch}>
                  {channelLabel(ch)}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        {cards.map((c) => (
          <Link
            key={c.label}
            to={c.link}
            className="card p-3 hover:shadow-md transition-all hover:-translate-y-0.5 group"
          >
            <div className="text-xs text-[var(--color-text-muted)] truncate">{c.label}</div>
            <div
              className="text-2xl font-bold mt-0.5"
              style={{ color: c.accent ? 'var(--color-brand-accent)' : 'var(--color-brand-primary)' }}
            >
              {c.value.toLocaleString()}
            </div>
          </Link>
        ))}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {tokenCards.map((c) => (
          <div key={c.label} className="card p-3">
            <div className="text-xs text-[var(--color-text-muted)] truncate">{c.label}</div>
            <div
              className="text-2xl font-bold mt-0.5"
              style={{ color: c.accent ? 'var(--color-brand-accent)' : 'var(--color-brand-primary)' }}
            >
              {c.value}
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
        <ChartCard
          title={d.tokenSplit}
          subtitle={d.tokenSplitSub}
          fullscreenContent={
            <TokenSplitChart data={analytics.daily} height={420} inputLabel={d.inputTokens} outputLabel={d.outputTokens} />
          }
        >
          <TokenSplitChart data={analytics.daily} inputLabel={d.inputTokens} outputLabel={d.outputTokens} />
        </ChartCard>

        <ChartCard
          title={d.costTrend}
          subtitle={d.costTrendSub}
          fullscreenContent={<CostTrendChart data={analytics.daily} height={420} />}
        >
          <CostTrendChart data={analytics.daily} />
        </ChartCard>

        <ChartCard
          title={d.tokenUsage}
          subtitle={d.tokenUsageSub}
          fullscreenContent={<TokenUsageChart data={analytics.daily} height={420} />}
        >
          <TokenUsageChart data={analytics.daily} />
        </ChartCard>

        <ChartCard
          title={d.channelBreakdown}
          subtitle={d.channelBreakdownSub}
          fullscreenContent={
            <ChannelBreakdownChart data={analytics.by_channel} channelLabel={channelLabel} height={420} />
          }
        >
          <ChannelBreakdownChart data={analytics.by_channel} channelLabel={channelLabel} />
        </ChartCard>

        <ChartCard
          title={d.messagesTrend}
          subtitle={d.messagesTrendSub}
          fullscreenContent={<MessagesTrendChart data={analytics.daily} height={420} />}
        >
          <MessagesTrendChart data={analytics.daily} />
        </ChartCard>
      </div>
    </div>
  )
}
