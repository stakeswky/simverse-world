import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  ChallengeApiError,
  approveChallenge,
  commitChallenge,
  createChallengeSession,
  getChallengeSession,
  investigateChallenge,
  resetChallenge,
  type ChallengeProjection,
} from './challenge'
import { API_BASE } from './core'

function projection(overrides: Record<string, unknown> = {}): ChallengeProjection {
  return {
    session_generation: 'generation-01',
    state: 'INITIAL',
    scenario_id: 'harbor-wage-crisis-v1',
    fixture_version: 1,
    world_version: 7,
    world_hash: `sha256:${'a'.repeat(64)}`,
    world_time: '2042-06-12T08:00:00Z',
    budget_sc: 300,
    tool_surface: ['simverse_investigate_crisis'],
    expires_at: '2042-06-12T08:15:00Z',
    csrf_token: 'csrf-01',
    world: {},
    evidence: null,
    preview: null,
    approval_fingerprint: null,
    approval_expires_at: null,
    receipt: null,
    verification: null,
    ...overrides,
  } as ChallengeProjection
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('challenge API client', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('uses API_BASE, include credentials, a timeout signal, and no auth storage', async () => {
    localStorage.setItem('token', 'must-not-be-read')
    const storageRead = vi.spyOn(localStorage, 'getItem')
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(jsonResponse(projection())),
    )
    vi.stubGlobal('fetch', fetchMock)

    await getChallengeSession()
    await createChallengeSession()

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      `${API_BASE}/challenge/session`,
      expect.objectContaining({
        method: 'GET',
        credentials: 'include',
        signal: expect.any(AbortSignal),
      }),
    )
    const createInit = fetchMock.mock.calls[1][1] as RequestInit
    expect(createInit).toEqual(expect.objectContaining({ method: 'POST', credentials: 'include' }))
    expect(new Headers(createInit.headers).get('Content-Type')).toBe('application/json')
    expect(new Headers(createInit.headers).has('Authorization')).toBe(false)
    expect(storageRead).not.toHaveBeenCalled()
  })

  it('sends snake_case JSON and the one shared CSRF header', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(projection()))
    vi.stubGlobal('fetch', fetchMock)

    await investigateChallenge({ budget_cap_sc: 300 }, 'csrf-01')

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${API_BASE}/challenge/investigate`)
    expect(init.method).toBe('POST')
    expect(init.credentials).toBe('include')
    expect(new Headers(init.headers).get('X-CSRF-Token')).toBe('csrf-01')
    expect(init.body).toBe(JSON.stringify({ budget_cap_sc: 300 }))
  })

  it('maps only the stable error envelope fields', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: 'PREVIEW_STALE',
              message: 'Preview is stale.',
              retryable: true,
              current_state: 'EVIDENCE_READY',
              next_action: 'preview',
              internal_trace: 'must-not-surface',
            },
            raw_exception: 'must-not-surface',
          },
          412,
        ),
      ),
    )

    const error = await getChallengeSession().catch((caught) => caught)
    expect(error).toBeInstanceOf(ChallengeApiError)
    expect(error).toMatchObject({
      code: 'PREVIEW_STALE',
      message: 'Preview is stale.',
      status: 412,
      retryable: true,
      currentState: 'EVIDENCE_READY',
      nextAction: 'preview',
    })
    expect(JSON.stringify(error)).not.toContain('internal_trace')
    expect(JSON.stringify(error)).not.toContain('raw_exception')
  })

  it.each([
    ['GET session', () => getChallengeSession()],
    ['investigate', () => investigateChallenge({ budget_cap_sc: 300 }, 'csrf-01')],
  ])('retries one network failure for %s', async (_name, invoke) => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('network down'))
      .mockResolvedValueOnce(jsonResponse(projection()))
    vi.stubGlobal('fetch', fetchMock)

    await expect(invoke()).resolves.toMatchObject({ state: 'INITIAL' })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it.each([
    ['approve', () => approveChallenge({ preview_id: 'preview-01', expected_world_version: 7, diff_hash: `sha256:${'a'.repeat(64)}` }, 'csrf-01')],
    ['commit', () => commitChallenge({ preview_id: 'preview-01', expected_world_version: 7, diff_hash: `sha256:${'a'.repeat(64)}` }, 'csrf-01')],
    ['reset', () => resetChallenge({ expected_generation: 'generation-01' }, 'csrf-01')],
  ])('does not blindly retry %s', async (_name, invoke) => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('network down'))
    vi.stubGlobal('fetch', fetchMock)

    await expect(invoke()).rejects.toBeInstanceOf(ChallengeApiError)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('aborts a non-retry mutation after exactly 15 seconds', async () => {
    vi.useFakeTimers()
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init: RequestInit) => new Promise((_resolve, reject) => {
        init.signal?.addEventListener('abort', () => reject(init.signal?.reason), { once: true })
      })),
    )

    const pending = approveChallenge(
      { preview_id: 'preview-01', expected_world_version: 7, diff_hash: `sha256:${'a'.repeat(64)}` },
      'csrf-01',
    )
    const rejection = expect(pending).rejects.toMatchObject({
      code: 'CHALLENGE_INTERNAL_ERROR',
      retryable: true,
    })
    await vi.advanceTimersByTimeAsync(14_999)
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    await rejection
  })
})
