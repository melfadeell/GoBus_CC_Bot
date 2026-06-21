import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { translations, type Locale, type TranslationTree } from './translations'

export type LanguageScope = 'admin' | 'chat'

const STORAGE_KEYS: Record<LanguageScope, string> = {
  admin: 'gobus_locale_admin',
  chat: 'gobus_locale_chat',
}

interface LanguageProviderProps {
  scope: LanguageScope
  defaultLocale: Locale
  children: ReactNode
}

interface LanguageContextValue {
  locale: Locale
  setLocale: (locale: Locale) => void
  toggleLocale: () => void
  t: TranslationTree
  dir: 'rtl' | 'ltr'
  scope: LanguageScope
}

const LanguageContext = createContext<LanguageContextValue | null>(null)

export function LanguageProvider({ scope, defaultLocale, children }: LanguageProviderProps) {
  const storageKey = STORAGE_KEYS[scope]

  const [locale, setLocaleState] = useState<Locale>(() => {
    const saved = localStorage.getItem(storageKey) as Locale | null
    if (saved === 'en' || saved === 'ar') return saved
    return defaultLocale
  })

  const setLocale = useCallback(
    (next: Locale) => {
      setLocaleState(next)
      localStorage.setItem(storageKey, next)
    },
    [storageKey]
  )

  const toggleLocale = useCallback(() => {
    setLocale(locale === 'ar' ? 'en' : 'ar')
  }, [locale, setLocale])

  const dir: 'rtl' | 'ltr' = locale === 'ar' ? 'rtl' : 'ltr'

  useEffect(() => {
    document.documentElement.lang = locale
    document.documentElement.dir = dir
  }, [locale, dir])

  const value = useMemo(
    () => ({
      locale,
      setLocale,
      toggleLocale,
      t: translations[locale],
      dir,
      scope,
    }),
    [locale, setLocale, toggleLocale, dir, scope]
  )

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}

export function useLanguage() {
  const ctx = useContext(LanguageContext)
  if (!ctx) throw new Error('useLanguage must be used within LanguageProvider')
  return ctx
}
