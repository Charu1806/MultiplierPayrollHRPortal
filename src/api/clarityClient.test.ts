import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ClarityApiError,
  clarityApi,
  clarityFetch,
  getClarityApiBase,
} from '@/api/clarityClient'

type FetchCall = { url: URL; init: RequestInit }

function mockFetch(
  status = 200,
  body: unknown = {},
  opts: { text?: string } = {},
): { calls: FetchCall[] } {
  const calls: FetchCall[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init: RequestInit) => {
      calls.push({ url: new URL(input), init })
      const text = opts.text ?? JSON.stringify(body)
      return new Response(text, {
        status,
        statusText: status === 200 ? 'OK' : 'Error',
        headers: { 'Content-Type': 'application/json' },
      })
    }),
  )
  return { calls }
}

describe('clarityFetch — URL and asOf building', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('prefixes the Clarity base and normalises a missing leading slash', async () => {
    const { calls } = mockFetch()
    await clarityFetch('cycles/current')
    expect(calls[0].url.pathname.endsWith('/api/cycles/current') || calls[0].url.pathname.endsWith('/cycles/current')).toBe(true)
    expect(calls[0].url.href).toContain('cycles/current')
    expect(getClarityApiBase()).toBeTruthy()
  })

  it('adds asOf as a query parameter', async () => {
    const { calls } = mockFetch()
    await clarityFetch('/employees', { asOf: '2026-10-13' })
    expect(calls[0].url.pathname.endsWith('/employees')).toBe(true)
    expect(calls[0].url.searchParams.get('asOf')).toBe('2026-10-13')
  })

  it('drops undefined and empty query values but keeps real ones', async () => {
    const { calls } = mockFetch()
    await clarityFetch('/employees', {
      asOf: '2026-10-12',
      query: { country: 'India', action_needed: undefined, status: '' },
    })
    const params = calls[0].url.searchParams
    expect(params.get('country')).toBe('India')
    expect(params.has('action_needed')).toBe(false)
    expect(params.has('status')).toBe(false)
    expect(params.get('asOf')).toBe('2026-10-12')
  })

  it('always sends the demo customer header; Content-Type only when there is a body', async () => {
    const { calls } = mockFetch()
    await clarityFetch('/issues')
    const getHeaders = calls[0].init.headers as Record<string, string>
    expect(getHeaders['X-Customer-Id']).toBe('cust_acme')
    expect(getHeaders['Content-Type']).toBeUndefined()
    expect(calls[0].init.body).toBeUndefined()

    await clarityFetch('/issues/issue_001/resolve', {
      method: 'POST',
      body: { resolution: 'confirm' },
    })
    const postHeaders = calls[1].init.headers as Record<string, string>
    expect(postHeaders['Content-Type']).toBe('application/json')
    expect(calls[1].init.method).toBe('POST')
    expect(JSON.parse(calls[1].init.body as string)).toEqual({ resolution: 'confirm' })
  })

  it('surfaces RFC-7807 detail and status as ClarityApiError', async () => {
    mockFetch(409, {
      type: 'https://multiplier.example/errors/blocking-open',
      title: 'Conflict',
      status: 409,
      detail: 'Resolve 1 blocking item first',
    })
    const err = await clarityFetch('/review/approve', { method: 'POST', body: {} }).catch(
      (e: unknown) => e,
    )
    expect(err).toBeInstanceOf(ClarityApiError)
    const apiErr = err as ClarityApiError
    expect(apiErr.status).toBe(409)
    expect(apiErr.message).toBe('Resolve 1 blocking item first')
    expect((apiErr.body as { type: string }).type).toContain('blocking-open')
  })

  it('falls back to statusText when the error body is not JSON', async () => {
    mockFetch(502, undefined, { text: 'bad gateway' })
    const err = (await clarityFetch('/health').catch((e: unknown) => e)) as ClarityApiError
    expect(err.status).toBe(502)
    expect(err.message).toBe('Error')
    expect(err.body).toBe('bad gateway')
  })

  it('returns null for an empty 200 body', async () => {
    mockFetch(200, undefined, { text: '' })
    await expect(clarityFetch('/health')).resolves.toBeNull()
  })
})

describe('clarityApi — endpoint wiring', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('getEmployees maps actionNeeded boolean to the API string flag', async () => {
    const { calls } = mockFetch()
    await clarityApi.getEmployees('2026-10-12', { country: 'UK', actionNeeded: true })
    await clarityApi.getEmployees('2026-10-12', { actionNeeded: false })
    await clarityApi.getEmployees('2026-10-12')
    expect(calls[0].url.searchParams.get('action_needed')).toBe('true')
    expect(calls[0].url.searchParams.get('country')).toBe('UK')
    expect(calls[1].url.searchParams.get('action_needed')).toBe('false')
    expect(calls[2].url.searchParams.has('action_needed')).toBe(false)
  })

  it('POST helpers mirror body.asOf into the query string', async () => {
    const { calls } = mockFetch()
    await clarityApi.resolveIssue('issue_001', {
      resolution: 'add_here',
      payload: { taxId: 'DE1' },
      asOf: '2026-10-12',
    })
    await clarityApi.attachDocument('emp_james', {
      fixture: 'bonus_letter_james.pdf',
      asOf: '2026-10-13',
    })
    await clarityApi.approveReview('2026-10-22')
    expect(calls[0].url.pathname.endsWith('/issues/issue_001/resolve')).toBe(true)
    expect(calls[0].url.searchParams.get('asOf')).toBe('2026-10-12')
    expect(calls[1].url.pathname.endsWith('/employees/emp_james/documents')).toBe(true)
    expect(calls[1].url.searchParams.get('asOf')).toBe('2026-10-13')
    expect(JSON.parse(calls[2].init.body as string)).toEqual({ asOf: '2026-10-22' })
  })

  it('getIssues defaults to open and passes other statuses through', async () => {
    const { calls } = mockFetch()
    await clarityApi.getIssues('2026-10-12')
    await clarityApi.getIssues('2026-10-12', 'all')
    expect(calls[0].url.searchParams.get('status')).toBe('open')
    expect(calls[1].url.searchParams.get('status')).toBe('all')
  })
})
