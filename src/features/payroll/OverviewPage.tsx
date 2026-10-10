import { Link } from 'react-router-dom'
import { EmptyState, PageHeader, StatusChip } from '@/components'
import { ChangesReminder } from '@/features/payroll/ChangesReminder'
import { StageTracker } from '@/features/payroll/components/StageTracker'
import { countryCode, countryStatusTone, formatIsoDate } from '@/features/payroll/lib/labels'
import { useAppStore } from '@/store'
import type { UpNextItem } from '@/api/types'

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

function UpNextRow({ item }: { item: UpNextItem }) {
  if (item.kind === 'milestone') {
    const end = (item as { deadlineEnd?: string }).deadlineEnd
    const dateLabel = end
      ? `${formatIsoDate(item.deadline)}–${formatIsoDate(end).replace(/^[A-Za-z]+ /, '')}`
      : formatIsoDate(item.deadline)
    const inner = (
      <div className="flex items-center justify-between gap-3 border-b border-border px-3 py-2.5 last:border-b-0">
        <div className="min-w-0">
          <p className="text-[13px] font-medium text-text-primary">
            {dateLabel} · {item.title}
          </p>
          <p className="text-xs text-text-secondary">{item.detail}</p>
        </div>
        {item.viewOnly ? (
          <StatusChip tone="neutral">View only</StatusChip>
        ) : item.href ? (
          <span className="text-xs font-medium text-status-info-text">Open →</span>
        ) : null}
      </div>
    )
    if (item.href && !item.viewOnly) {
      return (
        <Link to={item.href} className="block hover:bg-surface-recessed">
          {inner}
        </Link>
      )
    }
    return inner
  }

  if (item.kind === 'reminder') {
    return (
      <div className="flex items-center justify-between gap-3 border-b border-border px-3 py-2.5 last:border-b-0">
        <div className="min-w-0">
          <p className="text-[13px] font-medium text-text-primary">{item.title}</p>
          <p className="text-xs text-text-secondary">
            {item.owner ?? 'Reminder'} · {formatIsoDate(item.deadline)}
          </p>
        </div>
        <StatusChip tone="neutral">Reminder</StatusChip>
      </div>
    )
  }

  return (
    <Link
      to={`/payroll/actions?issue=${item.issueId}`}
      className="flex items-center justify-between gap-3 border-b border-border px-3 py-2.5 last:border-b-0 hover:bg-surface-recessed"
    >
      <div className="min-w-0">
        <p className="text-[13px] font-medium text-text-primary">{item.title}</p>
        <p className="text-xs text-text-secondary">
          {item.who} · due {formatIsoDate(item.deadline)}
        </p>
      </div>
      <span className="text-xs font-medium text-status-info-text">Take action →</span>
    </Link>
  )
}

