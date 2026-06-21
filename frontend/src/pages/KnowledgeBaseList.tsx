import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Eye, Pencil, Plus, Trash2 } from 'lucide-react'
import { api, KbArticle, KbCategory } from '@/api/client'
import Modal from '@/components/admin/Modal'
import { EmptyState, ErrorState, LoadingState, PageHeader, SearchBar } from '@/components/admin/Shared'
import { useDebounce } from '@/hooks/useDebounce'
import { useLanguage } from '@/i18n/LanguageProvider'

const TAB_CODES = ['services', 'faq', 'about', 'policies', 'destinations'] as const

export default function KnowledgeBaseListPage() {
  const { t } = useLanguage()
  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = searchParams.get('tab')
  const activeTab = TAB_CODES.includes(tabParam as (typeof TAB_CODES)[number]) ? tabParam! : 'services'

  const [categories, setCategories] = useState<KbCategory[]>([])
  const [items, setItems] = useState<KbArticle[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [viewItem, setViewItem] = useState<KbArticle | null>(null)
  const debouncedSearch = useDebounce(search)

  const activeCategory = categories.find((c) => c.code === activeTab)

  useEffect(() => {
    api.getKbCategories().then(setCategories)
  }, [])

  function setActiveTab(code: string) {
    setSearchParams({ tab: code })
  }

  function load() {
    if (!activeCategory) return
    setLoading(true)
    setError(null)
    api.getKbArticles({
      page: '1',
      page_size: '50',
      category_id: String(activeCategory.id),
      ...(debouncedSearch ? { search: debouncedSearch } : {}),
    })
      .then((res) => setItems(res.items))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!activeCategory) {
      if (categories.length > 0) setLoading(false)
      return
    }
    load()
  }, [debouncedSearch, activeCategory?.id, categories.length])

  async function remove(id: number) {
    if (!confirm(t.common.confirmDelete)) return
    try {
      await api.deleteKbArticle(id)
      load()
    } catch (e) {
      alert(e instanceof Error ? e.message : t.common.delete)
    }
  }

  const tabLabels: Record<string, string> = {
    services: t.kb.tabs.services,
    faq: t.kb.tabs.faq,
    about: t.kb.tabs.about,
    policies: t.kb.tabs.policies,
    destinations: t.kb.tabs.destinations,
  }

  return (
    <div className="fade-in">
      <PageHeader
        title={t.kb.title}
        subtitle={t.kb.subtitle}
        action={
          <Link to={`/admin/kb/new?category=${activeTab}`} className="btn-primary flex items-center gap-2">
            <Plus size={16} /> {t.kb.add}
          </Link>
        }
      />

      <div className="flex flex-wrap gap-2 mb-4 border-b border-[var(--color-border-default)] pb-3">
        {TAB_CODES.map((code) => (
          <button
            key={code}
            type="button"
            onClick={() => setActiveTab(code)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === code
                ? 'bg-[var(--color-brand-primary)] text-white'
                : 'bg-[var(--color-surface-muted)] hover:bg-gray-200'
            }`}
          >
            {tabLabels[code]}
          </button>
        ))}
      </div>

      <SearchBar value={search} onChange={setSearch} placeholder={t.kb.search} />
      {error && <ErrorState message={error} onRetry={load} />}
      {!error && loading ? <LoadingState /> : !error && items.length === 0 ? (
        <EmptyState message={t.common.noData} />
      ) : !error ? (
        <div className="card table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>{t.kb.titleLabel}</th>
                <th>{t.kb.scope}</th>
                <th>{t.kb.status}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td className="font-medium">{item.title}</td>
                  <td>{item.service_scope}</td>
                  <td>{item.is_active ? t.common.active : t.common.inactive}</td>
                  <td className="flex gap-2 items-center">
                    <button
                      type="button"
                      className="p-1.5 rounded hover:bg-[var(--color-surface-muted)] text-[var(--color-brand-primary)]"
                      title={t.kb.viewArticle}
                      onClick={() => setViewItem(item)}
                    >
                      <Eye size={16} />
                    </button>
                    <Link to={`/admin/kb/${item.id}`} className="p-1.5 rounded hover:bg-[var(--color-surface-muted)] text-blue-600">
                      <Pencil size={16} />
                    </Link>
                    <button type="button" className="p-1.5 rounded hover:bg-[var(--color-surface-muted)] text-red-600" onClick={() => remove(item.id!)}>
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <Modal
        open={!!viewItem}
        onClose={() => setViewItem(null)}
        title={viewItem?.title || t.kb.viewArticle}
        wide
        footer={
          viewItem?.id ? (
            <>
              <button type="button" className="btn-ghost" onClick={() => setViewItem(null)}>{t.common.cancel}</button>
              <Link to={`/admin/kb/${viewItem.id}`} className="btn-primary" onClick={() => setViewItem(null)}>{t.common.edit}</Link>
            </>
          ) : undefined
        }
      >
        {viewItem && (
          <div className="space-y-3 text-sm">
            <div><span className="font-medium">{t.kb.scope}:</span> {viewItem.service_scope}</div>
            <div><span className="font-medium">{t.kb.status}:</span> {viewItem.is_active ? t.common.active : t.common.inactive}</div>
            <div>
              <span className="font-medium">{t.kb.content}:</span>
              <p className="mt-1 whitespace-pre-wrap text-[var(--color-text-muted)] max-h-64 overflow-y-auto">{viewItem.content}</p>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
