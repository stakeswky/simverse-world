import { publishAgentActivity } from './activity'
import { getChallengeStatus, type ChallengeStatus } from './challengeStatus'
import {
  getModelContext,
  type WebMcpModelContext,
  type WebMcpToolDefinition,
} from './types'
import type { WebMcpRegistrationState } from './challengeToolSurfaceManager'

export type { WebMcpRegistrationState } from './challengeToolSurfaceManager'

export const CHALLENGE_STATUS_TOOL_NAME = 'simverse_get_challenge_status'

export interface ChallengeStatusToolError {
  readonly error: {
    readonly code: 'invalid_input' | 'challenge_status_unavailable'
    readonly message: 'Tool input must be an empty object.' | 'Challenge status is temporarily unavailable.'
  }
}

export type ChallengeStatusToolResult = ChallengeStatus | ChallengeStatusToolError
interface ToolOptions {
  readonly document?: Document
  readonly statusProvider?: () => ChallengeStatus
  readonly clock?: () => number
}

interface RegistrationOptions extends ToolOptions {
  readonly enabled?: boolean
  readonly navigator?: Navigator
  readonly signal?: AbortSignal
}

interface RegistrationRecord {
  readonly controller: AbortController
  readonly consumerSignals: Set<AbortSignal>
  permanent: boolean
  cleanupScheduled: boolean
  promise: Promise<WebMcpRegistrationState>
}

const SAFE_TOOL_ERROR: ChallengeStatusToolError = Object.freeze({
  error: Object.freeze({
    code: 'challenge_status_unavailable',
    message: 'Challenge status is temporarily unavailable.',
  }),
})

const SAFE_INPUT_ERROR: ChallengeStatusToolError = Object.freeze({
  error: Object.freeze({
    code: 'invalid_input',
    message: 'Tool input must be an empty object.',
  }),
})

let registrations = new WeakMap<Document, RegistrationRecord>()
let registrationRecords = new Set<RegistrationRecord>()

function scheduleRegistrationCleanup(
  toolDocument: Document,
  record: RegistrationRecord,
): void {
  if (record.permanent || record.consumerSignals.size > 0 || record.cleanupScheduled) return
  record.cleanupScheduled = true
  queueMicrotask(() => {
    record.cleanupScheduled = false
    if (record.permanent || record.consumerSignals.size > 0) return
    if (registrations.get(toolDocument) === record) registrations.delete(toolDocument)
    registrationRecords.delete(record)
    record.controller.abort()
  })
}

function attachRegistrationConsumer(
  toolDocument: Document,
  record: RegistrationRecord,
  signal?: AbortSignal,
): boolean {
  if (!signal) {
    record.permanent = true
    return true
  }
  if (signal.aborted) return false
  if (record.consumerSignals.has(signal)) return true
  record.consumerSignals.add(signal)
  signal.addEventListener('abort', () => {
    record.consumerSignals.delete(signal)
    scheduleRegistrationCleanup(toolDocument, record)
  }, { once: true })
  return true
}

function currentDocument(): Document | undefined {
  return typeof document === 'undefined' ? undefined : document
}

function monotonicNow(): number {
  return globalThis.performance?.now?.() ?? Date.now()
}

function hasValidInput(input: unknown): boolean {
  if (input === undefined) return true
  if (input === null || typeof input !== 'object' || Array.isArray(input)) return false
  return Object.keys(input).length === 0
}

function safeDuration(clock: () => number, startedAt: number): number {
  try {
    return Math.max(0, Math.round(clock() - startedAt))
  } catch {
    return 0
  }
}

function recordActivity(
  toolDocument: Document | undefined,
  outcome: 'completed' | 'failed',
  clock: () => number,
  startedAt: number,
): void {
  if (!toolDocument) return
  try {
    publishAgentActivity(toolDocument, {
      toolName: CHALLENGE_STATUS_TOOL_NAME,
      outcome,
      durationMs: safeDuration(clock, startedAt),
    })
  } catch {
    // A visual receipt must never make the tool leak an internal browser error.
  }
}

export function isWebMcpEnabled(): boolean {
  return import.meta.env.VITE_WEBMCP_ENABLED === 'true'
}

export function createChallengeStatusTool(options: ToolOptions = {}): WebMcpToolDefinition {
  const toolDocument = options.document ?? currentDocument()
  const statusProvider = options.statusProvider ?? getChallengeStatus
  const clock = options.clock ?? monotonicNow

  return {
    name: CHALLENGE_STATUS_TOOL_NAME,
    description: 'Read the fixed Day-0 status for the Simverse WebMCP Challenge Town. This tool does not change the world.',
    inputSchema: {
      type: 'object',
      properties: {},
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true, untrustedContentHint: false },
    execute: async (input) => {
      let startedAt = 0
      try {
        startedAt = clock()
      } catch {
        // Duration is diagnostic only; tool behavior must not depend on it.
      }
      try {
        if (!hasValidInput(input)) {
          recordActivity(toolDocument, 'failed', clock, startedAt)
          return SAFE_INPUT_ERROR
        }
        const status = statusProvider()
        recordActivity(toolDocument, 'completed', clock, startedAt)
        return status
      } catch {
        recordActivity(toolDocument, 'failed', clock, startedAt)
        return SAFE_TOOL_ERROR
      }
    },
  }
}

export async function registerChallengeStatusTool(
  options: RegistrationOptions = {},
): Promise<WebMcpRegistrationState> {
  if (!(options.enabled ?? isWebMcpEnabled())) return 'disabled'
  if (options.signal?.aborted) return 'failed'

  const toolDocument = options.document ?? currentDocument()
  let modelContext: WebMcpModelContext
  let registerTool: WebMcpModelContext['registerTool']
  try {
    if (!toolDocument) return 'unsupported'
    const detectedModelContext = getModelContext(toolDocument, options.navigator)
    if (!detectedModelContext) return 'unsupported'
    const detectedRegisterTool = detectedModelContext.registerTool
    if (typeof detectedRegisterTool !== 'function') return 'unsupported'
    modelContext = detectedModelContext
    registerTool = detectedRegisterTool
  } catch {
    return 'unsupported'
  }

  const existingRegistration = registrations.get(toolDocument)
  if (existingRegistration) {
    if (!attachRegistrationConsumer(toolDocument, existingRegistration, options.signal)) return 'failed'
    return existingRegistration.promise
  }

  const controller = new AbortController()
  const record: RegistrationRecord = {
    controller,
    consumerSignals: new Set<AbortSignal>(),
    permanent: false,
    cleanupScheduled: false,
    promise: Promise.resolve('failed'),
  }
  if (!attachRegistrationConsumer(toolDocument, record, options.signal)) return 'failed'

  const registration = Promise.resolve()
    .then(() => Promise.resolve(registerTool.call(
      modelContext,
      createChallengeStatusTool({
        document: toolDocument,
        statusProvider: options.statusProvider,
        clock: options.clock,
      }),
      { signal: controller.signal },
    )))
    .then(() => 'registered' as const)
    .catch(() => {
      if (registrations.get(toolDocument) === record) registrations.delete(toolDocument)
      registrationRecords.delete(record)
      controller.abort()
      return 'failed' as const
    })

  record.promise = registration
  registrations.set(toolDocument, record)
  registrationRecords.add(record)
  return registration
}

/** Test isolation only. Production registrations live for an active document or page lease. */
export function resetWebMcpRegistrationsForTests(): void {
  for (const record of registrationRecords) record.controller.abort()
  registrationRecords = new Set<RegistrationRecord>()
  registrations = new WeakMap<Document, RegistrationRecord>()
}
