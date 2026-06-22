import { Clock, MapPin } from 'lucide-react'
import type { StationCardData } from '@/hooks/useChatStream'
import { useLanguage } from '@/i18n/LanguageProvider'

interface StationCardListProps {
  stations: StationCardData[]
}

/** Deterministic station rendering — layout never depends on the model output. */
export default function StationCardList({ stations }: StationCardListProps) {
  const { locale, t } = useLanguage()
  const mapLabel = locale === 'ar' ? 'افتح الخريطة' : t.chat.openMap

  return (
    <div className="station-card-list mt-2 flex flex-col gap-2">
      {stations.map((s, i) => (
        <div key={`${s.name}-${i}`} className="station-card" dir="auto">
          <div className="station-card-name">{s.name}</div>
          {s.address ? (
            <div className="station-card-row">
              <MapPin size={14} className="station-card-icon shrink-0" />
              <span>{s.address}</span>
            </div>
          ) : null}
          {s.working_hours ? (
            <div className="station-card-row">
              <Clock size={14} className="station-card-icon shrink-0" />
              <span>{s.working_hours}</span>
            </div>
          ) : null}
          {s.map_url ? (
            <a
              className="station-card-map"
              href={s.map_url}
              target="_blank"
              rel="noreferrer noopener"
            >
              <MapPin size={14} />
              <span>{mapLabel}</span>
            </a>
          ) : null}
        </div>
      ))}
    </div>
  )
}