export function OverviewPage() {
  const overview = useAppStore((s) => s.overview)
  const asOf = useAppStore((s) => s.asOf)

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
    upNext,
    changesReminder,
    outcome,
    funding,
    submitted,
    reviewMeta,
    dates,
    octoberSummary,
  } = overview
  const totalEmployees = countries.reduce((sum, c) => sum + c.employeeCount, 0)
  const n = statusLine.openActions
  const kind = statusLine.kind || 'actions'
  const toneDanger = kind === 'actions' && n > 0
  const toneOk = kind === 'signed' || kind === 'approved' || (kind === 'actions' && n === 0)
  const href = statusLine.href || statusLine.actionsHref || '/payroll/actions'
  const stageDates = {
    cutoff: dates?.cutoff || cycle.inputFinalisation,
    calculation:
      dates?.calculation || cycle.calculation || reviewMeta?.calculationDate || cycle.inputFinalisation,
    reviewOpen: dates?.reviewOpen || cycle.reviewOpen || reviewMeta?.reviewOpen || cycle.approval,
    reviewClose: dates?.reviewClose || cycle.reviewClose || reviewMeta?.reviewClose || cycle.approval,
    funding: dates?.fundingDue || cycle.fundingDue,
    submitted: dates?.submitted || cycle.submitted,
    pay: dates?.payDate || cycle.payDate,
  }

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Overview" subtitle="What’s due before the next deadline" />

      <ChangesReminder reminder={changesReminder} />

      {octoberSummary ? (
        <Link
          to={octoberSummary.href || '/payroll/review?cycle=october'}
          className={[
            'block rounded border px-4 py-3 text-[13px] hover:opacity-90',
            octoberSummary.tone === 'ok'
              ? 'border-status-ok-border bg-status-ok-bg text-status-ok-text'
              : 'border-status-warn-border bg-status-warn-bg text-status-warn-text',
          ].join(' ')}
        >
          {renderStatusMessage(octoberSummary.message)}{' '}
          <span className="font-medium underline">
            {octoberSummary.linkLabel || 'View October summary'}
          </span>
        </Link>
      ) : null}

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
          {statusLine.message
            ? renderStatusMessage(statusLine.message)
            : (
              <>
                <span className="font-semibold text-text-primary">
                  {n} {n === 1 ? 'action needs you' : 'actions need you'}
                </span>{' '}
                <span className="text-text-secondary">
                  before input finalisation on {formatIsoDate(cycle.inputFinalisation)}
                </span>
                <span className="text-text-muted"> · {statusLine.countdown}</span>
              </>
            )}
        </Link>
      </section>

      <StageTracker
        asOf={asOf}
        openActions={n}
        outcome={outcome}
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
      />

      <section className="rounded border border-border bg-surface">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-text-primary">Countries</h2>
          <p className="text-xs text-text-secondary">
            {overview.customer.name} · {totalEmployees} employees · {countries.length} countries
          </p>
        </div>
        <div className="divide-y divide-border">
          {countries.map((row) => {
            const needs = row.actionNeededCount ?? 0
            const code = row.code || countryCode(row.country)
            return (
              <div
                key={row.country}
                data-testid={`country-${row.country}`}
                className="flex items-center justify-between gap-3 px-4 py-2.5"
              >
                <div className="flex min-w-0 items-center gap-2.5">
                  <span className="flex h-6 w-6 items-center justify-center rounded bg-surface-recessed text-[11px] font-semibold text-text-primary">
                    {code}
                  </span>
                  <div className="min-w-0">
                    <p className="text-[13px] font-medium text-text-primary">
                      {row.country} · {row.employeeCount} employees
                      {needs > 0 ? (
                        <>
                          {' '}
                          ·{' '}
                          <span className="font-semibold text-status-danger-text">
                            {needs} need{needs === 1 ? 's' : ''} action
                          </span>
                        </>
                      ) : null}
                    </p>
                  </div>
                </div>
                {needs > 0 && row.href ? (
                  <Link
                    to={row.href}
                    className="shrink-0 text-xs font-medium text-status-info-text hover:underline"
                  >
                    Take action →
                  </Link>
                ) : (
                  <StatusChip tone={countryStatusTone(row.status)}>On track</StatusChip>
                )}
              </div>
            )
          })}
        </div>
      </section>

      <section className="rounded border border-border bg-surface">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-text-primary">Up next</h2>
          <p className="text-xs text-text-secondary">Upcoming deadlines, ordered by date</p>
        </div>
        <div>
          {upNext.length === 0 ? (
            <div className="px-4 py-8 text-center text-xs text-text-secondary">
              Nothing queued – payroll is on track
            </div>
          ) : (
            upNext.map((item, index) => (
              <UpNextRow
                key={
                  item.kind === 'milestone'
                    ? `${item.title}-${item.deadline}`
                    : item.kind === 'issue'
                      ? item.issueId
                      : `${item.title}-${item.deadline}-${index}`
                }
                item={item}
              />
            ))
          )}
        </div>
      </section>

      {!octoberSummary && funding ? (
        <section className="rounded border border-border bg-surface px-4 py-3">
          <p className="text-[13px] font-semibold text-text-primary">
            Funds received from finance ✓
          </p>
          <p className="mt-1 text-xs text-text-secondary">
            Received {formatIsoDate(funding.receivedOn)}
            {funding.countries?.length
              ? ` · ${funding.countries.map((c) => c.country).join(', ')}`
              : ''}
          </p>
        </section>
      ) : null}

      {!octoberSummary && submitted ? (
        <section className="rounded border border-border bg-surface px-4 py-3">
          <p className="text-[13px] font-semibold text-text-primary">{submitted.message}</p>
        </section>
      ) : null}

      {!octoberSummary && outcome ? (
        <section className="rounded border border-border bg-surface px-4 py-3">
          <p className="text-[13px] font-semibold text-text-primary">Pay date outcome</p>
          <div className="mt-2 grid grid-cols-3 gap-3">
            <Link to={outcome.paidOnTime.href} className="rounded border border-border px-3 py-2">
              <p className="text-[11px] uppercase tracking-wide text-text-muted">Paid on time</p>
              <p className="mt-1 text-lg font-semibold tabular text-text-primary">
                {outcome.paidOnTime.count} of {outcome.inRun ?? outcome.total}
              </p>
            </Link>
            <div className="rounded border border-border px-3 py-2">
              <p className="text-[11px] uppercase tracking-wide text-text-muted">Moved to next cycle</p>
              <p className="mt-1 text-lg font-semibold tabular text-text-primary">
                {outcome.movedToNovember.count}
              </p>
              <p className="mt-1 text-[11px] text-text-secondary">
                {outcome.movedToNovember.employees
                  .slice(0, 4)
                  .map((e) => `${e.name}${e.reason ? ` (${e.reason})` : ''}`)
                  .join('; ') || '—'}
              </p>
            </div>
            <div className="rounded border border-status-danger-border bg-status-danger-bg px-3 py-2">
              <p className="text-[11px] uppercase tracking-wide text-status-danger-text">
                Still at risk
              </p>
              <p className="mt-1 text-lg font-semibold tabular text-status-danger-text">
                {outcome.stillAtRisk.count}
              </p>
              <p className="mt-1 text-[11px] text-status-danger-text">
                {outcome.stillAtRisk.message}
              </p>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  )
}
