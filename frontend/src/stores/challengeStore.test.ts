import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  getChallengeSession: vi.fn(),
  createChallengeSession: vi.fn(),
  investigateChallenge: vi.fn(),
  previewChallenge: vi.fn(),
  approveChallenge: vi.fn(),
  revokeChallenge: vi.fn(),
  commitChallenge: vi.fn(),
  verifyChallenge: vi.fn(),
  resetChallenge: vi.fn(),
}))

vi.mock('../services/api/challenge', async () => {
  const actual = await vi.importActual<typeof import('../services/api/challenge')>(
    '../services/api/challenge',
  )
  return { ...actual, ...apiMocks }
})

import { ChallengeApiError, type ChallengeProjection } from '../services/api/challenge'
import { useChallengeStore } from './challengeStore'

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

describe('challenge store', () => {
  beforeEach(() => {
    localStorage.clear()
    useChallengeStore.getState().clearForTests()
    for (const mock of Object.values(apiMocks)) mock.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('restores an existing anonymous session with GET', async () => {
    apiMocks.getChallengeSession.mockResolvedValue(
      projection({ state: 'EVIDENCE_READY', tool_surface: ['simverse_preview_intervention'] }),
    )

    await useChallengeStore.getState().initialize()

    expect(apiMocks.getChallengeSession).toHaveBeenCalledTimes(1)
    expect(apiMocks.createChallengeSession).not.toHaveBeenCalled()
    expect(useChallengeStore.getState()).toMatchObject({
      loading: false,
      activeToolNames: ['simverse_preview_intervention'],
    })
    expect(useChallengeStore.getState().session?.state).toBe('EVIDENCE_READY')
  })

  it('creates with POST only after GET reports not-ready', async () => {
    apiMocks.getChallengeSession.mockRejectedValue(
      new ChallengeApiError('CHALLENGE_SESSION_NOT_READY', 'Not ready.', 409, true),
    )
    apiMocks.createChallengeSession.mockResolvedValue(projection())

    await useChallengeStore.getState().initialize()

    expect(apiMocks.getChallengeSession).toHaveBeenCalledTimes(1)
    expect(apiMocks.createChallengeSession).toHaveBeenCalledTimes(1)
    expect(useChallengeStore.getState().session?.session_generation).toBe('generation-01')
  })

  it('keeps session state and csrf in memory only', async () => {
    apiMocks.getChallengeSession.mockResolvedValue(projection())
    await useChallengeStore.getState().initialize()

    expect(useChallengeStore.getState().session?.csrf_token).toBe('csrf-01')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('passes execution signals, updates one session, and returns a redacted tool result', async () => {
    const controller = new AbortController()
    apiMocks.getChallengeSession.mockResolvedValue(projection())
    apiMocks.investigateChallenge.mockResolvedValue(
      projection({
        state: 'EVIDENCE_READY',
        world_version: 7,
        tool_surface: ['simverse_investigate_crisis', 'simverse_preview_intervention'],
      }),
    )
    await useChallengeStore.getState().initialize()

    const result = await useChallengeStore
      .getState()
      .investigate({ budget_cap_sc: 300 }, controller.signal)

    expect(apiMocks.investigateChallenge).toHaveBeenCalledWith(
      { budget_cap_sc: 300 },
      'csrf-01',
      controller.signal,
    )
    expect(useChallengeStore.getState().session?.state).toBe('EVIDENCE_READY')
    expect(result.structuredContent).toMatchObject({
      state: 'EVIDENCE_READY',
      world_version: 7,
      next_tool: 'simverse_investigate_crisis',
    })
    expect(JSON.stringify(result)).not.toContain('csrf-01')
  })

  it('requires a trusted visible approval and never calls the API when rejected', async () => {
    apiMocks.getChallengeSession.mockResolvedValue(
      projection({ state: 'PREVIEW_READY', tool_surface: ['simverse_preview_intervention'] }),
    )
    await useChallengeStore.getState().initialize()
    const input = {
      preview_id: 'preview-01',
      expected_world_version: 7,
      diff_hash: `sha256:${'a'.repeat(64)}`,
    }

    await expect(
      useChallengeStore.getState().approve(input, { isTrusted: false }),
    ).rejects.toMatchObject({
      code: 'APPROVAL_REQUIRED',
      message: 'Use the visible trusted approval control.',
      currentState: 'PREVIEW_READY',
      nextAction: 'Review and approve the visible World Diff.',
    })
    expect(apiMocks.approveChallenge).not.toHaveBeenCalled()
  })

  it('accepts trusted approval when userActivation is absent and has no WebMCP dependency', async () => {
    apiMocks.getChallengeSession.mockResolvedValue(
      projection({ state: 'PREVIEW_READY', tool_surface: ['simverse_preview_intervention'] }),
    )
    apiMocks.approveChallenge.mockResolvedValue(
      projection({ state: 'APPROVED_ONCE', tool_surface: ['simverse_commit_approved'] }),
    )
    Reflect.deleteProperty(document, 'modelContext')
    Reflect.deleteProperty(navigator, 'modelContext')
    await useChallengeStore.getState().initialize()

    await useChallengeStore.getState().approve(
      {
        preview_id: 'preview-01',
        expected_world_version: 7,
        diff_hash: `sha256:${'a'.repeat(64)}`,
      },
      { isTrusted: true },
    )

    expect(apiMocks.approveChallenge).toHaveBeenCalledTimes(1)
    expect(useChallengeStore.getState().session?.state).toBe('APPROVED_ONCE')
  })

  it('resets using the in-memory csrf and adopts the returned generation', async () => {
    const controller = new AbortController()
    apiMocks.getChallengeSession.mockResolvedValue(
      projection({ state: 'VERIFIED', tool_surface: ['simverse_reset_town'] }),
    )
    apiMocks.resetChallenge.mockResolvedValue(
      projection({ session_generation: 'generation-02', csrf_token: 'csrf-02' }),
    )
    await useChallengeStore.getState().initialize()

    const result = await useChallengeStore
      .getState()
      .reset({ expected_generation: 'generation-01' }, controller.signal)

    expect(apiMocks.resetChallenge).toHaveBeenCalledWith(
      { expected_generation: 'generation-01' },
      'csrf-01',
      controller.signal,
    )
    expect(useChallengeStore.getState().session?.session_generation).toBe('generation-02')
    expect(result.structuredContent).toMatchObject({ state: 'INITIAL' })
    expect(localStorage.length).toBe(0)
  })
})
