/**
 * Sole HTTP entry to the Clarity API.
 * Browser never imports SQLite or server services.
 */

import type {
  ApproveResponse,
  AttachDocumentBody,
  CreateEmployeeBody,
  CycleCurrentResponse,
  DocumentFixturesResponse,
  EmployeeDto,
  EmployeesListResponse,
  ExtractResult,
  IssuesListResponse,
  IssueDto,
  MissingFieldsBody,
  NotificationDetail,
  NotificationsListResponse,
  OverviewResponse,
  PrototypeDatesResponse,
  ResolveIssueBody,
  ResolveIssueResponse,
  ReviewResponse,
} from '@/api/types'

export function getClarityApiBase(): string {
  const env = import.meta.env.VITE_CLARITY_API_BASE?.replace(/\/$/, '')
  if (env) return env
  if (typeof window !== 'undefined') return '/api'
  return 'http://127.0.0.1:8787/api'
}

export class ClarityApiError extends Error {
  status: number
  body: unknown

  constructor(message: string, status: number, body: unknown) {
    super(message)
    this.name = 'ClarityApiError'
    this.status = status
    this.body = body
  }
}

type ClarityRequestInit = Omit<RequestInit, 'body'> & {
  body?: unknown
  asOf?: string
  query?: Record<string, string | undefined>
}

