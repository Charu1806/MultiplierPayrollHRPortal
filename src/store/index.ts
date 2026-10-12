/**
 * Zustand cache of Clarity API DTOs.
 * Mutations call the API; setAsOf refetches derived views.
 */

import { create } from 'zustand'
import { ClarityApiError, clarityApi } from '@/api/clarityClient'
import type { ConfirmRequest } from '@/components/ConfirmModal'
import type {
  AttachDocumentBody,
  CompanyConfig,
  CreateEmployeeBody,
  EmployeeDto,
  IssueDto,
  MissingFieldsBody,
  NotificationDetail,
  NotificationListItem,
  OverviewResponse,
  PrototypeDate,
  PrototypeDatesResponse,
  ResolveIssueBody,
  ResolveIssueResponse,
  ReviewResponse,
} from '@/api/types'
import type { FieldFormatSpec } from '@/lib/fieldValidation'
import { readStoredPersona, writeStoredPersona, type PersonaId } from '@/features/persona'

export type { PrototypeDate }

export type Toast = {
  id: string
  message: string
}

type LoadState = 'idle' | 'loading' | 'ready' | 'error'

function inDateRange(value: string, min = '2026-10-01', max = '2027-01-31'): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && value >= min && value <= max
}

type AppStore = {
  asOf: PrototypeDate
  persona: PersonaId
  prototypeDates: PrototypeDatesResponse | null
  overview: OverviewResponse | null
  company: CompanyConfig | null
  rules: { fieldFormats?: Record<string, FieldFormatSpec> } | null
  issues: IssueDto[]
  selectedIssue: IssueDto | null
  selectedIssueId: string | null
  employees: EmployeeDto[]
  employeeDetail: EmployeeDto | null
  review: ReviewResponse | null
  notifications: NotificationListItem[]
  selectedNotification: NotificationDetail | null
  toasts: Toast[]
  notice: string | null
  confirm: ConfirmRequest | null
  confirmBusy: boolean
  confirmError: string | null
  bootStatus: LoadState
  bootError: string | null
  isRefreshing: boolean

  pushToast: (message: string) => void
  dismissToast: (id: string) => void
  showNotice: (message: string) => void
  dismissNotice: () => void
  askConfirm: (req: ConfirmRequest) => void
  cancelConfirm: () => void
  setConfirmBusy: (busy: boolean) => void
  setConfirmError: (error: string | null) => void
  setSelectedIssueId: (id: string | null) => void

  boot: () => Promise<void>
  setAsOf: (date: PrototypeDate) => Promise<void>
  setPersona: (persona: PersonaId) => void
  refreshAll: () => Promise<void>
  refreshOverview: () => Promise<void>
  refreshIssues: () => Promise<void>
  loadIssue: (id: string) => Promise<void>
  resolveIssue: (id: string, body: ResolveIssueBody) => Promise<ResolveIssueResponse>
  remindIssue: (id: string) => Promise<string | undefined>
  refreshEmployees: () => Promise<void>
  loadEmployee: (id: string) => Promise<void>
  createEmployee: (body: CreateEmployeeBody) => Promise<EmployeeDto>
  attachDocument: (employeeId: string, body: AttachDocumentBody) => Promise<EmployeeDto>
  fillMissingFields: (employeeId: string, body?: MissingFieldsBody) => Promise<EmployeeDto>
  patchEmployee: (id: string, body: Record<string, unknown>, confirmAi?: boolean) => Promise<EmployeeDto>
  syncFromWorkday: (trigger?: 'Manual' | 'Final') => Promise<{
    summary?: string | null
    actor: string
    trigger: string
    syncedAt: string
    steps: string[]
    activity?: {
      previousCutoff?: string
      newEmployees?: { name: string; dateAdded: string }[]
      bonuses?: { name: string; label: string }[]
      hikes?: { name?: string | null; summary?: string | null }[]
    }
  }>
  addOneTimePayment: (id: string, body: Record<string, unknown>) => Promise<EmployeeDto>
  recordExit: (id: string, body: Record<string, unknown>) => Promise<EmployeeDto>
  undoExit: (id: string) => Promise<EmployeeDto>
  reopenReview: (employeeId: string) => Promise<void>
  refreshReview: () => Promise<void>
  approveLine: (lineId: string) => Promise<void>
  unapproveLine: (lineId: string) => Promise<void>
  signOff: () => Promise<import('@/api/types').ApproveResponse>
  approveReview: () => Promise<import('@/api/types').ApproveResponse>
  refreshNotifications: () => Promise<void>
  loadNotification: (id: string) => Promise<void>
  resetDemo: () => Promise<void>
}

