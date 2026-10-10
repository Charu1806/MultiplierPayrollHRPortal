import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, PageHeader, StatusChip } from '@/components'
import { formatIsoDate, formatMoney } from '@/features/payroll/lib/labels'
import { useAppStore } from '@/store'
import type { Country, EmployeeDto } from '@/api/types'

type CountryFilter = 'all' | Country
type ActionFilter = 'all' | 'yes' | 'no'

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('')
}

function formatOneOff(emp: EmployeeDto): string | null {
  if (!emp.oneOffs.length) return null
  return emp.oneOffs
    .map((o) => {
      const month =
        o.cycleMonth?.replace(/\s*\d{4}\s*/, '').trim() ||
        o.cycleMonth ||
        'this cycle'
      const label = /bonus/i.test(o.label) ? 'Bonus' : o.label
      return `${label} ${formatMoney(emp.currency, o.amount)} (one-off) · ${month}`
    })
    .join('; ')
}

const flagClass: Record<'ok' | 'warn' | 'danger' | 'info' | 'neutral', string> = {
  ok: 'border-status-ok-border bg-status-ok-bg text-status-ok-text',
  warn: 'border-status-warn-border bg-status-warn-bg text-status-warn-text',
  danger: 'border-status-danger-border bg-status-danger-bg text-status-danger-text',
  info: 'border-status-info-border bg-status-info-bg text-status-info-text',
  neutral: 'border-border bg-surface-recessed text-text-secondary',
}

function payCell(emp: EmployeeDto): {
  text: string
  tone: 'ok' | 'warn' | 'danger' | 'info' | 'neutral'
  showOffCycle: boolean
} {
  const oneOff = formatOneOff(emp)
  if (oneOff) {
    return { text: oneOff, tone: 'info', showOffCycle: false }
  }

  const level = emp.payTiming.level
  if (level === 'amber') {
    return {
      text: emp.payTiming.message,
      tone: 'warn',
      showOffCycle: emp.payTiming.showOffCycleStub,
    }
  }
  if (level === 'red') {
    return {
      text: emp.payTiming.message,
      tone: 'danger',
      showOffCycle: emp.payTiming.showOffCycleStub,
    }
  }

  if (emp.ifNoActionWillBePaid) {
    return {
      text: `If no action: will be paid ${emp.ifNoActionWillBePaid}`,
      tone: 'ok',
      showOffCycle: false,
    }
  }

  return {
    text: emp.payTiming.message,
    tone: 'ok',
    showOffCycle: false,
  }
}

function EmployeeRow({
  emp,
  onOpen,
  onOffCycle,
}: {
  emp: EmployeeDto
  onOpen: () => void
  onOffCycle: () => void
}) {
  const pay = payCell(emp)
  const clickable = emp.isNew

  return (
    <tr
      className={[
        'border-b border-border last:border-b-0',
        clickable ? 'cursor-pointer hover:bg-canvas' : 'hover:bg-canvas/60',
      ].join(' ')}
      onClick={() => {
        if (clickable) onOpen()
      }}
    >
      <td className="px-3 py-2.5">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-surface-recessed text-[11px] font-semibold text-text-primary">
            {initials(emp.name)}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="truncate text-[13px] font-semibold text-text-primary">
                {emp.name}
              </span>
              {emp.isNew ? <StatusChip tone="info">New</StatusChip> : null}
            </div>
            <p className="truncate text-xs text-text-secondary">{emp.role}</p>
          </div>
        </div>
      </td>
      <td className="px-3 py-2.5 text-[13px] text-text-primary">{emp.country}</td>
      <td className="px-3 py-2.5 tabular text-[13px] text-text-secondary">
        {emp.dateAdded ? formatIsoDate(emp.dateAdded) : 'Before cycle'}
      </td>
      <td className="px-3 py-2.5 text-[13px] text-text-primary">{emp.stage}</td>
      <td className="px-3 py-2.5">
        <StatusChip tone={emp.actionNeeded ? 'warn' : 'ok'}>
          {emp.actionNeeded ? 'Yes' : 'No'}
        </StatusChip>
      </td>
      <td className="px-3 py-2.5">
        <div className="flex flex-col items-start gap-1.5">
          <span
            className={`inline-block rounded border px-1.5 py-0.5 text-[11px] font-medium leading-snug ${flagClass[pay.tone]}`}
          >
            {pay.text}
          </span>
          {pay.showOffCycle ? (
            <Button
              variant="secondary"
              className="h-7"
              onClick={(e) => {
                e.stopPropagation()
                onOffCycle()
              }}
            >
              Request off-cycle payment
            </Button>
          ) : null}
        </div>
      </td>
    </tr>
  )
}

