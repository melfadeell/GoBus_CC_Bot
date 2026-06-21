import { FormEvent, useEffect, useState } from 'react'
import { api, Service } from '@/api/client'
import ToggleSwitch from '@/components/admin/ToggleSwitch'
import { LoadingState, PageHeader } from '@/components/admin/Shared'
import { useLanguage } from '@/i18n/LanguageProvider'

export default function ServicesPage() {
  const { t } = useLanguage()
  const [items, setItems] = useState<Service[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<number | null>(null)

  useEffect(() => {
    api.getServices().then(setItems).finally(() => setLoading(false))
  }, [])

  async function save(id: number, data: Partial<Service>) {
    setSaving(id)
    try {
      const updated = await api.updateService(id, data)
      setItems((prev) => prev.map((s) => (s.id === id ? updated : s)))
    } finally {
      setSaving(null)
    }
  }

  if (loading) return <LoadingState />

  return (
    <div>
      <PageHeader title={t.services.title} />
      <div className="space-y-4">
        {items.map((svc) => (
          <ServiceCard key={svc.id} service={svc} saving={saving === svc.id} onSave={(data) => save(svc.id, data)} />
        ))}
      </div>
    </div>
  )
}

function ServiceCard({ service, saving, onSave }: { service: Service; saving: boolean; onSave: (d: Partial<Service>) => void }) {
  const { t } = useLanguage()
  const [form, setForm] = useState(service)

  useEffect(() => { setForm(service) }, [service])

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    onSave({ name_ar: form.name_ar, name_en: form.name_en, description: form.description, is_active: form.is_active })
  }

  return (
    <form onSubmit={handleSubmit} className="card p-5 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-bold">{form.name_ar} ({form.code})</h3>
        <span className={`badge ${form.has_detailed_data ? 'badge-open' : 'badge-cancelled'}`}>
          {form.has_detailed_data ? t.services.fullData : t.services.generalOnly}
        </span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <input className="input-field" value={form.name_ar} onChange={(e) => setForm({ ...form, name_ar: e.target.value })} />
        <input className="input-field ltr" value={form.name_en} onChange={(e) => setForm({ ...form, name_en: e.target.value })} />
      </div>
      <textarea className="textarea-field min-h-[100px]" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
      <div className="flex items-center justify-between">
        <ToggleSwitch checked={form.is_active} onChange={(v) => setForm({ ...form, is_active: v })} label={t.common.active} />
        <button type="submit" className="btn-primary" disabled={saving}>{saving ? t.common.saving : t.common.save}</button>
      </div>
    </form>
  )
}
