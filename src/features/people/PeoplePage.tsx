import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Button, PageHeader, StatusChip } from '@/components'
import { PeopleTabs } from '@/features/people/PeopleTabs'
import { formatIsoDate } from '@/features/payroll/lib/labels'
import { clarityApi } from '@/api/clarityClient'
import { useAppStore } from '@/store'
import type { Country, EmployeeDto } from '@/api/types'

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('')
}

const flagClass: Record<string, string> = {
  ok: 'border-status-ok-border bg-status-ok-bg text-status-ok-text',
  warn: 'border-status-warn-border bg-status-warn-bg text-status-warn-text',
  danger: 'border-status-danger-border bg-status-danger-bg text-status-danger-text',
  info: 'border-status-info-border bg-status-info-bg text-status-info-text',
}

function payTone(emp: EmployeeDto): 'ok' | 'warn' | 'danger' | 'info' {
  const t = emp.payOutlook?.tone
  if (t === 'warn') return 'warn'
  if (t === 'danger') return 'danger'
  if (t === 'info') return 'info'
  return 'ok'
}

function payText(emp: EmployeeDto): string {
  if (emp.payOutlook?.display) {
    return emp.payOutlook.note
      ? `${emp.payOutlook.display} · ${emp.payOutlook.note}`
      : emp.payOutlook.display
  }
  return emp.ifNoActionWillBePaid || emp.payTiming.message
}

