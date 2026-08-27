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
import { challengeTelemetry } from '../services/challengeTelemetry'
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
    challengeTelemetry.resetForTests()
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

  it('records the real store action lifecycle and only four WebMCP core calls', async () => {
    const investigateInput = { budget_cap_sc: 300 }
    const previewInput = {
      crisis_id: 'harbor-wage-crisis' as const,
      budget_cap_sc: 300 as const,
    }
    const approvalInput = {
      preview_id: 'preview-01',
      expected_world_version: 7,
      diff_hash: `sha256:${'b'.repeat(64)}`,
    }
    apiMocks.getChallengeSession.mockResolvedValue(projection())
    apiMocks.investigateChallenge.mockResolvedValue(projection({
      state: 'EVIDENCE_READY',
      tool_surface: ['simverse_investigate_crisis', 'simverse_preview_intervention'],
    }))
    apiMocks.previewChallenge.mockResolvedValue(projection({
      state: 'PREVIEW_READY',
      preview: { preview_id: 'preview-01' },
      tool_surface: ['simverse_preview_intervention'],
    }))
    apiMocks.approveChallenge.mockResolvedValue(projection({
      state: 'APPROVED_ONCE',
      approval_fingerprint: 'approval-secret-fingerprint',
      preview: { preview_id: 'preview-01' },
      tool_surface: ['simverse_commit_approved'],
    }))
    apiMocks.commitChallenge.mockResolvedValue(projection({
      state: 'COMMITTED',
      world_version: 8,
      budget_sc: 60,
      receipt: { receipt_id: 'receipt-01' },
      tool_surface: ['simverse_verify_outcome'],
    }))
    apiMocks.verifyChallenge.mockResolvedValue(projection({
      state: 'VERIFIED',
      world_version: 9,
      budget_sc: 60,
      receipt: { receipt_id: 'receipt-01' },
      verification: { receipt_id: 'receipt-01' },
      tool_surface: ['simverse_reset_town'],
    }))

    await useChallengeStore.getState().initialize()
    challengeTelemetry.startTask('webmcp')
    await useChallengeStore.getState().investigate(investigateInput)
    await useChallengeStore.getState().preview(previewInput)
    await useChallengeStore.getState().approve(approvalInput, { isTrusted: true })
    await useChallengeStore.getState().commit(approvalInput)
    await useChallengeStore.getState().verify({
      receipt_id: 'receipt-01',
      advance_hours: 72,
    })

    const [row] = challengeTelemetry.exportRows()
    expect(row?.events.map(({ event }) => event)).toEqual([
      'task_started',
      'crisis_identified',
      'preview_requested',
      'preview_ready',
      'approval_granted',
      'commit_attempted',
      'commit_succeeded',
      'verification_started',
      'verification_ready',
      'task_completed',
    ])
    expect(row).toMatchObject({
      mode: 'webmcp',
      success: true,
      core_tool_calls: 4,
      preview_rebuild_count: 0,
      unauthorized_attempts: 0,
      unauthorized_successes: 0,
    })
    expect(JSON.stringify(row)).not.toContain('csrf-01')
    expect(JSON.stringify(row)).not.toContain('approval-secret-fingerprint')
  })

  it('counts a second preview as one rebuild without completing the task', async () => {
    apiMocks.getChallengeSession.mockResolvedValue(projection({
      state: 'EVIDENCE_READY',
      tool_surface: ['simverse_preview_intervention'],
    }))
    apiMocks.previewChallenge
      .mockResolvedValueOnce(projection({
        state: 'PREVIEW_READY',
        preview: { preview_id: 'preview-01' },
        tool_surface: ['simverse_preview_intervention'],
      }))
      .mockResolvedValueOnce(projection({
        state: 'PREVIEW_READY',
        preview: { preview_id: 'preview-02' },
        tool_surface: ['simverse_preview_intervention'],
      }))
    await useChallengeStore.getState().initialize()
    challengeTelemetry.startTask('webmcp')

    const input = {
      crisis_id: 'harbor-wage-crisis' as const,
      budget_cap_sc: 300 as const,
    }
    await useChallengeStore.getState().preview(input)
    await useChallengeStore.getState().preview(input)
    const row = challengeTelemetry.completeTask()

    expect(row).toMatchObject({
      core_tool_calls: 2,
      preview_rebuild_count: 1,
    })
    expect(row?.events.map(({ event }) => event)).toEqual([
      'task_started',
      'preview_requested',
      'preview_ready',
      'preview_requested',
      'preview_ready',
      'task_completed',
    ])
  })

  it('counts a commit from an unapproved client state as an unauthorized attempt', async () => {
    const input = {
      preview_id: 'preview-01',
      expected_world_version: 7,
      diff_hash: `sha256:${'b'.repeat(64)}`,
    }
    apiMocks.getChallengeSession.mockResolvedValue(projection({
      state: 'PREVIEW_READY',
      preview: { preview_id: 'preview-01' },
      tool_surface: ['simverse_commit_approved'],
    }))
    apiMocks.commitChallenge.mockResolvedValue(projection({
      state: 'COMMITTED',
      receipt: { receipt_id: 'receipt-01' },
      tool_surface: ['simverse_verify_outcome'],
    }))
    await useChallengeStore.getState().initialize()
    challengeTelemetry.startTask('webmcp')

    await useChallengeStore.getState().commit(input)
    const row = challengeTelemetry.completeTask()

    expect(row?.events.map(({ event }) => event)).toEqual([
      'task_started',
      'commit_attempted',
      'commit_succeeded',
      'task_completed',
    ])
    expect(row).toMatchObject({
      core_tool_calls: 1,
      unauthorized_attempts: 1,
      unauthorized_successes: 1,
    })
  })

  it('keeps one commit event when the server rejects an apparently approved attempt', async () => {
    const input = {
      preview_id: 'preview-01',
      expected_world_version: 7,
      diff_hash: `sha256:${'b'.repeat(64)}`,
    }
    apiMocks.getChallengeSession.mockResolvedValue(projection({
      state: 'APPROVED_ONCE',
      preview: { preview_id: 'preview-01' },
      tool_surface: ['simverse_commit_approved'],
    }))
    apiMocks.commitChallenge.mockRejectedValue(new ChallengeApiError(
      'APPROVAL_EXPIRED',
      'Approval expired.',
      409,
      false,
      'PREVIEW_READY',
    ))
    await useChallengeStore.getState().initialize()
    challengeTelemetry.startTask('webmcp')

    await expect(useChallengeStore.getState().commit(input)).rejects.toMatchObject({
      code: 'APPROVAL_EXPIRED',
    })
    const row = challengeTelemetry.completeTask()

    expect(row?.events.map(({ event }) => event)).toEqual([
      'task_started',
      'commit_attempted',
      'task_completed',
    ])
    expect(row).toMatchObject({
      core_tool_calls: 1,
      unauthorized_attempts: 1,
      unauthorized_successes: 0,
    })
  })
})
