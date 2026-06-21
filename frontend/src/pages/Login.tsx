import { FormEvent, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { api, getToken, setToken } from '@/api/client'
import LanguageToggle from '@/components/layout/LanguageToggle'
import { useLanguage } from '@/i18n/LanguageProvider'

export default function LoginPage() {
  const navigate = useNavigate()
  const { t } = useLanguage()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (getToken()) return <Navigate to="/admin" replace />

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const res = await api.login(email, password)
      setToken(res.access_token)
      navigate('/admin')
    } catch (err) {
      setError(err instanceof Error ? err.message : t.login.error)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="min-h-dvh flex items-center justify-center p-4 relative"
      style={{ background: 'linear-gradient(135deg, #112347 0%, #1a3358 50%, #112347 100%)' }}
    >
      <div className="absolute top-4 end-4">
        <LanguageToggle />
      </div>
      <div className="card w-full max-w-md p-8 shadow-lg fade-in">
        <div className="text-center mb-8">
          <img src="/gobus_logo.jpg" alt="GoBus" className="h-16 w-16 rounded-full mx-auto mb-4 ring-4 ring-[var(--color-accent-soft)] object-cover" />
          <h1 className="text-xl font-bold">{t.login.title}</h1>
          <p className="text-sm text-[var(--color-text-muted)] mt-1">{t.login.subtitle}</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm mb-1.5 font-medium">{t.login.email}</label>
            <input
              className="input-field ltr"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t.login.emailPlaceholder}
              required
              autoComplete="username"
            />
          </div>
          <div>
            <label className="block text-sm mb-1.5 font-medium">{t.login.password}</label>
            <input
              className="input-field ltr"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t.login.passwordPlaceholder}
              required
              autoComplete="current-password"
            />
          </div>
          {error && <div className="alert-error text-sm">{error}</div>}
          <button type="submit" className="btn-primary w-full py-3" disabled={loading}>
            {loading ? t.login.submitting : t.login.submit}
          </button>
        </form>
        <div className="mt-6 text-center">
          <Link to="/chat" className="text-sm font-medium" style={{ color: 'var(--color-brand-accent)' }}>
            {t.login.tryChat}
          </Link>
        </div>
      </div>
    </div>
  )
}
