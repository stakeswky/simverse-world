import {
  ChallengeApiError,
  type ChallengeProjection,
  type CommitInput,
  type InvestigateInput,
  type PreviewInput,
  type ResetInput,
  type VerifyInput,
} from '../services/api/challenge'
import { useChallengeStore } from '../stores/challengeStore'
import { publishAgentActivity } from './activity'
import {
  buildCommitToolOutput,
  buildInvestigateToolOutput,
  buildPreviewToolOutput,
  buildResetToolOutput,
  buildVerifyToolOutput,
} from './challengeToolResults'
import type { WebMcpToolDefinition } from './types'

export const INVESTIGATE_TOOL_NAME = 'simverse_investigate_crisis'
export const PREVIEW_TOOL_NAME = 'simverse_preview_intervention'
export const COMMIT_TOOL_NAME = 'simverse_commit_approved'
export const VERIFY_TOOL_NAME = 'simverse_verify_outcome'
export const RESET_TOOL_NAME = 'simverse_reset_town'

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
  readonly verify: (
    input: VerifyInput,
    signal?: AbortSignal,
  ) => Promise<unknown>
  readonly reset: (
    input: ResetInput,
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

function hasVerifyInput(input: Record<string, unknown>): input is {
  receipt_id: string
  advance_hours: 72
} {
  return (
    Object.keys(input).length === 2
    && typeof input.receipt_id === 'string'
    && Number.isInteger(input.advance_hours)
    && input.advance_hours === 72
  )
}

function hasResetInput(input: Record<string, unknown>): input is {
  expected_generation: string
} {
  return (
    Object.keys(input).length === 1
    && typeof input.expected_generation === 'string'
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

export function createVerifyTool(
  options: ChallengeToolOptions = {},
): WebMcpToolDefinition {
  const store = options.store ?? useChallengeStore
  const toolDocument = options.document ?? currentDocument()
  const clock = options.clock ?? monotonicNow

  return {
    name: VERIFY_TOOL_NAME,
    title: 'Verify 72-hour Harbor outcome',
    description: 'Advance the committed isolated Challenge Town by exactly 72 hours and compare its actual result with the forecast and paired no-action control.',
    inputSchema: {
      type: 'object',
      properties: {
        receipt_id: { type: 'string' },
        advance_hours: { type: 'integer', const: 72 },
      },
      required: ['receipt_id', 'advance_hours'],
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
          toolName: VERIFY_TOOL_NAME,
          phase: 'verify',
          outcome,
          durationMs: safeDuration(clock, startedAt),
          reasonCode,
          worldVersionBefore: before?.world_version ?? 0,
          worldVersionAfter: after?.world_version ?? before?.world_version ?? 0,
          receiptId: after?.verification?.receipt_id
            ?? before?.receipt?.receipt_id
            ?? null,
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
      if (!hasVerifyInput(input)) {
        record('failed', 'INVALID_INPUT', before)
        return safeError(
          'INVALID_INPUT',
          'Tool input must match the 72-hour verification schema.',
        )
      }

      try {
        await store.getState().verify(
          {
            receipt_id: input.receipt_id,
            advance_hours: input.advance_hours,
          },
          executionOptions.signal,
        )
        const after = store.getState().session
        if (!after) throw new Error('Missing challenge projection.')
        const output = buildVerifyToolOutput(after)
        record('completed', 'VERIFIED', after)
        return output
      } catch (error) {
        const after = store.getState().session
        const code = errorCode(error, executionOptions.signal.aborted)
        record('failed', code, after)
        return safeError(
          code,
          code === 'REQUEST_ABORTED'
            ? 'Tool execution was cancelled.'
            : 'Challenge outcome verification could not be completed.',
          code === 'REQUEST_ABORTED'
            || (error instanceof ChallengeApiError && error.retryable),
        )
      }
    },
  }
}

export function createResetTool(
  options: ChallengeToolOptions = {},
): WebMcpToolDefinition {
  const store = options.store ?? useChallengeStore
  const toolDocument = options.document ?? currentDocument()
  const clock = options.clock ?? monotonicNow

  return {
    name: RESET_TOOL_NAME,
    title: 'Reset isolated Challenge Town',
    description: 'Discard the terminal challenge run and restore a new anonymous session at the locked public v7 fixture.',
    inputSchema: {
      type: 'object',
      properties: {
        expected_generation: { type: 'string' },
      },
      required: ['expected_generation'],
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
          toolName: RESET_TOOL_NAME,
          phase: 'reset',
          outcome,
          durationMs: safeDuration(clock, startedAt),
          reasonCode,
          worldVersionBefore: before?.world_version ?? 0,
          worldVersionAfter: after?.world_version ?? before?.world_version ?? 0,
          receiptId: before?.receipt?.receipt_id ?? null,
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
      if (!hasResetInput(input)) {
        record('failed', 'INVALID_INPUT', before)
        return safeError(
          'INVALID_INPUT',
          'Tool input must match the reset generation schema.',
        )
      }

      try {
        await store.getState().reset(
          { expected_generation: input.expected_generation },
          executionOptions.signal,
        )
        const after = store.getState().session
        if (!after) throw new Error('Missing challenge projection.')
        const output = buildResetToolOutput(after)
        record('completed', 'INITIAL', after)
        return output
      } catch (error) {
        const after = store.getState().session
        const code = errorCode(error, executionOptions.signal.aborted)
        record('failed', code, after)
        return safeError(
          code,
          code === 'REQUEST_ABORTED'
            ? 'Tool execution was cancelled.'
            : 'Challenge Town reset could not be completed.',
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
  if (name === VERIFY_TOOL_NAME) return createVerifyTool(options)
  if (name === RESET_TOOL_NAME) return createResetTool(options)
  throw new Error(`Tool ${name} is not implemented for this phase.`)
}
