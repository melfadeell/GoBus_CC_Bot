import { ReactNode, useState } from 'react'
import { Maximize2 } from 'lucide-react'
import Modal from '@/components/admin/Modal'
import { useLanguage } from '@/i18n/LanguageProvider'

interface ChartCardProps {
  title: string
  subtitle?: string
  children: ReactNode
  fullscreenContent?: ReactNode
}

export default function ChartCard({ title, subtitle, children, fullscreenContent }: ChartCardProps) {
  const { t } = useLanguage()
  const [open, setOpen] = useState(false)

  return (
    <>
      <div className="card p-4 fade-in relative">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div>
            <h3 className="font-bold text-sm">{title}</h3>
            {subtitle && <p className="text-xs text-[var(--color-text-muted)] mt-0.5">{subtitle}</p>}
          </div>
          <button
            type="button"
            className="p-1.5 rounded-lg hover:bg-[var(--color-surface-muted)] text-[var(--color-text-muted)] shrink-0"
            onClick={() => setOpen(true)}
            title={t.dashboard.fullscreen}
          >
            <Maximize2 size={16} />
          </button>
        </div>
        <div className="h-56">{children}</div>
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title={title} extraWide stacked>
        {subtitle && <p className="text-sm text-[var(--color-text-muted)] mb-4">{subtitle}</p>}
        <div>{fullscreenContent ?? children}</div>
      </Modal>
    </>
  )
}
