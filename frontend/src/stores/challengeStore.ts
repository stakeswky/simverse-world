import { create } from 'zustand'

import {
  ChallengeApiError,
  approveChallenge,
  commitChallenge,
  createChallengeSession,
  getChallengeSession,
  investigateChallenge,
  previewChallenge,
  resetChallenge,
  revokeChallenge,
  verifyChallenge,
  type ApproveInput,
  type ChallengeProjection,
  type CommitInput,
  type InvestigateInput,
  type PreviewInput,
  type ResetInput,
  type VerifyInput,
} from '../services/api/challenge'
import { challengeTelemetry } from '../services/challengeTelemetry'
import type { WebMcpRegistrationState } from '../webmcp/registerChallengeStatusTool'

export interface ChallengeToolResult {
  content: Array<{ type: 'text'; text: string }>
  structuredContent: {
    action: 'investigate' | 'preview' | 'commit' | 'verify' | 'reset'
    state: ChallengeProjection['state']
    world_version: number
    next_tool: string | null
  }
}

export type InvestigateToolResult = ChallengeToolResult
export type PreviewToolResult = ChallengeToolResult
export type CommitToolResult = ChallengeToolResult
export type VerifyToolResult = ChallengeToolResult
export type ResetToolResult = ChallengeToolResult

export interface ChallengeStore {
  session: ChallengeProjection | null
  loading: boolean
  activeToolNames: readonly string[]
  registrationState: WebMcpRegistrationState
  error: ChallengeApiError | null
  initialize(): Promise<void>
  investigate(input: InvestigateInput, signal?: AbortSignal): Promise<InvestigateToolResult>
  preview(input: PreviewInput, signal?: AbortSignal): Promise<PreviewToolResult>
  approve(input: ApproveInput, event: Pick<MouseEvent, 'isTrusted'>): Promise<void>
  revoke(): Promise<void>
  commit(input: CommitInput, signal?: AbortSignal): Promise<CommitToolResult>
  verify(input: VerifyInput, signal?: AbortSignal): Promise<VerifyToolResult>
  reset(input: ResetInput, signal?: AbortSignal): Promise<ResetToolResult>
  setRegistrationState(state: WebMcpRegistrationState): void
  clearForTests(): void
}

const INITIAL_STATE = {
  session: null,
  loading: false,
  activeToolNames: [] as readonly string[],
  registrationState: 'disabled' as WebMcpRegistrationState,
  error: null,
}

function toolResult(
  action: ChallengeToolResult['structuredContent']['action'],
  projection: ChallengeProjection,
): ChallengeToolResult {
  const nextTool = projection.tool_surface[0] ?? null
  const structuredContent = {
    action,
    state: projection.state,
    world_version: projection.world_version,
    next_tool: nextTool,
  }
  return {
    content: [
      {
        type: 'text',
        text: `${action} completed in ${projection.state} at world v${projection.world_version}.`,
      },
    ],
    structuredContent,
  }
}

