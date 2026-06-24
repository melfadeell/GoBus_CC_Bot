import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { api, type TicketDetail as TicketDetailData } from '@/api/client'
import { ErrorState, LoadingState, PageHeader } from '@/components/admin/Shared'
import { useLanguage } from '@/i18n/LanguageProvider'

const STATUSES = ['open', 'in_progress', 'waiting_customer', 'resolved', 'closed']
const PRIORITIES = ['low', 'medium', 'high', 'urgent']

export default function TicketDetail() {
  const { id } = useParams<{ id: string }>()
  const ticketId = Number(id)
  const navigate = useNavigate()
  const { t, locale } = useLanguage()
  const crm = t.crm
  const tk = t.chat.ticket

  const [ticket, setTicket] = useState<TicketDetailData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  const [saving, setSaving] = useState(false)
  const [replyBody, setReplyBody] = useState('')
  const [sending, setSending] = useState(false)
  const [adminId, setAdminId] = useState<number | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    api
      .getAdminTicket(ticketId)
      .then((tt) => {
        setTicket(tt)
        setStatus(tt.status)
        setPriority(tt.priority)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [ticketId])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    api.getAdminMe().then((m) => setAdminId(m.id)).catch(() => {})
  }, [])

  const statusLabel = (s: string) => (tk.statuses as Record<string, string>)[s] ?? s
  const priorityLabel = (p: string) => (tk.priorities as Record<string, string>)[p] ?? p
  const categoryLabel = (c: string) => (tk.categories as Record<string, string>)[c] ?? c
  const authorLabel = (a: string) => (crm.authors as Record<string, string>)[a] ?? a

  async function saveChanges() {
    if (!ticket) return
    setSaving(true)
    try {
      const updated = await api.updateAdminTicket(ticket.id, { status, priority })
      setTicket(updated)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function assignToMe() {
    if (!ticket || adminId == null) return
    setSaving(true)
    try {
      const updated = await api.updateAdminTicket(ticket.id, { assigned_admin_id: adminId })
      setTicket(updated)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function sendReply() {
    if (!ticket || !replyBody.trim()) return
    setSending(true)
    try {
      const updated = await api.replyAdminTicket(ticket.id, replyBody.trim())
      setTicket(updated)
      setReplyBody('')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSending(false)
    }
  }

  if (loading && !ticket) return <LoadingState />
  if (error && !ticket) return <ErrorState message={error} onRetry={load} />
  if (!ticket) return null

  const fmt = (d: string | null) =>
    d ? new Date(d).toLocaleString(locale === 'ar' ? 'ar-EG' : 'en-GB') : '—'
  const dirty = status !== ticket.status || priority !== ticket.priority

  return (
    <div className="fade-in">
      <button type="button" className="btn-ghost mb-3 inline-flex items-center gap-1 text-sm" onClick={() => navigate('/admin/tickets')}>
        <ArrowRight size={15} className="rotate-180 rtl:rotate-0" />
        {crm.back}
      </button>

      <PageHeader title={ticket.ref_number} subtitle={ticket.subject} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left: details + thread */}
        <div className="lg:col-span-2 space-y-4">
          <div className="card p-4">
            <h3 className="font-semibold mb-2">{crm.details}</h3>
            <p className="text-sm whitespace-pre-wrap text-[var(--color-text-default)]">{ticket.description}</p>
            <div className="grid grid-cols-2 gap-2 mt-3 text-xs text-[var(--color-text-muted)]">
              <div>{crm.category}: <b>{categoryLabel(ticket.category)}</b></div>
              <div>{crm.channel}: <b>{(t.dashboard.channels as Record<string, string>)[ticket.channel] ?? ticket.channel}</b></div>
              <div>{crm.created}: <b>{fmt(ticket.created_at)}</b></div>
              <div>{crm.resolvedAt}: <b>{fmt(ticket.resolved_at)}</b></div>
              <div>{crm.autoPriority}: <b>{ticket.priority_auto ? priorityLabel(ticket.priority_auto) : '—'}</b></div>
              {ticket.session_id ? <div>{crm.openedFrom}: <b className="font-mono">{ticket.session_id.slice(0, 12)}…</b></div> : null}
            </div>
          </div>

          <div className="card p-4">
            <h3 className="font-semibold mb-3">{crm.thread}</h3>
            <div className="space-y-3">
              {ticket.messages.length === 0 ? (
                <p className="text-sm text-[var(--color-text-muted)]">{crm.noMessages}</p>
              ) : (
                ticket.messages.map((m) => (
                  <div key={m.id} className={`ticket-thread-msg ticket-thread-${m.author_type}`} dir="auto">
                    <div className="ticket-thread-head">
                      <span className="ticket-thread-author">{authorLabel(m.author_type)}</span>
                      <span className="ticket-thread-time">{fmt(m.created_at)}</span>
                    </div>
                    <div className="ticket-thread-body">{m.body}</div>
                  </div>
                ))
              )}
            </div>

            <div className="mt-4">
              <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">{crm.reply}</label>
              <textarea
                className="input-field"
                rows={3}
                placeholder={crm.replyPlaceholder}
                value={replyBody}
                onChange={(e) => setReplyBody(e.target.value)}
              />
              <button
                type="button"
                className="btn-accent mt-2"
                disabled={sending || !replyBody.trim()}
                onClick={sendReply}
              >
                {sending ? crm.sending : crm.send}
              </button>
            </div>
          </div>
        </div>

        {/* Right: controls + contact */}
        <div className="space-y-4">
          <div className="card p-4 space-y-3">
            <div>
              <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">{crm.status}</label>
              <select className="input-field" value={status} onChange={(e) => setStatus(e.target.value)}>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>{statusLabel(s)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">{crm.priority}</label>
              <select className="input-field" value={priority} onChange={(e) => setPriority(e.target.value)}>
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>{priorityLabel(p)}</option>
                ))}
              </select>
            </div>
            <button type="button" className="btn-accent w-full" disabled={saving || !dirty} onClick={saveChanges}>
              {saving ? crm.saving : crm.save}
            </button>
            <div className="text-xs text-[var(--color-text-muted)]">
              {crm.assignee}: <b>{ticket.assigned_admin_id ? `#${ticket.assigned_admin_id}` : crm.unassigned}</b>
            </div>
            <button type="button" className="btn-ghost w-full" disabled={saving || adminId == null} onClick={assignToMe}>
              {crm.assignToMe}
            </button>
          </div>

          <div className="card p-4 text-sm space-y-1">
            <h3 className="font-semibold mb-1">{crm.contact}</h3>
            <div>{crm.customer}: <b>{ticket.customer_id ? `#${ticket.customer_id}` : ticket.guest_name || crm.guest}</b></div>
            <div>{crm.email}: <b dir="ltr">{ticket.guest_email || '—'}</b></div>
            <div>{crm.phone}: <b dir="ltr">{ticket.guest_phone || '—'}</b></div>
          </div>
        </div>
      </div>

      {error && <div className="alert-error text-sm mt-3">{error}</div>}
    </div>
  )
}
