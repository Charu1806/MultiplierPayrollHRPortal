import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { clarityApi } from '@/api/clarityClient'
import { EmptyState, PageHeader, StatusChip } from '@/components'
import { StageTracker } from '@/features/payroll/components/StageTracker'
import { countryCode, formatIsoDate } from '@/features/payroll/lib/labels'
import { countryAdmins, cycleDay, personaCountry, type CountryAdmin, type PersonaId } from '@/features/persona'
import { reviewCards } from '@/features/payroll/lib/scope'
import type { CountryPaySlice } from '@/api/types'
import { useAppStore } from '@/store'

function QueryMail({
  admin,
  onClose,
}: {
  admin: CountryAdmin
  onClose: () => void
}) {
  const asOf = useAppStore((s) => s.asOf)
  const pushToast = useAppStore((s) => s.pushToast)
  const refreshNotifications = useAppStore((s) => s.refreshNotifications)
  const [body, setBody] = useState(
    `Hi ${admin.name}, please confirm the open payroll items for ${admin.country}.`,
  )
  const [sending, setSending] = useState(false)

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/30 p-6">
      <form
        className="w-full max-w-md rounded border border-border bg-surface p-4"
        onSubmit={(event) => {
          event.preventDefault()
          setSending(true)
          void clarityApi
            .sendHrQuery({
              asOf,
              recipient: `${admin.name}, ${admin.country} HR admin`,
              subject: `Payroll query · ${admin.country}`,
              body,
              href: `/payroll/actions?country=${admin.code}`,
            })
            .then(async () => {
              await refreshNotifications()
              pushToast(`Query sent to ${admin.name}`)
              onClose()
            })
            .catch((err: unknown) => {
              pushToast(err instanceof Error ? err.message : 'Could not send mail')
            })
            .finally(() => setSending(false))
        }}
      >
        <h2 className="text-sm font-semibold text-text-primary">Write to {admin.name}</h2>
        <p className="mt-1 text-xs text-text-secondary">
          {admin.role} · {admin.country} · {admin.email}
        </p>
        <textarea
          className="mt-3 h-28 w-full rounded border border-border px-2 py-1.5 text-[13px] text-text-primary"
          value={body}
          onChange={(event) => setBody(event.target.value)}
        />
        <div className="mt-3 flex justify-end gap-2">
          <button type="button" className="h-8 rounded border border-border px-3 text-xs" onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            disabled={sending || !body.trim()}
            className="h-8 rounded bg-text-primary px-3 text-xs font-medium text-white disabled:opacity-50"
          >
            Send mail
          </button>
        </div>
      </form>
    </div>
  )
}

function daysUntil(from: string, to: string): number {
  const start = Date.parse(`${from.slice(0, 10)}T00:00:00Z`)
  const end = Date.parse(`${to.slice(0, 10)}T00:00:00Z`)
  return Math.round((end - start) / 86400000)
}

function daysLeft(days: number): string | null {
  if (days > 1) return `${days} days left`
  if (days === 1) return '1 day left'
  if (days === 0) return 'Today'
  return null
}

