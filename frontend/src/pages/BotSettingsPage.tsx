import { FormEvent, useEffect, useState } from 'react'
import { Sparkles } from 'lucide-react'
import { api, BotSettings, PromptVersion } from '@/api/client'
import Modal from '@/components/admin/Modal'
import EnhanceCompareModal from '@/components/admin/EnhanceCompareModal'
import { LoadingState, PageHeader, SuccessBanner, ErrorState } from '@/components/admin/Shared'
import { useLanguage } from '@/i18n/LanguageProvider'

export default function BotSettingsPage() {
  const { t } = useLanguage()
  const [form, setForm] = useState<BotSettings | null>(null)
  const [versions, setVersions] = useState<PromptVersion[]>([])
  const [saving, setSaving] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [modalOpen, setModalOpen] = useState(false)
  const [instruction, setInstruction] = useState('')
  const [proposedPrompt, setProposedPrompt] = useState('')
  const [enhancing, setEnhancing] = useState(false)
  const [savingPrompt, setSavingPrompt] = useState(false)
  const [compareOpen, setCompareOpen] = useState(false)
  const [compareOriginal, setCompareOriginal] = useState('')
  const [compareEnhanced, setCompareEnhanced] = useState('')

  function loadVersions() {
    api.getPromptVersions().then(setVersions).catch(() => {})
  }

  useEffect(() => {
    api.getBotSettings().then(setForm)
    loadVersions()
  }, [])

  async function handleGreetingSubmit(e: FormEvent) {
    e.preventDefault()
    if (!form) return
    setSaving(true)
    setError(null)
    try {
      const updated = await api.updateBotSettings({ greeting_ar: form.greeting_ar })
      setForm(updated)
      setSuccess(true)
      setTimeout(() => setSuccess(false), 3000)
    } catch (e) {
      setError(e instanceof Error ? e.message : t.common.saveFailed)
    } finally {
      setSaving(false)
    }
  }

  function openModal() {
    setInstruction('')
    setProposedPrompt(form?.system_prompt || '')
    setModalOpen(true)
  }

  async function handleEnhance() {
    if (!instruction.trim()) return
    setEnhancing(true)
    setError(null)
    const original = proposedPrompt || form?.system_prompt || ''
    try {
      const res = await api.enhancePrompt(instruction, original)
      setCompareOriginal(original)
      setCompareEnhanced(res.proposed_prompt)
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

  function useOriginalPrompt() {
    closeCompare()
  }

  function useEnhancedPrompt() {
    setProposedPrompt(compareEnhanced)
    closeCompare()
  }

  async function handleSavePrompt() {
    if (!proposedPrompt.trim()) return
    setSavingPrompt(true)
    setError(null)
    try {
      const updated = await api.savePrompt(proposedPrompt, instruction || undefined)
      setForm(updated)
      setModalOpen(false)
      loadVersions()
      setSuccess(true)
      setTimeout(() => setSuccess(false), 3000)
    } catch (e) {
      setError(e instanceof Error ? e.message : t.common.saveFailed)
    } finally {
      setSavingPrompt(false)
    }
  }

  async function handleRestore(versionId: number) {
    if (!confirm(t.botSettings.restore + '?')) return
    try {
      const updated = await api.restorePromptVersion(versionId)
      setForm(updated)
      loadVersions()
    } catch (e) {
      setError(e instanceof Error ? e.message : t.common.saveFailed)
    }
  }

  if (!form) return <LoadingState />

  return (
    <div>
      <PageHeader title={t.botSettings.title} subtitle={t.botSettings.subtitle} />
      {success && <SuccessBanner message={t.botSettings.promptSaved} />}
      {error && <div className="mb-4"><ErrorState message={error} /></div>}

      <form onSubmit={handleGreetingSubmit} className="card p-6 space-y-4 max-w-4xl mb-6">
        <div>
          <label className="block text-sm mb-1 font-medium">{t.botSettings.greeting}</label>
          <textarea className="textarea-field min-h-[52px] resize-y" rows={2} value={form.greeting_ar} onChange={(e) => setForm({ ...form, greeting_ar: e.target.value })} />
        </div>
        <button type="submit" className="btn-primary" disabled={saving}>{saving ? t.common.saving : t.common.save}</button>
      </form>

      <div className="card p-6 max-w-4xl mb-6">
        <div className="flex items-center justify-between mb-3">
          <label className="text-sm font-medium">{t.botSettings.systemPrompt}</label>
          <button type="button" className="btn-primary text-sm" onClick={openModal}>{t.botSettings.editPrompt}</button>
        </div>
        <pre className="text-sm whitespace-pre-wrap ltr text-left bg-[var(--color-surface-muted)] p-4 rounded-lg max-h-64 overflow-y-auto border border-[var(--color-border-default)]" dir="ltr">
          {form.system_prompt}
        </pre>
        <p className="text-xs text-[var(--color-text-muted)] mt-2">{t.botSettings.guardrailsNote}</p>
      </div>

      {versions.length > 0 && (
        <div className="card p-6 max-w-4xl">
          <h3 className="font-bold mb-4">{t.botSettings.versionHistory}</h3>
          <div className="space-y-3">
            {versions.map((v) => (
              <div key={v.id} className="flex items-start justify-between gap-4 p-3 rounded-lg bg-[var(--color-surface-muted)] text-sm">
                <div className="min-w-0">
                  <div className="font-medium">{t.botSettings.version} {v.version_number}</div>
                  <div className="text-xs text-[var(--color-text-muted)] mt-0.5">{new Date(v.created_at).toLocaleString()}</div>
                  {v.instruction_note && <p className="text-[var(--color-text-muted)] mt-1 truncate">{v.instruction_note}</p>}
                </div>
                <button type="button" className="btn-ghost text-xs shrink-0" onClick={() => handleRestore(v.id)}>{t.botSettings.restore}</button>
              </div>
            ))}
          </div>
        </div>
      )}

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={t.botSettings.editPrompt}
        wide
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setModalOpen(false)}>{t.common.cancel}</button>
            <button type="button" className="btn-primary" onClick={handleSavePrompt} disabled={savingPrompt || !proposedPrompt.trim()}>
              {savingPrompt ? t.common.saving : t.common.save}
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm mb-1 font-medium">{t.botSettings.instruction}</label>
            <textarea
              className="textarea-field min-h-[100px]"
              placeholder={t.botSettings.instructionPlaceholder}
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
            />
            <button type="button" className="btn-ghost text-sm mt-2 flex items-center gap-1" onClick={handleEnhance} disabled={enhancing || !instruction.trim()}>
              <Sparkles size={14} /> {enhancing ? t.botSettings.enhancing : t.botSettings.enhance}
            </button>
          </div>
          <div>
            <label className="block text-sm mb-1 font-medium">{t.botSettings.proposedPrompt}</label>
            <textarea
              className="textarea-field min-h-[280px] ltr"
              dir="ltr"
              value={proposedPrompt}
              onChange={(e) => setProposedPrompt(e.target.value)}
            />
          </div>
        </div>
      </Modal>

      <EnhanceCompareModal
        open={compareOpen}
        onClose={useOriginalPrompt}
        original={compareOriginal}
        enhanced={compareEnhanced}
        onUseOriginal={useOriginalPrompt}
        onUseEnhanced={useEnhancedPrompt}
        ltr
      />
    </div>
  )
}
