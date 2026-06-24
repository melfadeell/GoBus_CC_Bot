import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Eye, Pencil, Plus, Trash2 } from 'lucide-react'
import { api, Station } from '@/api/client'
import Modal from '@/components/admin/Modal'
import { EmptyState, LoadingState, PageHeader, SearchBar } from '@/components/admin/Shared'
import { useLanguage } from '@/i18n/LanguageProvider'

export default function StationsListPage() {
  const { t } = useLanguage()
  const [items, setItems] = useState<Station[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [viewStation, setViewStation] = useState<Station | null>(null)

  function load() {
    setLoading(true)
    api.getStations({ page: '1', page_size: '100', ...(search ? { search } : {}) })
      .then((res) => setItems(res.items))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [search])

  async function remove(id: number) {
    if (!confirm(t.common.confirmDelete)) return
    await api.deleteStation(id)
    load()
  }

  return (
    <div>
      <PageHeader title={t.stations.title} action={<Link to="/admin/stations/new" className="btn-primary flex items-center gap-2"><Plus size={16} /> {t.stations.add}</Link>} />
      <SearchBar value={search} onChange={setSearch} placeholder={t.stations.search} />
      {loading ? <LoadingState /> : items.length === 0 ? <EmptyState message={t.common.noData} /> : (
        <div className="card table-wrap">
          <table className="data-table">
            <thead><tr><th>{t.stations.name}</th><th>{t.stations.hours}</th><th>{t.stations.map}</th><th></th></tr></thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.id}>
                  <td className="font-medium">{s.name}</td>
                  <td>{s.working_hours || (s.is_24_hours ? t.stations.hours24 : '—')}</td>
                  <td>{s.map_url ? <a href={s.map_url} target="_blank" rel="noreferrer" className="text-blue-600 text-sm">{t.stations.view}</a> : '—'}</td>
                  <td className="flex gap-2 items-center">
                    <button type="button" className="p-1.5 rounded hover:bg-[var(--color-surface-muted)] text-[var(--color-brand-primary)]" title={t.stations.viewStation} onClick={() => setViewStation(s)}>
                      <Eye size={16} />
                    </button>
                    <Link to={`/admin/stations/${s.id}`} className="p-1.5 rounded hover:bg-[var(--color-surface-muted)] text-blue-600"><Pencil size={16} /></Link>
                    <button type="button" className="p-1.5 rounded hover:bg-[var(--color-surface-muted)] text-red-600" onClick={() => remove(s.id!)}><Trash2 size={16} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal
        open={!!viewStation}
        onClose={() => setViewStation(null)}
        title={viewStation?.name || t.stations.viewStation}
        footer={
          viewStation?.id ? (
            <>
              <button type="button" className="btn-ghost" onClick={() => setViewStation(null)}>{t.common.cancel}</button>
              <Link to={`/admin/stations/${viewStation.id}`} className="btn-primary" onClick={() => setViewStation(null)}>{t.common.edit}</Link>
            </>
          ) : undefined
        }
      >
        {viewStation && (
          <div className="space-y-3 text-sm">
            <div><span className="font-medium">{t.stations.description}:</span><p className="mt-1 whitespace-pre-wrap text-[var(--color-text-muted)]">{viewStation.description}</p></div>
            <div><span className="font-medium">{t.stations.workingHours}:</span> {viewStation.working_hours || (viewStation.is_24_hours ? t.stations.hours24 : '—')}</div>
            {viewStation.map_url && (
              <div><span className="font-medium">{t.stations.mapUrl}:</span> <a href={viewStation.map_url} target="_blank" rel="noreferrer" className="text-blue-600 ltr inline-block">{viewStation.map_url}</a></div>
            )}
            <div><span className="font-medium">{t.common.active}:</span> {viewStation.is_active ? t.common.yes : t.common.no}</div>
          </div>
        )}
      </Modal>
    </div>
  )
}
