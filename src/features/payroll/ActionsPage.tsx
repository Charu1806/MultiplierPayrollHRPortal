import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Info } from 'lucide-react'
import { Button, EmptyState, PageHeader, StatusChip } from '@/components'
import { ChangesReminder } from '@/features/payroll/ChangesReminder'
import { FinalReportNote } from '@/features/payroll/components/StageTracker'
import {
  formatIsoDate,
  formatMoney,
  severityLabel,
  severityTone,
  whoLabel,
} from '@/features/payroll/lib/labels'
import { validateFieldValue, type FieldFormatSpec } from '@/lib/fieldValidation'
import { personaCountry, seesAllCountries } from '@/features/persona'
import { useAppStore } from '@/store'
import type { IssueDto } from '@/api/types'
import { ClarityApiError } from '@/api/clarityClient'

function GuidedInfo() {
  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        className="rounded p-1 text-text-muted hover:bg-surface-recessed hover:text-text-primary"
        aria-label="AI Chat Assistance (V2)"
      >
        <Info size={14} />
      </button>
      <span className="pointer-events-none absolute bottom-full right-0 z-10 mb-1 hidden whitespace-nowrap rounded border border-border bg-text-primary px-2 py-1 text-[11px] text-white group-hover:block">
        AI Chat Assistance (V2)
      </span>
    </span>
  )
}

function IssueListItem({
  issue,
  selected,
  onSelect,
}: {
  issue: IssueDto
  selected: boolean
  onSelect: () => void
}) {
  const carried = Boolean(issue.carriedOver || issue.severity === 'next_cycle')
  return (
    <button
      type="button"
      onClick={onSelect}
      className={[
        'w-full rounded px-3 py-3 text-left transition-colors',
        selected
          ? 'border-2 border-sky-600 bg-sky-50'
          : 'border border-slate-200 bg-white hover:bg-slate-50',
      ].join(' ')}
    >
      <div className="mb-1 flex flex-wrap items-center gap-1.5">
        <StatusChip tone={severityTone(issue.severity)}>
          {severityLabel(issue.severity)}
        </StatusChip>
        {carried ? <StatusChip tone="neutral">Carried over</StatusChip> : null}
        <span className="text-xs text-text-secondary">{issue.country}</span>
      </div>
      <p className="text-[13px] font-semibold text-text-primary">{issue.title}</p>
      <p className="mt-0.5 text-xs text-text-secondary">
        {whoLabel(issue)} · due {formatIsoDate(issue.deadline)}
      </p>
      {issue.reminderLabel ? (
        <p className="mt-1 text-[11px] text-text-muted">{issue.reminderLabel}</p>
      ) : null}
      <div className="mt-2 flex items-center justify-between">
        <span className="text-[11px] text-text-muted">Owner: {issue.owner}</span>
        <span className="text-[11px] font-medium text-brand">Take action →</span>
      </div>
    </button>
  )
}

function DemoField({
  field,
  value,
  demo,
  error,
  onChange,
}: {
  field: string
  value: string
  demo?: string
  error?: string | null
  onChange: (v: string) => void
}) {
  return (
    <label className="flex min-w-[200px] flex-1 flex-col gap-1 text-xs text-text-secondary">
      {field}
      <input
        className={[
          'h-8 rounded border bg-surface px-2 text-[13px] text-text-primary placeholder:text-text-muted focus:outline-none',
          error ? 'border-status-danger-border focus:border-status-danger-text' : 'border-border focus:border-text-primary',
        ].join(' ')}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={demo || field}
        aria-invalid={Boolean(error)}
      />
      {error ? <span className="text-[11px] text-status-danger-text">{error}</span> : null}
      {demo ? (
        <button
          type="button"
          className="self-start text-[11px] text-brand hover:underline"
          onClick={() => onChange(demo)}
        >
          Use demo value
        </button>
      ) : null}
    </label>
  )
}

