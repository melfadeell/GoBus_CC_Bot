import { ReactNode, useEffect } from 'react'
import { X } from 'lucide-react'

interface ModalProps {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  footer?: ReactNode
  wide?: boolean
  extraWide?: boolean
  stacked?: boolean
}

export default function Modal({ open, onClose, title, children, footer, wide, extraWide, stacked }: ModalProps) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className={`fixed inset-0 flex items-center justify-center p-4 ${stacked ? 'z-[60]' : 'z-50'}`}>
      <button type="button" className="absolute inset-0 bg-black/40" aria-label="Close" onClick={onClose} />
      <div
        className={`relative bg-white rounded-xl shadow-xl w-full max-h-[90vh] flex flex-col ${
          extraWide ? 'max-w-5xl' : wide ? 'max-w-3xl' : 'max-w-lg'
        }`}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <h3 className="font-bold text-lg">{title}</h3>
          <button type="button" className="p-1 rounded hover:bg-[var(--color-surface-muted)]" onClick={onClose}>
            <X size={20} />
          </button>
        </div>
        <div className="p-5 overflow-y-auto flex-1">{children}</div>
        {footer && <div className="px-5 py-4 border-t flex gap-3 justify-end">{footer}</div>}
      </div>
    </div>
  )
}
