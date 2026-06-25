import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, LogOut, Ticket as TicketIcon } from 'lucide-react'
import {
  ApiError,
  clearCustomerToken,
  customerApi,
  getCustomerToken,
  type CustomerProfile,
  type TicketSummary,
} from '@/api/client'
import { formatValidationDetail } from '@/api/validationErrors'
import { useLanguage } from '@/i18n/LanguageProvider'

const STATUS_ORDER = ['open', 'in_progress', 'waiting_customer', 'resolved', 'closed']

export default function CustomerAccountPage() {
  const { t, locale } = useLanguage()
  const navigate = useNavigate()
  const a = t.chat.account
  const tk = t.chat.ticket
  const validationMsgs = {
    ...t.chat.auth.validation,
    passwordsMismatch: t.chat.auth.passwordsMismatch,
  }

  function apiErrorMessage(err: unknown, fallback: string) {
    if (err instanceof ApiError) {
      return formatValidationDetail(err.detail, validationMsgs)
    }
    return (err as Error).message || fallback
  }

  const [profile, setProfile] = useState<CustomerProfile | null>(null)
  const [tickets, setTickets] = useState<TicketSummary[]>([])
  const [loading, setLoading] = useState(true)

  // profile form
  const [fullName, setFullName] = useState('')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [pMsg, setPMsg] = useState<string | null>(null)
  const [pErr, setPErr] = useState<string | null>(null)
  const [savingProfile, setSavingProfile] = useState(false)

  // password form
  const [oldPw, setOldPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [pwMsg, setPwMsg] = useState<string | null>(null)
  const [pwErr, setPwErr] = useState<string | null>(null)
  const [savingPw, setSavingPw] = useState(false)

  useEffect(() => {
    if (!getCustomerToken()) {
      navigate('/chat')
      return
    }
    Promise.all([customerApi.me(), customerApi.listMyTickets().catch(() => [])])
      .then(([p, ts]) => {
        setProfile(p)
        setFullName(p.full_name)
        setPhone(p.phone)
        setEmail(p.email)
        setTickets(ts)
      })
      .catch(() => navigate('/chat'))
      .finally(() => setLoading(false))
  }, [navigate])

  const grouped = useMemo(() => {
    const g: Record<string, TicketSummary[]> = {}
    for (const ticket of tickets) (g[ticket.status] ??= []).push(ticket)
    return g
  }, [tickets])

  async function saveProfile() {
    setPMsg(null)
    setPErr(null)
    setSavingProfile(true)
    try {
      const updated = await customerApi.updateProfile({
        full_name: fullName.trim(),
        phone: phone.trim(),
        email: email.trim(),
      })
      setProfile(updated)
      setPMsg(a.saved)
    } catch (e) {
      setPErr(apiErrorMessage(e, a.updateError))
    } finally {
      setSavingProfile(false)
    }
  }

  async function savePassword() {
    setPwMsg(null)
    setPwErr(null)
    if (newPw !== confirmPw) {
      setPwErr(t.chat.auth.passwordsMismatch)
      return
    }
    setSavingPw(true)
    try {
      await customerApi.changePassword({
        old_password: oldPw,
        new_password: newPw,
        confirm_password: confirmPw,
      })
      setPwMsg(a.passwordChanged)
      setOldPw('')
      setNewPw('')
      setConfirmPw('')
    } catch (e) {
      setPwErr(apiErrorMessage(e, a.passwordError))
    } finally {
      setSavingPw(false)
    }
  }

  function logout() {
    clearCustomerToken()
    navigate('/chat')
  }

  if (loading) {
    return <div className="account-page text-[var(--color-text-muted)]">{t.common.loading}</div>
  }
  if (!profile) return null

  const statusLabel = (s: string) => (tk.statuses as Record<string, string>)[s] ?? s
  const priorityLabel = (p: string) => (tk.priorities as Record<string, string>)[p] ?? p
  const initials = profile.full_name.trim().charAt(0).toUpperCase()

  return (
    <div className="account-page" dir="auto">
      <div className="flex items-center justify-between mb-4">
        <button type="button" className="ticket-btn ticket-btn-ghost" onClick={() => navigate('/chat')}>
          <ArrowRight size={15} className="rotate-180 rtl:rotate-0" />
          {a.backToChat}
        </button>
        <button type="button" className="ticket-btn" onClick={logout}>
          <LogOut size={15} />
          {t.chat.auth.logout}
        </button>
      </div>

      {/* Identity */}
      <div className="account-card flex items-center gap-4">
        <div className="account-avatar">{initials}</div>
        <div>
          <div className="font-bold text-lg">{profile.full_name}</div>
          <div className="text-sm text-[var(--color-text-muted)]" dir="ltr">{profile.email}</div>
          <div className="text-sm text-[var(--color-text-muted)]" dir="ltr">{profile.phone}</div>
        </div>
      </div>

      {/* Edit profile */}
      <div className="account-card">
        <h3>{a.editProfile}</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="ticket-field">
            <span>{t.chat.auth.fullName}</span>
            <input className="ticket-input" value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </label>
          <label className="ticket-field">
            <span>{t.chat.auth.phone}</span>
            <input className="ticket-input" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </label>
          <label className="ticket-field sm:col-span-2">
            <span>{t.chat.auth.email}</span>
            <input className="ticket-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
        </div>
        {pErr && <div className="ticket-error mt-2">{pErr}</div>}
        {pMsg && <div className="ticket-verified mt-2">{pMsg}</div>}
        <button type="button" className="ticket-btn ticket-btn-primary mt-3" disabled={savingProfile} onClick={saveProfile}>
          {savingProfile ? a.saving : a.save}
        </button>
      </div>

      {/* Change password */}
      <div className="account-card">
        <h3>{a.changePassword}</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <label className="ticket-field">
            <span>{a.oldPassword}</span>
            <input className="ticket-input" type="password" value={oldPw} onChange={(e) => setOldPw(e.target.value)} />
          </label>
          <label className="ticket-field">
            <span>{a.newPassword}</span>
            <input className="ticket-input" type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} />
          </label>
          <label className="ticket-field">
            <span>{a.confirmPassword}</span>
            <input className="ticket-input" type="password" value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} />
          </label>
        </div>
        {pwErr && <div className="ticket-error mt-2">{pwErr}</div>}
        {pwMsg && <div className="ticket-verified mt-2">{pwMsg}</div>}
        <button type="button" className="ticket-btn ticket-btn-primary mt-3" disabled={savingPw} onClick={savePassword}>
          {savingPw ? a.saving : a.changePassword}
        </button>
      </div>

      {/* My tickets grouped by status */}
      <div className="account-card">
        <h3 className="flex items-center gap-2"><TicketIcon size={16} /> {a.myTickets}</h3>
        {tickets.length === 0 ? (
          <div className="ticket-empty">{a.noTickets}</div>
        ) : (
          STATUS_ORDER.filter((s) => grouped[s]?.length).map((s) => (
            <div key={s} className="account-ticket-group">
              <div className="account-ticket-group-title">
                <span className={`ticket-status ticket-status-${s}`}>{statusLabel(s)}</span>
                <span>({grouped[s].length})</span>
              </div>
              <div className="ticket-card-list">
                {grouped[s].map((ticket) => (
                  <div key={ticket.ref_number} className="ticket-card">
                    <div className="ticket-card-head">
                      <span className="ticket-ref">{ticket.ref_number}</span>
                      <span className={`ticket-prio ticket-prio-${ticket.priority}`}>{priorityLabel(ticket.priority)}</span>
                    </div>
                    <div className="ticket-card-subject">{ticket.subject}</div>
                    <div className="ticket-card-meta">
                      <span className="ticket-date">
                        {new Date(ticket.created_at).toLocaleDateString(locale === 'ar' ? 'ar-EG' : 'en-GB')}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
