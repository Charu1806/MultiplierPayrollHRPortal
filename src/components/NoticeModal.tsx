import { useEffect } from 'react'
import { Button } from '@/components/Button'

type Props = {
  message: string | null
  onOk: () => void
}

function noticeCopy(message: string): { title: string; lines: string[] } {
  if (message.startsWith('Reminder emailed')) {
    const parts = message
      .split(' · ')
      .map((part) => part.trim())
      .filter(Boolean)
    return { title: parts[0] || 'Reminder emailed', lines: parts.slice(1) }
  }
  return { title: 'Notice', lines: [message] }
}

export function NoticeModal({ message, onOk }: Props) {
  useEffect(() => {
    if (!message) return
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape' || event.key === 'Enter') onOk()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [message, onOk])

  if (!message) return null

  const { title, lines } = noticeCopy(message)

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-900/40 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="notice-title"
        className="w-[440px] max-w-[calc(100vw-2rem)] rounded border border-border bg-surface p-5 shadow-lg"
      >
        <h2 id="notice-title" className="text-sm font-semibold text-text-primary">
          {title}
        </h2>
        {lines.length > 0 ? (
          <div className="mt-2 space-y-1 text-[13px] text-text-secondary">
            {lines.map((line) => (
              <p key={line}>{line}</p>
            ))}
          </div>
        ) : null}
        <div className="mt-4 flex justify-end">
          <Button variant="primary" onClick={onOk}>
            OK
          </Button>
        </div>
      </div>
    </div>
  )
}
