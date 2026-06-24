import { Hash, Clock } from 'lucide-react'
import type { TicketSummary } from '@/api/client'
import { useLanguage } from '@/i18n/LanguageProvider'

interface TicketCardListProps {
  tickets: TicketSummary[]
}

/** Deterministic ticket follow-up cards (never model markdown). */
export default function TicketCardList({ tickets }: TicketCardListProps) {
  const { t, locale } = useLanguage()
  const tk = t.chat.ticket

  if (!tickets.length) {
    return <div className="ticket-empty mt-2">{tk.noTickets}</div>
  }

  const statusLabel = (s: string) =>
    (tk.statuses as Record<string, string>)[s] ?? s
  const priorityLabel = (p: string) =>
    (tk.priorities as Record<string, string>)[p] ?? p
  const categoryLabel = (c: string) =>
    (tk.categories as Record<string, string>)[c] ?? c

  return (
    <div className="ticket-card-list mt-2 flex flex-col gap-2">
      {tickets.map((t0) => (
        <div key={t0.ref_number} className="ticket-card" dir="auto">
          <div className="ticket-card-head">
            <span className="ticket-ref">
              <Hash size={12} />
              {t0.ref_number}
            </span>
            <span className={`ticket-status ticket-status-${t0.status}`}>
              {statusLabel(t0.status)}
            </span>
          </div>
          <div className="ticket-card-subject">{t0.subject}</div>
          <div className="ticket-card-meta">
            <span className={`ticket-prio ticket-prio-${t0.priority}`}>
              {priorityLabel(t0.priority)}
            </span>
            <span className="ticket-cat">{categoryLabel(t0.category)}</span>
            <span className="ticket-date">
              <Clock size={11} />
              {new Date(t0.created_at).toLocaleDateString(locale === 'ar' ? 'ar-EG' : 'en-GB')}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}
