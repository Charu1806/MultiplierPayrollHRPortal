import { useEffect, useMemo, useRef, useState } from 'react'
import { formatIsoDate } from '@/features/payroll/lib/labels'
import { useAppStore } from '@/store'

function iso(y: number, m: number, d: number) {
  return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`
}

function parseIso(value: string) {
  const [y, m, d] = value.split('-').map(Number)
  return { y, m, d }
}

type Props = {
  value: string
  onChange: (isoDate: string) => void
  busy?: boolean
}

export function DatePicker({ value, onChange, busy }: Props) {
  const prototypeDates = useAppStore((s) => s.prototypeDates)
  const min = prototypeDates?.min || '2026-10-01'
  const max = prototypeDates?.max || '2027-01-31'
  const keyDates = useMemo(() => {
    const map: Record<string, string> = {}
    for (const k of prototypeDates?.keyDates || []) {
      map[k.value] = k.label
    }
    return map
  }, [prototypeDates])

  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const initial = parseIso(value || prototypeDates?.default || min)
  const [viewY, setViewY] = useState(initial.y)
  const [viewM, setViewM] = useState(initial.m)

  useEffect(() => {
    const p = parseIso(value)
    setViewY(p.y)
    setViewM(p.m)
  }, [value])

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!root.current?.contains(e.target as Node)) setOpen(false)
    }
    if (open) document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  const cells = useMemo(() => {
    const first = new Date(viewY, viewM - 1, 1)
    const startPad = (first.getDay() + 6) % 7 // Mon=0
    const daysInMonth = new Date(viewY, viewM, 0).getDate()
    const out: { day: number | null; iso?: string }[] = []
    for (let i = 0; i < startPad; i++) out.push({ day: null })
    for (let d = 1; d <= daysInMonth; d++) {
      out.push({ day: d, iso: iso(viewY, viewM, d) })
    }
    while (out.length % 7 !== 0) out.push({ day: null })
    return out
  }, [viewY, viewM])

  function shiftMonth(delta: number) {
    let m = viewM + delta
    let y = viewY
    if (m < 1) {
      m = 12
      y -= 1
    }
    if (m > 12) {
      m = 1
      y += 1
    }
    const first = iso(y, m, 1)
    const last = iso(y, m, new Date(y, m, 0).getDate())
    if (last < min || first > max) return
    setViewY(y)
    setViewM(m)
  }

  const monthLabel = new Date(viewY, viewM - 1, 1).toLocaleString('en-US', {
    month: 'long',
    year: 'numeric',
  })

  const rangeLabel = `${formatIsoDate(min)} – ${formatIsoDate(max)}, ${parseIso(min).y}`

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-label="Prototype date"
        disabled={busy}
        className="inline-flex h-6 items-center gap-1.5 rounded border border-border bg-surface px-1.5 text-xs text-text-primary hover:bg-surface-recessed disabled:opacity-50"
        onClick={() => setOpen((o) => !o)}
      >
        <span aria-hidden>📅</span>
        {formatIsoDate(value)}
      </button>
      {open ? (
        <div className="absolute left-0 top-full z-40 mt-1 w-72 rounded border border-border bg-surface p-3 shadow-sm">
          <div className="mb-2 flex items-center justify-between">
            <button
              type="button"
              className="rounded px-1.5 py-0.5 text-xs text-text-secondary hover:bg-surface-recessed"
              onClick={() => shiftMonth(-1)}
            >
              ‹
            </button>
            <span className="text-xs font-medium text-text-primary">{monthLabel}</span>
            <button
              type="button"
              className="rounded px-1.5 py-0.5 text-xs text-text-secondary hover:bg-surface-recessed"
              onClick={() => shiftMonth(1)}
            >
              ›
            </button>
          </div>
          <div className="mb-1 grid grid-cols-7 gap-0.5 text-center text-[10px] text-text-muted">
            {['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'].map((d) => (
              <span key={d}>{d}</span>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-0.5">
            {cells.map((c, i) => {
              if (!c.day || !c.iso) return <span key={`e-${i}`} />
              const disabled = c.iso < min || c.iso > max
              const selected = c.iso === value
              const key = keyDates[c.iso]
              return (
                <button
                  key={c.iso}
                  type="button"
                  disabled={disabled}
                  title={key || undefined}
                  className={[
                    'relative flex h-8 flex-col items-center justify-center rounded text-xs',
                    disabled
                      ? 'cursor-not-allowed text-text-muted opacity-40'
                      : selected
                        ? 'bg-text-primary text-white'
                        : 'text-text-primary hover:bg-surface-recessed',
                  ].join(' ')}
                  onClick={() => {
                    onChange(c.iso!)
                    setOpen(false)
                  }}
                >
                  {c.day}
                  {key ? (
                    <span
                      className={[
                        'absolute bottom-0.5 h-1 w-1 rounded-full',
                        selected ? 'bg-white' : 'bg-status-info-text',
                      ].join(' ')}
                    />
                  ) : null}
                </button>
              )
            })}
          </div>
          <p className="mt-2 text-[10px] text-text-muted">
            Dots mark key payroll dates (hover for label). Range {rangeLabel}.
          </p>
        </div>
      ) : null}
    </div>
  )
}
