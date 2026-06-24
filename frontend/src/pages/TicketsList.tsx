import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, CHAT_CHANNELS, type TicketAdminSummary } from '@/api/client'
import { EmptyState, ErrorState, LoadingState, PageHeader } from '@/components/admin/Shared'
import { useLanguage } from '@/i18n/LanguageProvider'

const STATUSES = ['open', 'in_progress', 'waiting_customer', 'resolved', 'closed']
const PRIORITIES = ['low', 'medium', 'high', 'urgent']
const PAGE_SIZE = 20

export default function TicketsList() {
  const { t, locale } = useLanguage()
  const navigate = useNavigate()
  const crm = t.crm
  const tk = t.chat.ticket

  const [items, setItems] = useState<TicketAdminSummary[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  const [channel, setChannel] = useState('')
  const [search, setSearch] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    const params: Record<string, string> = { page: String(page), page_size: String(PAGE_SIZE) }
    if (status) params.status = status
    if (priority) params.priority = priority
    if (channel) params.channel = channel
    if (search.trim()) params.search = search.trim()
    api
      .getAdminTickets(params)
      .then((res) => {
        setItems(res.items)
        setTotal(res.total)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [page, status, priority, channel, search])

  useEffect(() => {
    load()
  }, [load])

  const statusLabel = (s: string) => (tk.statuses as Record<string, string>)[s] ?? s
  const priorityLabel = (p: string) => (tk.priorities as Record<string, string>)[p] ?? p
  const categoryLabel = (c: string) => (tk.categories as Record<string, string>)[c] ?? c
  const channelLabel = (c: string) =>
    (t.dashboard.channels as Record<string, string>)[c] ?? c
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="fade-in">
      <PageHeader title={crm.title} subtitle={crm.subtitle} />

      <div className="card p-4 mb-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <input
            className="input-field"
            placeholder={crm.search}
            value={search}
            onChange={(e) => {
              setPage(1)
              setSearch(e.target.value)
            }}
          />
          <select className="input-field" value={status} onChange={(e) => { setPage(1); setStatus(e.target.value) }}>
            <option value="">{crm.allStatuses}</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>{statusLabel(s)}</option>
            ))}
          </select>
          <select className="input-field" value={priority} onChange={(e) => { setPage(1); setPriority(e.target.value) }}>
            <option value="">{crm.allPriorities}</option>
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>{priorityLabel(p)}</option>
            ))}
          </select>
          <select className="input-field" value={channel} onChange={(e) => { setPage(1); setChannel(e.target.value) }}>
            <option value="">{crm.allChannels}</option>
            {CHAT_CHANNELS.map((c) => (
              <option key={c} value={c}>{channelLabel(c)}</option>
            ))}
          </select>
        </div>
      </div>

      {loading && items.length === 0 ? (
        <LoadingState />
      ) : error && items.length === 0 ? (
        <ErrorState message={error} onRetry={load} />
      ) : items.length === 0 ? (
        <EmptyState message={crm.empty} />
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]">
              <tr>
                <th className="text-start p-3">{crm.ref}</th>
                <th className="text-start p-3">{crm.subject}</th>
                <th className="text-start p-3">{crm.category}</th>
                <th className="text-start p-3">{crm.customer}</th>
                <th className="text-start p-3">{crm.status}</th>
                <th className="text-start p-3">{crm.priority}</th>
                <th className="text-start p-3">{crm.channel}</th>
                <th className="text-start p-3">{crm.created}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr
                  key={row.id}
                  className="border-t border-[var(--color-border-default)] hover:bg-[var(--color-surface-muted)] cursor-pointer"
                  onClick={() => navigate(`/admin/tickets/${row.id}`)}
                >
                  <td className="p-3 font-mono text-xs whitespace-nowrap">{row.ref_number}</td>
                  <td className="p-3 max-w-[18rem] truncate">{row.subject}</td>
                  <td className="p-3 whitespace-nowrap text-xs">{categoryLabel(row.category)}</td>
                  <td className="p-3 whitespace-nowrap">
                    {row.customer_id ? `#${row.customer_id}` : row.guest_name || row.guest_email || crm.guest}
                  </td>
                  <td className="p-3">
                    <span className={`ticket-status ticket-status-${row.status}`}>{statusLabel(row.status)}</span>
                  </td>
                  <td className="p-3">
                    <span className={`ticket-prio ticket-prio-${row.priority}`}>{priorityLabel(row.priority)}</span>
                  </td>
                  <td className="p-3 whitespace-nowrap">{channelLabel(row.channel)}</td>
                  <td className="p-3 whitespace-nowrap text-xs text-[var(--color-text-muted)]">
                    {new Date(row.created_at).toLocaleString(locale === 'ar' ? 'ar-EG' : 'en-GB')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-4 text-sm">
          <button type="button" className="btn-ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            {crm.prev}
          </button>
          <span className="text-[var(--color-text-muted)]">
            {crm.page} {page} / {totalPages}
          </span>
          <button type="button" className="btn-ghost" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
            {crm.next}
          </button>
        </div>
      )}
    </div>
  )
}
