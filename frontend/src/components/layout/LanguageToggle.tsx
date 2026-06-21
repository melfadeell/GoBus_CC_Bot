import { useLanguage } from '@/i18n/LanguageProvider'

interface LanguageToggleProps {
  className?: string
  /** Use on dark backgrounds (e.g. chat widget header) */
  onDark?: boolean
}

export default function LanguageToggle({ className = '', onDark = false }: LanguageToggleProps) {
  const { locale, setLocale } = useLanguage()

  const activeClass = onDark
    ? 'bg-white text-[var(--color-brand-primary)]'
    : 'bg-[var(--color-brand-primary)] text-white'

  const inactiveClass = onDark
    ? 'bg-white/15 text-white hover:bg-white/25'
    : 'bg-[var(--color-surface-muted)] text-[var(--color-brand-primary)] hover:bg-gray-200'

  const borderClass = onDark ? 'border-white/30' : 'border-[var(--color-border-default)]'

  return (
    <div className={`inline-flex rounded-lg border overflow-hidden text-xs font-semibold ${borderClass} ${className}`}>
      <button
        type="button"
        onClick={() => setLocale('ar')}
        className={`px-3 py-1.5 transition-colors ${locale === 'ar' ? activeClass : inactiveClass}`}
      >
        AR
      </button>
      <button
        type="button"
        onClick={() => setLocale('en')}
        className={`px-3 py-1.5 transition-colors ${locale === 'en' ? activeClass : inactiveClass}`}
      >
        EN
      </button>
    </div>
  )
}
