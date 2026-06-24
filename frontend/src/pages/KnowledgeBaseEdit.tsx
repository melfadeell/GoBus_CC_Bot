import { ChangeEvent, FormEvent, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { FileUp, Sparkles } from 'lucide-react'
import { api, KbArticle, KbCategory } from '@/api/client'
import { LoadingState, PageHeader, FormActions, ErrorState, SuccessBanner } from '@/components/admin/Shared'
import EnhanceCompareModal from '@/components/admin/EnhanceCompareModal'
import ToggleSwitch from '@/components/admin/ToggleSwitch'
import { useLanguage } from '@/i18n/LanguageProvider'
import { SERVICE_CODES, parseServiceScope, serializeServiceScope } from '@/utils/serviceScope'

export default function KnowledgeBaseEditPage() {
  const { t } = useLanguage()
  const { id } = useParams()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const isNew = id === 'new'
  const [categories, setCategories] = useState<KbCategory[]>([])
  const [form, setForm] = useState<KbArticle>({
    category_id: null,
    title: '',
    content: '',
    service_scope: 'gobus',
    is_active: true,
  })
  const [scopeAll, setScopeAll] = useState(false)
  const [scopeServices, setScopeServices] = useState<string[]>(['gobus'])
  const [loading, setLoading] = useState(!isNew)
  const [saving, setSaving] = useState(false)
  const [enhancing, setEnhancing] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [compareOpen, setCompareOpen] = useState(false)
  const [compareOriginal, setCompareOriginal] = useState('')
  const [compareEnhanced, setCompareEnhanced] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    api.getKbCategories().then((cats) => {
      setCategories(cats)
      if (isNew) {
        const code = searchParams.get('category')
        const match = cats.find((c) => c.code === code)
        if (match) setForm((f) => ({ ...f, category_id: match.id }))
      }
    })
    if (!isNew && id) {
      api.getKbArticle(Number(id)).then((article) => {
        setForm(article)
        const parsed = parseServiceScope(article.service_scope)
        setScopeAll(parsed.all)
        setScopeServices(parsed.services.length ? parsed.services : ['gobus'])
      }).finally(() => setLoading(false))
    }
  }, [id, isNew, searchParams])

  function updateScope(all: boolean, services: string[]) {
    // Selecting every individual scope is equivalent to "All" — collapse to it.
    if (!all && services.length >= SERVICE_CODES.length) {
      all = true
      services = []
    }
    setScopeAll(all)
    setScopeServices(services)
    setForm((f) => ({ ...f, service_scope: serializeServiceScope(all, services) }))
  }

  function toggleService(code: string) {
    if (scopeAll) updateScope(false, [code])
    else {
      const next = scopeServices.includes(code)
        ? scopeServices.filter((s) => s !== code)
        : [...scopeServices, code]
      updateScope(false, next.length ? next : [code])
    }
  }

  async function handleImportFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setExtracting(true)
    setError(null)
    try {
      const res = await api.extractKbFile(file)
      setForm((f) => ({
        ...f,
        content: res.text,
        title: f.title.trim() || file.name.replace(/\.[^.]+$/, ''),
      }))
    } catch (err) {
      setError(err instanceof Error ? err.message : t.common.saveFailed)
    } finally {
      setExtracting(false)
    }
  }

  async function handleEnhance() {
    if (!form.content.trim()) return
    setEnhancing(true)
    setError(null)
    const original = form.content
    try {
      const res = await api.enhanceText(original)
      setCompareOriginal(original)
      setCompareEnhanced(res.text)
      setCompareOpen(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : t.common.saveFailed)
    } finally {
      setEnhancing(false)
    }
  }

  function closeCompare() {
    setCompareOpen(false)
  }

  function useOriginalText() {
    closeCompare()
  }

  function useEnhancedText() {
    setForm((f) => ({ ...f, content: compareEnhanced }))
    closeCompare()
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!form.category_id) {
      setError(t.kb.selectCategory)
      return
    }
    setSaving(true)
    setError(null)
    const { slug: _slug, ...rest } = form
    const payload = { ...rest, service_scope: serializeServiceScope(scopeAll, scopeServices) }
    try {
      if (isNew) {
        await api.createKbArticle(payload)
        navigate('/admin/kb')
      } else {
        await api.updateKbArticle(Number(id), payload)
        setSuccess(true)
        setTimeout(() => setSuccess(false), 3000)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t.common.saveFailed)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <LoadingState />

  return (
    <div>
      <PageHeader title={isNew ? t.kb.addArticle : t.kb.editArticle} />
      {success && <SuccessBanner message={t.kb.saved} />}
      {error && <div className="mb-4"><ErrorState message={error} /></div>}
      <form onSubmit={handleSubmit} className="card p-6 space-y-4 max-w-4xl">
        <div>
          <label className="block text-sm mb-1 font-medium">{t.kb.titleLabel}</label>
          <input className="input-field" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm mb-1 font-medium">{t.kb.categoryLabel}</label>
            <select
              className="input-field"
              value={form.category_id ?? ''}
              onChange={(e) => setForm({ ...form, category_id: e.target.value ? Number(e.target.value) : null })}
              required
            >
              <option value="">{t.kb.selectCategory}</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>{c.name_ar}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm mb-1 font-medium">{t.kb.scopeLabel}</label>
            <div className="flex flex-wrap gap-2 mt-1">
              <button
                type="button"
                className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${scopeAll ? 'bg-[var(--color-brand-primary)] text-white border-transparent' : 'border-[var(--color-border-default)]'}`}
                onClick={() => updateScope(true, [])}
              >
                {t.kb.scopeAll}
              </button>
              {SERVICE_CODES.map((code) => (
                <button
                  key={code}
                  type="button"
                  className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                    !scopeAll && scopeServices.includes(code)
                      ? 'bg-[var(--color-brand-accent)] text-white border-transparent'
                      : 'border-[var(--color-border-default)]'
                  }`}
                  onClick={() => toggleService(code)}
                >
                  {code === 'gobus' ? 'GoBus' : code === 'gomini' ? 'GoMini' : 'GoLemo'}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div>
          <div className="flex items-center justify-between mb-1 gap-2 flex-wrap">
            <label className="text-sm font-medium">{t.kb.content}</label>
            <div className="flex items-center gap-2">
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept=".txt,.md,.csv,.pdf,.jpg,.jpeg,.png,.webp"
                onChange={handleImportFile}
              />
              <button
                type="button"
                className="btn-ghost text-xs flex items-center gap-1"
                onClick={() => fileInputRef.current?.click()}
                disabled={extracting || saving}
              >
                <FileUp size={14} /> {extracting ? t.kb.extracting : t.kb.importFromFile}
              </button>
              <button type="button" className="btn-ghost text-xs flex items-center gap-1" onClick={handleEnhance} disabled={enhancing || extracting || !form.content.trim()}>
                <Sparkles size={14} /> {enhancing ? t.kb.enhancing : t.kb.enhance}
              </button>
            </div>
          </div>
          <textarea className="textarea-field" value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} required />
        </div>
        <ToggleSwitch checked={form.is_active} onChange={(v) => setForm({ ...form, is_active: v })} label={t.common.active} />
        <FormActions saving={saving} onCancel={() => navigate('/admin/kb')} />
      </form>

      <EnhanceCompareModal
        open={compareOpen}
        onClose={useOriginalText}
        original={compareOriginal}
        enhanced={compareEnhanced}
        onUseOriginal={useOriginalText}
        onUseEnhanced={useEnhancedText}
      />
    </div>
  )
}
