import { CalendarDays, X } from 'lucide-react'
import { useLanguage } from '@/i18n/LanguageProvider'

interface DateRangeFilterProps {
  from: string
  to: string
  onChange: (from: string, to: string) => void
  presets?: boolean
}

function isoDaysAgo(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString().slice(0, 10)
}

/** Modern, reusable date-range control (from/to + quick presets + clear). */
export default function DateRangeFilter({ from, to, onChange, presets = true }: DateRangeFilterProps) {
  const { t } = useLanguage()
  const active = Boolean(from || to)

  return (
    <div className="date-range-filter">
      <span className="drf-icon">
        <CalendarDays size={15} />
      </span>
      <div className="drf-field">
        <span className="drf-label">{t.common.dateFrom}</span>
        <input
          type="date"
          className="drf-input"
          value={from}
          max={to || undefined}
          onChange={(e) => onChange(e.target.value, to)}
        />
      </div>
      <span className="drf-sep">→</span>
      <div className="drf-field">
        <span className="drf-label">{t.common.dateTo}</span>
        <input
          type="date"
          className="drf-input"
          value={to}
          min={from || undefined}
          onChange={(e) => onChange(from, e.target.value)}
        />
      </div>

      {presets && (
        <div className="drf-presets">
          <button type="button" className="drf-preset" onClick={() => onChange(isoDaysAgo(6), isoDaysAgo(0))}>
            {t.common.last7days}
          </button>
          <button type="button" className="drf-preset" onClick={() => onChange(isoDaysAgo(29), isoDaysAgo(0))}>
            {t.common.last30days}
          </button>
        </div>
      )}

      {active && (
        <button type="button" className="drf-clear" onClick={() => onChange('', '')} title={t.common.clearDates}>
          <X size={14} />
        </button>
      )}
    </div>
  )
}
