import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, DASHBOARD_CHANNELS, DashboardAnalytics, DashboardStats } from '@/api/client'
import ChannelBreakdownChart from '@/components/dashboard/ChannelBreakdownChart'
import ChartCard from '@/components/dashboard/ChartCard'
import MessagesTrendChart from '@/components/dashboard/MessagesTrendChart'
import TokenUsageChart from '@/components/dashboard/TokenUsageChart'
import { ErrorState, LoadingState, PageHeader } from '@/components/admin/Shared'
import { useLanguage } from '@/i18n/LanguageProvider'

export default function DashboardPage() {
  const { t } = useLanguage()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [analytics, setAnalytics] = useState<DashboardAnalytics | null>(null)
  const [channel, setChannel] = useState('')
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
    const params = channel ? { channel } : undefined
    Promise.all([api.getStats(params), api.getAnalytics({ ...params, days: 30 })])
      .then(([s, a]) => {
        setStats(s)
        setAnalytics(a)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [channel])

  useEffect(() => {
    load()
  }, [load])

  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} onRetry={load} />
  if (!stats || !analytics) return null

  const cards = [
    { label: t.dashboard.conversations, value: stats.total_sessions, link: '/admin/conversations' },
    { label: t.dashboard.messages, value: stats.total_messages, link: '/admin/conversations' },
    { label: t.dashboard.kbArticles, value: stats.kb_articles, link: '/admin/kb', accent: true },
    { label: t.dashboard.stations, value: stats.stations, link: '/admin/stations' },
    { label: t.dashboard.destinations, value: stats.destinations, link: '/admin/kb?tab=destinations' },
    { label: t.dashboard.activeTrips, value: stats.active_trips, link: '/admin/trips', accent: true },
  ]

  return (
    <div className="fade-in space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <PageHeader title={t.dashboard.title} subtitle={t.dashboard.subtitle} />
        <div className="shrink-0">
          <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">
            {t.dashboard.filterChannel}
          </label>
          <select
            className="input-field min-w-[180px]"
            value={channel}
            onChange={(e) => setChannel(e.target.value)}
          >
            <option value="">{t.dashboard.allChannels}</option>
            {DASHBOARD_CHANNELS.map((ch) => (
              <option key={ch} value={ch}>
                {channelLabel(ch)}
              </option>
            ))}
          </select>
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

      <div className="card p-3 flex items-center justify-between gap-4">
        <div>
          <div className="text-xs text-[var(--color-text-muted)]">{t.dashboard.totalTokens}</div>
          <div className="text-2xl font-bold" style={{ color: 'var(--color-brand-accent)' }}>
            {stats.total_tokens.toLocaleString()}
          </div>
        </div>
        {channel && (
          <div className="text-sm text-[var(--color-text-muted)]">
            {channelLabel(channel)}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
        <ChartCard
          title={t.dashboard.tokenUsage}
          subtitle={t.dashboard.tokenUsageSub}
          fullscreenContent={<TokenUsageChart data={analytics.daily} height={420} />}
        >
          <TokenUsageChart data={analytics.daily} />
        </ChartCard>

        <ChartCard
          title={t.dashboard.channelBreakdown}
          subtitle={t.dashboard.channelBreakdownSub}
          fullscreenContent={
            <ChannelBreakdownChart data={analytics.by_channel} channelLabel={channelLabel} height={420} />
          }
        >
          <ChannelBreakdownChart data={analytics.by_channel} channelLabel={channelLabel} />
        </ChartCard>

        <ChartCard
          title={t.dashboard.messagesTrend}
          subtitle={t.dashboard.messagesTrendSub}
          fullscreenContent={<MessagesTrendChart data={analytics.daily} height={420} />}
        >
          <MessagesTrendChart data={analytics.daily} />
        </ChartCard>
      </div>
    </div>
  )
}
