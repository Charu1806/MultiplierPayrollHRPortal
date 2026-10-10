import { beforeEach, describe, expect, it, vi } from 'vitest'
import type {
  EmployeeDto,
  IssueDto,
  OverviewResponse,
  ReviewResponse,
} from '@/api/types'

vi.mock('@/api/clarityClient', () => {
  class ClarityApiError extends Error {
    status: number
    body: unknown
    constructor(message: string, status: number, body: unknown) {
      super(message)
      this.status = status
      this.body = body
    }
  }
  return {
    ClarityApiError,
    getClarityApiBase: () => 'http://test/clarity/v1',
    clarityApi: {
      getPrototypeDates: vi.fn(),
      getConfig: vi.fn(),
      getOverview: vi.fn(),
      getIssues: vi.fn(),
      getIssue: vi.fn(),
      getEmployees: vi.fn(),
      getEmployee: vi.fn(),
      getReview: vi.fn(),
      getNotifications: vi.fn(),
      getNotification: vi.fn(),
      resolveIssue: vi.fn(),
      approveReview: vi.fn(),
      createEmployee: vi.fn(),
      attachDocument: vi.fn(),
      fillMissingFields: vi.fn(),
      remindIssue: vi.fn(),
    },
  }
})

import { ClarityApiError, clarityApi } from '@/api/clarityClient'
import { useAppStore } from '@/store'

const api = clarityApi as unknown as Record<string, ReturnType<typeof vi.fn>>

function overview(openActions: number, germany = 'Action needed'): OverviewResponse {
  return {
    customer: { id: 'cust_acme', name: 'Acme Tech', hrTool: 'Workday' },
    cycle: {
      id: 'cycle_2026_10',
      label: 'October 2026',
      stage: 'Input finalisation',
      inputFinalisation: '2026-10-15',
      approval: '2026-10-22',
      fundingDue: '2026-10-23',
      payDate: '2026-10-28',
      changedLines: 38,
      matchedLines: 32,
      needsHumanCheck: 6,
      approved: false,
    },
    asOf: '2026-10-12',
    countdown: '3 days left',
    statusLine: { openActions, countdown: '3 days left' },
    countries: [
      { country: 'India', employeeCount: 50, status: 'Deadline risk' },
      { country: 'UK', employeeCount: 30, status: 'Action needed' },
      { country: 'Germany', employeeCount: 22, status: germany as 'On track' },
      { country: 'Brazil', employeeCount: 18, status: 'Deadline risk' },
    ],
    upNext: [],
  }
}

function issue(id: string, status: 'open' | 'resolved' = 'open'): IssueDto {
  return {
    id,
    title: id === 'issue_001' ? 'Missing tax ID' : 'Salary up 3x',
    severity: id === 'issue_001' ? 'blocking' : 'needs_confirmation',
    employeeId: id === 'issue_001' ? 'emp_lena' : 'emp_james',
    country: id === 'issue_001' ? 'Germany' : 'UK',
    owner: 'HR admin',
    deadline: '2026-10-15',
    source: 'Workday',
    impact: 'x',
    detail: null,
    status,
    resolvedAt: status === 'resolved' ? '2026-10-12' : null,
    resolvedBy: status === 'resolved' ? 'HR admin' : null,
    resolutionLog: null,
  }
}

const review: ReviewResponse = {
  available: false,
  changedLines: 38,
  matchedLines: 32,
  needsHumanCheck: 6,
  lines: [],
  canApprove: false,
  approved: false,
}

const james: EmployeeDto = {
  id: 'emp_james',
  name: 'James Patel',
  role: 'Engineer',
  country: 'UK',
  currency: '£',
  monthlyNet: 4000,
  dateAdded: null,
  isNew: false,
  stage: 'Input finalisation',
  source: 'Workday',
  workEmail: null,
  hireDate: null,
  managerName: null,
  missingFields: [],
  oneOffs: [],
  actionNeeded: true,
  payTiming: { level: 'green', message: 'Payment on track for October', showOffCycleStub: false },
  ifNoActionWillBePaid: null,
  notes: null,
  featured: true,
}

function primeApi() {
  api.getPrototypeDates.mockResolvedValue({ dates: [], labels: [] })
  api.getConfig.mockResolvedValue({
    dates: { dates: [], labels: [] },
    company: { name: 'Acme', payrollCaption: 'Powered by Multiplier', admin: { name: 'Maya Rao' } },
    rules: { fieldFormats: {} },
    cycle: {},
  })
  api.getOverview.mockResolvedValue(overview(4))
  api.getIssues.mockResolvedValue({
    issues: [issue('issue_001'), issue('issue_002')],
    asOf: '2026-10-12',
  })
  api.getEmployees.mockResolvedValue({ employees: [james], count: 1, asOf: '2026-10-12' })
  api.getReview.mockResolvedValue(review)
  api.getNotifications.mockResolvedValue({ notifications: [], asOf: '2026-10-12' })
}

