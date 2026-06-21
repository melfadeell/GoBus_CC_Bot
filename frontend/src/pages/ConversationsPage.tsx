import { useCallback, useEffect, useState } from 'react'
import { api, ChatMessage, ChatSession } from '@/api/client'
import MessageBubble from '@/components/chat/MessageBubble'
import { EmptyState, ErrorState, LoadingState, PageHeader } from '@/components/admin/Shared'
import { useLanguage } from '@/i18n/LanguageProvider'

export default function ConversationsPage() {
  const { t } = useLanguage()
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [total, setTotal] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [messagesLoading, setMessagesLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [minMessages, setMinMessages] = useState('')

  const loadSessions = useCallback(() => {
    setLoading(true)
    setError(null)
    const params: Record<string, string> = { page: '1', page_size: '30' }
    if (dateFrom) params.date_from = dateFrom
    if (dateTo) params.date_to = dateTo
    if (minMessages.trim()) params.min_messages = minMessages.trim()

    api.getConversations(params)
      .then((res) => {
        setSessions(res.items)
        setTotal(res.total)
        setSelected((prev) => {
          if (prev && res.items.some((s) => s.session_id === prev)) return prev
          return res.items[0]?.session_id ?? null
        })
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [dateFrom, dateTo, minMessages])

  useEffect(() => {
    loadSessions()
  }, [loadSessions])

  useEffect(() => {
    if (!selected) {
      setMessages([])
      return
    }
    setMessagesLoading(true)
    api.getConversationMessages(selected)
      .then(setMessages)
      .catch((e) => setError(e.message))
      .finally(() => setMessagesLoading(false))
  }, [selected])

  function clearFilters() {
    setDateFrom('')
    setDateTo('')
    setMinMessages('')
  }

  const hasFilters = Boolean(dateFrom || dateTo || minMessages.trim())

  if (loading && sessions.length === 0) return <LoadingState />
  if (error && sessions.length === 0) return <ErrorState message={error} onRetry={loadSessions} />

  return (
    <div className="fade-in">
      <PageHeader title={t.conversations.title} subtitle={t.conversations.subtitle} />

      <div className="card p-4 mb-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 items-end">
          <div>
            <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">
              {t.conversations.dateFrom}
            </label>
            <input
              type="date"
              className="input-field"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">
              {t.conversations.dateTo}
            </label>
            <input
              type="date"
              className="input-field"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">
              {t.conversations.minMessages}
            </label>
            <input
              type="number"
              min={0}
              className="input-field"
              placeholder="0"
              value={minMessages}
              onChange={(e) => setMinMessages(e.target.value)}
            />
          </div>
          <div className="flex gap-2">
            {hasFilters && (
              <button type="button" className="btn-ghost flex-1" onClick={clearFilters}>
                {t.conversations.clearFilters}
              </button>
            )}
          </div>
        </div>
        {total > 0 && (
          <p className="text-xs text-[var(--color-text-muted)] mt-3">
            {t.conversations.resultsCount.replace('{count}', String(total))}
          </p>
        )}
      </div>

      {sessions.length === 0 ? (
        <EmptyState message={hasFilters ? t.conversations.noResults : t.conversations.empty} />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="card p-3 space-y-2 max-h-[640px] overflow-y-auto">
            {sessions.map((s) => (
              <button
                key={s.session_id}
                type="button"
                onClick={() => setSelected(s.session_id)}
                className={`w-full text-right p-3 rounded-lg text-sm transition-colors ${
                  selected === s.session_id
                    ? 'bg-[var(--color-accent-soft)] border border-[var(--color-brand-accent)]'
                    : 'hover:bg-[var(--color-surface-muted)]'
                }`}
              >
                <div className="font-medium truncate ltr text-left">{s.session_id.slice(0, 16)}…</div>
                <div className="text-xs text-[var(--color-text-muted)] mt-1">
                  {s.message_count} {t.conversations.messages} · {new Date(s.started_at).toLocaleString()}
                </div>
              </button>
            ))}
          </div>
          <div className="lg:col-span-2 card p-4 max-h-[640px] overflow-y-auto space-y-3 bg-[var(--color-surface-muted)]">
            {messagesLoading ? (
              <LoadingState label={t.conversations.loadingMsgs} />
            ) : messages.length === 0 ? (
              <EmptyState message={t.conversations.noMsgs} />
            ) : (
              messages.map((m) => (
                <MessageBubble
                  key={m.id}
                  role={m.role as 'user' | 'assistant'}
                  content={m.content}
                  imageUrl={m.image_url || undefined}
                />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