export async function clarityFetch<T>(
  path: string,
  init: ClarityRequestInit = {},
): Promise<T> {
  const { asOf, body, headers, query, ...rest } = init
  const base = getClarityApiBase()
  const pathPart = path.startsWith('/') ? path : `/${path}`
  const href = `${base}${pathPart}`
  const url = href.startsWith('http')
    ? new URL(href)
    : new URL(href, typeof window === 'undefined' ? 'http://127.0.0.1:5173' : window.location.origin)
  if (asOf) {
    url.searchParams.set('asOf', asOf)
  }
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== '') {
        url.searchParams.set(key, value)
      }
    }
  }

  const response = await fetch(url.toString(), {
    ...rest,
    headers: {
      Accept: 'application/json',
      'X-Customer-Id': 'cust_acme',
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  const text = await response.text()
  let data: unknown = null
  if (text) {
    try {
      data = JSON.parse(text) as unknown
    } catch {
      data = text
    }
  }

  if (!response.ok) {
    const detail =
      typeof data === 'object' &&
      data &&
      'detail' in data &&
      typeof (data as { detail: unknown }).detail === 'string'
        ? (data as { detail: string }).detail
        : response.statusText
    throw new ClarityApiError(detail, response.status, data)
  }

  return data as T
}

export const clarityApi = {
  getPrototypeDates: () =>
    clarityFetch<PrototypeDatesResponse>('/meta/prototype-dates'),

  getConfig: () =>
    clarityFetch<{
      cycle: unknown
      rules: unknown
      company: import('@/api/types').CompanyConfig
      dates: PrototypeDatesResponse
    }>('/config'),

  getState: (asOf: string) =>
    clarityFetch<{
      asOf: string
      dates: PrototypeDatesResponse
      overview: OverviewResponse
      issues: IssueDto[]
      employees: EmployeeDto[]
      review: ReviewResponse
      notifications: NotificationsListResponse['notifications']
    }>('/state', { asOf }),

  getCycleCurrent: (asOf: string) =>
    clarityFetch<CycleCurrentResponse>('/cycles/current', { asOf }),

  getOverview: (asOf: string) =>
    clarityFetch<OverviewResponse>('/cycles/current/overview', { asOf }),

  getEmployees: (
    asOf: string,
    opts?: {
      country?: string
      actionNeeded?: boolean
      q?: string
      status?: string
      filter?: string
      page?: number
      pageSize?: number
    },
  ) =>
    clarityFetch<EmployeesListResponse>('/employees', {
      asOf,
      query: {
        country: opts?.country,
        action_needed:
          opts?.actionNeeded === undefined
            ? undefined
            : opts.actionNeeded
              ? 'true'
              : 'false',
        q: opts?.q,
        status: opts?.status,
        filter: opts?.filter,
        page: opts?.page,
        pageSize: opts?.pageSize,
      },
    }),

  getEmployee: (id: string, asOf: string) =>
    clarityFetch<EmployeeDto>(`/employees/${id}`, { asOf }),

  createEmployee: (body: CreateEmployeeBody) =>
    clarityFetch<EmployeeDto>('/employees', {
      method: 'POST',
      body,
      asOf: body.asOf,
    }),

  previewInput: (body: Record<string, unknown>, asOf: string) =>
    clarityFetch<{
      cycle: { key: string; label: string; payDate: string; inputFinalisation: string }
      confirmationMessage: string
      findings?: { rule: string; severity: string; field: string; owner: string; message: string }[]
      flags?: string[]
      prorate?: { amount: number; formula: string }
    }>('/inputs/preview', {
      method: 'POST',
      body: { ...body, asOf },
      asOf,
    }),

  generateDocument: (body: Record<string, unknown>) =>
    clarityFetch<{
      fileName: string
      contentType: string
      base64: string
      textPreview?: string
      docType?: string
    }>('/documents/generate', {
      method: 'POST',
      body,
    }),

  syncFromWorkday: (asOf: string, trigger: 'Manual' | 'Final' = 'Manual') =>
    clarityFetch<{
      status: string
      trigger: string
      syncedAt: string
      actor: string
      summary?: string | null
      added: number
      changed: number
      exited: number
      steps: string[]
      idempotent?: boolean
      activity?: {
        previousCutoff?: string
        deadline?: string
        newEmployees?: { id: string; name: string; dateAdded: string }[]
        bonuses?: { id: string; name: string; label: string }[]
        hikes?: { id: string; name?: string | null; summary?: string | null }[]
      }
      classificationSource?: string
    }>('/sync', { method: 'POST', body: { asOf, trigger }, asOf }),

  patchEmployee: (id: string, body: Record<string, unknown>, asOf: string) =>
    clarityFetch<EmployeeDto>(`/employees/${id}`, {
      method: 'PATCH',
      body: { ...body, asOf },
      asOf,
    }),

  attachDocument: (employeeId: string, body: AttachDocumentBody) =>
    clarityFetch<EmployeeDto>(`/employees/${employeeId}/documents`, {
      method: 'POST',
      body,
      asOf: body.asOf,
    }),

  fillMissingFields: (employeeId: string, body: MissingFieldsBody) =>
    clarityFetch<EmployeeDto>(`/employees/${employeeId}/missing-fields`, {
      method: 'POST',
      body,
      asOf: typeof body.asOf === 'string' ? body.asOf : undefined,
    }),

  addOneTimePayment: (employeeId: string, body: Record<string, unknown>, asOf: string) =>
    clarityFetch<EmployeeDto>(`/employees/${employeeId}/one-time-payments`, {
      method: 'POST',
      body: { ...body, asOf },
      asOf,
    }),

  reopenReview: (employeeId: string, asOf: string) =>
    clarityFetch<ReviewResponse>(`/employees/${employeeId}/reopen-review`, {
      method: 'POST',
      body: { asOf },
      asOf,
    }),

  recordExit: (employeeId: string, body: Record<string, unknown>, asOf: string) =>
    clarityFetch<EmployeeDto>(`/employees/${employeeId}/exit`, {
      method: 'POST',
      body: { ...body, asOf },
      asOf,
    }),

  undoExit: (employeeId: string, asOf: string) =>
    clarityFetch<EmployeeDto>(`/employees/${employeeId}/exit`, {
      method: 'DELETE',
      asOf,
    }),

  getIssues: (asOf: string, status: 'open' | 'resolved' | 'all' = 'open') =>
    clarityFetch<IssuesListResponse>('/issues', {
      asOf,
      query: { status },
    }),

  getIssue: (id: string, asOf: string) =>
    clarityFetch<IssueDto>(`/issues/${id}`, { asOf }),

  resolveIssue: (id: string, body: ResolveIssueBody) =>
    clarityFetch<ResolveIssueResponse>(`/issues/${id}/resolve`, {
      method: 'POST',
      body,
      asOf: body.asOf,
    }),

  remindIssue: (id: string, asOf: string) =>
    clarityFetch<{
      issue: IssueDto
      message: string
      formUrl?: string
      formPath?: string
      emailSent?: boolean
    }>(`/issues/${id}/remind`, {
      method: 'POST',
      body: { asOf },
      asOf,
    }),

  getForm: (token: string, asOf: string) =>
    clarityFetch<{
      employee: { id: string; name: string; country: string }
      fields: string[]
      demoValues: Record<string, string>
      cutoffLabel?: string
    }>(`/forms/${encodeURIComponent(token)}`, { asOf }),

  submitForm: (token: string, fields: Record<string, string>, asOf: string) =>
    clarityFetch<{ employee: EmployeeDto; message: string }>(
      `/forms/${encodeURIComponent(token)}`,
      {
        method: 'POST',
        body: { fields, asOf },
        asOf,
      },
    ),

  getReview: (asOf: string) =>
    clarityFetch<ReviewResponse>('/review', { asOf }),

  approveLine: (lineId: string, asOf: string) =>
    clarityFetch<ReviewResponse>(`/review/${lineId}/approve`, {
      method: 'POST',
      body: { asOf },
      asOf,
    }),

  decideReviewLine: (lineId: string, asOf: string) =>
    clarityFetch<{ lineId: string; llmDecision: import('./types').LlmDecisionDto }>(
      `/review/${lineId}/llm-decide`,
      {
        method: 'POST',
        body: { asOf },
        asOf,
      },
    ),

  unapproveLine: (lineId: string, asOf: string) =>
    clarityFetch<ReviewResponse>(`/review/${lineId}/unapprove`, {
      method: 'POST',
      body: { asOf },
      asOf,
    }),

  signOff: (asOf: string) =>
    clarityFetch<ApproveResponse>('/review/signoff', {
      method: 'POST',
      body: { asOf },
      asOf,
    }),

  approveReview: (asOf: string) =>
    clarityFetch<ApproveResponse>('/review/signoff', {
      method: 'POST',
      body: { asOf },
      asOf,
    }),

  getNotifications: (asOf: string, channel = 'email') =>
    clarityFetch<NotificationsListResponse>('/notifications', {
      asOf,
      query: { channel },
    }),

  getNotification: (id: string, asOf: string) =>
    clarityFetch<NotificationDetail>(`/notifications/${id}`, { asOf }),

  sendHrQuery: (body: { asOf: string; recipient: string; subject: string; body: string; href?: string }) =>
    clarityFetch<{ ok: boolean }>('/notifications/query', { method: 'POST', asOf: body.asOf, body }),

  getDocumentFixtures: () =>
    clarityFetch<DocumentFixturesResponse>('/documents/fixtures'),

  extractDrive: (body: {
    fileId?: string
    accessToken?: string
    fileName?: string
    employeeId?: string
    asOf?: string
  }) =>
    clarityFetch<ExtractResult>('/drive/extract', {
      method: 'POST',
      body,
      asOf: body.asOf,
    }),

  extractUpload: async (
    file: File,
    opts: { employeeId?: string; asOf?: string } = {},
  ) => {
    const base = getClarityApiBase()
    const form = new FormData()
    form.append('file', file)
    if (opts.employeeId) form.append('employeeId', opts.employeeId)
    if (opts.asOf) form.append('asOf', opts.asOf)
    const res = await fetch(`${base}/documents/extract`, {
      method: 'POST',
      headers: { 'X-Customer-Id': 'cust_acme' },
      body: form,
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      throw new ClarityApiError(
        (data as { detail?: string }).detail || 'Upload failed',
        res.status,
        data,
      )
    }
    return data as ExtractResult
  },

  resetDemo: () =>
    clarityFetch<{ ok: boolean; asOf: string }>('/demo/reset', { method: 'POST' }),
}
