import type { EmployeeDto, ReviewLineDto, ReviewResponse } from '@/api/types'

export type ReviewCards = {
  lines: ReviewLineDto[]
  changed: number
  matched: number
  needs: number
  approved: number
}

/** Same headline as the review API, limited to one country when a country admin is signed in. */
export function reviewCards(
  review: ReviewResponse,
  employees: EmployeeDto[],
  country: string | null,
): ReviewCards {
  const lines = review.lines.filter((line) => !country || line.country === country)
  const approved = lines.filter((line) => line.approved).length
  if (!country) {
    return {
      lines,
      changed: review.changedLines,
      matched: review.matchedLines,
      needs: review.needsHumanCheck,
      approved,
    }
  }
  if (review.cycleKey === 'november') {
    return {
      lines,
      changed: lines.length,
      matched: lines.filter((line) => line.approved || line.rejected).length,
      needs: lines.filter((line) => line.needsHumanCheck).length,
      approved,
    }
  }
  const emps = employees.filter((emp) => emp.country === country)
  const lineIds = new Set(lines.map((line) => line.employeeId).filter(Boolean))
  const resolvedIds = new Set(
    lines
      .filter((line) => (line.approved || line.rejected) && line.employeeId)
      .map((line) => line.employeeId),
  )
  const changedIds = new Set<string>()
  for (const emp of emps) {
    if (lineIds.has(emp.id) || emp.matchedSource) {
      changedIds.add(emp.id)
      continue
    }
    if (!emp.changedThisCycle) continue
    const base = emp.salary?.base ?? 0
    const sept = emp.septemberPay ?? 0
    const leave = emp.salary?.unpaidLeaveDays ?? 0
    if (Math.abs(base - sept) > 0.5 || leave > 0) changedIds.add(emp.id)
  }
  let matched = 0
  for (const id of changedIds) {
    const emp = emps.find((row) => row.id === id)
    if (resolvedIds.has(id) || emp?.matchedSource) matched += 1
  }
  return {
    lines,
    changed: changedIds.size,
    matched,
    needs: changedIds.size - matched,
    approved,
  }
}
