import Modal from '@/components/admin/Modal'
import { useLanguage } from '@/i18n/LanguageProvider'

interface EnhanceCompareModalProps {
  open: boolean
  onClose: () => void
  original: string
  enhanced: string
  onUseOriginal: () => void
  onUseEnhanced: () => void
  ltr?: boolean
}

export default function EnhanceCompareModal({
  open,
  onClose,
  original,
  enhanced,
  onUseOriginal,
  onUseEnhanced,
  ltr = false,
}: EnhanceCompareModalProps) {
  const { t } = useLanguage()

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t.common.enhanceCompareTitle}
      extraWide
      stacked
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={onUseOriginal}>
            {t.common.useOriginal}
          </button>
          <button type="button" className="btn-primary" onClick={onUseEnhanced}>
            {t.common.useEnhanced}
          </button>
        </>
      }
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium mb-2">{t.common.originalText}</label>
          <textarea
            className={`textarea-field min-h-[240px] resize-none bg-[var(--color-surface-muted)] ${ltr ? 'ltr' : ''}`}
            dir={ltr ? 'ltr' : 'auto'}
            value={original}
            readOnly
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-2">{t.common.enhancedText}</label>
          <textarea
            className={`textarea-field min-h-[240px] resize-none ${ltr ? 'ltr' : ''}`}
            dir={ltr ? 'ltr' : 'auto'}
            value={enhanced}
            readOnly
          />
        </div>
      </div>
    </Modal>
  )
}
