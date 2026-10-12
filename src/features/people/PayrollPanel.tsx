import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Check, Circle } from 'lucide-react'
import { Button, StatusChip } from '@/components'
import { formatIsoDate, formatJourneyAt, formatMoney } from '@/features/payroll/lib/labels'
import { DEFAULT_FIELD_FORMATS, validateFieldValue } from '@/lib/fieldValidation'
import { useAppStore } from '@/store'
import type { EmployeeDto, MappingRowDto } from '@/api/types'

function namesMatch(a: string, b: string) {
  return a.trim().toLowerCase().replace(/\s+/g, ' ') === b.trim().toLowerCase().replace(/\s+/g, ' ')
}

function isNameField(field: string) {
  return /employee name|legal name/i.test(field)
}

type Props = {
  employee: EmployeeDto
  composer: 'bonus' | 'hike' | null
  onComposer: (next: 'bonus' | 'hike' | null) => void
  children?: ReactNode
}

function LetterLink({
  letter,
  label,
}: {
  letter?: { id: string; fileName: string } | null
  label: string
}) {
  if (!letter?.id) return null
  return (
    <a
      href={`/api/documents/${letter.id}/file`}
      target="_blank"
      rel="noreferrer"
      className="inline-flex h-8 items-center px-1 text-[13px] font-medium text-brand underline"
    >
      {label}
    </a>
  )
}

function payTone(level: string): 'ok' | 'warn' | 'danger' | 'neutral' {
  if (level === 'green') return 'ok'
  if (level === 'amber') return 'warn'
  if (level === 'red') return 'danger'
  return 'neutral'
}

function resultCopy(employee: EmployeeDto): string | null {
  const { payTiming, name, missingFields } = employee
  if (payTiming.level === 'green') return null
  if (payTiming.level === 'amber') {
    const holding = employee.paymentMissingFields ?? missingFields
    const missing = holding.join(' and ') || 'required fields'
    return `Saved to this cycle's payroll – at risk. Add ${missing} by the input finalisation date, otherwise ${name} moves to the next cycle.`
  }
  if (/Moved to /i.test(payTiming.message)) {
    return `${name} was still missing data after cutoff — ${payTiming.message}.`
  }
  return payTiming.message
}

const DETAILS_ON_TRACK = 'Thanks for adding your details. Payment is on track.'

const EMPLOYEE_OWNED = new Set([
  'PAN',
  'Tax ID',
  'CPF',
  'Bank account',
  'IFSC',
  'NI number',
  'Sort code',
  'IBAN',
  'Tax class',
  'PIX key',
])