function cycleFocus(asOf: string, pay: string, submitted: string | null): {
  title: string
  detail: string
  countdown: string | null
  extra: string
} {
  const inputClose = cycleDay(pay, 15)
  const reviewBy = cycleDay(pay, 19)
  const reportDay = cycleDay(pay, 20)
  const closure = cycleDay(pay, 22)
  const inputLabel = formatIsoDate(inputClose)
  const reviewLabel = formatIsoDate(reviewBy)
  const reportLabel = formatIsoDate(reportDay)
  const closureLabel = formatIsoDate(closure)
  const payLabel = formatIsoDate(pay)
  const submittedLabel = submitted ? formatIsoDate(submitted) : null
  const later = [submittedLabel ? `Payroll submitted ${submittedLabel}` : null, `Pay day ${payLabel}`]
    .filter(Boolean)
    .join(' · ')

  if (asOf <= inputClose) {
    return {
      title: `Add employees, bonuses, hikes, and missing details by ${inputLabel}`,
      detail: `People added after ${inputLabel} move to next month. Complete review by ${reviewLabel}. Final report ${reportLabel}. Final closure ${closureLabel}.`,
      countdown: daysLeft(daysUntil(asOf, inputClose)),
      extra: later,
    }
  }
  if (asOf <= reviewBy) {
    return {
      title: `Complete review by ${reviewLabel}`,
      detail: `Finish review and approvals by ${reviewLabel}. Final report ${reportLabel}. Final closure is ${closureLabel}. Changes after ${closureLabel} apply next month.`,
      countdown: daysLeft(daysUntil(asOf, reviewBy)),
      extra: later,
    }
  }
  if (asOf <= reportDay) {
    return {
      title: `Final report ${reportLabel}`,
      detail: `The report goes to the Global HR admin and each country HR admin. Final closure is ${closureLabel}.`,
      countdown: daysLeft(daysUntil(asOf, reportDay)),
      extra: later,
    }
  }
  if (asOf <= closure) {
    return {
      title: `Final closure ${closureLabel}`,
      detail: `Close missing details and approvals by ${closureLabel}. Changes after this date apply next month.`,
      countdown: daysLeft(daysUntil(asOf, closure)),
      extra: later,
    }
  }
  if (submitted && asOf < submitted) {
    return {
      title: `Payroll submitted ${submittedLabel}`,
      detail: `Inputs are closed. Payroll is submitted on ${submittedLabel}.`,
      countdown: daysLeft(daysUntil(asOf, submitted)),
      extra: `Pay day ${payLabel}`,
    }
  }
  if (asOf < pay) {
    return {
      title: `Pay day ${payLabel}`,
      detail: submittedLabel ? `Payroll submitted ${submittedLabel}.` : 'Payroll has been submitted.',
      countdown: daysLeft(daysUntil(asOf, pay)),
      extra: '',
    }
  }
  return {
    title: `Pay day ${payLabel}`,
    detail: submittedLabel ? `Payroll submitted ${submittedLabel}.` : 'Payroll has been submitted.',
    countdown: asOf === pay ? 'Today' : 'Paid',
    extra: '',
  }
}

