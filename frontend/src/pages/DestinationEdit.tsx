import { FormEvent, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, Destination } from '@/api/client'
import ToggleSwitch from '@/components/admin/ToggleSwitch'
import { LoadingState, PageHeader } from '@/components/admin/Shared'
import { useLanguage } from '@/i18n/LanguageProvider'

const empty: Destination = { name_ar: '', content: '', gobus_web_id: null, is_active: true }

export default function DestinationEditPage() {
  const { t } = useLanguage()
  const { id } = useParams()
  const navigate = useNavigate()
  const isNew = id === 'new'
  const [form, setForm] = useState<Destination>(empty)
  const [loading, setLoading] = useState(!isNew)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!isNew && id) api.getDestination(Number(id)).then(setForm).finally(() => setLoading(false))
  }, [id, isNew])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      const { slug: _slug, ...payload } = form
      if (isNew) await api.createDestination(payload)
      else await api.updateDestination(Number(id), payload)
      navigate('/admin/destinations')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <LoadingState />

  return (
    <div>
      <PageHeader title={isNew ? t.destinations.addDest : t.destinations.editDest} />
      <form onSubmit={handleSubmit} className="card p-6 space-y-4 max-w-4xl">
        <div>
          <label className="block text-sm mb-1 font-medium">{t.destinations.name}</label>
          <input className="input-field" value={form.name_ar} onChange={(e) => setForm({ ...form, name_ar: e.target.value })} required />
        </div>
        <div><label className="block text-sm mb-1 font-medium">{t.destinations.webId}</label><input className="input-field ltr max-w-xs" type="number" value={form.gobus_web_id ?? ''} onChange={(e) => setForm({ ...form, gobus_web_id: e.target.value ? Number(e.target.value) : null })} /></div>
        <div><label className="block text-sm mb-1 font-medium">{t.destinations.content}</label><textarea className="textarea-field min-h-[300px]" value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} required /></div>
        <ToggleSwitch checked={form.is_active} onChange={(v) => setForm({ ...form, is_active: v })} label={t.common.active} />
        <div className="flex gap-3"><button type="submit" className="btn-primary" disabled={saving}>{saving ? t.common.saving : t.common.save}</button><button type="button" className="btn-ghost" onClick={() => navigate('/admin/destinations')}>{t.common.cancel}</button></div>
      </form>
    </div>
  )
}