const AS_OF_STORAGE_KEY = 'clarity.asOf'

function readStoredAsOf(): PrototypeDate {
  try {
    const stored = globalThis.localStorage?.getItem(AS_OF_STORAGE_KEY)
    if (stored && inDateRange(stored)) return stored
  } catch {
    /* storage unavailable */
  }
  return '2026-10-12'
}

function writeStoredAsOf(date: PrototypeDate) {
  try {
    globalThis.localStorage?.setItem(AS_OF_STORAGE_KEY, date)
  } catch {
    /* ignore */
  }
}

function toastId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

function errorMessage(err: unknown): string {
  if (err instanceof ClarityApiError) return err.message
  if (err instanceof Error) return err.message
  return 'Something went wrong talking to Clarity API'
}

export const useAppStore = create<AppStore>((set, get) => ({
  asOf: readStoredAsOf(),
  prototypeDates: null,
  overview: null,
  company: null,
  persona: readStoredPersona(),
  rules: null,
  issues: [],
  selectedIssue: null,
  selectedIssueId: null,
  employees: [],
  employeeDetail: null,
  review: null,
  notifications: [],
  selectedNotification: null,
  toasts: [],
  notice: null,
  confirm: null,
  confirmBusy: false,
  confirmError: null,
  bootStatus: 'idle',
  bootError: null,
  isRefreshing: false,

  pushToast: (message) =>
    set((state) => {
      if (state.toasts.some((t) => t.message === message)) return state
      return { toasts: [...state.toasts, { id: toastId(), message }] }
    }),

  dismissToast: (id) =>
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),

  showNotice: (message) => set({ notice: message }),
  dismissNotice: () => set({ notice: null }),

  askConfirm: (req) => set({ confirm: req, confirmError: null, confirmBusy: false }),
  cancelConfirm: () => set({ confirm: null, confirmError: null, confirmBusy: false }),
  setConfirmBusy: (busy) => set({ confirmBusy: busy }),
  setConfirmError: (error) => set({ confirmError: error }),

  setSelectedIssueId: (id) => set({ selectedIssueId: id }),

  boot: async () => {
    set({ bootStatus: 'loading', bootError: null })
    try {
      const asOf = get().asOf
      const [cfg, overview, issuesRes, employeesRes, review, notificationsRes] =
        await Promise.all([
          clarityApi.getConfig(),
          clarityApi.getOverview(asOf),
          clarityApi.getIssues(asOf, 'open'),
          clarityApi.getEmployees(asOf),
          clarityApi.getReview(asOf),
          clarityApi.getNotifications(asOf),
        ])
      set({
        prototypeDates: cfg.dates,
        company: cfg.company,
        rules: (cfg.rules as { fieldFormats?: Record<string, FieldFormatSpec> }) ?? null,
        overview,
        issues: issuesRes.issues,
        employees: employeesRes.employees,
        review,
        notifications: notificationsRes.notifications,
        bootStatus: 'ready',
        bootError: null,
      })
    } catch (err) {
      const message = errorMessage(err)
      set({ bootStatus: 'error', bootError: message })
      get().pushToast(message)
    }
  },

  refreshAll: async () => {
    const { asOf } = get()
    set({ isRefreshing: true })
    try {
      const [overview, issuesRes, employeesRes, review, notificationsRes] =
        await Promise.all([
          clarityApi.getOverview(asOf),
          clarityApi.getIssues(asOf, 'open'),
          clarityApi.getEmployees(asOf),
          clarityApi.getReview(asOf),
          clarityApi.getNotifications(asOf),
        ])
      set({
        overview,
        issues: issuesRes.issues,
        employees: employeesRes.employees,
        review,
        notifications: notificationsRes.notifications,
        isRefreshing: false,
      })
      const selectedId = get().selectedIssueId
      if (selectedId) await get().loadIssue(selectedId)
    } catch (err) {
      set({ isRefreshing: false })
      get().pushToast(errorMessage(err))
    }
  },

  setPersona: (persona) => {
    writeStoredPersona(persona)
    set({ persona })
  },

  setAsOf: async (date) => {
    if (!inDateRange(date)) return
    writeStoredAsOf(date)
    set({ asOf: date })
    await get().refreshAll()
  },

  refreshOverview: async () => {
    try {
      set({ overview: await clarityApi.getOverview(get().asOf) })
    } catch (err) {
      get().pushToast(errorMessage(err))
    }
  },

  refreshIssues: async () => {
    try {
      const res = await clarityApi.getIssues(get().asOf, 'open')
      set({ issues: res.issues })
    } catch (err) {
      get().pushToast(errorMessage(err))
    }
  },

  loadIssue: async (id) => {
    set({ selectedIssueId: id })
    try {
      set({ selectedIssue: await clarityApi.getIssue(id, get().asOf) })
    } catch (err) {
      get().pushToast(errorMessage(err))
    }
  },

  resolveIssue: async (id, body) => {
    try {
      const result = await clarityApi.resolveIssue(id, {
        ...body,
        asOf: body.asOf ?? get().asOf,
      })
      set({ selectedIssue: result.issue, overview: result.overview, confirm: null })
      await Promise.all([get().refreshIssues(), get().refreshEmployees(), get().refreshReview()])
      return result
    } catch (err) {
      if (!get().confirm) {
        get().pushToast(errorMessage(err))
      }
      throw err
    }
  },

  remindIssue: async (id) => {
    try {
      const result = await clarityApi.remindIssue(id, get().asOf)
      set({ selectedIssue: result.issue, confirm: null })
      await Promise.all([get().refreshNotifications(), get().refreshIssues()])
      return result.message
    } catch (err) {
      if (!get().confirm) {
        get().pushToast(errorMessage(err))
      }
      throw err
    }
  },

  refreshEmployees: async () => {
    try {
      const res = await clarityApi.getEmployees(get().asOf)
      set({ employees: res.employees })
    } catch (err) {
      get().pushToast(errorMessage(err))
    }
  },

  loadEmployee: async (id) => {
    try {
      set({ employeeDetail: await clarityApi.getEmployee(id, get().asOf) })
    } catch (err) {
      get().pushToast(errorMessage(err))
      throw err
    }
  },

  createEmployee: async (body) => {
    try {
      const employee = await clarityApi.createEmployee({
        ...body,
        asOf: body.asOf ?? get().asOf,
      })
      set({ employeeDetail: employee, confirm: null })
      await Promise.all([get().refreshEmployees(), get().refreshOverview(), get().refreshIssues()])
      return employee
    } catch (err) {
      get().pushToast(errorMessage(err))
      throw err
    }
  },

  attachDocument: async (employeeId, body) => {
    try {
      const employee = await clarityApi.attachDocument(employeeId, {
        ...body,
        asOf: body.asOf ?? get().asOf,
      })
      set({ employeeDetail: employee, confirm: null })
      await Promise.all([
        get().refreshEmployees(),
        get().refreshOverview(),
        get().refreshIssues(),
        get().refreshReview(),
      ])
      return employee
    } catch (err) {
      get().pushToast(errorMessage(err))
      throw err
    }
  },

  fillMissingFields: async (employeeId, body = {}) => {
    try {
      const employee = await clarityApi.fillMissingFields(employeeId, {
        ...body,
        asOf: (typeof body.asOf === 'string' ? body.asOf : undefined) ?? get().asOf,
      })
      set({ employeeDetail: employee, confirm: null })
      await Promise.all([
        get().refreshEmployees(),
        get().refreshOverview(),
        get().refreshIssues(),
        get().refreshNotifications(),
      ])
      return employee
    } catch (err) {
      get().pushToast(errorMessage(err))
      throw err
    }
  },

  syncFromWorkday: async (trigger = 'Manual') => {
    const result = await clarityApi.syncFromWorkday(get().asOf, trigger)
    await Promise.all([
      get().refreshOverview(),
      get().refreshIssues(),
      get().refreshEmployees(),
      get().refreshReview(),
      get().refreshNotifications(),
    ])
    return result
  },

  patchEmployee: async (id, body, confirmAi = false) => {
    try {
      const employee = await clarityApi.patchEmployee(
        id,
        { ...body, confirmAiCheck: confirmAi },
        get().asOf,
      )
      set({ employeeDetail: employee, confirm: null })
      await Promise.all([get().refreshEmployees(), get().refreshReview(), get().refreshIssues()])
      return employee
    } catch (err) {
      if (err instanceof ClarityApiError && err.status === 409) {
        throw err
      }
      get().pushToast(errorMessage(err))
      throw err
    }
  },

  addOneTimePayment: async (id, body) => {
    try {
      const employee = await clarityApi.addOneTimePayment(id, body, get().asOf)
      set({ employeeDetail: employee })
      await Promise.all([get().refreshEmployees(), get().refreshReview(), get().refreshIssues()])
      return employee
    } catch (err) {
      // Surface to caller (Confirm modal); do not stack toasts for duplicates
      throw err instanceof Error ? err : new Error(errorMessage(err))
    }
  },

  reopenReview: async (employeeId) => {
    try {
      const review = await clarityApi.reopenReview(employeeId, get().asOf)
      set({ review, confirm: null })
      get().pushToast('Moved to Need your check')
      await Promise.all([get().refreshEmployees(), get().refreshOverview()])
    } catch (err) {
      get().pushToast(errorMessage(err))
      throw err
    }
  },

  recordExit: async (id, body) => {
    const employee = await clarityApi.recordExit(id, body, get().asOf)
    set({ employeeDetail: employee, confirm: null })
    await Promise.all([get().refreshEmployees(), get().refreshReview()])
    get().pushToast(`${employee.name} removed · full and final is on Review & approve`)
    return employee
  },

  undoExit: async (id) => {
    const employee = await clarityApi.undoExit(id, get().asOf)
    set({ employeeDetail: employee, confirm: null })
    await Promise.all([get().refreshEmployees(), get().refreshReview()])
    get().pushToast(`${employee.name} is back on payroll`)
    return employee
  },

  refreshReview: async () => {
    try {
      set({ review: await clarityApi.getReview(get().asOf) })
    } catch (err) {
      get().pushToast(errorMessage(err))
    }
  },

  approveLine: async (lineId) => {
    const review = await clarityApi.approveLine(lineId, get().asOf)
    set({ review })
    await get().refreshOverview()
  },

  unapproveLine: async (lineId) => {
    try {
      const review = await clarityApi.unapproveLine(lineId, get().asOf)
      set({ review })
      await get().refreshOverview()
    } catch (err) {
      get().pushToast(errorMessage(err))
      throw err
    }
  },

  signOff: async () => {
    const result = await clarityApi.signOff(get().asOf)
    set({ review: result.review ?? get().review })
    await Promise.all([get().refreshReview(), get().refreshOverview()])
    return result
  },

  approveReview: async () => get().signOff(),

  refreshNotifications: async () => {
    try {
      const res = await clarityApi.getNotifications(get().asOf)
      set({ notifications: res.notifications })
    } catch (err) {
      get().pushToast(errorMessage(err))
    }
  },

  loadNotification: async (id) => {
    try {
      set({ selectedNotification: await clarityApi.getNotification(id, get().asOf) })
      const res = await clarityApi.getNotifications(get().asOf)
      set({ notifications: res.notifications })
    } catch (err) {
      get().pushToast(errorMessage(err))
    }
  },

  resetDemo: async () => {
    try {
      const res = await clarityApi.resetDemo()
      writeStoredAsOf(res.asOf)
      set({ asOf: res.asOf, confirm: null })
      await get().refreshAll()
      get().pushToast('Demo reset to default seed')
    } catch (err) {
      get().pushToast(errorMessage(err))
    }
  },
}))

/** Prototype date options come from /config (config/cycle.json) via store.prototypeDates. */