function SyncSummary({
  country,
  openActions,
  needApproval,
  matched,
  willMiss,
  wrongPay,
}: {
  country: string | null
  openActions: number
  needApproval: number
  matched: number
  willMiss: number
  wrongPay: number
}) {
  const overview = useAppStore((s) => s.overview)
  const asOf = useAppStore((s) => s.asOf)
  const cycle = overview?.cycle
  if (!overview || !cycle) return null
  const readiness = overview.readiness
  const outcomes = overview.payOutcomes
  const countryPay = country ? outcomes?.byCountry?.[country] : undefined
  const variance = overview.fundingVariance
  const estimate = overview.fundingEstimate
  const reminder = overview.changesReminder
  const pay = overview.dates?.payDate || cycle.payDate
  const submitted = overview.dates?.submitted || cycle.submitted || null
  const focus = cycleFocus(asOf, pay, submitted)
  const actionsHref = country ? '/payroll/actions' : overview.statusLine.href || overview.statusLine.actionsHref || '/payroll/actions'
  const shownActions = country ? openActions : overview.statusLine.openActions
  const shownApproval = country ? needApproval : (readiness?.needApproval ?? 0)
  const shownMatched = country ? matched : (readiness?.matched ?? 0)

  return (
    <section className="rounded border border-border bg-surface text-[13px]" data-testid="sync-summary">
      <div
        className={[
          'flex items-start justify-between gap-3 border-b px-4 py-2',
          willMiss > 0 || wrongPay > 0 ? 'border-status-warn-border bg-status-warn-bg' : 'border-border bg-canvas',
        ].join(' ')}
      >
        <div className="min-w-0">
          <p className="text-[13px] font-medium text-text-primary">
            {country ? `${country} · ` : ''}
            {focus.title}
          </p>
          <p className="mt-0.5 text-[12px] leading-snug text-text-secondary">{focus.detail}</p>
          {focus.extra ? (
            <p className="mt-0.5 text-[12px] leading-snug text-text-secondary">{focus.extra}</p>
          ) : null}
          {willMiss > 0 ? (
            <button
              type="button"
              className="mt-1 block text-[13px] font-semibold text-text-primary hover:underline"
              onClick={() =>
                document.getElementById('countries')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
              }
            >
              {willMiss} will miss payment
            </button>
          ) : null}
          {wrongPay > 0 ? (
            <button
              type="button"
              className="mt-1 block text-[13px] font-semibold text-text-primary hover:underline"
              onClick={() =>
                document.getElementById('countries')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
              }
            >
              {wrongPay} will not get the right payment
            </button>
          ) : null}
        </div>
        {focus.countdown ? (
          <span className="shrink-0 tabular text-xs text-text-secondary">{focus.countdown}</span>
        ) : null}
      </div>

      {readiness || country ? (
        <div className="flex flex-wrap items-center gap-1.5 px-4 py-3">
          {shownActions > 0 ? (
            <Link to={actionsHref}>
              <StatusChip tone="danger">
                {shownActions} {shownActions === 1 ? 'action needs you' : 'actions need you'}
              </StatusChip>
            </Link>
          ) : (
            <StatusChip tone="ok">No issues</StatusChip>
          )}
          {shownApproval > 0 ? (
            <Link to="/payroll/review">
              <StatusChip tone="warn">
                {shownApproval} need approval
              </StatusChip>
            </Link>
          ) : (
            <StatusChip tone="ok">No approvals pending</StatusChip>
          )}
          <StatusChip tone="ok">{shownMatched} matched</StatusChip>
        </div>
      ) : null}

      {reminder ? (
        <div className="flex flex-wrap gap-2 border-t border-border px-4 py-3">
          {reminder.actions.map((action) => (
            <Link
              key={action.href}
              to={action.href}
              className="inline-flex h-8 items-center justify-center rounded border border-border bg-surface px-3 text-xs font-medium text-text-primary hover:bg-surface-recessed"
            >
              {action.label}
            </Link>
          ))}
        </div>
      ) : null}

      {overview.recentChanges && overview.recentChanges.length > 0 ? (
        <ul className="border-t border-border px-4 py-3 text-text-secondary">
          {overview.recentChanges.map((row, i) => (
            <li key={`${row.at}-${i}`}>
              {row.summary}
              {row.cycleAssignment === 'next' ? ' · Next cycle' : ''}
            </li>
          ))}
        </ul>
      ) : null}
      {estimate && variance ? (
        <p className="border-t border-border px-4 py-3 text-text-secondary">
          Funding variance {variance.currency} {variance.total} (forex {variance.forex}, rates{' '}
          {variance.employerRates}, other {variance.other}). {estimate.note}
        </p>
      ) : null}
      {countryPay ? (
        <p className="border-t border-border px-4 py-3 text-text-secondary">
          Simulated pay: {countryPay.paid} of {countryPay.of} paid ·{' '}
          <OutcomeFix
            count={countryPay.paidPreviousSalary.count}
            label="not the right payment"
            href={countryPay.paidPreviousSalary.href}
          />{' '}
          ·{' '}
          <OutcomeFix
            count={countryPay.missingInputs.count}
            label="missing inputs"
            href={countryPay.missingInputs.href}
          />{' '}
          · {countryPay.addedAfterCutoff.count} added after cutoff · {countryPay.paymentReturned.count} returned
        </p>
      ) : outcomes ? (
        <p className="border-t border-border px-4 py-3 text-text-secondary">
          Simulated pay: {outcomes.paidSuccessfully.count} of {outcomes.paidSuccessfully.of} paid ·{' '}
          <OutcomeFix
            count={outcomes.paidPreviousSalary.count}
            label="not the right payment"
            href={outcomes.paidPreviousSalary.href}
          />{' '}
          ·{' '}
          <OutcomeFix
            count={outcomes.missingInputs.count}
            label="missing inputs"
            href={outcomes.missingInputs.href}
          />{' '}
          · {outcomes.addedAfterCutoff.count} added after cutoff · {outcomes.paymentReturned.count} returned
        </p>
      ) : null}
    </section>
  )
}

function countrySummary<T extends { month?: string; tone?: string; byCountry?: Record<string, CountryPaySlice> }>(
  summary: T | null | undefined,
  country: string | null,
): (T & CountryPaySlice) | null {
  if (!summary?.month) return null
  if (!country) return summary as T & CountryPaySlice
  const slice = summary.byCountry?.[country]
  if (!slice) return null
  const missed =
    (slice.paidPreviousSalary?.count ?? 0) +
    (slice.missingInputs?.count ?? 0) +
    (slice.addedAfterCutoff?.count ?? 0) +
    (slice.paymentReturned?.count ?? 0)
  return { ...summary, ...slice, tone: missed ? 'warn' : 'ok' }
}

