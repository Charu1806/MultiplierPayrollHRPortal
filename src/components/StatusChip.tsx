import type { ReactNode } from 'react'

export type Tone = 'ok' | 'warn' | 'danger' | 'info' | 'neutral'

type Props = {
  tone?: Tone
  children: ReactNode
}

const tones: Record<Tone, string> = {
  ok: 'bg-status-ok-bg border-status-ok-border text-status-ok-text',
  warn: 'bg-status-warn-bg border-status-warn-border text-status-warn-text',
  danger: 'bg-status-danger-bg border-status-danger-border text-status-danger-text',
  info: 'bg-status-info-bg border-status-info-border text-status-info-text',
  neutral: 'bg-surface-recessed border-border text-text-secondary',
}

export function StatusChip({ tone = 'neutral', children }: Props) {
  return (
    <span
      className={`inline-flex h-5 items-center rounded border px-1.5 text-[11px] font-medium leading-none ${tones[tone]}`}
    >
      {children}
    </span>
  )
}
