import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Check } from 'lucide-react'
import { Button, EmptyState, PageHeader } from '@/components'
import { formatIsoDate } from '@/features/payroll/lib/labels'
import { personaCountry } from '@/features/persona'
import { reviewCards } from '@/features/payroll/lib/scope'
import { useAppStore } from '@/store'
import type { ReviewLineDto, ReviewResponse } from '@/api/types'

function countryCarry(
  review: ReviewResponse | null,
  country: string | null,
  employees: { id: string; country: string }[],
): ReviewResponse['ifUnapproved'] {
  const block = review?.ifUnapproved
  if (!block) return null
  if (!country) return block
  const ids = new Set(employees.filter((emp) => emp.country === country).map((emp) => emp.id))
  const items = block.items.filter((item) => ids.has(item.employeeId))
  if (!items.length) return null
  return { ...block, items }
}

function countryNotInRun(review: ReviewResponse | null, country: string | null) {
  const block = review?.notInRun
  if (!block || block.count === 0) return null
  if (!country) return block
  const held = block.employees.filter((emp) => emp.country === country)
  if (!held.length) return null
  const rest = block.message.split('. ').slice(1).join('. ')
  const lead = `${held.length} employee${held.length === 1 ? ' is' : 's are'} not in this run because data is missing.`
  return {
    ...block,
    count: held.length,
    employees: held,
    message: rest ? `${lead} ${rest}` : lead,
  }
}

function isRecovery(line: ReviewLineDto): boolean {
  if (line.requiresEmployeeNotified) return true
  return /recovery|deductible/i.test(`${line.changeSummary} ${line.whyFlagged}`)
}

