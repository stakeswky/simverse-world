import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  ChallengeWebMcpHarness,
  challengeProjection,
} from '../test/challengeWebMcpHarness'
import {
  ChallengeToolSurfaceManager,
  STALE_TOOL_SURFACE_RESULT,
} from './challengeToolSurfaceManager'
import type { WebMcpToolDefinition } from './types'

function definition(
  name: string,
  execute: WebMcpToolDefinition['execute'] = vi.fn(async () => ({ name })),
): WebMcpToolDefinition {
  return {
    name,
    description: `Challenge tool ${name}`,
    inputSchema: {
      type: 'object',
      properties: {},
      additionalProperties: false,
    },
    execute,
  }
}

function manager(
  harness: ChallengeWebMcpHarness,
  createTool: (name: string) => WebMcpToolDefinition = definition,
): ChallengeToolSurfaceManager {
  return new ChallengeToolSurfaceManager({
    modelContext: harness.modelContext,
    createTool: (name) => createTool(name),
    reload: harness.reload,
  })
}

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('ChallengeToolSurfaceManager', () => {
  it('registers the projected surface with one shared lifecycle signal', async () => {
    const harness = new ChallengeWebMcpHarness()
    const surface = manager(harness)

    await expect(surface.sync(challengeProjection())).resolves.toBe('registered')

    expect(harness.toolNames()).toEqual(['simverse_investigate_crisis'])
    expect(harness.registrationCalls).toHaveLength(1)
    expect(harness.registrationCalls[0]?.options).toEqual({
      signal: expect.any(AbortSignal),
    })
    expect(harness.registrationCalls[0]?.options?.signal?.aborted).toBe(false)
  })

  it('waits for abort-driven removal through getTools and toolchange before replacing a surface', async () => {
    vi.useFakeTimers()
    const harness = new ChallengeWebMcpHarness({ unregisterDelayMs: 75 })
    const surface = manager(harness)
    await surface.sync(challengeProjection())

    const next = surface.sync(challengeProjection({
      state: 'PREVIEW_READY',
      tool_surface: ['simverse_preview_intervention'],
    }))
    await vi.advanceTimersByTimeAsync(75)

    await expect(next).resolves.toBe('registered')
    expect(harness.toolNames()).toEqual(['simverse_preview_intervention'])
    expect(harness.getToolsCalls).toBeGreaterThan(0)
    expect(harness.getToolsCalls).toBeLessThan(21)
  })

  it('deduplicates a StrictMode-style repeated sync for the same projection', async () => {
    const harness = new ChallengeWebMcpHarness()
    const surface = manager(harness)
    const projection = challengeProjection()

    const states = await Promise.all([
      surface.sync(projection),
      surface.sync(projection),
      surface.sync(projection),
    ])

    expect(states).toEqual(['registered', 'registered', 'registered'])
    expect(harness.registrationCalls).toHaveLength(1)
    expect(surface.currentEpoch()).toBe(1)
  })

  it('makes a captured old-epoch handler return the fixed stale result', async () => {
    const originalExecute = vi.fn(async () => ({ ok: true }))
    const harness = new ChallengeWebMcpHarness()
    const surface = manager(harness, (name) => definition(name, originalExecute))
    await surface.sync(challengeProjection())
    const oldTool = harness.tool('simverse_investigate_crisis')

    await surface.sync(challengeProjection({
      state: 'PREVIEW_READY',
      tool_surface: ['simverse_preview_intervention'],
    }))
    const result = await oldTool?.execute(
      {},
      { signal: new AbortController().signal },
    )

    expect(result).toEqual(STALE_TOOL_SURFACE_RESULT)
    expect(originalExecute).not.toHaveBeenCalled()
  })

  it('does not let a rejected old registration erase a newer epoch', async () => {
    let rejectOld: (reason?: unknown) => void = () => undefined
    const pending = new Promise<void>((_resolve, reject) => {
      rejectOld = reject
    })
    const harness = new ChallengeWebMcpHarness()
    harness.queueRegistrationOutcome(pending)
    const surface = manager(harness)

    const oldState = surface.sync(challengeProjection())
    await Promise.resolve()
    const newState = surface.sync(challengeProjection({
      state: 'PREVIEW_READY',
      tool_surface: ['simverse_preview_intervention'],
    }))
    await expect(newState).resolves.toBe('registered')
    rejectOld(new Error('old registration rejected'))

    await expect(oldState).resolves.toBe('stale')
    expect(harness.toolNames()).toEqual(['simverse_preview_intervention'])
    expect(harness.registrationCalls[1]?.options?.signal?.aborted).toBe(false)
  })

  it('keeps a newly registered same-name tool when the old signal aborts', async () => {
    const harness = new ChallengeWebMcpHarness()
    const surface = manager(harness)
    await surface.sync(challengeProjection({
      state: 'EVIDENCE_READY',
      tool_surface: [
        'simverse_investigate_crisis',
        'simverse_preview_intervention',
      ],
    }))
    const oldPreview = harness.tool('simverse_preview_intervention')

    await surface.sync(challengeProjection({
      state: 'PREVIEW_READY',
      tool_surface: ['simverse_preview_intervention'],
    }))

    expect(harness.toolNames()).toEqual(['simverse_preview_intervention'])
    expect(harness.tool('simverse_preview_intervention')).not.toBe(oldPreview)
  })

  it('destroy aborts the active surface and advances the epoch', async () => {
    const harness = new ChallengeWebMcpHarness()
    const surface = manager(harness)
    await surface.sync(challengeProjection())
    const signal = harness.registrationCalls[0]?.options?.signal
    const epoch = surface.currentEpoch()

    surface.destroy()

    expect(surface.currentEpoch()).toBe(epoch + 1)
    expect(signal?.aborted).toBe(true)
    expect(harness.toolNames()).toEqual([])
  })

  it('fails closed and invalidates the old epoch for a non-challenge tool name', async () => {
    const harness = new ChallengeWebMcpHarness()
    const surface = manager(harness)
    await surface.sync(challengeProjection())
    const oldTool = harness.tool('simverse_investigate_crisis')

    await expect(surface.sync(challengeProjection({
      tool_surface: ['untrusted-notice-requested-tool'],
    }))).resolves.toBe('failed')

    expect(harness.toolNames()).toEqual([])
    expect(await oldTool?.execute(
      {},
      { signal: new AbortController().signal },
    )).toEqual(STALE_TOOL_SURFACE_RESULT)
    expect(harness.registrationCalls).toHaveLength(1)
  })

  it('reloads and stops when replacing a surface on a host without getTools', async () => {
    const harness = new ChallengeWebMcpHarness({ supportsGetTools: false })
    const surface = manager(harness)
    await expect(surface.sync(challengeProjection())).resolves.toBe('registered')

    await expect(surface.sync(challengeProjection({
      state: 'PREVIEW_READY',
      tool_surface: ['simverse_preview_intervention'],
    }))).resolves.toBe('stale')

    expect(harness.reloadCount).toBe(1)
    expect(harness.registrationCalls).toHaveLength(1)
  })

  it('marks the surface stale and reloads when old tools remain for 500ms', async () => {
    vi.useFakeTimers()
    const harness = new ChallengeWebMcpHarness({ retainToolsOnAbort: true })
    const surface = manager(harness)
    await surface.sync(challengeProjection())

    const next = surface.sync(challengeProjection({
      state: 'PREVIEW_READY',
      tool_surface: ['simverse_preview_intervention'],
    }))
    await vi.advanceTimersByTimeAsync(500)

    await expect(next).resolves.toBe('stale')
    expect(harness.reloadCount).toBe(1)
    expect(harness.registrationCalls).toHaveLength(1)
  })
})
