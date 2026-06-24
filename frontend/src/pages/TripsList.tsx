import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Eye, Pencil, Plus, Trash2 } from 'lucide-react'
import { api, Route, Station, Trip } from '@/api/client'
import DateRangeFilter from '@/components/admin/DateRangeFilter'
import Modal from '@/components/admin/Modal'
import { EmptyState, LoadingState, PageHeader, StatusBadge } from '@/components/admin/Shared'
import { useLanguage } from '@/i18n/LanguageProvider'

const CLASSES = ['standard', 'elite', 'business']
const STATUSES = ['open', 'full', 'cancelled']

export default function TripsListPage() {
  const { t } = useLanguage()
  const [items, setItems] = useState<Trip[]>([])
  const [routes, setRoutes] = useState<Route[]>([])
  const [stations, setStations] = useState<Station[]>([])
  const [loading, setLoading] = useState(true)
  const [viewTrip, setViewTrip] = useState<Trip | null>(null)

  // Filters
  const [routeId, setRouteId] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [stationId, setStationId] = useState('')
  const [depFrom, setDepFrom] = useState('')
  const [depTo, setDepTo] = useState('')
  const [busClass, setBusClass] = useState('')
  const [status, setStatus] = useState('')
  const [bookable, setBookable] = useState('')
  const [priceMin, setPriceMin] = useState('')
  const [priceMax, setPriceMax] = useState('')

  useEffect(() => {
    api.getRoutes().then(setRoutes).catch(() => {})
    api.getStations({ page_size: '300' }).then((r) => setStations(r.items)).catch(() => {})
  }, [])

  const load = useCallback(() => {
    setLoading(true)
    const params: Record<string, string> = { page: '1', page_size: '50' }
    if (routeId) params.route_id = routeId
    if (dateFrom) params.date_from = dateFrom
    if (dateTo) params.date_to = dateTo
    if (stationId) params.departure_station_id = stationId
    if (depFrom) params.departure_from = depFrom
    if (depTo) params.departure_to = depTo
    if (busClass) params.bus_class = busClass
    if (status) params.status = status
    if (bookable) params.is_bookable = bookable
    if (priceMin) params.price_min = priceMin
    if (priceMax) params.price_max = priceMax
    api.getTrips(params).then((res) => setItems(res.items)).finally(() => setLoading(false))
  }, [routeId, dateFrom, dateTo, stationId, depFrom, depTo, busClass, status, bookable, priceMin, priceMax])

  useEffect(() => {
    load()
  }, [load])

  async function remove(id: number) {
    if (!confirm(t.common.confirmDelete)) return
    await api.deleteTrip(id)
    load()
  }

  return (
    <div>
      <PageHeader title={t.trips.title} action={<Link to="/admin/trips/new" className="btn-primary flex items-center gap-2"><Plus size={16} /> {t.trips.add}</Link>} />

      <div className="card p-4 mb-4 space-y-3">
        <DateRangeFilter from={dateFrom} to={dateTo} onChange={(f, t2) => { setDateFrom(f); setDateTo(t2) }} />
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          <select className="input-field" value={routeId} onChange={(e) => setRouteId(e.target.value)}>
            <option value="">{t.trips.allRoutes}</option>
            {routes.map((r) => (
              <option key={r.id} value={r.id}>{r.origin} → {r.destination}</option>
            ))}
          </select>
          <select className="input-field" value={stationId} onChange={(e) => setStationId(e.target.value)}>
            <option value="">{t.trips.allStations}</option>
            {stations.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          <select className="input-field" value={busClass} onChange={(e) => setBusClass(e.target.value)}>
            <option value="">{t.trips.allClasses}</option>
            {CLASSES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select className="input-field" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">{t.trips.allStatuses}</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select className="input-field" value={bookable} onChange={(e) => setBookable(e.target.value)}>
            <option value="">{t.trips.anyBookable}</option>
            <option value="true">{t.trips.bookableOnly}</option>
            <option value="false">{t.trips.notBookable}</option>
          </select>
          <label className="flex flex-col text-xs text-[var(--color-text-muted)]">
            {t.trips.depFrom}
            <input type="time" className="input-field ltr" value={depFrom} onChange={(e) => setDepFrom(e.target.value)} />
          </label>
          <label className="flex flex-col text-xs text-[var(--color-text-muted)]">
            {t.trips.depTo}
            <input type="time" className="input-field ltr" value={depTo} onChange={(e) => setDepTo(e.target.value)} />
          </label>
          <div className="flex gap-2">
            <input type="number" min={0} className="input-field" placeholder={t.trips.priceMin} value={priceMin} onChange={(e) => setPriceMin(e.target.value)} />
            <input type="number" min={0} className="input-field" placeholder={t.trips.priceMax} value={priceMax} onChange={(e) => setPriceMax(e.target.value)} />
          </div>
        </div>
      </div>

      {loading ? <LoadingState /> : items.length === 0 ? <EmptyState message={t.common.noData} /> : (
        <div className="card table-wrap">
          <table className="data-table">
            <thead>
              <tr><th>{t.trips.route}</th><th>{t.trips.departureStation}</th><th>{t.trips.arrivalStation}</th><th>{t.trips.date}</th><th>{t.trips.departure}</th><th>{t.trips.class}</th><th>{t.trips.seats}</th><th>{t.trips.price}</th><th>{t.trips.status}</th><th>{t.trips.bookable}</th><th></th></tr>
            </thead>
            <tbody>
              {items.map((trip) => (
                <tr key={trip.id}>
                  <td>{trip.route ? `${trip.route.origin} → ${trip.route.destination}` : trip.route_id}</td>
                  <td>{trip.departure_station_name || '—'}</td>
                  <td>{trip.arrival_station_name || '—'}</td>
                  <td>{trip.trip_date}</td>
                  <td>{trip.departure_time?.slice(0, 5)}</td>
                  <td>{trip.bus_class}</td>
                  <td>{trip.available_seats}/{trip.total_seats}</td>
                  <td>{trip.price_egp} EGP</td>
                  <td><StatusBadge status={trip.status} /></td>
                  <td>{trip.is_bookable ? t.common.yes : t.common.no}</td>
                  <td className="flex gap-2 items-center">
                    <button
                      type="button"
                      className="p-1.5 rounded hover:bg-[var(--color-surface-muted)] text-[var(--color-brand-primary)]"
                      title={t.trips.viewTrip}
                      onClick={() => setViewTrip(trip)}
                    >
                      <Eye size={16} />
                    </button>
                    <Link to={`/admin/trips/${trip.id}`} className="p-1.5 rounded hover:bg-[var(--color-surface-muted)] text-blue-600">
                      <Pencil size={16} />
                    </Link>
                    <button type="button" className="p-1.5 rounded hover:bg-[var(--color-surface-muted)] text-red-600" onClick={() => remove(trip.id!)}>
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal
        open={!!viewTrip}
        onClose={() => setViewTrip(null)}
        title={viewTrip?.route ? `${viewTrip.route.origin} → ${viewTrip.route.destination}` : t.trips.viewTrip}
        footer={
          viewTrip?.id ? (
            <>
              <button type="button" className="btn-ghost" onClick={() => setViewTrip(null)}>{t.common.cancel}</button>
              <Link to={`/admin/trips/${viewTrip.id}`} className="btn-primary" onClick={() => setViewTrip(null)}>{t.common.edit}</Link>
            </>
          ) : undefined
        }
      >
        {viewTrip && (
          <div className="space-y-2 text-sm">
            <div><span className="font-medium">{t.trips.departureStation}:</span> {viewTrip.departure_station_name || '—'}</div>
            <div><span className="font-medium">{t.trips.arrivalStation}:</span> {viewTrip.arrival_station_name || '—'}</div>
            <div><span className="font-medium">{t.trips.date}:</span> {viewTrip.trip_date}</div>
            <div><span className="font-medium">{t.trips.departure}:</span> {viewTrip.departure_time?.slice(0, 5)}</div>
            <div><span className="font-medium">{t.trips.arrival}:</span> {viewTrip.arrival_time?.slice(0, 5)}</div>
            <div><span className="font-medium">{t.trips.class}:</span> {viewTrip.bus_class}</div>
            <div><span className="font-medium">{t.trips.seats}:</span> {viewTrip.available_seats}/{viewTrip.total_seats}</div>
            <div><span className="font-medium">{t.trips.price}:</span> {viewTrip.price_egp} EGP</div>
            <div><span className="font-medium">{t.trips.status}:</span> <StatusBadge status={viewTrip.status} /></div>
            <div><span className="font-medium">{t.trips.bookable}:</span> {viewTrip.is_bookable ? t.common.yes : t.common.no}</div>
          </div>
        )}
      </Modal>
    </div>
  )
}
