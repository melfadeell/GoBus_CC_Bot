import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Eye, Pencil, Plus, Trash2 } from 'lucide-react'
import { api, Trip } from '@/api/client'
import Modal from '@/components/admin/Modal'
import { EmptyState, LoadingState, PageHeader, StatusBadge } from '@/components/admin/Shared'
import { useLanguage } from '@/i18n/LanguageProvider'

export default function TripsListPage() {
  const { t } = useLanguage()
  const [items, setItems] = useState<Trip[]>([])
  const [loading, setLoading] = useState(true)
  const [viewTrip, setViewTrip] = useState<Trip | null>(null)

  function load() {
    setLoading(true)
    api.getTrips({ page: '1', page_size: '50' }).then((res) => setItems(res.items)).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  async function remove(id: number) {
    if (!confirm(t.common.confirmDelete)) return
    await api.deleteTrip(id)
    load()
  }

  return (
    <div>
      <PageHeader title={t.trips.title} action={<Link to="/admin/trips/new" className="btn-primary flex items-center gap-2"><Plus size={16} /> {t.trips.add}</Link>} />
      {loading ? <LoadingState /> : items.length === 0 ? <EmptyState message={t.common.noData} /> : (
        <div className="card table-wrap">
          <table className="data-table">
            <thead>
              <tr><th>{t.trips.route}</th><th>{t.trips.date}</th><th>{t.trips.departure}</th><th>{t.trips.class}</th><th>{t.trips.seats}</th><th>{t.trips.price}</th><th>{t.trips.status}</th><th>{t.trips.bookable}</th><th></th></tr>
            </thead>
            <tbody>
              {items.map((trip) => (
                <tr key={trip.id}>
                  <td>{trip.route ? `${trip.route.origin} → ${trip.route.destination}` : trip.route_id}</td>
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
