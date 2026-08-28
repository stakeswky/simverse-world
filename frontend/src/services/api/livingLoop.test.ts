import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  chooseLivingLoopDecision,
  getAdminLivingLoopMetrics,
  getLivingLoopToday,
  markLivingLoopResultViewed,
  postProductEventsBatch,
} from './livingLoop'
import { API_BASE } from './core'

const DECISION_ID = 'afe0c239-bd26-401c-80cf-97d4fc9953bc'
const EVENT_ID = '52cecfca-265b-442b-a7ec-c2f5b487d571'
const SESSION_ID = '66e32de4-2ba0-44d0-90ca-a1ca9f146dcf'
const IDEMPOTENCY_KEY = '4a67d265-7917-4c31-82b5-4d741c08ab37'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  localStorage.clear()
  localStorage.setItem('token', 'resident-token')
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Living Loop API client', () => {
  it('loads the authenticated Today projection and forwards a caller abort signal', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      experiment: { key: 'living_loop_p0', enabled: true },
      status: 'ready',
    }))
    vi.stubGlobal('fetch', fetchMock)
    const controller = new AbortController()

    await getLivingLoopToday(controller.signal)

    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/living-loop/today`,
      expect.objectContaining({
        signal: expect.any(AbortSignal),
        headers: expect.objectContaining({ Authorization: 'Bearer resident-token' }),
      }),
    )
  })

  it('submits only the selected choice and UUID idempotency key', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ state: 'chosen' }))
    vi.stubGlobal('fetch', fetchMock)

    await chooseLivingLoopDecision(DECISION_ID, {
      choice_key: 'private_mediation',
      idempotency_key: IDEMPOTENCY_KEY,
    })

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${API_BASE}/living-loop/decisions/${DECISION_ID}/choose`)
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({
      choice_key: 'private_mediation',
      idempotency_key: IDEMPOTENCY_KEY,
    })
    expect(JSON.stringify(init.body)).not.toContain('user_id')
    expect(JSON.stringify(init.body)).not.toContain('immediate_result')
    expect(JSON.stringify(init.body)).not.toContain('delayed_result')
  })

  it('marks a delayed result viewed with an empty authenticated POST', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ state: 'result_viewed' }))
    vi.stubGlobal('fetch', fetchMock)

    await markLivingLoopResultViewed(DECISION_ID)

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${API_BASE}/living-loop/decisions/${DECISION_ID}/result-viewed`)
    expect(init.method).toBe('POST')
    expect(init.body).toBeUndefined()
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer resident-token')
  })

  it('posts the privacy-bounded product event batch without adding identity fields', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ accepted: 1, duplicates: 0 }))
    vi.stubGlobal('fetch', fetchMock)
    const batch = {
      events: [{
        event_id: EVENT_ID,
        session_id: SESSION_ID,
        event_name: 'living_loop_choice_previewed' as const,
        client_occurred_at: '2026-08-28T12:00:00Z',
        properties: {
          surface_version: 1 as const,
          decision_id: DECISION_ID,
          scenario_key: 'harbor_wage_dispute_v1' as const,
          scenario_version: 1 as const,
          choice_key: 'private_mediation' as const,
        },
      }],
    }

    await postProductEventsBatch(batch)

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${API_BASE}/product-events/batch`)
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual(batch)
    expect(String(init.body)).not.toContain('resident@example.com')
    expect(String(init.body)).not.toContain('user_id')
  })

  it('loads the admin funnel with the pinned admin token and UTC window', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ generated_at: '2026-08-28T12:00:00Z' }))
    vi.stubGlobal('fetch', fetchMock)
    const params = {
      from: '2026-08-01T00:00:00Z',
      to: '2026-08-28T23:59:59Z',
    }

    await getAdminLivingLoopMetrics('admin-token', params)

    const query = new URLSearchParams(params).toString()
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/admin/product-metrics/living-loop-p0?${query}`,
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer admin-token' }),
      }),
    )
  })
})