function IssueDetail({ issue }: { issue: IssueDto }) {
  const resolveIssue = useAppStore((s) => s.resolveIssue)
  const remindIssue = useAppStore((s) => s.remindIssue)
  const askConfirm = useAppStore((s) => s.askConfirm)
  const cancelConfirm = useAppStore((s) => s.cancelConfirm)
  const setConfirmBusy = useAppStore((s) => s.setConfirmBusy)
  const setConfirmError = useAppStore((s) => s.setConfirmError)
  const pushToast = useAppStore((s) => s.pushToast)
  const showNotice = useAppStore((s) => s.showNotice)
  const asOf = useAppStore((s) => s.asOf)
  const fieldFormats = useAppStore((s) => s.rules?.fieldFormats) as
    | Record<string, FieldFormatSpec>
    | undefined
  const [values, setValues] = useState<Record<string, string>>({})
  const [showAdd, setShowAdd] = useState<'employee' | 'hr' | null>(null)
  const [touched, setTouched] = useState<Record<string, boolean>>({})

  useEffect(() => {
    setValues({})
    setShowAdd(null)
    setTouched({})
  }, [issue.id])

  const first = (issue.employeeName || 'this employee').split(' ')[0]
  const employeeFields = issue.employeeOwnedFields ?? []
  const hrFields = issue.hrOwnedFields ?? []
  const formats = fieldFormats

  function fieldError(field: string, raw: string): string | null {
    if (!raw.trim()) return `${field} is required`
    return validateFieldValue(field, raw, formats).error ?? null
  }

  function validatedFields(fields: string[]): { ok: boolean; payload: Record<string, string> } {
    const payload: Record<string, string> = {}
    for (const f of fields) {
      const raw = values[f] ?? ''
      const result = validateFieldValue(f, raw, formats)
      if (!result.ok) {
        return { ok: false, payload: {} }
      }
      payload[f] = result.normalised
    }
    return { ok: true, payload }
  }

  const employeeAddValid = useMemo(() => {
    if (!employeeFields.length) return false
    return employeeFields.every((f) => validateFieldValue(f, values[f] ?? '', formats).ok)
  }, [employeeFields, values, formats])

  function runRemind() {
    askConfirm({
      title: issue.reminderSentOn ? 'Resend reminder' : 'Remind employee',
      body: issue.reminderSentOn
        ? `Send ${first} another email to add ${employeeFields.join(', ')}?`
        : `Send ${first} an email to add ${employeeFields.join(', ')}? Uses Gmail SMTP when configured; otherwise saves to Notifications with a form link.`,
      onConfirm: async () => {
        setConfirmBusy(true)
        setConfirmError(null)
        try {
          const msg = await remindIssue(issue.id)
          cancelConfirm()
          if (msg) showNotice(msg)
        } catch (err) {
          const detail =
            err instanceof ClarityApiError
              ? err.message
              : err instanceof Error
                ? err.message
                : 'Could not send reminder'
          setConfirmError(detail)
        } finally {
          setConfirmBusy(false)
        }
      },
    })
  }

  function saveFields(fields: Record<string, string>, resolution: string) {
    const saving = Object.keys(fields).filter((f) => (fields[f] || '').trim())
    const still = [...employeeFields, ...hrFields].filter((f) => !saving.includes(f))
    const done = still.length === 0
    const savedLabel = saving.join(', ')
    const who = issue.employeeName || first
    askConfirm({
      title: done ? 'Confirm' : 'Save details',
      body: done
        ? `Mark ${issue.title}${issue.employeeName ? ` – ${who}` : ''} as resolved? ${first} will be included in this cycle's pay.`
        : `Save ${savedLabel} for ${who}. ${still.join(', ')} ${still.length === 1 ? 'is' : 'are'} still missing, so this issue stays open.`,
      confirmLabel: done ? 'Confirm' : 'Save',
      onConfirm: async () => {
        setConfirmBusy(true)
        setConfirmError(null)
        try {
          const result = await resolveIssue(issue.id, {
            resolution,
            payload: { fields },
            actor: 'HR admin',
            asOf,
          })
          cancelConfirm()
          if (result.partial || !done) {
            pushToast(`${savedLabel} saved. Still missing ${still.join(', ')}.`)
          } else {
            pushToast(`Resolved: ${issue.title}`)
          }
        } catch (err) {
          const detail =
            err instanceof ClarityApiError
              ? err.message
              : err instanceof Error
                ? err.message
                : 'Could not save details'
          setConfirmError(detail)
        } finally {
          setConfirmBusy(false)
        }
      },
    })
  }

  function openAddDetailsConfirm(fields: string[], resolution: string) {
    const { ok, payload } = validatedFields(fields)
    if (!ok) return
    saveFields(payload, resolution)
  }

  const isPayConfirm = issue.kind === 'pay_confirmation'
  const employees = useAppStore((s) => s.employees)
  const targetEmp = employees.find((e) => e.id === issue.employeeId)
  const confirmedBase = targetEmp?.salary?.base
  const confirmedLabel =
    confirmedBase != null
      ? formatMoney(targetEmp?.currency || '£', confirmedBase)
      : issue.facts?.submitted?.split('→').pop()?.trim() || 'new base'

  function confirmResolve(resolution: string, payload?: Record<string, unknown>) {
    askConfirm({
      title: 'Confirm',
      body: `Mark *${issue.title}${issue.employeeName ? ` – ${issue.employeeName}` : ''}* as resolved? ${first} will be included in this cycle's pay.`,
      onConfirm: async () => {
        await resolveIssue(issue.id, { resolution, payload, actor: 'HR admin', asOf })
        pushToast(`Resolved: ${issue.title}`)
      },
    })
  }

  return (
    <div className="rounded border border-border bg-surface">
      <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div>
          <div className="mb-1 flex items-center gap-1.5">
            <StatusChip tone={severityTone(issue.severity)}>
              {severityLabel(issue.severity)}
            </StatusChip>
            <span className="text-xs text-text-secondary">{issue.country}</span>
          </div>
          <h2 className="text-base font-semibold text-text-primary">{issue.title}</h2>
          <p className="mt-0.5 text-xs text-text-secondary">
            {whoLabel(issue)} · Owner: {issue.owner} · Fix by {formatIsoDate(issue.deadline)}
          </p>
        </div>
        <GuidedInfo />
      </div>

      <div className="space-y-4 px-4 py-4 text-[13px]">
        {issue.detail ? (
          <div>
            <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-text-muted">
              What’s wrong
            </p>
            <p className="text-text-primary">{issue.detail}</p>
          </div>
        ) : null}

        <div>
          <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-text-muted">Impact</p>
          <p className="text-text-primary">{issue.impact}</p>
        </div>

        {isPayConfirm && issue.facts ? (
          <div className="grid grid-cols-2 gap-3 rounded border border-border bg-canvas px-3 py-2.5">
            <div>
              <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">Submitted</p>
              <p className="tabular text-text-primary">{issue.facts.submitted}</p>
            </div>
            <div>
              <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">Pay history</p>
              <p className="tabular text-text-primary">{issue.facts.payHistory}</p>
            </div>
          </div>
        ) : null}

        {issue.aiNote ? (
          <div className="rounded border border-status-info-border bg-status-info-bg px-3 py-2.5">
            <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-status-info-text">
              AI note
            </p>
            <p className="text-text-primary">{issue.aiNote}</p>
            <p className="mt-2 text-[11px] text-text-muted">
              AI explains only — it never changes a pay amount.
            </p>
          </div>
        ) : null}

        {issue.reminderLabel ? (
          <div className="flex flex-wrap items-center gap-2 text-xs text-text-secondary">
            <span>{issue.reminderLabel}</span>
            {issue.status !== 'resolved' && employeeFields.length > 0 ? (
              <Button variant="primary" onClick={runRemind}>
                Resend reminder
              </Button>
            ) : null}
          </div>
        ) : null}

        {issue.status === 'resolved' ? (
          <div className="rounded border border-status-ok-border bg-status-ok-bg px-3 py-2.5 text-status-ok-text">
            <p className="font-medium">Resolved</p>
            {issue.resolutionLog ? <p className="mt-1 text-xs">{issue.resolutionLog}</p> : null}
          </div>
        ) : isPayConfirm ? (
          <div className="flex flex-col gap-3 border-t border-border pt-4">
            <Link
              to={issue.employeeId ? `/people/${issue.employeeId}?panel=salary` : '/people'}
              className="inline-flex w-fit rounded bg-text-primary px-3 py-1.5 text-[13px] font-medium text-white"
            >
              Fix in HR tool
            </Link>
            <Button
              variant="secondary"
              onClick={() =>
                askConfirm({
                  title: `${confirmedLabel} is correct`,
                  body: `Confirm ${issue.employeeName || 'employee'}'s new base salary is ${confirmedLabel} per month?`,
                  extra:
                    'Reason required on next step (Promotion / Role change / Retention / Contract correction / Other). This will be their base salary from this cycle onward.',
                  confirmLabel: `Confirm ${confirmedLabel}`,
                  onConfirm: async () => {
                    await resolveIssue(issue.id, {
                      resolution: 'confirm',
                      payload: {
                        reason: 'Promotion',
                        confirmedBase: confirmedBase,
                      },
                    })
                    pushToast(`Confirmed ${confirmedLabel} as base salary`)
                  },
                })
              }
            >
              {confirmedLabel} is correct
            </Button>
            <Link
              to={
                issue.employeeId
                  ? `/people/${issue.employeeId}?panel=salary&hike=1`
                  : '/people'
              }
              className="text-[13px] font-medium text-text-primary hover:underline"
            >
              Salary hike + bonus
            </Link>
            <Link
              to={issue.facts?.openSalaryHref || (issue.employeeId ? `/people/${issue.employeeId}?panel=salary` : '/people')}
              className="text-[13px] font-medium text-status-info-text hover:underline"
            >
              Open salary structure
            </Link>
          </div>
        ) : (
          <div className="space-y-4 border-t border-border pt-4">
            {employeeFields.length > 0 ? (
              <div>
                <p className="mb-2 text-[13px] font-medium text-text-primary">
                  Employee needs to add: {employeeFields.join(', ')}
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button variant="primary" onClick={runRemind}>
                    {issue.reminderSentOn ? 'Resend reminder' : 'Remind employee'}
                  </Button>
                  {issue.employeeId ? (
                    <Link
                      to={`/people/${issue.employeeId}?panel=missing#missing-details`}
                      className="inline-flex h-8 items-center rounded bg-text-primary px-3 text-[13px] font-medium text-white"
                    >
                      Add details
                    </Link>
                  ) : null}
                </div>
                {showAdd === 'employee' ? (
                  <div className="mt-3 space-y-2 rounded border border-border bg-canvas p-3">
                    <div className="flex flex-wrap gap-3">
                      {employeeFields.map((f) => (
                        <DemoField
                          key={f}
                          field={f}
                          value={values[f] ?? ''}
                          demo={issue.demoValues?.[f]}
                          error={
                            touched[f] || (values[f] ?? '').trim()
                              ? fieldError(f, values[f] ?? '')
                              : null
                          }
                          onChange={(v) => {
                            setValues((s) => ({ ...s, [f]: v }))
                            setTouched((s) => ({ ...s, [f]: true }))
                          }}
                        />
                      ))}
                    </div>
                    <Button
                      variant="primary"
                      disabled={!employeeAddValid}
                      onClick={() => openAddDetailsConfirm(employeeFields, 'add_details')}
                    >
                      Save & resolve
                    </Button>
                  </div>
                ) : null}
              </div>
            ) : null}

            {hrFields.length > 0 ? (
              <div>
                <p className="mb-2 text-[13px] font-medium text-text-primary">
                  You need to add: {hrFields.join(', ')}
                </p>
                {issue.employeeId ? (
                  <Link
                    to={`/people/${issue.employeeId}?panel=missing#missing-details`}
                    className="inline-flex h-8 items-center rounded bg-text-primary px-3 text-[13px] font-medium text-white"
                  >
                    Add details
                  </Link>
                ) : null}
                {showAdd === 'hr' ? (
                  <div className="mt-3 space-y-2 rounded border border-border bg-canvas p-3">
                    <div className="flex flex-wrap gap-3">
                      {hrFields.map((f) => (
                        <DemoField
                          key={f}
                          field={f}
                          value={values[f] ?? ''}
                          demo={issue.demoValues?.[f]}
                          onChange={(v) => setValues((s) => ({ ...s, [f]: v }))}
                        />
                      ))}
                    </div>
                    <Button
                      variant="primary"
                      disabled={hrFields.some((f) => !(values[f] || '').trim())}
                      onClick={() =>
                        saveFields(
                          Object.fromEntries(hrFields.map((f) => [f, values[f] || ''])),
                          'add_details',
                        )
                      }
                    >
                      Save
                    </Button>
                  </div>
                ) : null}
              </div>
            ) : null}

            <p className="text-[11px] text-text-muted opacity-70">Auto-sync fix back to Workday – V2</p>
          </div>
        )}
      </div>
    </div>
  )
}

