import { ReactNode } from 'react'
import { AlertCircle, CheckCircle2 } from 'lucide-react'
import { useLanguage } from '@/i18n/LanguageProvider'

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6">
      <div>
        <h2 className="text-xl font-bold">{title}</h2>
        {subtitle && <p className="text-sm text-[var(--color-text-muted)] mt-1">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}

export function SearchBar({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  const { t } = useLanguage()
  return (
    <input className="input-field max-w-md mb-4" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder || t.common.search} />
  )
}

export function LoadingState({ label }: { label?: string }) {
  const { t } = useLanguage()
  return <div className="text-center py-16 text-[var(--color-text-muted)]">{label || t.common.loading}</div>
}

export function EmptyState({ message }: { message: string }) {
  return <div className="card py-16 text-center text-[var(--color-text-muted)] fade-in">{message}</div>
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useLanguage()
  return (
    <div className="alert-error flex items-start gap-3 fade-in">
      <AlertCircle size={18} className="shrink-0 mt-0.5" />
      <div className="flex-1">
        <p>{message}</p>
        {onRetry && <button type="button" className="btn-ghost mt-3 text-sm" onClick={onRetry}>{t.common.retry}</button>}
      </div>
    </div>
  )
}

export function SuccessBanner({ message }: { message: string }) {
  return (
    <div className="alert-success flex items-center gap-2 mb-4 fade-in">
      <CheckCircle2 size={18} />
      <span>{message}</span>
    </div>
  )
}

export function FormActions({ saving, onCancel, saveLabel }: { saving: boolean; onCancel: () => void; saveLabel?: string }) {
  const { t } = useLanguage()
  return (
    <div className="flex gap-3 pt-2">
      <button type="submit" className="btn-primary" disabled={saving}>{saving ? t.common.saving : (saveLabel || t.common.save)}</button>
      <button type="button" className="btn-ghost" onClick={onCancel}>{t.common.cancel}</button>
    </div>
  )
}

export function StatusBadge({ status }: { status: string }) {
  const { t } = useLanguage()
  const labels: Record<string, string> = { open: t.common.open, full: t.common.full, cancelled: t.common.cancelled }
  const cls = status === 'open' ? 'badge-open' : status === 'full' ? 'badge-full' : 'badge-cancelled'
  return <span className={`badge ${cls}`}>{labels[status] || status}</span>
}
