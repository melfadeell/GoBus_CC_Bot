import { FormEvent, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, Route, Trip } from '@/api/client'
import ToggleSwitch from '@/components/admin/ToggleSwitch'
import { LoadingState, PageHeader } from '@/components/admin/Shared'
import { useLanguage } from '@/i18n/LanguageProvider'

const empty: Trip = {
  route_id: 1,
  trip_date: new Date().toISOString().slice(0, 10),
  departure_time: '08:00:00',
  arrival_time: '11:00:00',
  bus_class: 'standard',
  total_seats: 45,
  available_seats: 30,
  price_egp: 150,
  is_bookable: true,
  status: 'open',
}

export default function TripEditPage() {
  const { t } = useLanguage()
  const { id } = useParams()
  const navigate = useNavigate()
  const isNew = id === 'new'
  const [routes, setRoutes] = useState<Route[]>([])
  const [form, setForm] = useState<Trip>(empty)
  const [loading, setLoading] = useState(!isNew)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.getRoutes().then(setRoutes)
    if (!isNew && id) api.getTrip(Number(id)).then(setForm).finally(() => setLoading(false))
  }, [id, isNew])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      if (isNew) await api.createTrip(form)
      else await api.updateTrip(Number(id), form)
      navigate('/admin/trips')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <LoadingState />

  return (
    <div>
      <PageHeader title={isNew ? t.trips.addTrip : t.trips.editTrip} />
      <form onSubmit={handleSubmit} className="card p-6 space-y-4 max-w-3xl">
        <div><label className="block text-sm mb-1 font-medium">{t.trips.route}</label>
          <select className="input-field" value={form.route_id} onChange={(e) => setForm({ ...form, route_id: Number(e.target.value) })}>
            {routes.map((r) => <option key={r.id} value={r.id}>{r.origin} → {r.destination}</option>)}
          </select>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div><label className="block text-sm mb-1 font-medium">{t.trips.date}</label><input className="input-field ltr" type="date" value={form.trip_date} onChange={(e) => setForm({ ...form, trip_date: e.target.value })} required /></div>
          <div><label className="block text-sm mb-1 font-medium">{t.trips.departure}</label><input className="input-field ltr" type="time" value={form.departure_time?.slice(0, 5)} onChange={(e) => setForm({ ...form, departure_time: e.target.value + ':00' })} required /></div>
          <div><label className="block text-sm mb-1 font-medium">{t.trips.arrival}</label><input className="input-field ltr" type="time" value={form.arrival_time?.slice(0, 5)} onChange={(e) => setForm({ ...form, arrival_time: e.target.value + ':00' })} required /></div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div><label className="block text-sm mb-1 font-medium">{t.trips.class}</label>
            <select className="input-field" value={form.bus_class} onChange={(e) => setForm({ ...form, bus_class: e.target.value })}>
              <option value="standard">Standard</option><option value="elite">Elite</option><option value="business">Business</option>
            </select>
          </div>
          <div><label className="block text-sm mb-1 font-medium">{t.trips.status}</label>
            <select className="input-field" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
              <option value="open">open</option><option value="full">full</option><option value="cancelled">cancelled</option>
            </select>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div><label className="block text-sm mb-1 font-medium">{t.trips.totalSeats}</label><input className="input-field ltr" type="number" value={form.total_seats} onChange={(e) => setForm({ ...form, total_seats: Number(e.target.value) })} /></div>
          <div><label className="block text-sm mb-1 font-medium">{t.trips.availableSeats}</label><input className="input-field ltr" type="number" value={form.available_seats} onChange={(e) => setForm({ ...form, available_seats: Number(e.target.value) })} /></div>
          <div><label className="block text-sm mb-1 font-medium">{t.trips.priceEgp}</label><input className="input-field ltr" type="number" value={form.price_egp} onChange={(e) => setForm({ ...form, price_egp: Number(e.target.value) })} /></div>
        </div>
        <ToggleSwitch checked={form.is_bookable} onChange={(v) => setForm({ ...form, is_bookable: v })} label={t.trips.bookableLabel} />
        <div className="flex gap-3"><button type="submit" className="btn-primary" disabled={saving}>{saving ? t.common.saving : t.common.save}</button><button type="button" className="btn-ghost" onClick={() => navigate('/admin/trips')}>{t.common.cancel}</button></div>
      </form>
    </div>
  )
}
