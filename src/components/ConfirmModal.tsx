import { useEffect, useState } from 'react'
import { Button } from '@/components/Button'

export type ConfirmRequest = {
  title: string
  body: string
  extra?: string
  confirmLabel?: string
  cancelLabel?: string
  /** When set, Confirm stays disabled until the checkbox is checked. */
  requireCheckbox?: { label: string }
  onConfirm: () => void | Promise<void>
}

type Props = {
  request: ConfirmRequest | null
  busy?: boolean
  error?: string | null
  onCancel: () => void
}

export function ConfirmModal({ request, busy, error, onCancel }: Props) {
  const [checked, setChecked] = useState(false)

  useEffect(() => {
    setChecked(false)
  }, [request?.title, request?.body])

  if (!request) return null

  const needsCheck = Boolean(request.requireCheckbox)
  const confirmDisabled = Boolean(busy) || (needsCheck && !checked)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        className="w-[480px] max-w-[calc(100vw-2rem)] rounded border border-border bg-surface p-5 shadow-lg"
      >
        <h2 id="confirm-title" className="text-sm font-semibold text-text-primary">
          {request.title}
        </h2>
        <p className="mt-2 whitespace-pre-line text-[13px] text-text-secondary">{request.body}</p>
        {request.extra ? (
          <p className="mt-2 rounded border border-status-warn-border bg-status-warn-bg px-3 py-2 text-xs text-status-warn-text">
            {request.extra}
          </p>
        ) : null}
        {request.requireCheckbox ? (
          <label className="mt-3 flex items-start gap-2 text-[13px] text-text-primary">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={checked}
              onChange={(e) => setChecked(e.target.checked)}
            />
            <span>{request.requireCheckbox.label}</span>
          </label>
        ) : null}
        {error ? (
          <p className="mt-3 rounded border border-status-danger-border bg-status-danger-bg px-3 py-2 text-xs text-status-danger-text">
            {error}
          </p>
        ) : null}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={onCancel} disabled={busy}>
            {request.cancelLabel ?? 'Cancel'}
          </Button>
          <Button
            variant="primary"
            disabled={confirmDisabled}
            onClick={() => {
              void (async () => {
                await request.onConfirm()
              })()
            }}
          >
            {busy ? 'Working…' : (request.confirmLabel ?? 'Confirm')}
          </Button>
        </div>
      </div>
    </div>
  )
}
