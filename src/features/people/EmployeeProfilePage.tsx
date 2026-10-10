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

      <PayrollPanel employee={employee} />
      <SalaryBlock employee={employee} open={panel === 'salary'} />
      <OneTimeBlock employee={employee} />
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

function SalaryBlock({ employee, open }: { employee: EmployeeDto; open: boolean }) {
  const salary = employee.salary
  const patchEmployee = useAppStore((s) => s.patchEmployee)
  const addOneTimePayment = useAppStore((s) => s.addOneTimePayment)
  const askConfirm = useAppStore((s) => s.askConfirm)
  const pushToast = useAppStore((s) => s.pushToast)
  const [edit, setEdit] = useState(open)
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

  async function save(confirmAi = false) {
    try {
      await patchEmployee(
        employee.id,
        { baseSalary: Number(base), allowances: Number(allowances), unpaidLeaveDays: Number(unpaid) },
        confirmAi,
      )
      pushToast('Salary updated')
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
      <dl className="mt-3 grid grid-cols-3 gap-3 text-[13px]">
        <Info label="Base salary" value={formatMoney(employee.currency, salary.base)} />
        <Info label="Allowances" value={formatMoney(employee.currency, salary.allowances)} />
        <Info label="One-time this cycle" value={formatMoney(employee.currency, salary.oneTimeTotal)} />
        <Info label="Deductions (unpaid leave)" value={formatMoney(employee.currency, salary.deductions)} />
        <Info label="Taxes" value={formatMoney(employee.currency, salary.tax)} />
        <Info label="Net pay" value={formatMoney(employee.currency, salary.net)} />
      </dl>
      <p className="mt-2 text-[11px] text-text-muted">Tax calculated by Multiplier</p>
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
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  )
}

function OneTimeBlock({ employee }: { employee: EmployeeDto }) {
  const addOneTimePayment = useAppStore((s) => s.addOneTimePayment)
  const askConfirm = useAppStore((s) => s.askConfirm)
  const cancelConfirm = useAppStore((s) => s.cancelConfirm)
  const setConfirmBusy = useAppStore((s) => s.setConfirmBusy)
  const setConfirmError = useAppStore((s) => s.setConfirmError)
  const pushToast = useAppStore((s) => s.pushToast)
  const [type, setType] = useState('Bonus')
  const [amountText, setAmountText] = useState('')
  const [amountValue, setAmountValue] = useState<number | null>(null)
  const [amountError, setAmountError] = useState(false)
  const [docName, setDocName] = useState<string | undefined>()

  function syncAmount(raw: string, blur = false) {
    const parsed = parseAmount(raw)
    setAmountValue(parsed)
    setAmountError(Boolean(raw.trim()) && parsed == null)
    if (blur && parsed != null) {
      setAmountText(formatAmountForCountry(employee.country, parsed))
    } else {
      setAmountText(raw)
    }
  }

  return (
    <section className="rounded border border-border bg-surface px-4 py-3">
      <h2 className="text-sm font-semibold">One-time payments</h2>
      <ul className="mt-2 text-[13px] text-text-secondary">
        {employee.oneOffs.length === 0 ? <li>None this cycle.</li> : null}
        {employee.oneOffs.map((o, i) => (
          <li key={i}>
            {o.label} · {formatMoney(employee.currency, o.amount)} · {o.cycleMonth}
            {o.cycleMonth && /Scheduled|December/i.test(String(o.cycleMonth)) ? (
              <span className="ml-1 rounded border border-border px-1 text-[10px] text-text-muted">
                Scheduled
              </span>
            ) : null}
          </li>
        ))}
      </ul>
      <div className="mt-3 space-y-3">
        <DriveAttach
          employeeId={employee.id}
          employeeName={employee.name}
          compact
          defaultType={type === 'Reimbursement' ? 'Reimbursement bill' : 'Bonus letter'}
          onExtracted={(name, mappings) => {
            setDocName(name)
            const amountRow = mappings.find((m) =>
              /amount|bonus|one-off|reimbursement/i.test(m.multiplierField || ''),
            )
            if (amountRow?.value) syncAmount(amountRow.value, true)
            if (/bonus/i.test(name) || /bonus/i.test(amountRow?.multiplierField || '')) {
              setType('Bonus')
            }
            if (/reimbursement|travel/i.test(name)) setType('Reimbursement')
          }}
        />
        <div className="flex flex-wrap items-end gap-2">
          <select
            className="h-8 rounded border border-border px-2 text-xs"
            value={type}
            onChange={(e) => setType(e.target.value)}
          >
            <option>Bonus</option>
            <option>Reimbursement</option>
            <option>Arrears</option>
            <option>Other</option>
          </select>
          <div className="flex flex-col gap-0.5">
            <input
              type="text"
              inputMode="decimal"
              className={[
                'h-8 w-36 rounded border px-2 text-xs',
                amountError ? 'border-status-danger-border' : 'border-border',
              ].join(' ')}
              placeholder="Amount"
              value={amountText}
              onChange={(e) => syncAmount(e.target.value)}
              onBlur={() => syncAmount(amountText, true)}
            />
            {amountError ? (
              <span className="text-[11px] text-status-danger-text">Enter a valid amount</span>
            ) : null}
          </div>
          <Button
            variant="primary"
            disabled={amountValue == null || amountError}
            onClick={() => {
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
                    { kind: 'otp', type, amount: amountValue, employeeId: employee.id },
                    asOf,
                  )
                  cycleLine = preview.confirmationMessage.replace(/\*\*/g, '')
                } catch {
                  cycleLine = ''
                }
                const body = [
                  `Add ${money} ${type.toLowerCase()} for ${employee.name}?`,
                  `Tax (${Math.round(taxRate * 100)}%, calculated by Multiplier): ${taxLabel} · Net to employee: ${netLabel}`,
                  cycleLine,
                ]
                  .filter(Boolean)
                  .join('\n')
                askConfirm({
                  title: 'Add one-time payment',
                  body,
                  onConfirm: async () => {
                  setConfirmBusy(true)
                  setConfirmError(null)
                  try {
                    await addOneTimePayment(employee.id, {
                      type,
                      amount: amountValue,
                      label: type === 'Bonus' ? 'Performance bonus' : type,
                      documentName: docName,
                    })
                    cancelConfirm()
                    setAmountText('')
                    setAmountValue(null)
                    setDocName(undefined)
                    pushToast(`${money} ${type.toLowerCase()} added`)
                  } catch (err) {
                    setConfirmError(err instanceof Error ? err.message : 'Could not add payment')
                  } finally {
                    setConfirmBusy(false)
                  }
                },
              })
              })()
            }}
          >
            Confirm
          </Button>
        </div>
      </div>
    </section>
  )
}

