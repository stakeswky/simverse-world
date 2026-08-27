import {
  ChallengeApiError,
  type ChallengeProjection,
  type InvestigateInput,
} from '../services/api/challenge'
import { useChallengeStore } from '../stores/challengeStore'
import { publishAgentActivity } from './activity'
import { buildInvestigateToolOutput } from './challengeToolResults'
import type { WebMcpToolDefinition } from './types'

export const INVESTIGATE_TOOL_NAME = 'simverse_investigate_crisis'

export interface ChallengeToolState {
  readonly session: ChallengeProjection | null
  readonly investigate: (
    input: InvestigateInput,
    signal?: AbortSignal,
  ) => Promise<unknown>
}

export interface ChallengeToolStore {
  getState(): ChallengeToolState
}

interface ChallengeToolOptions {
  readonly store?: ChallengeToolStore
  readonly document?: Document
  readonly clock?: () => number
}

interface SafeToolError {
  readonly error: {
    readonly code: string
    readonly message: string
    readonly retryable: boolean
  }
}

function currentDocument(): Document | undefined {
  return typeof document === 'undefined' ? undefined : document
}

function monotonicNow(): number {
  return globalThis.performance?.now?.() ?? Date.now()
}

function safeDuration(clock: () => number, startedAt: number): number {
  try {
    return Math.max(0, Math.round(clock() - startedAt))
  } catch {
    return 0
  }
}

function hasInvestigateInput(input: Record<string, unknown>): input is {
  budget_cap_sc: number
} {
  return (
    Object.keys(input).length === 1
    && Number.isInteger(input.budget_cap_sc)
    && typeof input.budget_cap_sc === 'number'
    && input.budget_cap_sc >= 1
    && input.budget_cap_sc <= 300
  )
}

function shortFingerprint(projection: ChallengeProjection | null): string | null {
  return projection?.world_hash.slice(0, 19) ?? null
}

function safeError(
  code: string,
  message: string,
  retryable = false,
): SafeToolError {
  return { error: { code, message, retryable } }
}

function errorCode(error: unknown, aborted: boolean): string {
  if (aborted) return 'REQUEST_ABORTED'
  if (error instanceof ChallengeApiError) return error.code
  return 'CHALLENGE_INTERNAL_ERROR'
}

export function createInvestigateTool(
  options: ChallengeToolOptions = {},
): WebMcpToolDefinition {
  const store = options.store ?? useChallengeStore
  const toolDocument = options.document ?? currentDocument()
  const clock = options.clock ?? monotonicNow

  return {
    name: INVESTIGATE_TOOL_NAME,
    title: 'Investigate Harbor crisis',
    description: 'Read cross-domain evidence for the isolated Harbor wage crisis without changing the world.',
    inputSchema: {
      type: 'object',
      properties: {
        budget_cap_sc: { type: 'integer', minimum: 1, maximum: 300 },
      },
      required: ['budget_cap_sc'],
      additionalProperties: false,
    },
    annotations: {
      readOnlyHint: true,
      untrustedContentHint: true,
    },
    execute: async (input, executionOptions) => {
      let startedAt = 0
      try {
        startedAt = clock()
      } catch {
        // Timing is diagnostic and never changes tool behavior.
      }
      const before = store.getState().session

      const record = (
        outcome: 'completed' | 'failed',
        reasonCode: string,
        after: ChallengeProjection | null,
      ) => {
        if (!toolDocument) return
        publishAgentActivity(toolDocument, {
          toolName: INVESTIGATE_TOOL_NAME,
          phase: 'investigate',
          outcome,
          durationMs: safeDuration(clock, startedAt),
          reasonCode,
          worldVersionBefore: before?.world_version ?? 0,
          worldVersionAfter: after?.world_version ?? before?.world_version ?? 0,
          receiptId: null,
          fingerprint: shortFingerprint(after ?? before),
        })
      }

      if (executionOptions.signal.aborted) {
        record('failed', 'REQUEST_ABORTED', before)
        return safeError(
          'REQUEST_ABORTED',
          'Tool execution was cancelled before the request started.',
          true,
        )
      }
      if (!hasInvestigateInput(input)) {
        record('failed', 'INVALID_INPUT', before)
        return safeError(
          'INVALID_INPUT',
          'Tool input must match the investigate schema.',
        )
      }

      try {
        await store.getState().investigate(
          { budget_cap_sc: input.budget_cap_sc },
          executionOptions.signal,
        )
        const after = store.getState().session
        if (!after) throw new Error('Missing challenge projection.')
        const output = buildInvestigateToolOutput(after)
        record('completed', 'EVIDENCE_READY', after)
        return output
      } catch (error) {
        const after = store.getState().session
        const code = errorCode(error, executionOptions.signal.aborted)
        record('failed', code, after)
        return safeError(
          code,
          code === 'REQUEST_ABORTED'
            ? 'Tool execution was cancelled.'
            : 'Challenge investigation could not be completed.',
          code === 'REQUEST_ABORTED'
            || (error instanceof ChallengeApiError && error.retryable),
        )
      }
    },
  }
}

export function createChallengeTool(
  name: string,
  options: ChallengeToolOptions = {},
): WebMcpToolDefinition {
  if (name === INVESTIGATE_TOOL_NAME) return createInvestigateTool(options)
  throw new Error(`Tool ${name} is not implemented for this phase.`)
}
