import {
  ChallengeApiError,
  type ChallengeProjection,
  type CommitInput,
  type InvestigateInput,
  type PreviewInput,
} from '../services/api/challenge'
import { useChallengeStore } from '../stores/challengeStore'
import { publishAgentActivity } from './activity'
import {
  buildCommitToolOutput,
  buildInvestigateToolOutput,
  buildPreviewToolOutput,
} from './challengeToolResults'
import type { WebMcpToolDefinition } from './types'

export const INVESTIGATE_TOOL_NAME = 'simverse_investigate_crisis'
export const PREVIEW_TOOL_NAME = 'simverse_preview_intervention'
export const COMMIT_TOOL_NAME = 'simverse_commit_approved'

export interface ChallengeToolState {
  readonly session: ChallengeProjection | null
  readonly investigate: (
    input: InvestigateInput,
    signal?: AbortSignal,
  ) => Promise<unknown>
  readonly preview: (
    input: PreviewInput,
    signal?: AbortSignal,
  ) => Promise<unknown>
  readonly commit: (
    input: CommitInput,
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

function hasPreviewInput(input: Record<string, unknown>): input is {
  crisis_id: 'harbor-wage-crisis'
  budget_cap_sc: 300
} {
  return (
    Object.keys(input).length === 2
    && input.crisis_id === 'harbor-wage-crisis'
    && input.budget_cap_sc === 300
  )
}

function hasCommitInput(input: Record<string, unknown>): input is {
  preview_id: string
  expected_world_version: number
  diff_hash: string
} {
  return (
    Object.keys(input).length === 3
    && typeof input.preview_id === 'string'
    && Number.isInteger(input.expected_world_version)
    && typeof input.expected_world_version === 'number'
    && typeof input.diff_hash === 'string'
    && /^sha256:[0-9a-f]{64}$/.test(input.diff_hash)
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

export function createPreviewTool(
  options: ChallengeToolOptions = {},
): WebMcpToolDefinition {
  const store = options.store ?? useChallengeStore
  const toolDocument = options.document ?? currentDocument()
  const clock = options.clock ?? monotonicNow

  return {
    name: PREVIEW_TOOL_NAME,
    title: 'Preview Harbor intervention',
    description: 'Build an immutable World Diff and deterministic 72-hour forecast without changing the challenge world.',
    inputSchema: {
      type: 'object',
      properties: {
        crisis_id: { type: 'string', enum: ['harbor-wage-crisis'] },
        budget_cap_sc: { type: 'integer', const: 300 },
      },
      required: ['crisis_id', 'budget_cap_sc'],
      additionalProperties: false,
    },
    annotations: {
      readOnlyHint: false,
      untrustedContentHint: false,
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
          toolName: PREVIEW_TOOL_NAME,
          phase: 'preview',
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
      if (!hasPreviewInput(input)) {
        record('failed', 'INVALID_INPUT', before)
        return safeError(
          'INVALID_INPUT',
          'Tool input must match the preview schema.',
        )
      }

      try {
        await store.getState().preview(
          {
            crisis_id: input.crisis_id,
            budget_cap_sc: input.budget_cap_sc,
          },
          executionOptions.signal,
        )
        const after = store.getState().session
        if (!after) throw new Error('Missing challenge projection.')
        const output = buildPreviewToolOutput(after)
        record('completed', 'PREVIEW_READY', after)
        return output
      } catch (error) {
        const after = store.getState().session
        const code = errorCode(error, executionOptions.signal.aborted)
        record('failed', code, after)
        return safeError(
          code,
          code === 'REQUEST_ABORTED'
            ? 'Tool execution was cancelled.'
            : 'Challenge preview could not be completed.',
          code === 'REQUEST_ABORTED'
            || (error instanceof ChallengeApiError && error.retryable),
        )
      }
    },
  }
}

export function createCommitTool(
  options: ChallengeToolOptions = {},
): WebMcpToolDefinition {
  const store = options.store ?? useChallengeStore
  const toolDocument = options.document ?? currentDocument()
  const clock = options.clock ?? monotonicNow

  return {
    name: COMMIT_TOOL_NAME,
    title: 'Commit approved Harbor intervention',
    description: 'Use the one-time capability for the exact approved diff. This action is irreversible inside the disposable Challenge Town.',
    inputSchema: {
      type: 'object',
      properties: {
        preview_id: { type: 'string' },
        expected_world_version: { type: 'integer' },
        diff_hash: {
          type: 'string',
          pattern: '^sha256:[0-9a-f]{64}$',
        },
      },
      required: ['preview_id', 'expected_world_version', 'diff_hash'],
      additionalProperties: false,
    },
    annotations: {
      readOnlyHint: false,
      untrustedContentHint: false,
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
          toolName: COMMIT_TOOL_NAME,
          phase: 'commit',
          outcome,
          durationMs: safeDuration(clock, startedAt),
          reasonCode,
          worldVersionBefore: before?.world_version ?? 0,
          worldVersionAfter: after?.world_version ?? before?.world_version ?? 0,
          receiptId: after?.receipt?.receipt_id ?? null,
          fingerprint: after?.receipt?.approval_fingerprint
            ?? before?.approval_fingerprint
            ?? null,
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
      if (!hasCommitInput(input)) {
        record('failed', 'INVALID_INPUT', before)
        return safeError(
          'INVALID_INPUT',
          'Tool input must match the approved commit schema.',
        )
      }

      try {
        await store.getState().commit(
          {
            preview_id: input.preview_id,
            expected_world_version: input.expected_world_version,
            diff_hash: input.diff_hash,
          },
          executionOptions.signal,
        )
        const after = store.getState().session
        if (!after) throw new Error('Missing challenge projection.')
        const output = buildCommitToolOutput(after)
        record('completed', 'COMMITTED', after)
        return output
      } catch (error) {
        const after = store.getState().session
        const code = errorCode(error, executionOptions.signal.aborted)
        record('failed', code, after)
        return safeError(
          code,
          code === 'REQUEST_ABORTED'
            ? 'Tool execution was cancelled.'
            : 'Approved challenge commit could not be completed.',
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
  if (name === PREVIEW_TOOL_NAME) return createPreviewTool(options)
  if (name === COMMIT_TOOL_NAME) return createCommitTool(options)
  throw new Error(`Tool ${name} is not implemented for this phase.`)
}
