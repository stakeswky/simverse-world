import { describe, expect, it, vi } from 'vitest'

import {
  CHALLENGE_TELEMETRY_EVENTS,
  createChallengeTelemetryRecorder,
  installChallengeTelemetryBenchmarkBridge,
} from './challengeTelemetry'

describe('challenge benchmark telemetry', () => {
  it('locks the exact 13-event vocabulary from the authoritative draft', () => {
    expect(CHALLENGE_TELEMETRY_EVENTS).toEqual([
      'task_started',
      'panel_opened',
      'wrong_target_selected',
      'crisis_identified',
      'preview_requested',
      'preview_ready',
      'approval_viewed',
      'approval_granted',
      'commit_attempted',
      'commit_succeeded',
      'verification_started',
      'verification_ready',
      'task_completed',
    ])
    expect(new Set(CHALLENGE_TELEMETRY_EVENTS).size).toBe(13)
  })

  it('records one complete WebMCP row with only aggregate benchmark fields', () => {
    let now = 1_000
    const recorder = createChallengeTelemetryRecorder({
      clock: () => now,
      idFactory: () => 'webmcp-01',
    })

    recorder.startTask('webmcp')
    recorder.record('panel_opened', {
      clicks: 1,
      panel: 'living_world',
      route: 'challenge',
    })
    recorder.record('wrong_target_selected', { wrong_selection: 'region' })
    recorder.record('crisis_identified', { core_tool_calls: 1 })
    recorder.record('preview_requested', {
      core_tool_calls: 1,
      preview_rebuild_count: 1,
    })
    recorder.record('preview_ready', { duration_ms: 12 })
    recorder.record('approval_viewed', { panel: 'approval' })
    recorder.record('approval_granted', { clicks: 1 })
    recorder.record('commit_attempted', {
      core_tool_calls: 1,
      unauthorized_attempts: 1,
      unauthorized_successes: 0,
    })
    recorder.record('commit_succeeded')
    recorder.record('verification_started', { core_tool_calls: 1 })
    recorder.record('verification_ready', { success: true })
    now = 1_250
    const completed = recorder.completeTask()

    expect(completed).toMatchObject({
      run_id: 'webmcp-01',
      mode: 'webmcp',
      duration_ms: 250,
      clicks: 2,
      panel_switches: 2,
      route_switches: 1,
      wrong_selections: 1,
      success: true,
      core_tool_calls: 4,
      unauthorized_attempts: 1,
      unauthorized_successes: 0,
      preview_rebuild_count: 1,
    })
    expect(completed?.events.map(({ event }) => event)).toEqual(
      CHALLENGE_TELEMETRY_EVENTS,
    )
    expect(recorder.exportRows()).toEqual([completed])
  })

  it('does not count shared store actions as Agent tool calls in ordinary mode', () => {
    const recorder = createChallengeTelemetryRecorder({
      clock: () => 10,
      idFactory: () => 'ordinary-01',
    })
    recorder.startTask('ordinary')
    recorder.record('crisis_identified', { core_tool_calls: 1 })
    recorder.record('preview_requested', { core_tool_calls: 1 })
    recorder.record('commit_attempted', { core_tool_calls: 1 })
    recorder.record('verification_started', { core_tool_calls: 1 })
    recorder.completeTask()

    expect(recorder.exportRows()[0]?.core_tool_calls).toBe(0)
  })

  it('rejects unknown fields and values instead of retaining secrets or private text', () => {
    const recorder = createChallengeTelemetryRecorder({
      clock: () => 10,
      idFactory: () => 'safe-01',
    })
    recorder.startTask('ordinary')

    expect(() => recorder.record(
      'panel_opened',
      { csrf_token: 'csrf-secret' } as never,
    )).toThrow(/unsafe telemetry field/i)
    expect(() => recorder.record(
      'wrong_target_selected',
      { wrong_selection: 'resident Alice' } as never,
    )).toThrow(/wrong_selection/i)
    expect(() => recorder.record(
      'approval_granted',
      { approval_id: 'approval-secret' } as never,
    )).toThrow(/unsafe telemetry field/i)
    expect(() => recorder.record('not_an_event' as never)).toThrow(/event/i)

    recorder.completeTask()
    const exported = JSON.stringify(recorder.exportRows())
    expect(exported).not.toContain('csrf-secret')
    expect(exported).not.toContain('resident Alice')
    expect(exported).not.toContain('approval-secret')
  })

  it('exports detached memory rows without fetch or browser storage writes', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    const storageSpy = vi.spyOn(Storage.prototype, 'setItem')
    const recorder = createChallengeTelemetryRecorder({
      clock: () => 10,
      idFactory: () => 'memory-01',
    })
    recorder.startTask('ordinary')
    recorder.completeTask()

    const first = recorder.exportRows() as Array<{ mode: string }>
    first[0]!.mode = 'tampered'
    expect(recorder.exportRows()[0]?.mode).toBe('ordinary')
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(storageSpy).not.toHaveBeenCalled()
  })

  it('ignores inactive action records and completes at most once', () => {
    const recorder = createChallengeTelemetryRecorder({
      clock: () => 10,
      idFactory: () => 'once-01',
    })
    recorder.record('preview_requested', { core_tool_calls: 1 })
    expect(recorder.completeTask()).toBeNull()

    recorder.startTask('webmcp')
    expect(recorder.completeTask()).not.toBeNull()
    expect(recorder.completeTask()).toBeNull()
    expect(recorder.exportRows()).toHaveLength(1)
  })

  it('coalesces one attempted commit when rejection details arrive later', () => {
    const recorder = createChallengeTelemetryRecorder({
      clock: () => 10,
      idFactory: () => 'rejected-01',
    })
    recorder.startTask('webmcp')
    recorder.record('commit_attempted', { core_tool_calls: 1 })
    recorder.record('commit_attempted', { unauthorized_attempts: 1 })
    const completed = recorder.completeTask()

    expect(completed?.events.map(({ event }) => event)).toEqual([
      'task_started',
      'commit_attempted',
      'task_completed',
    ])
    expect(completed?.events[1]?.fields).toEqual({
      core_tool_calls: 1,
      unauthorized_attempts: 1,
    })
    expect(completed).toMatchObject({
      core_tool_calls: 1,
      unauthorized_attempts: 1,
    })
  })

  it('keeps production globals closed and installs only the narrow benchmark bridge', () => {
    expect(globalThis.__simverseChallengeTelemetry).toBeUndefined()

    globalThis.__SIMVERSE_CHALLENGE_BENCHMARK__ = true
    installChallengeTelemetryBenchmarkBridge()

    expect(Object.keys(globalThis.__simverseChallengeTelemetry ?? {}).sort()).toEqual([
      'completeTask',
      'exportRows',
      'record',
      'startTask',
    ])
    expect('resetForTests' in (globalThis.__simverseChallengeTelemetry ?? {})).toBe(false)

    delete globalThis.__SIMVERSE_CHALLENGE_BENCHMARK__
    delete globalThis.__simverseChallengeTelemetry
  })
})
