import { useEffect, type ReactNode } from 'react'
import { useAppStore } from '@/store'
import { getClarityApiBase } from '@/api/clarityClient'
import { Button } from '@/components'

type Props = {
  children: ReactNode
}

export function Bootstrap({ children }: Props) {
  const boot = useAppStore((s) => s.boot)
  const bootStatus = useAppStore((s) => s.bootStatus)
  const bootError = useAppStore((s) => s.bootError)

  useEffect(() => {
    void boot()
  }, [boot])

  if (bootStatus === 'idle' || bootStatus === 'loading') {
    return (
      <div className="flex min-h-full min-w-[1440px] items-center justify-center bg-canvas">
        <div className="rounded border border-border bg-surface px-6 py-5 text-center">
          <p className="text-sm font-medium text-text-primary">
            Loading Payroll Clarity…
          </p>
          <p className="mt-1 text-xs text-text-secondary">
            Hydrating from {getClarityApiBase()}
          </p>
        </div>
      </div>
    )
  }

  if (bootStatus === 'error') {
    return (
      <div className="flex min-h-full min-w-[1440px] items-center justify-center bg-canvas">
        <div className="w-[420px] rounded border border-status-danger-border bg-surface px-6 py-5">
          <p className="text-sm font-medium text-status-danger-text">
            Could not reach Clarity API
          </p>
          <p className="mt-2 text-xs text-text-secondary">{bootError}</p>
          <p className="mt-2 text-xs text-text-muted">
            Start the API with{' '}
            <code className="rounded bg-surface-recessed px-1">
              python3 -m server.app
            </code>{' '}
            then retry.
          </p>
          <div className="mt-4">
            <Button variant="primary" onClick={() => void boot()}>
              Retry
            </Button>
          </div>
        </div>
      </div>
    )
  }

  return children
}