describe('useAppStore cache', () => {
  beforeEach(async () => {
    for (const fn of Object.values(api)) fn.mockReset()
    primeApi()
    useAppStore.setState({
      asOf: '2026-10-12',
      overview: null,
      issues: [],
      selectedIssue: null,
      selectedIssueId: null,
      employees: [],
      toasts: [],
      bootStatus: 'idle',
    })
    await useAppStore.getState().boot()
  })

  it('boot hydrates every slice from the API', () => {
    const s = useAppStore.getState()
    expect(s.bootStatus).toBe('ready')
    expect(s.overview?.statusLine.openActions).toBe(4)
    expect(s.issues.map((i) => i.id)).toEqual(['issue_001', 'issue_002'])
    expect(s.employees[0].id).toBe('emp_james')
  })

  it('resolveIssue updates the cache from the resolve response, then refetches lists', async () => {
    api.resolveIssue.mockResolvedValue({
      issue: issue('issue_001', 'resolved'),
      overview: overview(3, 'On track'),
    })
    api.getIssues.mockResolvedValue({ issues: [issue('issue_002')], asOf: '2026-10-12' })

    await useAppStore.getState().resolveIssue('issue_001', {
      resolution: 'add_here',
      payload: { taxId: 'DE1' },
    })

    const s = useAppStore.getState()
    expect(api.resolveIssue).toHaveBeenCalledWith(
      'issue_001',
      expect.objectContaining({ resolution: 'add_here', asOf: '2026-10-12' }),
    )
    expect(s.selectedIssue?.status).toBe('resolved')
    expect(s.overview?.statusLine.openActions).toBe(3)
    expect(s.overview?.countries.find((c) => c.country === 'Germany')?.status).toBe('On track')
    expect(s.issues.map((i) => i.id)).toEqual(['issue_002'])
    // refetches use the current asOf
    expect(api.getIssues).toHaveBeenLastCalledWith('2026-10-12', 'open')
    expect(api.getEmployees).toHaveBeenLastCalledWith('2026-10-12')
  })

  it('resolveIssue surfaces API errors as a toast and rethrows', async () => {
    api.resolveIssue.mockRejectedValue(
      new ClarityApiError('Not built in prototype', 501, {}),
    )
    await expect(
      useAppStore.getState().resolveIssue('issue_001', { resolution: 'fix_in_workday' }),
    ).rejects.toBeInstanceOf(ClarityApiError)
    expect(useAppStore.getState().toasts.at(-1)?.message).toBe('Not built in prototype')
    // cache untouched
    expect(useAppStore.getState().overview?.statusLine.openActions).toBe(4)
  })

  it('setAsOf refetches every derived view with the new date', async () => {
    api.getOverview.mockResolvedValue({ ...overview(2), asOf: '2026-10-17' })
    await useAppStore.getState().setAsOf('2026-10-17')
    const s = useAppStore.getState()
    expect(s.asOf).toBe('2026-10-17')
    expect(api.getOverview).toHaveBeenLastCalledWith('2026-10-17')
    expect(api.getIssues).toHaveBeenLastCalledWith('2026-10-17', 'open')
    expect(api.getEmployees).toHaveBeenLastCalledWith('2026-10-17')
    expect(api.getReview).toHaveBeenLastCalledWith('2026-10-17')
    expect(api.getNotifications).toHaveBeenLastCalledWith('2026-10-17')
    expect(s.overview?.statusLine.openActions).toBe(2)
  })

  it('setAsOf persists the view date for the next page load', async () => {
    const store = new Map<string, string>()
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
    })
    await useAppStore.getState().setAsOf('2026-10-22')
    expect(store.get('clarity.asOf')).toBe('2026-10-22')
    vi.unstubAllGlobals()
  })

  it('setAsOf ignores dates outside the Oct–Nov range', async () => {
    const calls = api.getOverview.mock.calls.length
    await useAppStore.getState().setAsOf('2026-09-01' as never)
    expect(useAppStore.getState().asOf).toBe('2026-10-12')
    expect(api.getOverview.mock.calls.length).toBe(calls)
  })

  it('attachDocument replaces employeeDetail and refreshes the roster', async () => {
    const withBonus: EmployeeDto = {
      ...james,
      source: 'Bonus letter',
      oneOffs: [{ label: 'Performance bonus (one-off)', amount: 8000, cycleMonth: 'October 2026' }],
    }
    api.attachDocument.mockResolvedValue(withBonus)
    api.getEmployees.mockResolvedValue({ employees: [withBonus], count: 1, asOf: '2026-10-13' })

    await useAppStore.getState().attachDocument('emp_james', {
      fixture: 'bonus_letter_james.pdf',
    })
    const s = useAppStore.getState()
    expect(s.employeeDetail?.oneOffs[0].amount).toBe(8000)
    expect(s.employeeDetail?.monthlyNet).toBe(4000)
    expect(s.employees[0].oneOffs).toHaveLength(1)
  })
})
