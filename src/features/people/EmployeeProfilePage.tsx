import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { Button, EmptyState, PageHeader, StatusChip } from '@/components'
import { ClarityApiError } from '@/api/clarityClient'
import { formatIsoDate, formatMoney } from '@/features/payroll/lib/labels'
import { PayrollPanel } from '@/features/people/PayrollPanel'
import { DriveAttach } from '@/features/people/DriveAttach'
import { formatAmountForCountry, parseAmount } from '@/lib/parseAmount'
import { useAppStore } from '@/store'
import type { EmployeeDto } from '@/api/types'

export function EmployeeProfilePage() {
  const { id } = useParams<{ id: string }>()
  const [params] = useSearchParams()
  const panel = params.get('panel')
  const loadEmployee = useAppStore((s) => s.loadEmployee)
  const employee = useAppStore((s) => s.employeeDetail)
  const asOf = useAppStore((s) => s.asOf)
  const [composer, setComposer] = useState<'bonus' | 'hike' | null>(
    params.get('hike') === '1' ? 'hike' : params.get('bonus') === '1' ? 'bonus' : null,
  )

  useEffect(() => {
    if (id) void loadEmployee(id)
  }, [id, asOf, loadEmployee])

  if (!id) {
    return <EmptyState title="Missing employee" description="No employee id in the URL." />
  }
  if (!employee || employee.id !== id) {
    return (
      <EmptyState
        title="Loading employee…"
        description="Fetching profile and Payroll panel from Clarity API."
      />
    )
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <PageHeader title={employee.name} subtitle="HR tool employee profile" />
        <Link to="/people">
          <Button variant="secondary">All employees</Button>
        </Link>
      </div>

      {employee.payrollSnapshot?.lastSyncAt ? (
        <p className="text-[13px] text-text-secondary" data-testid="payroll-snapshot">
          Payroll snapshot · last synced {employee.payrollSnapshot.lastSyncAt}. Payroll figures update when
          Multiplier syncs from the HR tool.
        </p>
      ) : null}

      <section className="rounded border border-border bg-surface px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          {employee.isNew ? <StatusChip tone="info">New</StatusChip> : null}
          <StatusChip tone="neutral">{employee.status || 'Active'}</StatusChip>
          <StatusChip tone="neutral">{employee.source}</StatusChip>
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-[13px] md:grid-cols-4">
          <Info label="Role" value={employee.role} />
          <Info label="Location" value={employee.country} />
          <Info label="Hire date" value={employee.hireDate ? formatIsoDate(employee.hireDate) : '—'} />
          <Info
            label="Date added"
            value={employee.dateAdded ? formatIsoDate(employee.dateAdded) : 'Before cycle'}
          />
          <Info label="Work email" value={employee.workEmail ?? '—'} />
          <Info label="Manager" value={employee.managerName ?? '—'} />
          <Info
            label="Sept base"
            value={formatMoney(employee.currency, employee.septemberPay ?? employee.monthlyNet)}
          />
        </dl>
      </section>

      <PayrollPanel employee={employee} composer={composer} onComposer={setComposer}>
        {composer === 'bonus' ? <OneTimeBlock employee={employee} mode="bonus" /> : null}
        {composer === 'hike' ? <OneTimeBlock employee={employee} mode="hike" /> : null}
      </PayrollPanel>
      <SalaryBlock employee={employee} open={panel === 'salary'} />
      <ExitBlock employee={employee} open={panel === 'exit'} />
    </div>
  )
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-text-muted">{label}</dt>
      <dd className="font-medium text-text-primary">{value}</dd>
    </div>
  )
}