const COUNTRY_PARAM: Record<string, string> = {
  IN: 'India',
  UK: 'UK',
  DE: 'Germany',
  BR: 'Brazil',
  India: 'India',
  Germany: 'Germany',
  Brazil: 'Brazil',
}

export function ActionsPage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const issues = useAppStore((s) => s.issues)
  const selectedIssue = useAppStore((s) => s.selectedIssue)
  const selectedIssueId = useAppStore((s) => s.selectedIssueId)
  const loadIssue = useAppStore((s) => s.loadIssue)
  const overview = useAppStore((s) => s.overview)
  const persona = useAppStore((s) => s.persona)
  const company = useAppStore((s) => s.company)
  const lockedCountry = personaCountry(persona, company)
  const lockedCode = seesAllCountries(persona) ? '' : persona

  const countryParam = lockedCode || params.get('country') || ''
  const countryFilter = lockedCountry || COUNTRY_PARAM[countryParam] || ''
  const openIssues = issues.filter((i) => {
    if (i.status !== 'open') return false
    if (countryFilter && i.country !== countryFilter) return false
    return true
  })
  const queryId = params.get('issue')
  const openIds = openIssues.map((issue) => issue.id).join(',')
  const detailIssue =
    selectedIssue && openIssues.some((issue) => issue.id === selectedIssue.id) ? selectedIssue : null

  useEffect(() => {
    const ids = openIds ? openIds.split(',') : []
    if (queryId && ids.includes(queryId)) {
      if (selectedIssueId !== queryId) void loadIssue(queryId)
      return
    }
    const next = new URLSearchParams()
    if (countryParam) next.set('country', countryParam)
    if (ids[0]) next.set('issue', ids[0])
    const search = next.toString()
    const target = search ? `/payroll/actions?${search}` : '/payroll/actions'
    if (`${window.location.pathname}${window.location.search}` !== target) {
      navigate(target, { replace: true })
    }
    if (!ids.length && selectedIssueId) {
      useAppStore.setState({ selectedIssue: null, selectedIssueId: null })
    }
  }, [queryId, openIds, selectedIssueId, countryParam, loadIssue, navigate])

  function select(id: string) {
    const next = new URLSearchParams(params)
    next.set('issue', id)
    navigate(`/payroll/actions?${next.toString()}`)
  }

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Action needed"
        subtitle={
          openIssues.length === 0
            ? countryFilter
              ? `No issues · ${countryFilter}`
              : 'No issues'
            : `${openIssues.length} open · blocking first, then by deadline`
        }
        actions={
          <label className="flex items-center gap-1.5 text-xs text-text-secondary">
            Country
            <select
              className="h-8 rounded border border-border bg-surface px-2 text-xs text-text-primary"
              value={countryParam}
              disabled={Boolean(lockedCode)}
              onChange={(e) => {
                const next = new URLSearchParams(params)
                if (e.target.value) next.set('country', e.target.value)
                else next.delete('country')
                next.delete('issue')
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
      <FinalReportNote />
      <ChangesReminder reminder={overview?.changesReminder} />

      {openIssues.length === 0 ? (
        <EmptyState
          title="No issues"
          description={
            countryFilter
              ? `No open issues for ${countryFilter} on this date.`
              : 'No open issues for this prototype date. Change the date or continue the demo.'
          }
        />
      ) : (
        <div className="grid grid-cols-12 gap-4">
          <div className="col-span-5 flex flex-col gap-2">
            <div className="flex items-center justify-between px-0.5">
              <span className="text-[11px] font-medium uppercase tracking-wide text-text-muted">
                Open issues{countryFilter ? ` · ${countryFilter}` : ''}
              </span>
              <GuidedInfo />
            </div>
            {openIssues.map((issue) => (
              <IssueListItem
                key={issue.id}
                issue={issue}
                selected={issue.id === (queryId || selectedIssueId)}
                onSelect={() => select(issue.id)}
              />
            ))}
          </div>
          <div className="col-span-7">
            {detailIssue ? (
              <IssueDetail issue={detailIssue} />
            ) : (
              <EmptyState
                title="Select an issue"
                description="Choose a row on the left to see impact and fix actions."
              />
            )}
          </div>
        </div>
      )}
    </div>
  )
}