function PayrollResultLine({
  summary,
  country,
}: {
  summary: {
    month?: string
    payDateLabel?: string
    paid?: number
    of?: number
    paidPreviousSalary?: { count: number; href?: string | null }
    missingInputs?: { count: number; href?: string | null }
    addedAfterCutoff?: { count: number; href?: string | null }
    paymentReturned?: { count: number; href?: string | null }
    added?: { count: number; href?: string | null }
    left?: { count: number; href?: string | null }
  }
  country: string | null
}) {
  return (
    <p className="text-[13px] text-text-primary">
      <span className="font-semibold">
        {country ? `${country} · ` : ''}
        {summary.month} payroll
      </span>
      <span>
        {' '}
        · paid {summary.payDateLabel} · {summary.paid} of {summary.of} received pay ·{' '}
      </span>
      <OutcomeFix
        count={summary.paidPreviousSalary?.count ?? 0}
        label="not the right payment"
        href={summary.paidPreviousSalary?.href}
      />
      <span> · </span>
      <OutcomeFix
        count={summary.missingInputs?.count ?? 0}
        label="missing inputs"
        href={summary.missingInputs?.href}
      />
      <span> · </span>
      <OutcomeFix
        count={summary.addedAfterCutoff?.count ?? 0}
        label="added after cutoff"
        href={summary.addedAfterCutoff?.href}
      />
      <span> · </span>
      <OutcomeFix
        count={summary.paymentReturned?.count ?? 0}
        label="returned"
        href={summary.paymentReturned?.href}
      />
      <span> · </span>
      <OutcomeFix
        count={summary.added?.count ?? 0}
        label={(summary.added?.count ?? 0) === 1 ? 'new addition' : 'new additions'}
        href={summary.added?.href}
      />
      <span> · </span>
      <OutcomeFix
        count={summary.left?.count ?? 0}
        label={(summary.left?.count ?? 0) === 1 ? 'person left' : 'people left'}
        href={summary.left?.href}
      />
    </p>
  )
}

function OutcomeFix({ count, label, href }: { count: number; label: string; href?: string | null }) {
  const text = `${count} ${label}`
  if (!href || count === 0) return <span>{text}</span>
  return (
    <Link
      to={href}
      className="font-medium text-sky-800 underline decoration-sky-800/40 underline-offset-2"
    >
      {text}
    </Link>
  )
}

function renderStatusMessage(message: string) {
  const parts = message.split(/(\*\*[^*]+\*\*)/g)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <span key={i} className="font-semibold text-text-primary">
          {part.slice(2, -2)}
        </span>
      )
    }
    return (
      <span key={i} className="text-text-secondary">
        {part}
      </span>
    )
  })
}

