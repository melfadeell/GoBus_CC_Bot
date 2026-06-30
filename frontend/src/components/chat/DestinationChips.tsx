import { useState } from 'react'
import { MapPin } from 'lucide-react'
import StationCardList from './StationCard'
import { apiUrl } from '@/api/client'
import type { StationCardData } from '@/hooks/useChatStream'
import { useLanguage } from '@/i18n/LanguageProvider'

interface DestinationChipsProps {
  destinations: string[]
}

export default function DestinationChips({ destinations }: DestinationChipsProps) {
  const { t } = useLanguage()
  const [selected, setSelected] = useState<string | null>(null)
  const [stations, setStations] = useState<StationCardData[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleClick(dest: string) {
    if (selected === dest) {
      setSelected(null)
      setStations(null)
      setError(null)
      return
    }

    setSelected(dest)
    setLoading(true)
    setError(null)
    setStations(null)

    try {
      const res = await fetch(
        apiUrl(`/api/chat/destination-stations?destination=${encodeURIComponent(dest)}`)
      )
      if (!res.ok) throw new Error('fetch failed')
      const data = (await res.json()) as { stations?: StationCardData[] }
      setStations(data.stations ?? [])
    } catch {
      setError(t.chat.loadStationsError)
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <div className="dest-chips mt-2">
        {destinations.map((d) => (
          <button
            key={d}
            type="button"
            className={`dest-chip${selected === d ? ' dest-chip--active' : ''}`}
            onClick={() => handleClick(d)}
            aria-expanded={selected === d}
            aria-label={t.chat.viewDestinationStations.replace('{destination}', d)}
          >
            <MapPin size={12} />
            {d}
          </button>
        ))}
      </div>

      {selected ? (
        <div className="dest-stations-panel mt-2">
          <div className="dest-stations-heading">
            {t.chat.stationsIn.replace('{destination}', selected)}
          </div>
          {loading ? (
            <div className="dest-stations-loading">{t.chat.loadingStations}</div>
          ) : error ? (
            <div className="dest-stations-error">{error}</div>
          ) : stations && stations.length > 0 ? (
            <StationCardList stations={stations} />
          ) : (
            <div className="dest-stations-empty">{t.chat.noStations}</div>
          )}
        </div>
      ) : null}
    </>
  )
}
