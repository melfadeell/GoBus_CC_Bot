import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Trash2 } from 'lucide-react'
import { api, Destination } from '@/api/client'
import { EmptyState, LoadingState, PageHeader, SearchBar } from '@/components/admin/Shared'
import { useLanguage } from '@/i18n/LanguageProvider'

export default function DestinationsListPage() {
  const { t } = useLanguage()
  const [items, setItems] = useState<Destination[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)

  function load() {
    setLoading(true)
    api.getDestinations({ page: '1', page_size: '50', ...(search ? { search } : {}) })
      .then((res) => setItems(res.items))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [search])

  async function remove(id: number) {
    if (!confirm(t.common.confirmDelete)) return
    await api.deleteDestination(id)
    load()
  }

  return (
    <div>
      <PageHeader title={t.destinations.title} action={<Link to="/admin/destinations/new" className="btn-primary flex items-center gap-2"><Plus size={16} /> {t.destinations.add}</Link>} />
      <SearchBar value={search} onChange={setSearch} />
      {loading ? <LoadingState /> : items.length === 0 ? <EmptyState message={t.common.noData} /> : (
        <div className="card table-wrap">
          <table className="data-table">
            <thead><tr><th>{t.destinations.name}</th><th>{t.destinations.webId}</th><th></th></tr></thead>
            <tbody>
              {items.map((d) => (
                <tr key={d.id}>
                  <td><Link to={`/admin/destinations/${d.id}`} className="font-medium hover:underline">{d.name_ar}</Link></td>
                  <td>{d.gobus_web_id ?? '—'}</td>
                  <td><button type="button" className="text-red-600" onClick={() => remove(d.id!)}><Trash2 size={16} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
