import type { ChallengeProjection } from '../services/api/challenge'
import {
  getModelContext,
  type WebMcpModelContext,
  type WebMcpToolDefinition,
} from './types'

export type WebMcpRegistrationState =
  | 'registered'
  | 'disabled'
  | 'unsupported'
  | 'failed'
  | 'stale'

export const CHALLENGE_TOOL_NAMES = Object.freeze([
  'simverse_investigate_crisis',
  'simverse_preview_intervention',
  'simverse_commit_approved',
  'simverse_verify_outcome',
  'simverse_reset_town',
] as const)

const CHALLENGE_TOOL_NAME_SET = new Set<string>(CHALLENGE_TOOL_NAMES)
const POLL_INTERVAL_MS = 25
const POLL_TIMEOUT_MS = 500

export const STALE_TOOL_SURFACE_RESULT = Object.freeze({
  error: Object.freeze({
    code: 'STALE_TOOL_SURFACE' as const,
    message: 'This tool belongs to an earlier challenge state. Refresh the tool list.',
    retryable: true as const,
  }),
})

export interface ChallengeToolSurfaceManagerOptions {
  readonly modelContext?: WebMcpModelContext
  readonly document?: Document
  readonly navigator?: Navigator
  readonly enabled?: boolean
  readonly createTool: (
    name: string,
    session: ChallengeProjection,
  ) => WebMcpToolDefinition
  readonly reload?: () => void
}

interface ActiveSurface {
  readonly controller: AbortController
  readonly names: readonly string[]
}

function currentDocument(): Document | undefined {
  return typeof document === 'undefined' ? undefined : document
}

function currentNavigator(): Navigator | undefined {
  return typeof navigator === 'undefined' ? undefined : navigator
}

function defaultReload(): void {
  if (typeof window !== 'undefined') window.location.reload()
}

function surfaceKey(session: ChallengeProjection): string {
  return [
    session.session_generation,
    session.state,
    session.world_version,
    ...session.tool_surface,
  ].join('|')
}

async function waitForToolChange(
  context: WebMcpModelContext,
  delayMs: number,
): Promise<void> {
  await new Promise<void>((resolve) => {
    let settled = false
    const finish = () => {
      if (settled) return
      settled = true
      globalThis.clearTimeout(timer)
      try {
        context.removeEventListener('toolchange', finish)
      } catch {
        // Polling remains the compatibility fallback for partial host previews.
      }
      resolve()
    }
    const timer = globalThis.setTimeout(finish, delayMs)
    try {
      context.addEventListener('toolchange', finish, { once: true })
    } catch {
      // The timer above still advances the bounded poll.
    }
  })
}

async function waitUntilChallengeToolsDisappear(
  context: WebMcpModelContext,
  getTools: NonNullable<WebMcpModelContext['getTools']>,
): Promise<boolean> {
  const attempts = POLL_TIMEOUT_MS / POLL_INTERVAL_MS
  for (let attempt = 0; attempt <= attempts; attempt += 1) {
    const tools = await getTools.call(context)
    if (!tools.some((tool) => CHALLENGE_TOOL_NAME_SET.has(tool.name))) return true
    if (attempt === attempts) break
    await waitForToolChange(context, POLL_INTERVAL_MS)
  }
  return false
}

export class ChallengeToolSurfaceManager {
  private readonly options: ChallengeToolSurfaceManagerOptions
  private epoch = 0
  private activeSurface: ActiveSurface | undefined
  private desiredKey: string | undefined
  private syncPromise: Promise<WebMcpRegistrationState> | undefined

  constructor(options: ChallengeToolSurfaceManagerOptions) {
    this.options = options
  }

  sync(session: ChallengeProjection): Promise<WebMcpRegistrationState> {
    const key = surfaceKey(session)
    if (this.desiredKey === key && this.syncPromise) return this.syncPromise

    this.desiredKey = key
    const promise = this.performSync(session)
    this.syncPromise = promise
    return promise
  }

  destroy(): void {
    this.epoch += 1
    this.activeSurface?.controller.abort()
    this.activeSurface = undefined
    this.desiredKey = undefined
    this.syncPromise = undefined
  }

  currentEpoch(): number {
    return this.epoch
  }

  private resolveModelContext(): WebMcpModelContext | undefined {
    if (this.options.modelContext) return this.options.modelContext
    const toolDocument = this.options.document ?? currentDocument()
    if (!toolDocument) return undefined
    return getModelContext(
      toolDocument,
      this.options.navigator ?? currentNavigator(),
    )
  }

  private async performSync(
    session: ChallengeProjection,
  ): Promise<WebMcpRegistrationState> {
    const capturedEpoch = this.epoch + 1
    this.epoch = capturedEpoch
    const oldSurface = this.activeSurface
    oldSurface?.controller.abort()
    this.activeSurface = undefined

    if (this.options.enabled === false) {
      this.desiredKey = undefined
      return 'disabled'
    }

    let context: WebMcpModelContext | undefined
    try {
      context = this.resolveModelContext()
      if (!context || typeof context.registerTool !== 'function') {
        this.desiredKey = undefined
        return 'unsupported'
      }
    } catch {
      this.desiredKey = undefined
      return 'unsupported'
    }

    if (oldSurface && oldSurface.names.length > 0) {
      let getTools: WebMcpModelContext['getTools']
      try {
        getTools = context.getTools
      } catch {
        getTools = undefined
      }
      if (typeof getTools !== 'function') {
        this.safeReload()
        this.desiredKey = undefined
        return 'stale'
      }
      try {
        if (!await waitUntilChallengeToolsDisappear(context, getTools)) {
          this.safeReload()
          this.desiredKey = undefined
          return 'stale'
        }
      } catch {
        if (capturedEpoch !== this.epoch) return 'stale'
        this.desiredKey = undefined
        return 'failed'
      }
      if (capturedEpoch !== this.epoch) return 'stale'
    }

    if (session.tool_surface.some((name) => !CHALLENGE_TOOL_NAME_SET.has(name))) {
      this.desiredKey = undefined
      return 'failed'
    }

    const controller = new AbortController()
    const names = [...session.tool_surface]
    this.activeSurface = { controller, names }

    try {
      for (const name of names) {
        const definition = this.options.createTool(name, session)
        if (definition.name !== name) throw new Error('Tool name mismatch.')
        const wrapped: WebMcpToolDefinition = {
          ...definition,
          execute: (input, executionOptions) => {
            if (capturedEpoch !== this.epoch || controller.signal.aborted) {
              return STALE_TOOL_SURFACE_RESULT
            }
            return definition.execute(input, executionOptions)
          },
        }
        await Promise.resolve(context.registerTool.call(context, wrapped, {
          signal: controller.signal,
        }))
      }
    } catch {
      controller.abort()
      if (capturedEpoch !== this.epoch) return 'stale'
      if (this.activeSurface?.controller === controller) {
        this.activeSurface = undefined
      }
      this.desiredKey = undefined
      return 'failed'
    }

    if (capturedEpoch !== this.epoch || controller.signal.aborted) return 'stale'
    return 'registered'
  }

  private safeReload(): void {
    try {
      (this.options.reload ?? defaultReload)()
    } catch {
      // A failed reload request must not expose browser internals to the tool.
    }
  }
}