export function OverviewPage() {
  const overview = useAppStore((s) => s.overview)
  const asOf = useAppStore((s) => s.asOf)
  const persona = useAppStore((s) => s.persona)
  const setPersona = useAppStore((s) => s.setPersona)
  const company = useAppStore((s) => s.company)
  const issues = useAppStore((s) => s.issues)
  const employees = useAppStore((s) => s.employees)
  const review = useAppStore((s) => s.review)
  const navigate = useNavigate()
  const [mailAdmin, setMailAdmin] = useState<CountryAdmin | null>(null)
  const admins = countryAdmins(company)
  const scopedCountry = personaCountry(persona, company)

  if (!overview) {
    return (
      <EmptyState
        title="Overview not loaded"
        description="Clarity API cache is empty. Retry from the boot screen or refresh."
      />
    )
  }

  const {
    statusLine,
    cycle,
    countries,
    reviewMeta,
    dates,
    octoberSummary,
    previousPayrolls,
  } = overview
  const visibleCountries = scopedCountry
    ? countries.filter((row) => row.country === scopedCountry)
    : countries
  const totalEmployees = visibleCountries.reduce((sum, c) => sum + c.employeeCount, 0)

  function countryMiss(country: string) {
    const open = issues.filter(
      (issue) =>
        issue.status !== 'resolved' &&
        issue.country === country &&
        (issue.kind === 'missing_fields' || issue.kind === 'missing_data' || !issue.kind),
    )
    const pending = (review?.lines || []).filter(
      (line) => !line.approved && !line.rejected && line.country === country,
    )
    const miss = new Set<string>()
    const wrong = new Set<string>()
    for (const issue of open) if (issue.employeeId) miss.add(issue.employeeId)
    for (const line of pending) if (line.employeeId) wrong.add(line.employeeId)
    return { people: miss.size, wrong: wrong.size, actions: open.length, approvals: pending.length }
  }

  const willMiss = visibleCountries.reduce((sum, row) => sum + countryMiss(row.country).people, 0)
  const wrongPay = visibleCountries.reduce((sum, row) => sum + countryMiss(row.country).wrong, 0)
  const scopedActions = scopedCountry
    ? issues.filter((issue) => issue.status === 'open' && issue.country === scopedCountry).length
    : statusLine.openActions
  const scopedCards = review ? reviewCards(review, employees, scopedCountry) : null
  const scopedApprovals = scopedCountry
    ? (review?.lines || []).filter((line) => !line.approved && !line.rejected && line.country === scopedCountry).length
    : (review?.badgeCount ?? 0)
  const financeName = company?.financeAdmin?.name || 'Finance'
  const cycleSummary = countrySummary(octoberSummary, scopedCountry)
  const earlierPayrolls = (previousPayrolls || [])
    .map((row) => countrySummary(row, scopedCountry))
    .filter((row): row is NonNullable<typeof row> => Boolean(row?.month))
  const reportOn = formatIsoDate(cycleDay(dates?.payDate || cycle.payDate, 20))

  function openCountryView(code: PersonaId, path: string) {
    if (code !== 'global') setPersona(code)
    navigate(path)
  }
  const n = statusLine.openActions
  const kind = statusLine.kind || 'actions'
  const toneDanger = kind === 'actions' && n > 0
  const toneOk = kind === 'signed' || kind === 'approved' || (kind === 'actions' && n === 0)
  const href = statusLine.href || statusLine.actionsHref || '/payroll/actions'
  const stageDates = {
    cutoff: dates?.cutoff || cycle.inputFinalisation,
    calculation:
      dates?.calculation || cycle.calculation || reviewMeta?.calculationDate || cycle.inputFinalisation,
    finalSync: dates?.finalSync || dates?.calculation || cycle.calculation,
    reviewOpen: dates?.reviewOpen || cycle.reviewOpen || reviewMeta?.reviewOpen || cycle.approval,
    reviewClose: dates?.reviewClose || cycle.reviewClose || reviewMeta?.reviewClose || cycle.approval,
    funding: dates?.fundingDue || cycle.fundingDue,
    submitted: dates?.submitted || cycle.submitted,
    pay: dates?.payDate || cycle.payDate,
  }

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Overview"
        subtitle={scopedCountry || 'What’s due before the next deadline'}
      />

      <SyncSummary
        country={scopedCountry}
        openActions={scopedActions}
        needApproval={scopedApprovals}
        matched={scopedCards?.matched ?? 0}
        willMiss={willMiss}
        wrongPay={wrongPay}
      />

      {cycleSummary?.month ? (
        <div
          className={[
            'rounded border px-4 py-3',
            cycleSummary.tone === 'ok'
              ? 'border-status-ok-border bg-status-ok-bg'
              : 'border-status-warn-border bg-status-warn-bg',
          ].join(' ')}
          data-testid="previous-cycle-summary"
        >
          <PayrollResultLine summary={cycleSummary} country={scopedCountry} />
        </div>
      ) : null}

      {scopedCountry || kind === 'actions' ? null : (
        <section
          className={[
            'rounded border px-4 py-3',
            toneDanger
              ? 'border-status-danger-border bg-status-danger-bg'
              : toneOk
                ? 'border-status-ok-border bg-status-ok-bg'
                : 'border-status-info-border bg-status-info-bg',
          ].join(' ')}
        >
          <Link to={href} className="block text-[13px] hover:underline">
            {statusLine.message ? (
              renderStatusMessage(statusLine.message)
            ) : (
              <span className="text-text-secondary">{statusLine.countdown}</span>
            )}
          </Link>
        </section>
      )}

      <StageTracker
        asOf={asOf}
        openActions={n}
        payOutcomes={overview.payOutcomes}
        signedOff={
          reviewMeta?.cycleKey === 'november'
            ? false
            : statusLine.signedOff || cycle.approved
        }
        signedOn={null}
        needsCheck={reviewMeta?.needsCheck}
        closedWithoutSignOff={reviewMeta?.closedWithoutSignOff}
        unappliedCount={reviewMeta?.unappliedCount}
        dates={stageDates}
        willMiss={willMiss}
        financeName={financeName}
        fundsAddedOn={overview.fundsAddedOn}
      />

      {scopedCountry ? null : (
      <section id="countries" className="scroll-mt-4 rounded border border-border bg-surface">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-text-primary">Countries</h2>
          <p className="text-xs text-text-secondary">
            {overview.customer.name} · {totalEmployees} employees · {visibleCountries.length}{' '}
            {visibleCountries.length === 1 ? 'country' : 'countries'}
            {scopedCountry ? ` · ${scopedCountry} only` : ''} · Final report {reportOn}
          </p>
        </div>
        <div className="divide-y divide-border">
          {visibleCountries.map((row) => {
            const report = countryMiss(row.country)
            const code = (row.code || countryCode(row.country)) as PersonaId
            const admin = admins.find((item) => item.country === row.country)
            const onTrack = report.people === 0 && report.wrong === 0
            return (
              <div
                key={row.country}
                data-testid={`country-${row.country}`}
                className="flex items-start justify-between gap-3 px-4 py-3"
              >
                <div className="flex min-w-0 items-start gap-2.5">
                  <span className="mt-0.5 flex h-6 w-6 items-center justify-center rounded bg-surface-recessed text-[11px] font-semibold text-text-primary">
                    {row.code || countryCode(row.country)}
                  </span>
                  <div className="min-w-0">
                    <p className="text-[13px] font-medium text-text-primary">
                      {row.country} · {row.employeeCount} employees
                    </p>
                    <p className="mt-0.5 text-xs text-text-secondary">
                      {onTrack ? 'Payroll is on track.' : null}
                      {report.people > 0 ? `${report.people} will miss payment.` : null}
                      {report.people > 0 && report.wrong > 0 ? ' ' : null}
                      {report.wrong > 0 ? `${report.wrong} will not get the right payment.` : null}
                      {report.actions > 0 ? (
                        <>
                          {' '}
                          <button
                            type="button"
                            className="font-medium text-sky-800 underline"
                            onClick={() => openCountryView(code, `/payroll/actions?country=${code}`)}
                          >
                            {report.actions} action needed
                          </button>
                        </>
                      ) : null}
                      {report.approvals > 0 ? (
                        <>
                          {' '}
                          ·{' '}
                          <button
                            type="button"
                            className="font-medium text-sky-800 underline"
                            onClick={() => openCountryView(code, `/payroll/review?country=${code}`)}
                          >
                            {report.approvals} approval pending
                          </button>
                        </>
                      ) : null}
                    </p>
                    {admin ? (
                      <p className="mt-0.5 text-xs text-text-secondary">
                        HR admin {admin.name}
                        {persona === 'global' ? (
                          <>
                            {' '}
                            ·{' '}
                            <button
                              type="button"
                              className="font-medium text-sky-800 underline"
                              onClick={() => setMailAdmin(admin)}
                            >
                              Write mail
                            </button>
                          </>
                        ) : null}
                      </p>
                    ) : null}
                  </div>
                </div>
                <StatusChip tone={onTrack ? 'ok' : 'warn'}>
                  {onTrack ? 'On track' : 'At risk'}
                </StatusChip>
              </div>
            )
          })}
        </div>
      </section>
      )}
      {mailAdmin ? <QueryMail admin={mailAdmin} onClose={() => setMailAdmin(null)} /> : null}

      {earlierPayrolls.length ? (
        <section className="rounded border border-border bg-surface" data-testid="previous-payrolls">
          <div className="border-b border-border px-4 py-3">
            <h2 className="text-sm font-semibold text-text-primary">Previous payrolls</h2>
            <p className="text-xs text-text-secondary">Closed payrolls from earlier months</p>
          </div>
          <div className="divide-y divide-border">
            {earlierPayrolls.map((row) => (
              <div key={row.month} className="px-4 py-3">
                <PayrollResultLine summary={row} country={scopedCountry} />
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  )
}
