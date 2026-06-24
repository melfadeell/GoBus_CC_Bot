import { useState } from 'react'
import { X } from 'lucide-react'
import { customerApi, setCustomerToken, type CustomerProfile } from '@/api/client'
import { useLanguage } from '@/i18n/LanguageProvider'

interface CustomerAuthModalProps {
  initialMode?: 'login' | 'register'
  onClose: () => void
  onAuthed: (profile: CustomerProfile) => void
}

export default function CustomerAuthModal({
  initialMode = 'login',
  onClose,
  onAuthed,
}: CustomerAuthModalProps) {
  const { t } = useLanguage()
  const a = t.chat.auth
  const [mode, setMode] = useState<'login' | 'register'>(initialMode)
  const [fullName, setFullName] = useState('')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    setError(null)
    if (mode === 'register' && password !== confirm) {
      setError(a.passwordsMismatch)
      return
    }
    setBusy(true)
    try {
      const res =
        mode === 'login'
          ? await customerApi.login(email.trim(), password)
          : await customerApi.register({
              full_name: fullName.trim(),
              phone: phone.trim(),
              email: email.trim(),
              password,
              confirm_password: confirm,
            })
      setCustomerToken(res.access_token)
      const profile = await customerApi.me()
      onAuthed(profile)
    } catch (err) {
      setError((err as Error).message || a.authError)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="cust-auth-overlay" onClick={onClose}>
      <div className="cust-auth-modal" onClick={(e) => e.stopPropagation()} dir="auto">
        <div className="cust-auth-head">
          <h3>{mode === 'login' ? a.loginTitle : a.registerTitle}</h3>
          <button type="button" className="cust-auth-close" onClick={onClose} aria-label={a.close}>
            <X size={18} />
          </button>
        </div>

        <div className="cust-auth-body">
          {mode === 'register' && (
            <label className="ticket-field">
              <span>{a.fullName}</span>
              <input value={fullName} onChange={(e) => setFullName(e.target.value)} className="ticket-input" />
            </label>
          )}
          {mode === 'register' && (
            <label className="ticket-field">
              <span>{a.phone}</span>
              <input value={phone} onChange={(e) => setPhone(e.target.value)} className="ticket-input" />
            </label>
          )}
          <label className="ticket-field">
            <span>{a.email}</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="ticket-input"
            />
          </label>
          <label className="ticket-field">
            <span>{a.password}</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="ticket-input"
            />
          </label>
          {mode === 'register' && (
            <label className="ticket-field">
              <span>{a.confirmPassword}</span>
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="ticket-input"
              />
            </label>
          )}

          {error && <div className="ticket-error">{error}</div>}

          <button
            type="button"
            className="ticket-btn ticket-btn-primary cust-auth-submit"
            onClick={submit}
            disabled={busy}
          >
            {busy
              ? t.common.loading
              : mode === 'login'
                ? a.submitLogin
                : a.submitRegister}
          </button>

          <button
            type="button"
            className="cust-auth-switch"
            onClick={() => {
              setError(null)
              setMode((m) => (m === 'login' ? 'register' : 'login'))
            }}
          >
            {mode === 'login' ? a.switchToRegister : a.switchToLogin}
          </button>
        </div>
      </div>
    </div>
  )
}
