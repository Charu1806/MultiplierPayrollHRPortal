import { Lock } from 'lucide-react'
import { Link } from 'react-router-dom'
import { formatIsoDate } from '@/features/payroll/lib/labels'
import type { OutcomeDto } from '@/api/types'

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
  reviewOpen: string
  reviewClose: string
  funding?: string | null
  submitted?: string | null
  pay: string
}

type Props = {
  asOf: string
  openActions: number
  outcome?: OutcomeDto | null
  signedOff?: boolean
  signedOn?: string | null
  needsCheck?: number
  closedWithoutSignOff?: boolean
  unappliedCount?: number
  dates: CycleDates
}

function daysBetween(from: string, to: string): number {
  return Math.max(
    0,
    Math.round(
      (new Date(`${to}T00:00:00`).getTime() - new Date(`${from}T00:00:00`).getTime()) /
        86400000,
    ),
  )
}

function buildStages(
  asOf: string,
  openActions: number,
  outcome: OutcomeDto | null | undefined,
  signedOff: boolean | undefined,
  signedOn: string | null | undefined,
  needsCheck: number,
  closedWithoutSignOff: boolean,
  unappliedCount: number,
  DATES: CycleDates,
): StageBox[] {
  const moved = outcome?.movedToNovember.count ?? (asOf > DATES.cutoff ? openActions : 0)

  const input: StageBox = (() => {
    if (asOf < DATES.cutoff) {
      const days = daysBetween(asOf, DATES.cutoff)
      const left =
        days === 0 ? 'Cutoff today' : days === 1 ? '1 day left' : `${days} days left`
      return {
        key: 'Input finalisation',
        dateLabel: formatIsoDate(DATES.cutoff),
        state: 'current',
        status: `${left}${openActions ? ` · ${openActions} actions open` : ''}`,
      }
    }
    if (asOf === DATES.cutoff) {
      return {
        key: 'Input finalisation',
        dateLabel: formatIsoDate(DATES.cutoff),
        state: 'current',
        status: `Cutoff today${openActions ? ` · ${openActions} actions open` : ''}`,
      }
    }
    if (openActions > 0 || moved > 0) {
      return {
        key: 'Input finalisation',
        dateLabel: formatIsoDate(DATES.cutoff),
        state: 'locked',
        status: `Inputs locked ${formatIsoDate(DATES.cutoff)} · ${moved || openActions} employees moved to next cycle`,
      }
    }
    return {
      key: 'Input finalisation',
      dateLabel: formatIsoDate(DATES.cutoff),
      state: 'done',
      status: `Inputs locked ${formatIsoDate(DATES.cutoff)} ✓`,
    }
  })()

  const calcDate = DATES.calculation
  const calculation: StageBox =
    asOf < calcDate
      ? {
          key: 'Calculation & final checks',
          dateLabel: formatIsoDate(calcDate),
          state: 'upcoming',
          status: `Calculation · ${formatIsoDate(calcDate)}`,
        }
      : asOf < DATES.reviewOpen
        ? {
            key: 'Calculation & final checks',
            dateLabel: formatIsoDate(calcDate),
            state: 'current',
            status: 'Multiplier calculating pay',
          }
        : {
            key: 'Calculation & final checks',
            dateLabel: formatIsoDate(calcDate),
            state: 'done',
            status: `Pay calculated ${formatIsoDate(calcDate)} ✓`,
          }

  const review: StageBox = (() => {
    if (asOf < DATES.reviewOpen) {
      return {
        key: 'Review',
        dateLabel: `${formatIsoDate(DATES.reviewOpen)}–${formatIsoDate(DATES.reviewClose).replace(/^[A-Za-z]+ /, '')}`,
        state: 'upcoming',
        status: `Opens ${formatIsoDate(DATES.reviewOpen)}`,
      }
    }
    if (asOf <= DATES.reviewClose) {
      if (signedOff) {
        return {
          key: 'Review',
          dateLabel: formatIsoDate(DATES.reviewClose),
          state: 'done',
          status: `Payroll approved ${formatIsoDate(signedOn || asOf)}`,
        }
      }
      return {
        key: 'Review',
        dateLabel: formatIsoDate(DATES.reviewClose),
        state: 'current',
        status: `Open · closes ${formatIsoDate(DATES.reviewClose)}`,
      }
    }
    if (signedOff) {
      return {
        key: 'Review',
        dateLabel: formatIsoDate(DATES.reviewClose),
        state: 'done',
        status: `Payroll approved ${formatIsoDate(signedOn || DATES.reviewClose)}`,
      }
    }
    const n = unappliedCount || needsCheck
    return {
      key: 'Review',
      dateLabel: formatIsoDate(DATES.reviewClose),
      state: 'locked',
      status: `Closed · ${n} changes moved to next cycle`,
    }
  })()

  const fundingDate = DATES.funding
  const funding: StageBox = fundingDate
    ? asOf < fundingDate
      ? {
          key: 'Funding',
          dateLabel: formatIsoDate(fundingDate),
          state: 'upcoming',
          status: `Funding · ${formatIsoDate(fundingDate)}`,
        }
      : {
          key: 'Funding',
          dateLabel: formatIsoDate(fundingDate),
          state: 'done',
          status: `Funded ${formatIsoDate(fundingDate)} ✓`,
        }
    : {
        key: 'Funding',
        dateLabel: '—',
        state: 'upcoming',
        status: 'Funding',
      }

  const submittedDate = DATES.submitted
  const submitted: StageBox = submittedDate
    ? asOf < submittedDate
      ? {
          key: 'Submitted',
          dateLabel: formatIsoDate(submittedDate),
          state: 'upcoming',
          status: `Submitted · ${formatIsoDate(submittedDate)}`,
        }
      : {
          key: 'Submitted',
          dateLabel: formatIsoDate(submittedDate),
          state: 'done',
          status: `Submitted ${formatIsoDate(submittedDate)} ✓`,
        }
    : {
        key: 'Submitted',
        dateLabel: '—',
        state: 'upcoming',
        status: 'Submitted',
      }

  const paid: StageBox =
    asOf < DATES.pay
      ? {
          key: 'Paid',
          dateLabel: formatIsoDate(DATES.pay),
          state: 'upcoming',
          status: `Pay day · ${formatIsoDate(DATES.pay)}`,
        }
      : {
          key: 'Paid',
          dateLabel: formatIsoDate(DATES.pay),
          state: 'paid',
          status: outcome
            ? `Paid ${formatIsoDate(DATES.pay)} · ${outcome.paidOnTime.count} of ${outcome.inRun ?? outcome.total} employees received pay`
            : `Paid ${formatIsoDate(DATES.pay)}`,
          href: outcome?.paidOnTime.href || '/people?filter=paid_october',
        }

  const stages = [input, calculation, review, funding, submitted, paid]
  if (asOf >= DATES.pay) {
    return stages.map((s) =>
      s.key === 'Paid' ? s : s.state === 'current' ? { ...s, state: 'done' as const } : s,
    )
  }
  return stages
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
  outcome,
  signedOff,
  signedOn,
  needsCheck = 0,
  closedWithoutSignOff = false,
  unappliedCount = 0,
  dates,
}: Props) {
  const stages = buildStages(
    asOf,
    openActions,
    outcome,
    signedOff,
    signedOn,
    needsCheck,
    closedWithoutSignOff,
    unappliedCount,
    dates,
  )

  return (
    <section className="rounded border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
          Stage tracker
        </p>
        <span className="tabular text-xs text-text-secondary">
          Pay date: {formatIsoDate(dates.pay)}
        </span>
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