export function PeoplePage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const asOf = useAppStore((s) => s.asOf)
  const overview = useAppStore((s) => s.overview)
  const pushToast = useAppStore((s) => s.pushToast)
  const askConfirm = useAppStore((s) => s.askConfirm)
  const reopenReview = useAppStore((s) => s.reopenReview)

  const country = (params.get('country') as Country | null) || 'all'
  const action = params.get('action') || 'all'
  const filter = params.get('filter') || ''
  const q = params.get('q') || ''
  const status = params.get('status') || 'all'
  const hint = params.get('hint')
  const page = Math.max(1, parseInt(params.get('page') || '1', 10) || 1)
  const pageSize = [25, 50, 100].includes(parseInt(params.get('pageSize') || '25', 10))
    ? parseInt(params.get('pageSize') || '25', 10)
    : 25

  const [rows, setRows] = useState<EmployeeDto[]>([])
  const [total, setTotal] = useState(0)
  const [busy, setBusy] = useState(false)

  function setParam(key: string, value: string, resetPage = true) {
    const next = new URLSearchParams(params)
    if (!value || value === 'all') next.delete(key)
    else next.set(key, value)
    if (resetPage && key !== 'page') next.set('page', '1')
    setParams(next)
  }

  useEffect(() => {
    let cancelled = false
    setBusy(true)
    void clarityApi
      .getEmployees(asOf, {
        country: country === 'all' ? undefined : country,
        actionNeeded: action === 'yes' ? true : action === 'no' ? false : undefined,
        q: q || undefined,
        status: status === 'all' ? undefined : status,
        filter: filter || undefined,
        page,
        pageSize,
      })
      .then((res) => {
        if (cancelled) return
        setRows(res.employees)
        setTotal(res.total ?? res.count)
      })
      .finally(() => {
        if (!cancelled) setBusy(false)
      })
    return () => {
      cancelled = true
    }
  }, [asOf, country, action, filter, q, status, page, pageSize])

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const safePage = Math.min(page, totalPages)
  const from = total === 0 ? 0 : (safePage - 1) * pageSize + 1
  const to = Math.min(safePage * pageSize, total)
  const showMatched = filter === 'reconciled'
  const customerName = overview?.customer.name

  const pageButtons = (() => {
    const pages: number[] = []
    const maxShow = 5
    let start = Math.max(1, safePage - 2)
    const end = Math.min(totalPages, start + maxShow - 1)
    start = Math.max(1, end - maxShow + 1)
    for (let i = start; i <= end; i++) pages.push(i)
    return pages
  })()

  return (
    <div className="flex flex-col gap-4">
      <PeopleTabs />
      <PageHeader
        title="Employees"
        subtitle={`${total} in cycle · new joiners at the top`}
      />
      {hint ? (
        <p className="rounded border border-status-info-border bg-status-info-bg px-3 py-2 text-xs text-status-info-text">
          Pick an employee to {hint === 'exit' ? 'record an exit' : 'add a one-time payment'}.
        </p>
      ) : null}

      <div className="rounded border border-border bg-surface">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-3 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <input
              className="h-8 min-w-[180px] rounded border border-border bg-surface px-2 text-xs text-text-primary placeholder:text-text-muted focus:border-text-primary focus:outline-none"
              placeholder="Filter by name…"
              value={q}
              onChange={(e) => setParam('q', e.target.value)}
            />
            <select
              className="h-8 rounded border border-border bg-surface px-2 text-xs"
              value={country}
              onChange={(e) => setParam('country', e.target.value)}
            >
              <option value="all">All countries</option>
              {(['India', 'UK', 'Germany', 'Brazil'] as Country[]).map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <select
              className="h-8 rounded border border-border bg-surface px-2 text-xs"
              value={action}
              onChange={(e) => setParam('action', e.target.value)}
            >
              <option value="all">All action statuses</option>
              <option value="yes">Action needed: Yes</option>
              <option value="no">Action needed: No</option>
            </select>
            <select
              className="h-8 rounded border border-border bg-surface px-2 text-xs"
              value={filter}
              onChange={(e) => setParam('filter', e.target.value)}
            >
              <option value="">All</option>
              <option value="changed">Changed this cycle</option>
              <option value="reconciled">Auto-reconciled</option>
              <option value="edited">Edited by you</option>
              <option value="paid_october">Paid on last pay date</option>
            </select>
            <select
              className="h-8 rounded border border-border bg-surface px-2 text-xs"
              value={status}
              onChange={(e) => setParam('status', e.target.value)}
            >
              <option value="all">Status: all</option>
              <option value="Active">Active</option>
              <option value="Exiting">Exiting</option>
              <option value="Exited">Exited</option>
            </select>
            <Button variant="secondary" onClick={() => setParams(new URLSearchParams())}>
              Reset
            </Button>
          </div>
          <span className="tabular text-xs text-text-secondary">
            {busy ? 'Loading…' : null}
            {customerName ? ` · ${customerName}` : null}
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full table-fixed border-collapse text-left">
            <colgroup>
              <col className="w-[22%]" />
              <col className="w-[8%]" />
              <col className="w-[16%]" />
              <col className="w-[10%]" />
              <col className="w-[18%]" />
              <col className="w-[8%]" />
              <col className="w-[18%]" />
            </colgroup>
            <thead>
              <tr className="h-8 bg-surface-recessed text-[11px] font-medium uppercase tracking-wide text-text-secondary">
                <th className="px-3 py-1 font-medium">Employee</th>
                <th className="px-3 py-1 font-medium">Country</th>
                <th className="px-3 py-1 font-medium">Role</th>
                <th className="px-3 py-1 font-medium">Date added</th>
                <th className="px-3 py-1 font-medium">Pay status</th>
                <th className="px-3 py-1 font-medium">Action needed</th>
                <th className="px-3 py-1 font-medium">Pay this cycle</th>
                {showMatched ? <th className="px-3 py-1 font-medium">Matched source</th> : null}
                {showMatched ? <th className="px-3 py-1 font-medium">Actions</th> : null}
              </tr>
            </thead>
            <tbody>
              {rows.map((emp) => {
                const tone = payTone(emp)
                return (
                  <tr
                    key={emp.id}
                    className="cursor-pointer border-b border-border last:border-b-0 hover:bg-canvas"
                    onClick={() =>
                      navigate(
                        `/people/${emp.id}${hint === 'one-time' ? '?panel=salary' : hint === 'exit' ? '?panel=exit' : ''}`,
                      )
                    }
                  >
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-2.5">
                        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-surface-recessed text-[11px] font-semibold">
                          {initials(emp.name)}
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span className="truncate text-[13px] font-semibold text-text-primary">
                              {emp.name}
                            </span>
                            {emp.isNew ? <StatusChip tone="info">New</StatusChip> : null}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="truncate px-3 py-2.5 text-[13px]" title={emp.country}>
                      {emp.country}
                    </td>
                    <td className="truncate px-3 py-2.5 text-[13px] text-text-secondary" title={emp.role}>
                      {emp.role}
                    </td>
                    <td className="px-3 py-2.5 tabular text-[13px] text-text-secondary">
                      {emp.dateAdded ? formatIsoDate(emp.dateAdded) : 'Before cycle'}
                    </td>
                    <td className="px-3 py-2.5">
                      <span
                        className={`inline-block rounded border px-1.5 py-0.5 text-[11px] font-medium leading-snug ${flagClass[tone]}`}
                        title={emp.payTiming.message}
                      >
                        {emp.payTiming.message}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      <StatusChip tone={emp.actionNeeded ? 'warn' : 'ok'}>
                        {emp.actionNeeded ? 'Yes' : 'No'}
                      </StatusChip>
                    </td>
                    <td className="px-3 py-2.5">
                      <span
                        className={`inline-block rounded border px-1.5 py-0.5 text-[11px] font-medium leading-snug ${flagClass[tone]}`}
                        title={payText(emp)}
                      >
                        {payText(emp)}
                      </span>
                    </td>
                    {showMatched ? (
                      <td className="truncate px-3 py-2.5 text-[13px] text-text-secondary" title={emp.matchedSource ?? ''}>
                        {emp.matchedSource ?? '—'}
                      </td>
                    ) : null}
                    {showMatched ? (
                      <td className="px-3 py-2.5">
                        {emp.matchedSource ? (
                          <Button
                            variant="primary"
                            onClick={(e) => {
                              e.stopPropagation()
                              askConfirm({
                                title: 'Reopen for review',
                                body: `Move ${emp.name} into Need your check? Their matched source will be cleared.`,
                                onConfirm: async () => {
                                  await reopenReview(emp.id)
                                },
                              })
                            }}
                          >
                            Reopen for review
                          </Button>
                        ) : (
                          <span className="text-xs text-text-muted">—</span>
                        )}
                      </td>
                    ) : null}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-3 py-2.5">
          <p
            className="tabular text-xs text-text-secondary"
            data-testid="people-pagination"
          >
            Showing {from}–{to} of {total}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              disabled={safePage <= 1}
              onClick={() => setParam('page', String(safePage - 1), false)}
            >
              Previous
            </Button>
            {pageButtons.map((p) => (
              <button
                key={p}
                type="button"
                className={[
                  'h-8 min-w-[28px] rounded px-2 text-xs',
                  p === safePage
                    ? 'bg-text-primary font-medium text-white'
                    : 'border border-border text-text-secondary hover:bg-surface-recessed',
                ].join(' ')}
                onClick={() => setParam('page', String(p), false)}
              >
                {p}
              </button>
            ))}
            <Button
              variant="secondary"
              disabled={safePage >= totalPages}
              onClick={() => setParam('page', String(safePage + 1), false)}
            >
              Next
            </Button>
            <select
              className="h-8 rounded border border-border bg-surface px-2 text-xs"
              value={pageSize}
              onChange={(e) => setParam('pageSize', e.target.value)}
              aria-label="Rows per page"
              data-testid="people-page-size"
            >
              <option value="25">25 / page</option>
              <option value="50">50 / page</option>
              <option value="100">100 / page</option>
            </select>
          </div>
        </div>

        <p className="border-t border-border px-3 py-2.5 text-xs text-text-secondary">
          Changes added on or before the input finalisation date are included in this run. Later
          changes move to the next cycle.
        </p>
      </div>
    </div>
  )
}
