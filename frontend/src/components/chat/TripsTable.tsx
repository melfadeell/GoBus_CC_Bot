import type { TripRow } from '@/hooks/useChatStream'
import { useLanguage } from '@/i18n/LanguageProvider'

interface TripsTableProps {
  trips: TripRow[]
}

/** Deterministic trips table rendered from structured data (never model markdown).
 *  Reuses the .chat-md-table classes so styling and PNG export work unchanged. */
export default function TripsTable({ trips }: TripsTableProps) {
  const { locale } = useLanguage()
  const ar = locale === 'ar'
  // Show the route column only when more than one route is present.
  const multiRoute = new Set(trips.map((t) => `${t.origin}→${t.destination}`)).size > 1

  const h = ar
    ? { route: 'المسار', date: 'التاريخ', dep: 'المغادرة', arr: 'الوصول', cls: 'الفئة', seats: 'المقاعد', price: 'السعر' }
    : { route: 'Route', date: 'Date', dep: 'Departure', arr: 'Arrival', cls: 'Class', seats: 'Seats', price: 'Price' }
  const currency = ar ? 'جنيه' : 'EGP'

  return (
    <div className="chat-md-table-wrap mt-2">
      <table className="chat-md-table">
        <thead className="chat-md-thead">
          <tr>
            {multiRoute ? <th className="chat-md-th">{h.route}</th> : null}
            <th className="chat-md-th">{h.date}</th>
            <th className="chat-md-th">{h.dep}</th>
            <th className="chat-md-th">{h.arr}</th>
            <th className="chat-md-th">{h.cls}</th>
            <th className="chat-md-th">{h.seats}</th>
            <th className="chat-md-th">{h.price}</th>
          </tr>
        </thead>
        <tbody>
          {trips.map((t, i) => (
            <tr key={i}>
              {multiRoute ? (
                <td className="chat-md-td">{`${t.origin} → ${t.destination}`}</td>
              ) : null}
              <td className="chat-md-td">{t.date}</td>
              <td className="chat-md-td">{t.departure}</td>
              <td className="chat-md-td">{t.arrival}</td>
              <td className="chat-md-td">{t.bus_class}</td>
              <td className="chat-md-td">{`${t.available_seats}/${t.total_seats}`}</td>
              <td className="chat-md-td">{`${t.price_egp.toFixed(2)} ${currency}`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
