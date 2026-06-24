import { useState } from 'react'
import { Check, CircleCheck, X } from 'lucide-react'
import { customerApi, type TicketDraft } from '@/api/client'
import { useLanguage } from '@/i18n/LanguageProvider'

const CATEGORIES = ['booking', 'refund_payment', 'complaint', 'lost_item', 'schedule_trip', 'other']
const PRIORITIES = ['low', 'medium', 'high', 'urgent']

interface TicketFormProps {
  draft: TicketDraft
  loggedIn: boolean
  channel: string
  sessionId: string | null
}

type Phase = 'edit' | 'created' | 'cancelled'

export default function TicketForm({ draft, loggedIn, channel, sessionId }: TicketFormProps) {
  const { t } = useLanguage()
  const tk = t.chat.ticket

  const [phase, setPhase] = useState<Phase>('edit')
  const [subject, setSubject] = useState(draft.subject)
  const [description, setDescription] = useState(draft.description)
  // Auto-classified, not shown to the customer — fixed from the agent's draft.
  const category = CATEGORIES.includes(draft.category) ? draft.category : 'other'
  const priority = PRIORITIES.includes(draft.priority) ? draft.priority : 'medium'

  // Guest contact + OTP
  const [guestName, setGuestName] = useState('')
  const [guestEmail, setGuestEmail] = useState('')
  const [guestPhone, setGuestPhone] = useState('')
  const [otpSent, setOtpSent] = useState(false)
  const [code, setCode] = useState('')
  const [verifiedToken, setVerifiedToken] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [createdRef, setCreatedRef] = useState('')

  const canCreate = loggedIn || !!verifiedToken

  async function sendOtp() {
    if (!guestEmail.trim()) return
    setBusy(true)
    setError(null)
    try {
      await customerApi.requestOtp(guestEmail.trim(), 'ticket_create')
      setOtpSent(true)
    } catch {
      setError(tk.otpError)
    } finally {
      setBusy(false)
    }
  }

  async function verify() {
    setBusy(true)
    setError(null)
    try {
      const res = await customerApi.verifyOtp(guestEmail.trim(), code.trim(), 'ticket_create')
      setVerifiedToken(res.verified_token)
    } catch {
      setError(tk.otpError)
    } finally {
      setBusy(false)
    }
  }

  async function create() {
    setBusy(true)
    setError(null)
    try {
      const ticket = await customerApi.createTicket({
        subject,
        description,
        category,
        priority,
        priority_auto: draft.priority,
        channel,
        session_id: sessionId,
        ...(loggedIn
          ? {}
          : {
              guest_name: guestName.trim(),
              guest_email: guestEmail.trim(),
              guest_phone: guestPhone.trim(),
              verified_token: verifiedToken ?? undefined,
            }),
      })
      setCreatedRef(ticket.ref_number)
      setPhase('created')
    } catch {
      setError(tk.createError)
    } finally {
      setBusy(false)
    }
  }

  if (phase === 'created') {
    return (
      <div className="ticket-form ticket-form-done mt-2" dir="auto">
        <CircleCheck size={18} className="shrink-0" />
        <span>
          {tk.created} <strong>{createdRef}</strong>
        </span>
      </div>
    )
  }
  if (phase === 'cancelled') {
    return (
      <div className="ticket-form ticket-form-cancelled mt-2" dir="auto">
        {tk.cancelled}
      </div>
    )
  }

  return (
    <div className="ticket-form mt-2" dir="auto">
      <div className="ticket-form-title">{tk.formTitle}</div>
      <p className="ticket-form-intro">{tk.intro}</p>

      <label className="ticket-field">
        <span>{tk.subject}</span>
        <input value={subject} onChange={(e) => setSubject(e.target.value)} className="ticket-input" />
      </label>
      <label className="ticket-field">
        <span>{tk.description}</span>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="ticket-input"
          rows={3}
        />
      </label>
      {/* Category & priority are auto-classified and handled internally — not shown
          to the customer. They're still submitted with the ticket. */}

      {!loggedIn && (
        <div className="ticket-guest">
          <p className="ticket-form-intro">{tk.guestNote}</p>
          <label className="ticket-field">
            <span>{tk.name}</span>
            <input value={guestName} onChange={(e) => setGuestName(e.target.value)} className="ticket-input" />
          </label>
          <div className="ticket-field-row">
            <label className="ticket-field">
              <span>{tk.email}</span>
              <input
                type="email"
                value={guestEmail}
                onChange={(e) => setGuestEmail(e.target.value)}
                className="ticket-input"
                disabled={!!verifiedToken}
              />
            </label>
            <label className="ticket-field">
              <span>{tk.phone}</span>
              <input value={guestPhone} onChange={(e) => setGuestPhone(e.target.value)} className="ticket-input" />
            </label>
          </div>

          {verifiedToken ? (
            <div className="ticket-verified">{tk.verified}</div>
          ) : otpSent ? (
            <div className="ticket-otp-row">
              <input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className="ticket-input"
                placeholder={tk.otpCode}
                inputMode="numeric"
              />
              <button type="button" className="ticket-btn" onClick={verify} disabled={busy || !code.trim()}>
                {busy ? tk.verifying : tk.verify}
              </button>
            </div>
          ) : (
            <button
              type="button"
              className="ticket-btn"
              onClick={sendOtp}
              disabled={busy || !guestEmail.trim() || !guestName.trim() || !guestPhone.trim()}
            >
              {busy ? tk.sending : tk.sendOtp}
            </button>
          )}
          {otpSent && !verifiedToken && <div className="ticket-hint">{tk.otpSent}</div>}
        </div>
      )}

      {error && <div className="ticket-error">{error}</div>}

      <div className="ticket-actions">
        <button
          type="button"
          className="ticket-btn ticket-btn-primary"
          onClick={create}
          disabled={busy || !canCreate || !subject.trim() || !description.trim()}
        >
          <Check size={14} />
          {busy ? tk.creating : tk.confirm}
        </button>
        <button
          type="button"
          className="ticket-btn ticket-btn-ghost"
          onClick={() => setPhase('cancelled')}
          disabled={busy}
        >
          <X size={14} />
          {tk.cancel}
        </button>
      </div>
    </div>
  )
}