export function PayrollPanel({ employee, composer, onComposer, children }: Props) {
  const [params] = useSearchParams()
  const asOf = useAppStore((s) => s.asOf)
  const fillMissingFields = useAppStore((s) => s.fillMissingFields)
  const remindIssue = useAppStore((s) => s.remindIssue)
  const askConfirm = useAppStore((s) => s.askConfirm)
  const cancelConfirm = useAppStore((s) => s.cancelConfirm)
  const setConfirmBusy = useAppStore((s) => s.setConfirmBusy)
  const setConfirmError = useAppStore((s) => s.setConfirmError)
  const issues = useAppStore((s) => s.issues)
  const refreshIssues = useAppStore((s) => s.refreshIssues)
  const pushToast = useAppStore((s) => s.pushToast)
  const showNotice = useAppStore((s) => s.showNotice)
  const [visibleSteps, setVisibleSteps] = useState(0)
  const [busy, setBusy] = useState(false)
  const [showMissing, setShowMissing] = useState(false)
  const missingRef = useRef<HTMLDivElement>(null)
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({})
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [thanked, setThanked] = useState(false)
  const fieldFormats = useAppStore((s) => s.rules?.fieldFormats) ?? DEFAULT_FIELD_FORMATS
  const [editMaps, setEditMaps] = useState<MappingRowDto[]>([])

  const steps = employee.journeySteps ?? []
  const mappings = employee.mappings ?? []

  const mappingsKey = mappings
    .map((m) => `${m.multiplierField}:${m.value}:${m.status}`)
    .join('|')

  useEffect(() => {
    setEditMaps(mappings.map((m) => ({ ...m })))
    // Remount edit state when server mappings change (attach / refresh)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mappingsKey encodes content
  }, [employee.id, mappingsKey])

  const nameMismatch = useMemo(() => {
    const nameRow = editMaps.find((m) => isNameField(m.multiplierField || ''))
    const docName = (nameRow?.value || '').trim()
    if (!docName || /not found/i.test(docName)) return null
    if (namesMatch(docName, employee.name)) return null
    return docName
  }, [editMaps, employee.name])

  const missing = employee.missingFields || []
  const canFillMissing = missing.length > 0
  const employeeOwnedMissing = missing.filter((f) => EMPLOYEE_OWNED.has(f))
  const hrOwnedMissing = missing.filter((f) => !EMPLOYEE_OWNED.has(f))

  const missingIssue = useMemo(
    () =>
      issues.find(
        (i) =>
          i.employeeId === employee.id &&
          i.status === 'open' &&
          (/missing/i.test(i.kind || '') || /missing/i.test(i.title || '')),
      ),
    [issues, employee.id],
  )

  const onTrack = employee.payTiming.level === 'green'
  const showThanks = onTrack && (thanked || params.get('panel') === 'missing')

  useEffect(() => {
    setThanked(false)
  }, [employee.id])

  useEffect(() => {
    const openMissing = params.get('panel') === 'missing'
    const hasMissing = (employee.missingFields?.length || 0) > 0
    setShowMissing(openMissing && hasMissing && !onTrack)
    if (openMissing && !onTrack) void refreshIssues()
  }, [employee.id, employee.missingFields, params, refreshIssues, onTrack])

  useEffect(() => {
    if (params.get('panel') !== 'missing' || (!showMissing && !showThanks)) return
    const scroll = () => {
      missingRef.current?.scrollIntoView({ behavior: 'auto', block: 'start' })
    }
    scroll()
    const timer = window.setTimeout(scroll, 250)
    return () => window.clearTimeout(timer)
  }, [showMissing, showThanks, params, employee.id])

  useEffect(() => {
    if (!steps.length) {
      setVisibleSteps(0)
      return
    }
    setVisibleSteps(0)
    let step = 0
    const timer = window.setInterval(() => {
      step += 1
      setVisibleSteps(step)
      if (step >= steps.length) {
        window.clearInterval(timer)
      }
    }, 400)
    return () => window.clearInterval(timer)
  }, [employee.id, steps.length, employee.source])

  function onRemindEmployee() {
    if (!missingIssue) {
      pushToast('No open missing-data issue for this employee yet')
      return
    }
    const fields = employeeOwnedMissing.length
      ? employeeOwnedMissing.join(', ')
      : missing.join(', ')
    askConfirm({
      title: missingIssue.reminderSentOn ? 'Resend reminder' : 'Remind employee',
      body: `Send ${employee.name} an email to add ${fields}? Uses Gmail SMTP when configured; otherwise saves to Notifications with a form link.`,
      onConfirm: async () => {
        setConfirmBusy(true)
        setConfirmError(null)
        try {
          const msg = await remindIssue(missingIssue.id)
          cancelConfirm()
          if (msg) showNotice(msg)
        } catch (err) {
          setConfirmError(err instanceof Error ? err.message : 'Could not send reminder')
        } finally {
          setConfirmBusy(false)
        }
      },
    })
  }

  useEffect(() => {
    setFieldValues({})
    setFieldErrors({})
  }, [employee.id])

  async function onSaveMissing() {
    const payload: Record<string, string> = {}
    const errors: Record<string, string> = {}
    for (const field of missing) {
      const raw = (fieldValues[field] || '').trim()
      if (!raw) continue
      const result = validateFieldValue(field, raw, fieldFormats)
      if (!result.ok) errors[field] = result.error
      else payload[field] = result.normalised
    }
    setFieldErrors(errors)
    if (Object.keys(errors).length) return
    if (!Object.keys(payload).length) {
      pushToast('Enter at least one missing field')
      return
    }
    setBusy(true)
    try {
      const saved = await fillMissingFields(employee.id, { fields: payload, asOf })
      if (saved.payTiming.level === 'green') {
        setThanked(true)
        pushToast(DETAILS_ON_TRACK)
      } else {
        pushToast('Details saved')
      }
      setShowMissing(false)
    } catch {
      /* toasted */
    } finally {
      setBusy(false)
    }
  }

  async function onFillSample() {
    setBusy(true)
    try {
      const saved = await fillMissingFields(employee.id, { fillSample: true, asOf })
      if (saved.payTiming.level === 'green') {
        setThanked(true)
        pushToast(DETAILS_ON_TRACK)
      } else {
        pushToast('Details saved')
      }
      setShowMissing(false)
    } catch {
      /* toasted */
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded border border-border bg-surface">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-text-primary">
            Payroll
          </h2>
          <p className="text-xs text-text-secondary">
            Data journey for this record · as of{' '}
            <span className="tabular">{asOf}</span>
          </p>
        </div>
        {employee.payTiming.level === 'green' ? null : (
          <StatusChip tone={payTone(employee.payTiming.level)}>
            {employee.payTiming.message}
          </StatusChip>
        )}
      </div>

      <div className="space-y-4 px-4 py-4">
        {steps.length > 0 ? (
          <div>
            <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-text-muted">
              Data journey
            </p>
            <ol className="space-y-1.5">
              {steps.map((step, index) => {
                const shown = index < visibleSteps
                return (
                  <li
                    key={step.key}
                    className={[
                      'flex items-center gap-2 rounded border px-2.5 py-1.5 text-[13px] transition-opacity',
                      shown
                        ? 'border-border bg-canvas text-text-primary opacity-100'
                        : 'border-transparent text-text-muted opacity-40',
                    ].join(' ')}
                  >
                    {shown ? (
                      <Check size={14} className="text-status-ok-text" />
                    ) : (
                      <Circle size={14} className="text-border-active" />
                    )}
                    <span className="flex-1">{step.label}</span>
                    <span className="tabular text-xs text-text-secondary">
                      {formatJourneyAt(step.at)}
                    </span>
                  </li>
                )
              })}
            </ol>
          </div>
        ) : (
          <p className="text-xs text-text-secondary">
            No document journey for this employee yet. Attach an offer, bonus, or
            salary revision letter to run validation.
          </p>
        )}

        {editMaps.length > 0 ? (
          <div>
            <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-text-muted">
              Field mapping
            </p>
            <p className="mb-2 text-[11px] text-text-secondary">
              Edit any value that looks wrong. Changes stay on this screen for review.
            </p>
            {nameMismatch ? (
              <div
                className="mb-2 rounded border border-status-danger-border bg-status-danger-bg px-3 py-2 text-[12px] text-status-danger-text"
                data-testid="mapping-name-mismatch"
              >
                Name doesn&apos;t match this employee — document says{' '}
                <strong>{nameMismatch}</strong>, profile / offer letter is{' '}
                <strong>{employee.name}</strong>. Correct the name below if this letter
                belongs to someone else, or keep and confirm if intentional.
              </div>
            ) : null}
            <div className="rounded border border-border">
              <table className="w-full table-fixed border-collapse text-left text-[12px]">
                <colgroup>
                  <col className="w-[14%]" />
                  <col className="w-[18%]" />
                  <col className="w-[22%]" />
                  <col className="w-[26%]" />
                  <col className="w-[20%]" />
                </colgroup>
                <thead>
                  <tr className="bg-surface-recessed text-[11px] uppercase tracking-wide text-text-secondary">
                    <th className="px-2 py-1.5 font-medium">Source</th>
                    <th className="px-2 py-1.5 font-medium">Source field</th>
                    <th className="px-2 py-1.5 font-medium">Multiplier field</th>
                    <th className="px-2 py-1.5 font-medium">Value</th>
                    <th className="px-2 py-1.5 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {editMaps.map((row, i) => {
                    const nameRow = isNameField(row.multiplierField || '')
                    const rowMismatch =
                      nameRow &&
                      Boolean(nameMismatch) &&
                      namesMatch(row.value || '', nameMismatch || '')
                    return (
                      <tr key={`${row.multiplierField}-${i}`} className="border-t border-border">
                        <td className="px-2 py-1.5 text-text-secondary">
                          {row.sourceSystem ?? '—'}
                        </td>
                        <td className="px-2 py-1.5 text-text-secondary">
                          {row.sourceField ?? '—'}
                        </td>
                        <td className="px-2 py-1.5 font-medium text-text-primary">
                          {row.multiplierField}
                        </td>
                        <td className="px-2 py-1.5">
                          <input
                            aria-label={row.multiplierField}
                            className={[
                              'h-7 w-full rounded border px-1.5 text-[12px] tabular text-text-primary',
                              rowMismatch
                                ? 'border-status-danger-border bg-status-danger-bg'
                                : 'border-border bg-surface',
                            ].join(' ')}
                            value={row.value}
                            onChange={(e) => {
                              const v = e.target.value
                              setEditMaps((prev) =>
                                prev.map((r, idx) =>
                                  idx === i
                                    ? {
                                        ...r,
                                        value: v,
                                        status: v.trim() ? 'mapped' : 'missing',
                                      }
                                    : r,
                                ),
                              )
                            }}
                          />
                          {rowMismatch ? (
                            <p className="mt-0.5 text-[10px] text-status-danger-text">
                              Doesn&apos;t match {employee.name}
                            </p>
                          ) : null}
                        </td>
                        <td className="px-2 py-1.5">
                          {rowMismatch ? (
                            <StatusChip tone="danger">Mismatch</StatusChip>
                          ) : (
                            <StatusChip
                              tone={row.status === 'mapped' ? 'ok' : 'danger'}
                            >
                              {row.status === 'mapped'
                                ? `✓ ${row.confidence ?? 'Mapped'}`
                                : `✗ ${row.confidence ?? 'Required'}`}
                            </StatusChip>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {employee.oneOffs.length > 0 ? (
          <div className="rounded border border-status-info-border bg-status-info-bg px-3 py-2 text-[13px] text-status-info-text">
            {employee.payExplanation ? (
              <p className="mb-1.5 text-[12px]">{employee.payExplanation}</p>
            ) : employee.hireDate || employee.dateAdded ? (
              <p className="mb-1.5 text-[12px]">
                {employee.hireDate ? (
                  <>
                    Hired {formatIsoDate(employee.hireDate)}
                    {employee.dateAdded ? ' · ' : null}
                  </>
                ) : null}
                {employee.dateAdded ? <>Added {formatIsoDate(employee.dateAdded)}</> : null}
                {employee.oneOffs.some((o) => /backdated/i.test(o.label)) &&
                employee.oneOffs[0]?.cycleMonth ? (
                  <>
                    {' '}
                    → paid in{' '}
                    <strong>
                      {employee.oneOffs.find((o) => /backdated/i.test(o.label))?.cycleMonth ||
                        employee.oneOffs[0].cycleMonth}
                    </strong>{' '}
                    (backdated months combined in that run).
                  </>
                ) : null}
              </p>
            ) : null}
            {employee.oneOffs.map((o) => {
              const payRun = o.cycleMonth?.trim() || null
              const isBackdated = /backdated/i.test(o.label)
              const isProrated = /prorated/i.test(o.label)
              return (
                <p key={`${o.label}-${o.amount}-${o.cycleMonth}`}>
                  {/bonus/i.test(o.label) ? 'Bonus' : o.label}{' '}
                  {formatMoney(employee.currency, o.amount)}
                  {isProrated ? null : ' (one-off)'}
                  {payRun ? (
                    <>
                      {' '}
                      · paid in <strong>{payRun}</strong>
                      {isBackdated || isProrated ? ' payroll' : ''}
                    </>
                  ) : null}
                </p>
              )
            })}
            <p className="mt-1 text-[11px]">
              Base monthly net remains{' '}
              <span className="tabular font-medium">
                {formatMoney(employee.currency, employee.monthlyNet)}
              </span>
              .
            </p>
          </div>
        ) : null}

        {showThanks ? (
          <div
            id="missing-details"
            ref={missingRef}
            className="scroll-mt-4 rounded border border-status-ok-border bg-status-ok-bg px-3 py-2.5 text-[13px] text-status-ok-text"
            data-testid="details-on-track"
          >
            {DETAILS_ON_TRACK}
          </div>
        ) : null}

        {resultCopy(employee) ? (
          <div
            className={[
              'rounded border px-3 py-2.5 text-[13px]',
              employee.payTiming.level === 'amber'
                ? 'border-status-warn-border bg-status-warn-bg text-status-warn-text'
                : 'border-status-danger-border bg-status-danger-bg text-status-danger-text',
            ].join(' ')}
          >
            {resultCopy(employee)}
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2">
          {canFillMissing ? (
            <Button
              variant="primary"
              disabled={busy}
              onClick={() => {
                setShowMissing((v) => {
                  const next = !v
                  if (next) void refreshIssues()
                  return next
                })
              }}
            >
              {showMissing ? 'Hide missing details' : 'Add missing details'}
            </Button>
          ) : null}
          <Button
            variant="primary"
            disabled={busy}
            data-testid="add-bonus"
            onClick={() => onComposer(composer === 'bonus' ? null : 'bonus')}
          >
            {composer === 'bonus' ? 'Hide bonus' : 'Add bonus'}
          </Button>
          <Button
            variant="primary"
            disabled={busy}
            onClick={() => onComposer(composer === 'hike' ? null : 'hike')}
          >
            {composer === 'hike' ? 'Hide hike' : 'Add hike'}
          </Button>
          <LetterLink letter={employee.letters?.offer} label="View offer letter" />
          <LetterLink letter={employee.letters?.bonus} label="View bonus letter" />
          <LetterLink letter={employee.letters?.hike} label="View hike letter" />
          {employee.payTiming.instantPaymentDisabled || employee.payTiming.showOffCycleStub ? (
            <Button
              variant="ghost"
              disabled
              title="Off-cycle and instant payments aren't supported. This employee will be paid in the next cycle."
              onClick={() =>
                pushToast(
                  "Off-cycle and instant payments aren't supported. This employee will be paid in the next cycle.",
                )
              }
            >
              Instant payment – not available
            </Button>
          ) : null}
        </div>

        {children}

        {showMissing && canFillMissing ? (
          <div
            id="missing-details"
            ref={missingRef}
            className="scroll-mt-4 rounded border border-border bg-canvas px-3 py-3"
            data-testid="missing-details-panel"
          >
            <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-text-muted">
              Missing details
            </p>
            <p className="mb-2 text-[12px] text-text-secondary">
              Fields still needed for {employee.name}. Employee-owned fields can be
              requested by email; HR can fill demo values if needed.
            </p>
            <table className="mb-3 w-full table-fixed text-left text-[12px]">
              <thead>
                <tr className="text-[11px] uppercase tracking-wide text-text-muted">
                  <th className="py-1.5 font-medium">Field</th>
                  <th className="py-1.5 font-medium">Value</th>
                  <th className="w-36 py-1.5 font-medium">Owner</th>
                  <th className="w-24 py-1.5 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {missing.map((field) => {
                  const empOwned = EMPLOYEE_OWNED.has(field)
                  const demo = employee.demoValues?.[field]
                  const error = fieldErrors[field]
                  return (
                    <tr key={field} className="border-t border-border align-top">
                      <td className="py-1.5 font-medium text-text-primary">{field}</td>
                      <td className="py-1.5 pr-3">
                        <input
                          aria-label={field}
                          className={[
                            'h-8 w-full rounded border bg-surface px-2 text-[13px] text-text-primary placeholder:text-text-muted focus:outline-none',
                            error
                              ? 'border-status-danger-border focus:border-status-danger-text'
                              : 'border-border focus:border-text-primary',
                          ].join(' ')}
                          value={fieldValues[field] || ''}
                          placeholder={demo || `Add ${field}`}
                          aria-invalid={Boolean(error)}
                          onChange={(e) => {
                            const value = e.target.value
                            setFieldValues((current) => ({ ...current, [field]: value }))
                            setFieldErrors((current) => {
                              if (!current[field]) return current
                              const next = { ...current }
                              delete next[field]
                              return next
                            })
                          }}
                        />
                        {error ? (
                          <p className="mt-0.5 text-[11px] text-status-danger-text">{error}</p>
                        ) : null}
                        {demo ? (
                          <button
                            type="button"
                            className="mt-0.5 text-[11px] text-brand hover:underline"
                            onClick={() =>
                              setFieldValues((current) => ({ ...current, [field]: demo }))
                            }
                          >
                            Use demo value
                          </button>
                        ) : null}
                      </td>
                      <td className="py-1.5 text-text-secondary">
                        {empOwned ? employee.name : 'HR admin'}
                      </td>
                      <td className="py-1.5">
                        <StatusChip tone="danger">Missing</StatusChip>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {hrOwnedMissing.length && !employeeOwnedMissing.length ? (
              <p className="mb-2 text-[11px] text-text-muted">
                Only HR-owned fields are missing — fill them in Action needed or use demo values.
              </p>
            ) : null}
            {missingIssue?.reminderLabel ? (
              <p className="mb-2 text-[11px] text-text-muted">{missingIssue.reminderLabel}</p>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button
                variant="primary"
                disabled={busy || !missingIssue || employeeOwnedMissing.length === 0}
                title={
                  !missingIssue
                    ? 'No open missing-data issue yet'
                    : employeeOwnedMissing.length === 0
                      ? 'No employee-owned fields to remind about'
                      : undefined
                }
                onClick={onRemindEmployee}
              >
                {missingIssue?.reminderSentOn ? 'Resend reminder' : 'Remind employee'}
              </Button>
              <Button variant="secondary" disabled={busy} onClick={() => void onSaveMissing()}>
                {busy ? 'Saving…' : 'Save details'}
              </Button>
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() => void onFillSample()}
              >
                Use demo values
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  )
}
