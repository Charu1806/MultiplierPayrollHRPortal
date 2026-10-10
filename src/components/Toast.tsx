import { X } from 'lucide-react'
import { useAppStore } from '@/store'

export function ToastStack() {
  const toasts = useAppStore((s) => s.toasts)
  const dismissToast = useAppStore((s) => s.dismissToast)

  if (toasts.length === 0) return null

  return (
    <div className="pointer-events-none fixed bottom-6 right-6 z-[70] flex w-80 flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className="pointer-events-auto flex items-start gap-2 rounded border border-border-active bg-surface px-3 py-2 text-xs text-text-primary shadow-[0px_4px_6px_-1px_rgba(15,23,42,0.08)]"
          role="status"
        >
          <p className="flex-1 pt-0.5">{toast.message}</p>
          <button
            type="button"
            aria-label="Dismiss"
            className="rounded p-0.5 text-text-muted hover:bg-surface-recessed hover:text-text-primary"
            onClick={() => dismissToast(toast.id)}
          >
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  )
}