function ExitBlock({ employee, open }: { employee: EmployeeDto; open: boolean }) {
  const recordExit = useAppStore((s) => s.recordExit)
  const askConfirm = useAppStore((s) => s.askConfirm)
  const [show, setShow] = useState(open)
  const [lwd, setLwd] = useState('')
  const [reason, setReason] = useState('')
  const [notice, setNotice] = useState('0')
  const [severance, setSeverance] = useState('0')
  const [leave, setLeave] = useState('0')
  const [recoveries, setRecoveries] = useState('0')
  const exit = employee.exit as
    | { message?: string; fnf?: { net: number; tax: number; gross: number } }
    | null
    | undefined

  return (
    <section className="rounded border border-border bg-surface px-4 py-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Record exit</h2>
        <Button variant="secondary" onClick={() => setShow((v) => !v)}>
          {show ? 'Close' : 'Record exit'}
        </Button>
      </div>
      {exit?.message ? (
        <p className="mt-2 text-[13px] text-text-secondary">{exit.message}</p>
      ) : null}
      {show ? (
        <div className="mt-3 grid grid-cols-2 gap-2">
          <label className="text-xs">
            Last working day
            <input type="date" className="mt-1 h-8 w-full rounded border border-border px-2" value={lwd} onChange={(e) => setLwd(e.target.value)} />
          </label>
          <label className="text-xs">
            Reason
            <input className="mt-1 h-8 w-full rounded border border-border px-2" value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <label className="text-xs">
            Notice pay
            <input className="mt-1 h-8 w-full rounded border border-border px-2" value={notice} onChange={(e) => setNotice(e.target.value)} />
          </label>
          <label className="text-xs">
            Severance
            <input className="mt-1 h-8 w-full rounded border border-border px-2" value={severance} onChange={(e) => setSeverance(e.target.value)} />
          </label>
          <label className="text-xs">
            Leave encashment (days)
            <input className="mt-1 h-8 w-full rounded border border-border px-2" value={leave} onChange={(e) => setLeave(e.target.value)} />
          </label>
          <label className="text-xs">
            Recoveries
            <input className="mt-1 h-8 w-full rounded border border-border px-2" value={recoveries} onChange={(e) => setRecoveries(e.target.value)} />
          </label>
          <Button
            variant="primary"
            onClick={() =>
              askConfirm({
                title: 'Record exit',
                body: `Record ${employee.name}'s last working day as ${lwd}? The record is kept for FnF and filings.`,
                onConfirm: async () => {
                  await recordExit(employee.id, {
                    lastWorkingDay: lwd,
                    reason,
                    noticePay: Number(notice),
                    severance: Number(severance),
                    leaveEncashmentDays: Number(leave),
                    recoveries: Number(recoveries),
                  })
                },
              })
            }
          >
            Save exit
          </Button>
        </div>
      ) : null}
    </section>
  )
}