function CarryNotice({ block }: { block: ReviewResponse['ifUnapproved'] }) {
  if (!block?.headline || block.items.length === 0) return null
  return (
    <div
      data-testid="carry-notice"
      className="rounded border border-status-warn-border bg-status-warn-bg px-4 py-3 text-[13px] text-status-warn-text"
    >
      <p className="font-medium">{block.headline}</p>
      {block.items.length ? (
        <ul className="mt-2 space-y-1">
          {block.items.map((item) => (
            <li key={`${item.employeeId}-${item.kind}`} data-testid={`carry-${item.employeeId}`}>
              <span className="font-medium">{item.name}</span>
              {' — '}
              {item.note}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

function RowActions({
  line,
  muted,
  nextLabel,
  onApprove,
  onUndo,
}: {
  line: ReviewLineDto
  muted: boolean
  nextLabel: string
  onApprove: () => void
  onUndo: () => void
}) {
  return (
    <div className="flex h-8 items-center justify-end gap-2 whitespace-nowrap">
      {line.approved ? (
        <>
          <span className="inline-flex h-8 items-center rounded border border-emerald-200 bg-emerald-50 px-3 text-sm font-medium text-emerald-800">
            Approved ✓
          </span>
          {!muted ? (
            <button
              type="button"
              className="h-8 px-3 text-sm text-slate-700 hover:underline"
              onClick={onUndo}
            >
              Undo
            </button>
          ) : null}
        </>
      ) : muted ? (
        <span className="inline-flex h-8 items-center rounded border border-slate-200 bg-slate-50 px-2 text-[11px] font-medium text-slate-500">
          Moved · {nextLabel}
        </span>
      ) : (
        <button
          type="button"
          className="inline-flex h-8 items-center gap-1.5 rounded border border-slate-300 bg-white px-3 text-sm font-medium text-slate-800 hover:bg-slate-50"
          onClick={onApprove}
        >
          <Check size={14} strokeWidth={2.5} />
          Approve
        </button>
      )}
      {line.employeeId ? (
        <Link
          to={line.openHref || `/people/${line.employeeId}?panel=salary`}
          className="inline-flex h-8 items-center px-3 text-sm text-slate-700 hover:underline"
        >
          View employee
        </Link>
      ) : null}
    </div>
  )
}

export function ReviewPage() {
  const asOf = useAppStore((s) => s.asOf)
  const review = useAppStore((s) => s.review)
  const employees = useAppStore((s) => s.employees)
  const overview = useAppStore((s) => s.overview)
  const company = useAppStore((s) => s.company)
  const persona = useAppStore((s) => s.persona)
  const [params, setParams] = useSearchParams()
  const lockedCountry = personaCountry(persona, company)
  const countryParam = persona === 'global' ? params.get('country') || '' : persona
  const countryName =
    lockedCountry ||
    ({ IN: 'India', UK: 'UK', DE: 'Germany', BR: 'Brazil' } as Record<string, string>)[countryParam] ||
    ''
  const cards = review ? reviewCards(review, employees, countryName || null) : null
  const reviewLines = cards?.lines || []
  const carry = countryCarry(review, countryName || null, employees)
  const heldOut = countryNotInRun(review, countryName || null)
  const refreshReview = useAppStore((s) => s.refreshReview)
  const approveLine = useAppStore((s) => s.approveLine)
  const unapproveLine = useAppStore((s) => s.unapproveLine)
  const signOff = useAppStore((s) => s.signOff)
  const askConfirm = useAppStore((s) => s.askConfirm)
  const setConfirmError = useAppStore((s) => s.setConfirmError)
  const setConfirmBusy = useAppStore((s) => s.setConfirmBusy)
  const cancelConfirm = useAppStore((s) => s.cancelConfirm)
  const pushToast = useAppStore((s) => s.pushToast)
  const [footerMsg, setFooterMsg] = useState<string | null>(null)

  useEffect(() => {
    void refreshReview()
  }, [asOf, refreshReview])

  useEffect(() => {
    if (review?.signedOff && review.signoff) {
      const month = overview?.cycle.label || 'Payroll'
      setFooterMsg(
        `${month} approved by ${review.signoff.signedBy} · ${formatIsoDate(review.signoff.signedOn)}${
          review.signoff.signedAt ? `, ${review.signoff.signedAt}` : ''
        } · funding request sent to finance`,
      )
    } else {
      setFooterMsg(null)
    }
  }, [review, overview?.cycle.label])

  const approvedCount = cards?.approved ?? 0
  const totalLines = reviewLines.length
  const remaining = Math.max(0, totalLines - approvedCount)
  const progress = totalLines ? Math.round((approvedCount / totalLines) * 100) : 0
  const cycleMonth = (overview?.cycle.label || 'Payroll').replace(/\s*\d{4}\s*/, '').trim() || 'Payroll'
  const employeesInRun = countryName
    ? (overview?.countries.find((row) => row.country === countryName)?.employeeCount ?? 0)
    : (overview?.cycle.employeeCount ??
      overview?.countries.reduce((sum, row) => sum + row.employeeCount, 0) ??
      0)

  if (!review) {
    return (
      <EmptyState
        title="Loading review…"
        description="Fetching changed / matched / needs-check lines from Clarity API."
      />
    )
  }

  const windowState = review.windowState || (review.available ? 'open' : 'before')
  const readOnly = review.readOnly || windowState !== 'open'
  const muted = windowState === 'closed'
  const nextLabel = review.nextReviewLabel || 'next cycle'
  const adminName = company?.admin?.name || 'Maya Rao'

  if (windowState === 'before') {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Review & approve" subtitle={review.header ?? 'Review opens soon'} />
        <p className="rounded border border-border bg-surface-recessed px-4 py-3 text-[13px] text-text-secondary">
          <strong className="text-text-primary">{review.header}.</strong> Multiplier calculates pay
          after inputs lock, so you&apos;ll review final numbers. Until then, fix open items in{' '}
          <Link to="/payroll/actions" className="font-medium text-status-info-text hover:underline">
            Action needed →
          </Link>
        </p>
        <CarryNotice block={carry} />
      </div>
    )
  }

  function openApproveLine(line: ReviewLineDto) {
    const recovery = isRecovery(line)
    const llm = line.llmDecision
    const llmNote = llm
      ? `\n\nLLM: ${llm.recommend === 'approve' ? 'Approve' : 'Hold'} (${Math.round((llm.confidence || 0) * 100)}%) — ${llm.reason}`
      : ''
    askConfirm({
      title: llm?.recommend === 'hold' ? 'Approve against LLM hold?' : 'Approve line',
      body: `Approve ${line.employeeName}'s change (${line.changeSummary})?${llmNote}`,
      requireCheckbox: recovery
        ? { label: 'Employee notified' }
        : undefined,
      confirmLabel: 'Confirm',
      onConfirm: async () => {
        setConfirmBusy(true)
        setConfirmError(null)
        try {
          await approveLine(line.id)
          cancelConfirm()
          pushToast(`Approved ${line.employeeName} · ${line.changeSummary}`)
        } catch (err) {
          setConfirmError(err instanceof Error ? err.message : 'Could not approve line')
        } finally {
          setConfirmBusy(false)
        }
      },
    })
  }

  function applyLlmApproves() {
    const targets = reviewLines.filter((l) => !l.approved && l.llmDecision?.recommend === 'approve')
    if (!targets.length) {
      pushToast('LLM did not recommend any lines to approve')
      return
    }
    askConfirm({
      title: 'Apply LLM approvals',
      body: `Approve ${targets.length} line${targets.length === 1 ? '' : 's'} the LLM recommended?\n\n${targets
        .map((l) => `• ${l.employeeName}: ${l.changeSummary}`)
        .join('\n')}`,
      confirmLabel: 'Approve LLM picks',
      onConfirm: async () => {
        setConfirmBusy(true)
        setConfirmError(null)
        try {
          for (const line of targets) {
            await approveLine(line.id)
          }
          cancelConfirm()
          pushToast(`Approved ${targets.length} line${targets.length === 1 ? '' : 's'} via LLM`)
        } catch (err) {
          setConfirmError(err instanceof Error ? err.message : 'Could not apply LLM approvals')
        } finally {
          setConfirmBusy(false)
        }
      },
    })
  }

  function openApprovePayroll() {
    const funding = overview?.dates?.fundingDue || overview?.cycle.fundingDue
    const moving = review.notInRun?.employees.map((e) => e.name).join(', ') || 'None'
    askConfirm({
      title: `Approve ${cycleMonth} payroll`,
      body: [
        `Employees in this run: ${employeesInRun}`,
        `Changes approved: ${approvedCount}`,
        `Auto-matched changes: ${review.matchedLines}`,
        `Moving to next cycle: ${moving}`,
        funding ? `Funding due: ${formatIsoDate(funding)}` : null,
      ]
        .filter(Boolean)
        .join('\n'),
      confirmLabel: 'Approve payroll',
      onConfirm: async () => {
        setConfirmBusy(true)
        setConfirmError(null)
        try {
          const result = await signOff()
          cancelConfirm()
          const msg =
            result?.message ||
            `${overview?.cycle.label || cycleMonth} approved by ${adminName} · funding request sent to finance`
          setFooterMsg(msg)
          pushToast(msg)
        } catch (err) {
          setConfirmError(err instanceof Error ? err.message : 'Could not approve payroll')
        } finally {
          setConfirmBusy(false)
        }
      },
    })
  }

  return (
    <div className="relative flex flex-col gap-4 pb-28">
      <PageHeader
        title="Review & approve"
        subtitle={review.header ?? ''}
        actions={
          <label className="flex items-center gap-1.5 text-xs text-text-secondary">
            Country
            <select
              className="h-8 rounded border border-border bg-surface px-2 text-xs text-text-primary"
              value={countryParam}
              disabled={Boolean(lockedCountry)}
              onChange={(event) => {
                const next = new URLSearchParams(params)
                if (event.target.value) next.set('country', event.target.value)
                else next.delete('country')
                setParams(next)
              }}
            >
              <option value="">All</option>
              <option value="IN">India</option>
              <option value="UK">UK</option>
              <option value="DE">Germany</option>
              <option value="BR">Brazil</option>
            </select>
          </label>
        }
      />
      {review.signoff?.reopened ? (
        <p className="rounded border border-status-warn-border bg-status-warn-bg px-3 py-2 text-xs text-status-warn-text">
          {review.signoff.reopenedNote || 'Payroll approval reopened – 1 line changed'}
        </p>
      ) : null}

      <div className="grid grid-cols-3 gap-3">
        {(
          [
            {
              to: '/people?filter=changed',
              label: 'Changed lines',
              value: cards?.changed ?? 0,
              tip: 'Employees whose pay is different this cycle.',
            },
            {
              to: '/people?filter=reconciled',
              label: 'Matched to a source',
              value: cards?.matched ?? 0,
              tip: 'Multiplier found a record that explains the change.',
            },
            {
              to: '#review-table',
              label: 'Need your check',
              value: cards?.needs ?? 0,
              tip: 'Changes with no matching source, or unusually large.',
              warn: true,
            },
          ] as const
        ).map((card) => {
          const Comp: 'a' | typeof Link = card.to.startsWith('#') ? 'a' : Link
          const props = card.to.startsWith('#') ? { href: card.to } : { to: card.to }
          return (
            <Comp
              key={card.label}
              {...(props as { to: string })}
              className={[
                'rounded border border-border bg-surface px-4 py-3',
                muted ? 'text-slate-400' : 'hover:bg-canvas',
              ].join(' ')}
            >
              {review.numbersLabel && muted ? (
                <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-400">
                  {review.numbersLabel}
                </p>
              ) : null}
              <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">
                {card.label}
              </p>
              <p
                className={[
                  'mt-1 text-2xl font-semibold tabular',
                  muted ? 'text-slate-400' : card.warn ? 'text-status-warn-text' : '',
                ].join(' ')}
              >
                {card.value}
              </p>
              <p className="mt-1 text-[11px] leading-snug text-text-secondary">{card.tip}</p>
            </Comp>
          )
        })}
      </div>

      {review.showOpenExtras && heldOut && heldOut.count > 0 ? (
        <p className="text-[13px] text-text-secondary">
          <strong className="text-text-primary">{heldOut.message}</strong>{' '}
          <Link to="/payroll/actions" className="text-brand hover:underline">
            View in Action needed
          </Link>
        </p>
      ) : null}

      {!muted && !readOnly ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-border bg-canvas px-3 py-2">
          <p className="text-[12px] text-text-secondary">
            LLM decides Approve vs Hold per line (set <code className="text-[11px]">LLM_API_KEY</code> in
            .env). Soft fallback is used without a key — not fixed % rules.
          </p>
          <Button variant="secondary" onClick={applyLlmApproves}>
            Apply LLM approvals
          </Button>
        </div>
      ) : null}

      <CarryNotice block={carry} />

      <div id="review-table" className="overflow-x-auto rounded border border-border bg-surface">
        <table className="w-full min-w-0 table-fixed border-collapse text-left">
          <colgroup>
            <col className="w-[15%]" />
            <col className="w-[16%]" />
            <col className="w-[16%]" />
            <col className="w-[14%]" />
            <col className="w-[18%]" />
            <col style={{ width: 220 }} />
          </colgroup>
          <thead>
            <tr className="h-8 bg-surface-recessed text-[11px] font-medium uppercase tracking-wide text-text-secondary">
              <th className="px-3 py-1">Employee</th>
              <th className="px-3 py-1">Change</th>
              <th className="px-3 py-1">Why flagged</th>
              <th className="px-3 py-1">Matching source</th>
              <th className="px-3 py-1">LLM decision</th>
              <th className="px-3 py-1 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {reviewLines.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-[13px] text-text-secondary">
                  No issues{countryName ? ` for ${countryName}` : ''}.
                </td>
              </tr>
            ) : null}
            {reviewLines.map((line) => {
              const llm = line.llmDecision
              const llmApprove = llm?.recommend === 'approve'
              return (
              <tr
                key={line.id}
                className={[
                  'border-t border-border align-middle',
                  line.approved && !muted ? 'bg-emerald-50' : '',
                  muted ? 'text-slate-400' : 'hover:bg-canvas',
                ].join(' ')}
              >
                <td className="px-3 py-2.5 text-[13px] font-medium">
                  {line.employeeName}{' '}
                  <span className={muted ? 'text-slate-400' : 'text-text-muted'}>
                    ({line.country})
                  </span>
                </td>
                <td className="px-3 py-2.5 tabular text-[13px]">
                  {line.changeSummary}
                  {line.carryNote ? (
                    <p
                      className="mt-1 text-[11px] font-normal leading-snug text-amber-800"
                      data-testid={`carry-note-${line.employeeId}`}
                    >
                      {line.carryNote}
                    </p>
                  ) : null}
                </td>
                <td className="px-3 py-2.5 text-[13px]">{line.whyFlagged}</td>
                <td className="px-3 py-2.5 text-[13px]">{line.matchingSource}</td>
                <td className="px-3 py-2.5 text-[12px]">
                  {llm ? (
                    <div>
                      <span
                        className={[
                          'inline-flex rounded border px-1.5 py-0.5 text-[11px] font-medium',
                          llmApprove
                            ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                            : 'border-status-warn-border bg-status-warn-bg text-status-warn-text',
                        ].join(' ')}
                      >
                        {llmApprove ? 'Approve' : 'Hold'}
                        {llm.source === 'llm'
                          ? ` · ${Math.round((llm.confidence || 0) * 100)}%`
                          : llm.source === 'fallback'
                            ? ' · fallback'
                            : ''}
                      </span>
                      <p className="mt-1 text-[11px] leading-snug text-text-muted">{llm.reason}</p>
                    </div>
                  ) : (
                    <span className="text-text-muted">—</span>
                  )}
                </td>
                <td className="px-3 py-2.5">
                  <RowActions
                    line={line}
                    muted={muted}
                    nextLabel={nextLabel}
                    onApprove={() => openApproveLine(line)}
                    onUndo={() => void unapproveLine(line.id)}
                  />
                </td>
              </tr>
            )})}
          </tbody>
        </table>
      </div>

      {!readOnly || footerMsg ? (
        <div className="sticky bottom-0 z-20 -mx-6 mt-2 border-t border-border bg-surface px-6 py-3 shadow-[0_-4px_12px_rgba(15,23,42,0.06)]">
          {footerMsg ? (
            <p className="text-[13px] font-medium text-emerald-800">{footerMsg}</p>
          ) : (
            <div className="flex items-center justify-between gap-6">
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-medium text-text-primary">
                  {totalLines === 0
                    ? 'No issues'
                    : `${approvedCount} of ${totalLines} lines approved`}
                </p>
                <div className="mt-1.5 h-1.5 w-full max-w-md overflow-hidden rounded-full bg-slate-200">
                  <div
                    className="h-full rounded-full bg-emerald-500 transition-all"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <p className="mt-1.5 text-[11px] text-text-muted">
                  {countryName
                    ? `${employeesInRun} employees in ${countryName}. Approve each line in this list.`
                    : `Approving payroll authorises pay for ${employeesInRun} employees and sends the funding request to finance.`}
                </p>
              </div>
              {countryName ? null : (
              <Button
                variant="primary"
                className="h-9 shrink-0 px-4 text-sm"
                disabled={!review.canSignOff}
                title={
                  review.canSignOff
                    ? undefined
                    : `Approve the remaining ${remaining} line${remaining === 1 ? '' : 's'} first`
                }
                onClick={openApprovePayroll}
              >
                Approve {cycleMonth} payroll
              </Button>
              )}
            </div>
          )}
        </div>
      ) : null}

    </div>
  )
}
