import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  getAgentActivityHistory,
  publishAgentActivity,
  resetAgentActivityForTests,
  subscribeToAgentActivity,
  type PublishAgentActivityInput,
} from './activity'

function activity(index: number): PublishAgentActivityInput {
  return {
    toolName: 'simverse_investigate_crisis',
    phase: 'investigate',
    outcome: index % 2 === 0 ? 'completed' : 'failed',
    durationMs: index,
    reasonCode: index % 2 === 0 ? 'EVIDENCE_READY' : 'INVALID_INPUT',
    worldVersionBefore: 7,
    worldVersionAfter: 7,
    receiptId: null,
    fingerprint: 'sha256:aaaaaaaaaaaa',
  }
}

afterEach(() => {
  resetAgentActivityForTests()
  vi.restoreAllMocks()
})

describe('agent activity', () => {
  it('publishes only the explicit safe receipt fields', () => {
    const entry = publishAgentActivity(document, activity(12))

    expect(entry).toMatchObject({
      toolName: 'simverse_investigate_crisis',
      phase: 'investigate',
      outcome: 'completed',
      durationMs: 12,
      reasonCode: 'EVIDENCE_READY',
      worldVersionBefore: 7,
      worldVersionAfter: 7,
      receiptId: null,
      fingerprint: 'sha256:aaaaaaaaaaaa',
    })
    expect(Object.keys(activity(12)).sort()).toEqual([
      'durationMs',
      'fingerprint',
      'outcome',
      'phase',
      'reasonCode',
      'receiptId',
      'toolName',
      'worldVersionAfter',
      'worldVersionBefore',
    ])
    expect(JSON.stringify(entry)).not.toMatch(
      /approvalId|csrf|cookie|headers|stack|rawError|Authorization|Bearer/i,
    )
  })

  it('retains only the newest twenty immutable receipts', () => {
    for (let index = 0; index < 25; index += 1) {
      publishAgentActivity(document, activity(index))
    }

    const history = getAgentActivityHistory(document)
    expect(history).toHaveLength(20)
    expect(history[0]?.durationMs).toBe(24)
    expect(history.at(-1)?.durationMs).toBe(5)
    expect(Object.isFrozen(history)).toBe(true)
    expect(Object.isFrozen(history[0])).toBe(true)
  })

  it('notifies healthy listeners even when another subscriber throws', () => {
    const healthy = vi.fn()
    subscribeToAgentActivity(document, () => { throw new Error('subscriber failed') })
    const unsubscribe = subscribeToAgentActivity(document, healthy)

    publishAgentActivity(document, activity(1))
    expect(healthy).toHaveBeenCalledTimes(1)

    unsubscribe()
    publishAgentActivity(document, activity(2))
    expect(healthy).toHaveBeenCalledTimes(1)
  })
})