export function EmployeesPage() {
  const navigate = useNavigate()
  const employees = useAppStore((s) => s.employees)
  const overview = useAppStore((s) => s.overview)
  const pushToast = useAppStore((s) => s.pushToast)

  const [country, setCountry] = useState<CountryFilter>('all')
  const [actionNeeded, setActionNeeded] = useState<ActionFilter>('all')
  const [query, setQuery] = useState('')
  const [showAll, setShowAll] = useState(false)

  // Default view: the named people from context.md plus any joiners
  // ("show ~8 in the table"). A search or "Show all" widens to the full roster.
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const widen = showAll || q.length > 0
    return employees.filter((emp) => {
      if (!widen && !emp.featured) return false
      if (country !== 'all' && emp.country !== country) return false
      if (actionNeeded === 'yes' && !emp.actionNeeded) return false
      if (actionNeeded === 'no' && emp.actionNeeded) return false
      if (
        q &&
        !emp.name.toLowerCase().includes(q) &&
        !emp.id.toLowerCase().includes(q) &&
        !emp.role.toLowerCase().includes(q)
      ) {
        return false
      }
      return true
    })
  }, [employees, country, actionNeeded, query, showAll])

  const countryCounts = useMemo(() => {
    const map: Record<string, number> = {}
    for (const emp of employees) {
      map[emp.country] = (map[emp.country] ?? 0) + 1
    }
    return map
  }, [employees])

  function resetFilters() {
    setCountry('all')
    setActionNeeded('all')
    setQuery('')
    setShowAll(false)
  }

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Employees"
        subtitle={`${employees.length} in cycle · new joiners at the top`}
      />

      <div className="rounded border border-border bg-surface">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-3 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <select
              className="h-8 rounded border border-border bg-surface px-2 text-xs text-text-primary focus:border-text-primary focus:outline-none"
              value={country}
              onChange={(e) => setCountry(e.target.value as CountryFilter)}
            >
              <option value="all">All countries</option>
              <option value="India">India ({countryCounts.India ?? 0})</option>
              <option value="UK">UK ({countryCounts.UK ?? 0})</option>
              <option value="Germany">Germany ({countryCounts.Germany ?? 0})</option>
              <option value="Brazil">Brazil ({countryCounts.Brazil ?? 0})</option>
            </select>
            <select
              className="h-8 rounded border border-border bg-surface px-2 text-xs text-text-primary focus:border-text-primary focus:outline-none"
              value={actionNeeded}
              onChange={(e) => setActionNeeded(e.target.value as ActionFilter)}
            >
              <option value="all">All action statuses</option>
              <option value="yes">Action needed: Yes</option>
              <option value="no">Action needed: No</option>
            </select>
            <input
              className="h-8 min-w-[200px] rounded border border-border bg-surface px-2 text-xs text-text-primary placeholder:text-text-muted focus:border-text-primary focus:outline-none"
              placeholder="Filter by name, role, or id…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <Button variant="ghost" onClick={resetFilters}>
              Reset
            </Button>
          </div>
          <div className="flex items-center gap-2">
            <span className="tabular rounded bg-surface-recessed px-2 py-1 text-xs text-text-secondary">
              Showing <strong className="text-text-primary">{filtered.length}</strong> of{' '}
              {employees.length}
              {overview ? ` · ${overview.customer.name}` : null}
            </span>
            <Button variant="secondary" onClick={() => setShowAll((v) => !v)}>
              {showAll ? 'Show fewer' : `Show all ${employees.length}`}
            </Button>
          </div>
        </div>

        <div>
          <table className="w-full table-fixed border-collapse text-left">
            <colgroup>
              <col className="w-[24%]" />
              <col className="w-[9%]" />
              <col className="w-[10%]" />
              <col className="w-[13%]" />
              <col className="w-[12%]" />
              <col className="w-[32%]" />
            </colgroup>
            <thead>
              <tr className="h-8 bg-surface-recessed text-[11px] font-medium uppercase tracking-wide text-text-secondary">
                <th className="px-3 py-1 font-medium">Employee</th>
                <th className="px-3 py-1 font-medium">Country</th>
                <th className="px-3 py-1 font-medium">Date added</th>
                <th className="px-3 py-1 font-medium">Stage</th>
                <th className="px-3 py-1 font-medium">Action needed</th>
                <th className="px-3 py-1 font-medium">If no action: will be paid</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((emp) => (
                <EmployeeRow
                  key={emp.id}
                  emp={emp}
                  onOpen={() => navigate(`/people/${emp.id}`)}
                  onOffCycle={() =>
                    pushToast('Request off-cycle payment – not built in prototype')
                  }
                />
              ))}
              {filtered.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-3 py-10 text-center text-xs text-text-secondary"
                  >
                    No employees match these filters.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <p className="border-t border-border px-3 py-2.5 text-xs text-text-secondary">
          Changes added on or before the input finalisation date are included in this
          run. Later changes move to the next cycle.
        </p>
      </div>
    </div>
  )
}