function Deductibles({ employee }: { employee: EmployeeDto }) {
  const cut = employee.payAdjustment
  if (!cut) return null
  const llm = cut.llmDecision
  const llmApprove = llm?.recommend === 'approve'
  return (
    <div className="mt-4 space-y-3 border-t border-border pt-3" data-testid="deductibles">
      <h3 className="text-[13px] font-semibold text-text-primary">Deductibles</h3>
      <div
        className="rounded border border-status-warn-border bg-status-warn-bg px-3 py-2.5 text-[13px] text-status-warn-text"
        data-testid="pay-cut-warning"
      >
        <p className="font-medium">{cut.whyFlagged || cut.label}</p>
        {cut.matchingSource ? (
          <p className="mt-1 text-[12px]">Matched to {cut.matchingSource}</p>
        ) : null}
        {llm ? (
          <div className="mt-2">
            <span
              className={[
                'inline-flex rounded border px-1.5 py-0.5 text-[11px] font-medium',
                llmApprove
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                  : 'border-status-warn-border bg-white text-status-warn-text',
              ].join(' ')}
            >
              {llmApprove ? 'Approve' : 'Hold'}
              {llm.source === 'llm'
                ? ` · ${Math.round((llm.confidence || 0) * 100)}%`
                : llm.source === 'fallback'
                  ? ' · fallback'
                  : ''}
            </span>
            {llm.reason ? <p className="mt-1 text-[12px] leading-snug">{llm.reason}</p> : null}
          </div>
        ) : null}
      </div>
      <table className="w-full text-left text-[13px]">
        <thead>
          <tr className="text-[11px] uppercase tracking-wide text-text-muted">
            <th className="py-1 font-medium">Deduction</th>
            <th className="py-1 font-medium">Change</th>
            <th className="py-1 font-medium">Amount</th>
            <th className="py-1 font-medium">Matched to</th>
          </tr>
        </thead>
        <tbody>
          <tr className="border-t border-border">
            <td className="py-1.5 text-text-primary">{cut.whyFlagged || cut.label}</td>
            <td className="py-1.5 tabular text-text-secondary">{cut.changeSummary || '—'}</td>
            <td className="py-1.5 tabular font-medium text-text-primary">
              {formatMoney(employee.currency, cut.amount)}
            </td>
            <td className="py-1.5 text-text-secondary">{cut.matchingSource || '—'}</td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}

function SalaryBlock({
  employee,
  open,
}: {
  employee: EmployeeDto
  open: boolean
}) {
  const salary = employee.salary
  const patchEmployee = useAppStore((s) => s.patchEmployee)
  const addOneTimePayment = useAppStore((s) => s.addOneTimePayment)
  const askConfirm = useAppStore((s) => s.askConfirm)
  const pushToast = useAppStore((s) => s.pushToast)
  const [edit, setEdit] = useState(open)
  const [showHike, setShowHike] = useState(false)
  const [base, setBase] = useState(String(salary?.base ?? ''))
  const [allowances, setAllowances] = useState(String(salary?.allowances ?? 0))
  const [unpaid, setUnpaid] = useState(String(salary?.unpaidLeaveDays ?? 0))

  useEffect(() => {
    setEdit(open)
    setBase(String(employee.salary?.base ?? ''))
    setAllowances(String(employee.salary?.allowances ?? 0))
    setUnpaid(String(employee.salary?.unpaidLeaveDays ?? 0))
  }, [employee.id, employee.salary?.base, open])

  if (!salary) return null

  const newBonus = employee.oneOffs
    .filter((o) => o.type === 'Bonus' || /bonus/i.test(o.label))
    .reduce((sum, o) => sum + o.amount, 0)
  const previousBase = employee.septemberPay ?? salary.base
  const newHike = Math.max(0, salary.base - previousBase)
  const exitPay = employee.exit as
    | { fnf?: { net: number; daysWorked?: number }; message?: string; onHold?: boolean }
    | null
    | undefined
  const finalAmount = exitPay?.fnf ? exitPay.fnf.net : salary.net

  async function save(confirmAi = false) {
    try {
      const sept = employee.septemberPay
      const current = employee.salary?.base
      const confirmingSpike =
        confirmAi && sept != null && current != null && current > sept * 1.5
      await patchEmployee(
        employee.id,
        { baseSalary: Number(base), allowances: Number(allowances), unpaidLeaveDays: Number(unpaid) },
        confirmAi,
      )
      pushToast(confirmingSpike ? 'Salary confirmed · issue resolved' : 'Salary updated')
      setEdit(false)
    } catch (err) {
      if (err instanceof ClarityApiError && err.status === 409) {
        const body = err.body as { aiCheck?: { message: string } }
        askConfirm({
          title: 'AI check',
          body: body.aiCheck?.message || err.message,
          confirmLabel: "It's correct",
          cancelLabel: 'Let me fix it',
          onConfirm: () => save(true),
        })
        return
      }
      throw err
    }
  }

  return (
    <section className="rounded border border-border bg-surface px-4 py-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Salary structure</h2>
        <Button variant="secondary" onClick={() => setEdit((v) => !v)}>
          {edit ? 'Close' : 'Edit'}
        </Button>
      </div>
      <dl className="mt-3 grid grid-cols-3 gap-3 text-[13px]" data-testid="salary-summary">
        <Info label="New bonus" value={formatMoney(employee.currency, newBonus)} />
        <Info label="New hike" value={formatMoney(employee.currency, newHike)} />
        <Info
          label={exitPay?.fnf?.daysWorked ? `Final amount (${exitPay.fnf.daysWorked} days)` : 'Final amount'}
          value={formatMoney(employee.currency, finalAmount)}
        />
      </dl>
      <dl className="mt-3 grid grid-cols-3 gap-3 border-t border-border pt-3 text-[13px]">
        <Info label="Base salary" value={formatMoney(employee.currency, salary.base)} />
        <Info label="Allowances" value={formatMoney(employee.currency, salary.allowances)} />
        <Info label="One-time this cycle" value={formatMoney(employee.currency, salary.oneTimeTotal)} />
        <Info label="Deductions (unpaid leave)" value={formatMoney(employee.currency, salary.deductions)} />
        <Info label="Taxes" value={formatMoney(employee.currency, salary.tax)} />
        <Info
          label={exitPay?.fnf?.daysWorked ? `Prorated pay (${exitPay.fnf.daysWorked} days)` : 'Net pay'}
          value={formatMoney(employee.currency, exitPay?.fnf ? exitPay.fnf.net : salary.net)}
        />
      </dl>
      {exitPay?.message ? (
        <p className="mt-2 text-[12px] text-text-secondary" data-testid="exit-pay-note">
          {exitPay.message}
        </p>
      ) : (
        <p className="mt-2 text-[11px] text-text-muted">Tax calculated by Multiplier</p>
      )}
      {employee.payAdjustment ? <Deductibles employee={employee} /> : null}
      {edit ? (
        <div className="mt-3 grid grid-cols-3 gap-2">
          <label className="text-xs text-text-secondary">
            Base
            <input className="mt-1 h-8 w-full rounded border border-border px-2 text-[13px]" value={base} onChange={(e) => setBase(e.target.value)} />
          </label>
          <label className="text-xs text-text-secondary">
            Allowances
            <input className="mt-1 h-8 w-full rounded border border-border px-2 text-[13px]" value={allowances} onChange={(e) => setAllowances(e.target.value)} />
          </label>
          <label className="text-xs text-text-secondary">
            Unpaid leave days
            <input className="mt-1 h-8 w-full rounded border border-border px-2 text-[13px]" value={unpaid} onChange={(e) => setUnpaid(e.target.value)} />
          </label>
          <div className="col-span-3 flex gap-2">
            <Button
              variant="primary"
              onClick={() =>
                askConfirm({
                  title: 'Update pay',
                  body: `Update ${employee.name}'s pay to ${formatMoney(employee.currency, Number(base) || 0)}?`,
                  onConfirm: () => save(false),
                })
              }
            >
              Save
            </Button>
            {employee.septemberPay != null &&
            employee.salary?.base != null &&
            employee.salary.base > employee.septemberPay * 1.4 ? (
              <>
                <Button
                  variant="secondary"
                  onClick={() => {
                    const sept = employee.septemberPay!
                    const bonus = Math.max(0, employee.salary!.base - sept)
                    setBase(String(sept))
                    void addOneTimePayment(employee.id, {
                      type: 'Bonus',
                      label: 'Performance bonus',
                      amount: bonus,
                    }).then(() =>
                      patchEmployee(employee.id, { baseSalary: sept }, true),
                    )
                  }}
                >
                  Split to base + bonus
                </Button>
                <Button variant="secondary" onClick={() => setShowHike((v) => !v)}>
                  {showHike ? 'Hide salary hike' : 'Salary hike + bonus'}
                </Button>
              </>
            ) : null}
          </div>
        </div>
      ) : null}
      {showHike ? (
        <div className="mt-3 space-y-2" data-testid="salary-hike-panel">
          <p className="text-[12px] text-text-secondary">
            Upload a salary revision letter that states the new monthly base and the
            bonus. That proves the hike. The salary issue closes as soon as the letter
            is read.
          </p>
          <DriveAttach
            employeeId={employee.id}
            employeeName={employee.name}
            defaultType="Salary revision letter"
            onExtracted={() =>
              pushToast('Salary hike and bonus saved from the letter · issue resolved')
            }
          />
        </div>
      ) : null}
    </section>
  )
}

function OneTimeBlock({ employee, mode }: { employee: EmployeeDto; mode: 'bonus' | 'hike' }) {
  const addOneTimePayment = useAppStore((s) => s.addOneTimePayment)
  const askConfirm = useAppStore((s) => s.askConfirm)
  const cancelConfirm = useAppStore((s) => s.cancelConfirm)
  const setConfirmBusy = useAppStore((s) => s.setConfirmBusy)
  const setConfirmError = useAppStore((s) => s.setConfirmError)
  const pushToast = useAppStore((s) => s.pushToast)
  const [amountText, setAmountText] = useState('')
  const [amountValue, setAmountValue] = useState<number | null>(null)
  const [amountError, setAmountError] = useState(false)

  function syncField(
    raw: string,
    blur: boolean,
    setText: (value: string) => void,
    setValue: (value: number | null) => void,
    setError: (value: boolean) => void,
  ) {
    const parsed = parseAmount(raw)
    setValue(parsed)
    setError(Boolean(raw.trim()) && parsed == null)
    if (blur && parsed != null) {
      setText(formatAmountForCountry(employee.country, parsed))
    } else {
      setText(raw)
    }
  }

  function syncAmount(raw: string, blur = false) {
    syncField(raw, blur, setAmountText, setAmountValue, setAmountError)
  }

  function submitBonus() {
    if (amountValue == null) return
    const asOf = useAppStore.getState().asOf
    const money = formatMoney(employee.currency, amountValue)
    const taxRate = employee.salary?.taxRate ?? 0.1
    const tax = Math.round(amountValue * taxRate)
    const net = amountValue - tax
    const taxLabel = formatMoney(employee.currency, tax)
    const netLabel = formatMoney(employee.currency, net)
    void (async () => {
      const { clarityApi } = await import('@/api/clarityClient')
      let cycleLine = ''
      try {
        const preview = await clarityApi.previewInput(
          { kind: 'otp', type: 'Bonus', amount: amountValue, employeeId: employee.id },
          asOf,
        )
        cycleLine = preview.confirmationMessage.replace(/\*\*/g, '')
      } catch {
        cycleLine = ''
      }
      const body = [
        `Add ${money} bonus for ${employee.name}?`,
        `Tax (${Math.round(taxRate * 100)}%, calculated by Multiplier): ${taxLabel} · Net to employee: ${netLabel}`,
        cycleLine,
      ]
        .filter(Boolean)
        .join('\n')
      askConfirm({
        title: 'Add bonus',
        body,
        onConfirm: async () => {
          setConfirmBusy(true)
          setConfirmError(null)
          try {
            await addOneTimePayment(employee.id, {
              type: 'Bonus',
              amount: amountValue,
              label: 'Performance bonus',
            })
            cancelConfirm()
            setAmountText('')
            setAmountValue(null)
            pushToast(`${money} bonus added`)
          } catch (err) {
            setConfirmError(err instanceof Error ? err.message : 'Could not add bonus')
          } finally {
            setConfirmBusy(false)
          }
        },
      })
    })()
  }

  function submitHike() {
    if (amountValue == null) return
    const money = formatMoney(employee.currency, amountValue)
    const run = async (confirmed: boolean) => {
      setConfirmBusy(true)
      setConfirmError(null)
      try {
        const patchEmployee = useAppStore.getState().patchEmployee
        await patchEmployee(
          employee.id,
          {
            baseSalary: amountValue,
            allowances: employee.salary?.allowances ?? 0,
            unpaidLeaveDays: employee.salary?.unpaidLeaveDays ?? 0,
          },
          confirmed,
        )
        cancelConfirm()
        setAmountText('')
        setAmountValue(null)
        pushToast(employee.saveMessage || 'Saved in HR tool')
      } catch (err) {
        if (err instanceof ClarityApiError && err.status === 409) {
          const body = err.body as { aiCheck?: { message: string } }
          setConfirmBusy(false)
          askConfirm({
            title: 'AI check',
            body: body.aiCheck?.message || err.message,
            confirmLabel: "It's correct",
            cancelLabel: 'Let me fix it',
            onConfirm: () => run(true),
          })
          return
        }
        setConfirmError(err instanceof Error ? err.message : 'Could not save hike')
      } finally {
        setConfirmBusy(false)
      }
    }
    askConfirm({
      title: 'New monthly salary',
      body: `Save ${employee.name}'s new monthly salary of ${money} in the HR tool? Payroll updates on the next sync.`,
      onConfirm: () => run(false),
    })
  }

  return (
    <section
      className="rounded border border-border bg-surface px-4 py-3"
      data-testid={mode === 'hike' ? 'salary-hike-letter' : 'add-bonus-panel'}
    >
      <p className="text-[13px] text-text-secondary">
        {mode === 'hike'
          ? `Set ${employee.name}'s new monthly salary. That amount is the hike. Or attach a salary revision letter and we'll read the new salary.`
          : `Add a bonus for ${employee.name}. Enter the amount, or attach a bonus letter and we'll read it.`}
      </p>
      <div className="mt-3 flex flex-wrap items-start gap-2">
        <div className="flex flex-col gap-0.5">
          <input
            type="text"
            inputMode="decimal"
            aria-label={mode === 'hike' ? 'New monthly salary' : 'Amount'}
            className={[
              'h-8 w-40 rounded border px-2 text-xs',
              amountError ? 'border-status-danger-border' : 'border-border',
            ].join(' ')}
            placeholder={mode === 'hike' ? 'New monthly salary' : 'Amount'}
            value={amountText}
            onChange={(e) => syncAmount(e.target.value)}
            onBlur={() => syncAmount(amountText, true)}
          />
          {amountError ? (
            <span className="text-[11px] text-status-danger-text">Enter a valid amount</span>
          ) : null}
        </div>
        <Button
          variant="secondary"
          disabled={amountValue == null || amountError}
          onClick={() => (mode === 'hike' ? submitHike() : submitBonus())}
        >
          {mode === 'hike' ? 'Add hike' : 'Add bonus'}
        </Button>
      </div>
      <div className="mt-3">
        <DriveAttach
          employeeId={employee.id}
          employeeName={employee.name}
          lockType
          defaultType={mode === 'hike' ? 'Salary revision letter' : 'Bonus letter'}
          onExtracted={() =>
            pushToast(
              mode === 'hike' ? 'Salary hike saved from the letter' : 'Bonus saved from the letter',
            )
          }
        />
      </div>
    </section>
  )
}

function ExitBlock({ employee, open }: { employee: EmployeeDto; open: boolean }) {
  const recordExit = useAppStore((s) => s.recordExit)
  const undoExit = useAppStore((s) => s.undoExit)
  const askConfirm = useAppStore((s) => s.askConfirm)
  const setConfirmBusy = useAppStore((s) => s.setConfirmBusy)
  const setConfirmError = useAppStore((s) => s.setConfirmError)
  const asOf = useAppStore((s) => s.asOf)
  const cycle = useAppStore((s) => s.overview?.cycle)
  const exit = employee.exit as
    | {
        message?: string
        lastWorkingDay?: string
        onHold?: boolean
        payMonth?: string
        daysWorked?: number
        fnf?: { net: number; tax: number; gross: number; daysWorked?: number }
      }
    | null
    | undefined
  const removed = employee.status === 'Removed' || employee.status === 'Exiting' || Boolean(exit)

  function fnfPreview() {
    const base = employee.salary?.base ?? 0
    const day = Number(asOf.slice(-2)) || 1
    const days = Math.max(0, Math.min(30, day))
    const prorated = Math.round((base * days) / 30 * 100) / 100
    const rate = employee.salary?.taxRate ?? 0
    const tax = Math.round(Math.max(0, prorated) * rate * 100) / 100
    return { net: Math.round((prorated - tax) * 100) / 100, days }
  }

  return (
    <section
      className="rounded border border-border bg-surface px-4 py-3"
      data-testid="record-exit"
      data-open={open ? 'true' : 'false'}
    >
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold">Record exit</h2>
        {removed ? (
          <Button
            variant="secondary"
            data-testid="undo-exit"
            onClick={() =>
              askConfirm({
                title: 'Undo exit',
                body: `Put ${employee.name} back on payroll? The exit and full and final payment come off Review & approve.`,
                confirmLabel: 'Undo',
                onConfirm: async () => {
                  setConfirmBusy(true)
                  setConfirmError(null)
                  try {
                    await undoExit(employee.id)
                  } catch (err) {
                    setConfirmError(err instanceof Error ? err.message : 'Could not undo exit')
                  } finally {
                    setConfirmBusy(false)
                  }
                },
              })
            }
          >
            Undo
          </Button>
        ) : (
          <Button
            variant="primary"
            data-testid="record-exit-button"
            onClick={() => {
              const preview = fnfPreview()
              const money = formatMoney(employee.currency, preview.net)
              const month = (cycle?.label || 'This month').split(' ')[0]
              const afterLock = Boolean(cycle?.inputFinalisation && asOf > cycle.inputFinalisation)
              const timing = afterLock
                ? `${month} pay is on hold because this exit is after the lock-in date. The prorated ${preview.days} days (${money}) will be paid next month.`
                : `Only ${preview.days} days (${money}) are paid in ${month}.`
              askConfirm({
                title: 'Record exit',
                body: `Remove ${employee.name} from payroll? Last working day is ${formatIsoDate(asOf)}. ${timing} The full monthly salary is not paid. You can undo this.`,
                confirmLabel: 'Remove',
                onConfirm: async () => {
                  setConfirmBusy(true)
                  setConfirmError(null)
                  try {
                    await recordExit(employee.id, { lastWorkingDay: asOf, reason: 'Exit' })
                  } catch (err) {
                    setConfirmError(err instanceof Error ? err.message : 'Could not record exit')
                  } finally {
                    setConfirmBusy(false)
                  }
                },
              })
            }}
          >
            Record exit
          </Button>
        )}
      </div>
      {removed && exit ? (
        <div className="mt-3 text-[13px] text-text-secondary">
          <p>{exit.message}</p>
          {exit.fnf ? (
            <dl className="mt-3 grid grid-cols-3 gap-3" data-testid="fnf-summary">
              <Info label="Full and final" value={formatMoney(employee.currency, exit.fnf.net)} />
              <Info label="Gross" value={formatMoney(employee.currency, exit.fnf.gross)} />
              <Info label="Tax" value={formatMoney(employee.currency, exit.fnf.tax)} />
            </dl>
          ) : null}
          {exit.lastWorkingDay ? (
            <p className="mt-2 text-[11px] text-text-muted">
              Last working day {formatIsoDate(exit.lastWorkingDay)}
            </p>
          ) : null}
        </div>
      ) : (
        <p className="mt-2 text-[13px] text-text-secondary">
          Removes {employee.name} from the people list and adds an exit with full and final pay on
          Review &amp; approve.
        </p>
      )}
    </section>
  )
}
