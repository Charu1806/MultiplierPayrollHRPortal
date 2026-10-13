import { Lock } from 'lucide-react'
import { Link } from 'react-router-dom'
import { formatIsoDate } from '@/features/payroll/lib/labels'
import { cycleDay } from '@/features/persona'
import { useAppStore } from '@/store'

type StageState = 'upcoming' | 'current' | 'locked' | 'done' | 'paid'

type StageBox = {
  key: string
  dateLabel: string
  state: StageState
  status: string
  action?: string
  note?: string
  href?: string
  /** Customer-chosen date, a Multiplier deadline, or a date derived from pay day. */
  owner?: 'customer' | 'multiplier' | 'calculated'
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
  /** Review lines HR has neither accepted nor rejected. They are paid at the old base. */
  noAction?: number
  financeName?: string
  fundsAddedOn?: string | null
}

function peopleWord(count: number) {
  return count === 1 ? 'employee' : 'employees'
}

function outcomeLine(asOf: string, payDay: string, willMiss: number, noAction: number) {
  const paid = asOf >= payDay
  const parts: string[] = []
  if (noAction > 0) {
    parts.push(
      paid
        ? `${noAction} ${peopleWord(noAction)} got old base pay because approvals were missing`
        : `${noAction} ${peopleWord(noAction)} will get old base pay because approvals are missing`,
    )
  }
  if (willMiss > 0) {
    parts.push(
      paid
        ? `${willMiss} ${peopleWord(willMiss)} missed payment`
        : `${willMiss} ${peopleWord(willMiss)} will miss payment`,
    )
  }
  return parts.join(' · ')
}

function daysBefore(iso: string, days: number): string {
  const [year, month, day] = iso.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  date.setUTCDate(date.getUTCDate() - days)
  return date.toISOString().slice(0, 10)
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
  noAction = 0,
  financeName = 'Finance',
  fundsAddedOn: string | null = null,
): StageBox[] {
  void openActions
  void payOutcomes
  void signedOff
  void signedOn
  void needsCheck
  void closedWithoutSignOff
  void unappliedCount
  const payDay = DATES.pay
  const inputClose = cycleDay(payDay, 15)
  const reviewStart = cycleDay(payDay, 16)
  const reviewEnd = cycleDay(payDay, 19)
  const finalReport = cycleDay(payDay, 20)
  const reviewClosed = daysBefore(payDay, 7)
  const fundStart = cycleDay(payDay, 23)
  const fundEnd = cycleDay(payDay, 27)
  const submittedOn = cycleDay(payDay, 28)
  const fundsIn = Boolean(fundsAddedOn && asOf >= fundsAddedOn)
  const payLeft = Math.round(
    (Date.parse(`${payDay}T00:00:00Z`) - Date.parse(`${asOf}T00:00:00Z`)) / 86400000,
  )
  const paidCount = payOutcomes?.paidSuccessfully
  const miss = outcomeLine(asOf, payDay, willMiss, noAction) || 'On track'
  const missHref = willMiss > 0 ? '/payroll/actions' : noAction > 0 ? '/payroll/review' : undefined
  const phase =
    asOf <= inputClose
      ? 'input'
      : asOf <= reviewEnd
        ? 'review'
        : asOf <= finalReport
          ? 'report'
          : asOf <= reviewClosed
            ? 'closed'
            : asOf < submittedOn
              ? 'funding'
              : asOf < payDay
                ? 'submitted'
                : asOf <= payDay
                  ? 'pay'
                  : 'after'
  const order = ['input', 'review', 'report', 'closed', 'funding', 'submitted', 'pay']
  const nowIndex = order.indexOf(phase)
  const stateFor = (key: string): StageState => {
    if (phase === 'after') return key === 'pay' ? 'paid' : 'done'
    const index = order.indexOf(key)
    if (index < nowIndex) return 'done'
    if (index === nowIndex) return 'current'
    return 'upcoming'
  }
  const payStatus =
    payLeft > 1
      ? `${payLeft} days left`
      : payLeft === 1
        ? '1 day left'
        : payLeft === 0
          ? 'Today'
          : paidCount
            ? `Paid ${paidCount.count} of ${paidCount.of}`
            : 'Paid'

  return [
    {
      key: 'Input close',
      dateLabel: formatIsoDate(inputClose),
      state: stateFor('input'),
      action: 'Add employees',
      note: 'Add employees, bonuses, and missing details. Later adds move to next month.',
      owner: 'customer',
      status: asOf <= inputClose ? 'Add employees' : `Closed ${formatIsoDate(inputClose)} ✓`,
      href: asOf <= inputClose ? '/people/add' : undefined,
    },
    {
      key: 'Review window',
      dateLabel: `${formatIsoDate(reviewStart)}–${formatIsoDate(reviewEnd).replace(/^[A-Za-z]+ /, '')}`,
      state: stateFor('review'),
      action: 'Complete review',
      owner: 'customer',
      status: asOf < reviewStart ? `Opens ${formatIsoDate(reviewStart)}` : miss,
      href: asOf >= reviewStart && asOf <= reviewEnd ? '/payroll/review' : missHref,
    },
    {
      key: 'Final report',
      dateLabel: formatIsoDate(finalReport),
      state: stateFor('report'),
      action: 'Check the report',
      owner: 'customer',
      status:
        asOf > finalReport
          ? miss === 'On track'
            ? 'On track'
            : miss
          : `On ${formatIsoDate(finalReport)}`,
      href: asOf === finalReport || (asOf > reviewEnd && asOf <= finalReport) ? '/payroll/overview' : missHref,
    },
    {
      key: 'Review close',
      dateLabel: formatIsoDate(reviewClosed),
      state: stateFor('closed'),
      action: 'Final closure',
      owner: 'calculated',
      note: 'Deadline imposed by Multiplier.',
      status: asOf > reviewClosed ? miss : `By ${formatIsoDate(reviewClosed)}`,
      href: asOf === reviewClosed ? '/payroll/actions' : missHref,
    },
    {
      key: 'Funding',
      dateLabel: `${formatIsoDate(fundStart)}–${formatIsoDate(fundEnd).replace(/^[A-Za-z]+ /, '')}`,
      state: stateFor('funding'),
      action: fundsIn
        ? `Funds added ${formatIsoDate(fundsAddedOn || '')} · ${financeName} ✓`
        : `Add funds · ${financeName}`,
      owner: 'customer',
      status: fundsIn
        ? `Funds added ${formatIsoDate(fundsAddedOn || '')} · ${financeName} ✓`
        : `Add funds · ${financeName}`,
    },
    {
      key: 'Payroll submitted',
      dateLabel: formatIsoDate(submittedOn),
      state: stateFor('submitted'),
      action: 'Payroll submitted',
      owner: 'calculated',
      note: 'The 28th of the pay month. Multiplier calculating the payment.',
      status:
        asOf > submittedOn ? `Submitted ${formatIsoDate(submittedOn)} ✓` : `On ${formatIsoDate(submittedOn)}`,
    },
    {
      key: 'Pay day',
      dateLabel: formatIsoDate(payDay),
      state: stateFor('pay'),
      action: payStatus,
      owner: 'customer',
      status: payStatus,
    },
  ]
}