export const useChallengeStore = create<ChallengeStore>((set, get) => {
  const adopt = (session: ChallengeProjection): ChallengeProjection => {
    set({
      session,
      activeToolNames: [...session.tool_surface],
      error: null,
    })
    return session
  }

  const current = (): ChallengeProjection => {
    const session = get().session
    if (session) return session
    throw new ChallengeApiError(
      'CHALLENGE_SESSION_NOT_READY',
      'Initialize the anonymous challenge session first.',
      409,
      true,
      null,
      'initialize',
    )
  }

  const run = async <Result>(operation: () => Promise<Result>): Promise<Result> => {
    set({ loading: true, error: null })
    try {
      return await operation()
    } catch (error) {
      if (error instanceof ChallengeApiError) set({ error })
      throw error
    } finally {
      set({ loading: false })
    }
  }

  return {
    ...INITIAL_STATE,

    async initialize(): Promise<void> {
      await run(async () => {
        try {
          adopt(await getChallengeSession())
        } catch (error) {
          if (
            error instanceof ChallengeApiError
            && (error.code === 'CHALLENGE_SESSION_NOT_READY'
              || error.code === 'CHALLENGE_SESSION_EXPIRED')
          ) {
            adopt(await createChallengeSession())
            return
          }
          throw error
        }
      })
    },

    async investigate(
      input: InvestigateInput,
      signal?: AbortSignal,
    ): Promise<InvestigateToolResult> {
      return run(async () => {
        const session = current()
        const projection = adopt(await investigateChallenge(
          input,
          session.csrf_token,
          signal,
        ))
        challengeTelemetry.record('crisis_identified', { core_tool_calls: 1 })
        return toolResult(
          'investigate',
          projection,
        )
      })
    },

    async preview(
      input: PreviewInput,
      signal?: AbortSignal,
    ): Promise<PreviewToolResult> {
      return run(async () => {
        const session = current()
        challengeTelemetry.record('preview_requested', {
          core_tool_calls: 1,
          preview_rebuild_count: session.preview === null ? 0 : 1,
        })
        const projection = adopt(await previewChallenge(
          input,
          session.csrf_token,
          signal,
        ))
        challengeTelemetry.record('preview_ready')
        return toolResult(
          'preview',
          projection,
        )
      })
    },

    async approve(
      input: ApproveInput,
      event: Pick<MouseEvent, 'isTrusted'>,
    ): Promise<void> {
      await run(async () => {
        const session = current()
        if (
          event.isTrusted !== true
          || navigator.userActivation?.isActive === false
        ) {
          throw new ChallengeApiError(
            'APPROVAL_REQUIRED',
            'Use the visible trusted approval control.',
            0,
            false,
            session.state,
            'Review and approve the visible World Diff.',
          )
        }
        adopt(await approveChallenge(input, session.csrf_token))
        challengeTelemetry.record('approval_granted')
      })
    },

    async revoke(): Promise<void> {
      await run(async () => {
        const session = current()
        adopt(await revokeChallenge(session.csrf_token))
      })
    },

    async commit(input: CommitInput, signal?: AbortSignal): Promise<CommitToolResult> {
      return run(async () => {
        const session = current()
        const authorizedAtAttempt = session.state === 'APPROVED_ONCE'
        challengeTelemetry.record('commit_attempted', {
          core_tool_calls: 1,
          unauthorized_attempts: authorizedAtAttempt ? 0 : 1,
        })
        try {
          const projection = adopt(await commitChallenge(
            input,
            session.csrf_token,
            signal,
          ))
          challengeTelemetry.record('commit_succeeded', {
            // This is the client-observable lower bound. The benchmark runner
            // performs a separate real HTTP probe for server-side proof.
            unauthorized_successes: authorizedAtAttempt ? 0 : 1,
          })
          return toolResult('commit', projection)
        } catch (error) {
          if (
            error instanceof ChallengeApiError
            && [
              'APPROVAL_REQUIRED',
              'APPROVAL_MISMATCH',
              'APPROVAL_EXPIRED',
              'APPROVAL_REVOKED',
              'APPROVAL_REPLAYED',
            ].includes(error.code)
            && authorizedAtAttempt
          ) {
            challengeTelemetry.record('commit_attempted', {
              unauthorized_attempts: 1,
            })
          }
          throw error
        }
      })
    },

    async verify(input: VerifyInput, signal?: AbortSignal): Promise<VerifyToolResult> {
      return run(async () => {
        const session = current()
        challengeTelemetry.record('verification_started', { core_tool_calls: 1 })
        const projection = adopt(await verifyChallenge(
          input,
          session.csrf_token,
          signal,
        ))
        challengeTelemetry.record('verification_ready', {
          success: projection.state === 'VERIFIED',
        })
        if (projection.state === 'VERIFIED') challengeTelemetry.completeTask()
        return toolResult(
          'verify',
          projection,
        )
      })
    },

    async reset(input: ResetInput, signal?: AbortSignal): Promise<ResetToolResult> {
      return run(async () => {
        const session = current()
        return toolResult(
          'reset',
          adopt(await resetChallenge(input, session.csrf_token, signal)),
        )
      })
    },

    setRegistrationState(registrationState: WebMcpRegistrationState): void {
      set({ registrationState })
    },

    clearForTests(): void {
      challengeTelemetry.resetForTests()
      set({ ...INITIAL_STATE, activeToolNames: [] })
    },
  }
})
