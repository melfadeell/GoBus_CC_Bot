import { FormEvent, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, Station } from '@/api/client'
import { LoadingState, PageHeader } from '@/components/admin/Shared'
import ToggleSwitch from '@/components/admin/ToggleSwitch'
import { useLanguage } from '@/i18n/LanguageProvider'
import { TIME_OPTIONS, formatWorkingHours, parseWorkingHours } from '@/utils/stationHours'

const empty: Station = {
  name: '',
  description: '',
  working_hours: '',
  is_24_hours: false,
  opens_at: '',
  closes_at: '',
  map_url: '',
  map_text: '',
  is_active: true,
}

export default function StationEditPage() {
  const { t } = useLanguage()
  const { id } = useParams()
  const navigate = useNavigate()
  const isNew = id === 'new'
  const [form, setForm] = useState<Station>(empty)
  const [loading, setLoading] = useState(!isNew)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!isNew && id) {
      api.getStation(Number(id)).then((s) => {
        const parsed = parseWorkingHours(s.working_hours)
        setForm({
          ...s,
          is_24_hours: s.is_24_hours ?? parsed.is_24_hours,
          opens_at: s.opens_at || parsed.opens_at,
          closes_at: s.closes_at || parsed.closes_at,
        })
      }).finally(() => setLoading(false))
    }
  }, [id, isNew])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    const payload: Station = {
      ...form,
      working_hours: formatWorkingHours(!!form.is_24_hours, form.opens_at, form.closes_at),
      opens_at: form.is_24_hours ? null : form.opens_at || null,
      closes_at: form.is_24_hours ? null : form.closes_at || null,
    }
    try {
      if (isNew) await api.createStation(payload)
      else await api.updateStation(Number(id), payload)
      navigate('/admin/stations')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <LoadingState />

  return (
    <div>
      <PageHeader title={isNew ? t.stations.addStation : t.stations.editStation} />
      <form onSubmit={handleSubmit} className="card p-6 space-y-4 max-w-3xl">
        <div><label className="block text-sm mb-1 font-medium">{t.stations.name}</label><input className="input-field" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></div>
        <div><label className="block text-sm mb-1 font-medium">{t.stations.description}</label><textarea className="textarea-field" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} required /></div>
        <div>
          <label className="block text-sm mb-2 font-medium">{t.stations.workingHours}</label>
          <ToggleSwitch
            checked={!!form.is_24_hours}
            onChange={(v) => setForm({ ...form, is_24_hours: v, opens_at: v ? '' : form.opens_at, closes_at: v ? '' : form.closes_at })}
            label={t.stations.hours24}
          />
          {!form.is_24_hours && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3">
              <div>
                <label className="block text-xs mb-1 text-[var(--color-text-muted)]">{t.stations.from}</label>
                <select className="input-field ltr" value={form.opens_at || ''} onChange={(e) => setForm({ ...form, opens_at: e.target.value })}>
                  <option value="">—</option>
                  {TIME_OPTIONS.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs mb-1 text-[var(--color-text-muted)]">{t.stations.to}</label>
                <select className="input-field ltr" value={form.closes_at || ''} onChange={(e) => setForm({ ...form, closes_at: e.target.value })}>
                  <option value="">—</option>
                  {TIME_OPTIONS.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                </select>
              </div>
            </div>
          )}
        </div>
        <div><label className="block text-sm mb-1 font-medium">{t.stations.mapUrl}</label><input className="input-field ltr" value={form.map_url || ''} onChange={(e) => setForm({ ...form, map_url: e.target.value })} /></div>
        <ToggleSwitch checked={form.is_active} onChange={(v) => setForm({ ...form, is_active: v })} label={t.common.active} />
        <div className="flex gap-3"><button type="submit" className="btn-primary" disabled={saving}>{saving ? t.common.saving : t.common.save}</button><button type="button" className="btn-ghost" onClick={() => navigate('/admin/stations')}>{t.common.cancel}</button></div>
      </form>
    </div>
  )
}