const stateClass: Record<StageState, string> = {
  upcoming: 'border-border bg-surface-recessed text-text-secondary',
  current: 'border-sky-600 bg-sky-50 text-sky-950 ring-1 ring-sky-600',
  locked: 'border-status-danger-border bg-status-danger-bg text-status-danger-text',
  done: 'border-status-ok-border bg-status-ok-bg text-status-ok-text',
  paid: 'border-status-ok-border bg-status-ok-bg text-status-ok-text',
}

export function FinalReportNote() {
  const overview = useAppStore((s) => s.overview)
  const pay = overview?.dates?.payDate || overview?.cycle?.payDate
  if (!pay) return null
  return (
    <p className="text-xs text-text-secondary">
      Final report <span className="font-medium text-text-primary">{formatIsoDate(cycleDay(pay, 20))}</span>
    </p>
  )
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
  noAction = 0,
  financeName,
  fundsAddedOn,
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
    noAction,
    financeName,
    fundsAddedOn,
  )

  return (
    <section className="rounded border border-border bg-surface p-4">
      <div className="mb-3">
        <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
          Stage tracker
        </p>
        <p className="mt-1 text-xs text-text-secondary">
          Input close, the review window, the final report, the funding window, and pay day are from your settings.
          Multiplier recommends them; you can choose other dates. Review close is a deadline imposed by Multiplier,
          back calculated from pay day. Payroll submitted is the 28th of the pay month. Funds are
          added on the day the fund manager clicks Yes.
        </p>
        {willMiss > 0 || noAction > 0 ? (
          <p className="mt-2 text-[13px] font-medium text-text-primary">
            {outcomeLine(asOf, dates.pay, willMiss, noAction)}
          </p>
        ) : null}
      </div>
      <div className="grid grid-cols-7 gap-2">
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
              {stage.owner === 'customer' ? (
                <p className="mt-1 text-[10px] font-medium uppercase tracking-wide opacity-80">From your settings</p>
              ) : null}
              {stage.owner === 'multiplier' ? (
                <p className="mt-1 text-[10px] font-medium uppercase tracking-wide text-[#863bff]">
                  Set by Multiplier
                </p>
              ) : null}
              {stage.owner === 'multiplier' || stage.owner === 'calculated' ? (
                <p className="mt-1 text-[10px] font-medium uppercase tracking-wide text-[#863bff]">Back calculated from pay day</p>
              ) : null}
              {stage.state === 'current' && stage.action && stage.action !== stage.status ? (
                <p className="mt-1 text-[11px] font-semibold leading-snug text-sky-800">{stage.action}</p>
              ) : null}
              <p
                className={[
                  'mt-1 text-[11px] leading-snug',
                  stage.state === 'current' ? 'text-[12px] font-semibold text-sky-800' : 'opacity-90',
                ].join(' ')}
              >
                {stage.status}
              </p>
              {stage.note ? (
                <p className="mt-1 text-[11px] leading-snug opacity-90">{stage.note}</p>
              ) : null}
            </>
          )
          const cls = `block min-h-[88px] rounded border px-2.5 py-2 ${stateClass[stage.state]}`
          if (stage.href) {
            return (
              <Link
                key={stage.key}
                to={stage.href}
                data-current={stage.state === 'current' ? 'true' : undefined}
                className={`${cls} hover:opacity-90`}
              >
                {body}
              </Link>
            )
          }
          return (
            <div key={stage.key} data-current={stage.state === 'current' ? 'true' : undefined} className={cls}>
              {body}
            </div>
          )
        })}
      </div>
    </section>
  )
}
