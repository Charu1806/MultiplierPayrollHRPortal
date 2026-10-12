import { Lock } from 'lucide-react'
import { Link } from 'react-router-dom'
import { formatIsoDate } from '@/features/payroll/lib/labels'
import { cycleDay } from '@/features/persona'

type StageState = 'upcoming' | 'current' | 'locked' | 'done' | 'paid'

type StageBox = {
  key: string
  dateLabel: string
  state: StageState
  status: string
  href?: string
}

type CycleDates = {
  cutoff: string
  calculation: string
  finalSync?: string
  reviewOpen: string
  reviewClose: string
  funding?: string | null
  submitted?: string | null
  pay: string
}

type PayResult = {
  paidSuccessfully: { count: number; of: number }
}

type Props = {
  asOf: string
  openActions: number
  payOutcomes?: PayResult | null
  signedOff?: boolean
  signedOn?: string | null
  needsCheck?: number
  closedWithoutSignOff?: boolean
  unappliedCount?: number
  dates: CycleDates
  willMiss?: number
  financeName?: string
}

function buildStages(
  asOf: string,
  openActions: number,
  payOutcomes: PayResult | null | undefined,
  signedOff: boolean | undefined,
  signedOn: string | null | undefined,
  needsCheck: number,
  closedWithoutSignOff: boolean,
  unappliedCount: number,
  DATES: CycleDates,
  willMiss = 0,
  financeName = 'Finance',
): StageBox[] {
  void openActions
  void payOutcomes
  void signedOff
  void signedOn
  void needsCheck
  void closedWithoutSignOff
  void unappliedCount
  const inputClose = cycleDay(DATES.pay, 15)
  const reviewStart = cycleDay(DATES.pay, 16)
  const reviewEnd = cycleDay(DATES.pay, 19)
  const finalReport = cycleDay(DATES.pay, 21)
  const reviewClosed = cycleDay(DATES.pay, 22)
  const fundStart = cycleDay(DATES.pay, 24)
  const fundEnd = cycleDay(DATES.pay, 27)
  const payDay = DATES.pay
  const payLeft = Math.round(
    (Date.parse(`${payDay}T00:00:00Z`) - Date.parse(`${asOf}T00:00:00Z`)) / 86400000,
  )
  const paidCount = payOutcomes?.paidSuccessfully
  const miss = willMiss > 0 ? `${willMiss} will miss payment` : 'On track'
  const missHref = willMiss > 0 ? '/payroll/actions' : undefined
  const span = (start: string, end: string): StageState =>
    asOf < start ? 'upcoming' : asOf <= end ? 'current' : 'done'

  return [
    {
      key: 'Input close',
      dateLabel: formatIsoDate(inputClose),
      state: span(inputClose, inputClose),
      status:
        asOf <= inputClose
          ? `New employees close ${formatIsoDate(inputClose)}`
          : `Closed ${formatIsoDate(inputClose)} ✓`,
    },
    {
      key: 'Review window',
      dateLabel: `${formatIsoDate(reviewStart)}–${formatIsoDate(reviewEnd).replace(/^[A-Za-z]+ /, '')}`,
      state: span(reviewStart, reviewEnd),
      status: miss,
      href: missHref,
    },
    {
      key: 'Final report',
      dateLabel: formatIsoDate(finalReport),
      state: span(finalReport, finalReport),
      status: willMiss > 0 ? `${willMiss} will miss this window` : 'On track',
      href: missHref,
    },
    {
      key: 'Review closed',
      dateLabel: formatIsoDate(reviewClosed),
      state: span(reviewClosed, reviewClosed),
      status: miss,
      href: missHref,
    },
    {
      key: 'Funding',
      dateLabel: `${formatIsoDate(fundStart)}–${formatIsoDate(fundEnd).replace(/^[A-Za-z]+ /, '')}`,
      state: span(fundStart, fundEnd),
      status:
        asOf > fundEnd
          ? `Funds added · ${financeName} ✓`
          : `Add funds · ${financeName}`,
    },
    {
      key: 'Pay day',
      dateLabel: formatIsoDate(payDay),
      state: payLeft > 1 ? 'upcoming' : payLeft >= 0 ? 'current' : 'paid',
      status:
        payLeft > 1
          ? `${payLeft} days left`
          : payLeft === 1
            ? '1 day left'
            : payLeft === 0
              ? 'Today'
              : paidCount
                ? `Paid ${paidCount.count} of ${paidCount.of}`
                : 'Paid',
    },
  ]
}

const stateClass: Record<StageState, string> = {
  upcoming: 'border-border bg-surface-recessed text-text-secondary',
  current: 'border-status-info-border bg-status-info-bg text-status-info-text',
  locked: 'border-status-danger-border bg-status-danger-bg text-status-danger-text',
  done: 'border-status-ok-border bg-status-ok-bg text-status-ok-text',
  paid: 'border-status-ok-border bg-status-ok-bg text-status-ok-text',
}

export function StageTracker({
  asOf,
  openActions,
  payOutcomes,
  signedOff,
  signedOn,
  needsCheck = 0,
  closedWithoutSignOff = false,
  unappliedCount = 0,
  dates,
  willMiss = 0,
  financeName,
}: Props) {
  const stages = buildStages(
    asOf,
    openActions,
    payOutcomes,
    signedOff,
    signedOn,
    needsCheck,
    closedWithoutSignOff,
    unappliedCount,
    dates,
    willMiss,
    financeName,
  )

  return (
    <section className="rounded border border-border bg-surface p-4">
      <div className="mb-3">
        <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
          Stage tracker
        </p>
      </div>
      <div className="grid grid-cols-6 gap-2">
        {stages.map((stage) => {
          const locked = stage.state === 'locked' || stage.state === 'done' || stage.state === 'paid'
          const body = (
            <>
              <div className="flex items-start justify-between gap-1">
                <p className="text-[12px] font-semibold leading-tight text-inherit">
                  {stage.key}
                </p>
                {locked ? <Lock size={12} className="mt-0.5 shrink-0 opacity-80" /> : null}
              </div>
              <p className="mt-1 tabular text-[11px] font-medium opacity-90">{stage.dateLabel}</p>
              <p className="mt-1 text-[11px] leading-snug opacity-90">{stage.status}</p>
            </>
          )
          const cls = `block min-h-[88px] rounded border px-2.5 py-2 ${stateClass[stage.state]}`
          if (stage.href) {
            return (
              <Link key={stage.key} to={stage.href} className={`${cls} hover:opacity-90`}>
                {body}
              </Link>
            )
          }
          return (
            <div key={stage.key} className={cls}>
              {body}
            </div>
          )
        })}
      </div>
    </section>
  )
}
