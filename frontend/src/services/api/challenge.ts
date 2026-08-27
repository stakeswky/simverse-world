import { API_BASE } from './core'

const CHALLENGE_TIMEOUT_MS = 15_000
const CSRF_HEADER = 'X-CSRF-Token'

export type ChallengeState =
  | 'INITIAL'
  | 'EVIDENCE_READY'
  | 'PREVIEW_READY'
  | 'APPROVED_ONCE'
  | 'COMMITTED'
  | 'VERIFIED'
  | 'FAILED'
  | 'EXPIRED'

export type ChallengeErrorCode =
  | 'INVALID_INPUT'
  | 'CHALLENGE_SESSION_NOT_READY'
  | 'CHALLENGE_SESSION_EXPIRED'
  | 'INVALID_STATE_TRANSITION'
  | 'NO_ACTIONABLE_CRISIS'
  | 'EVIDENCE_STALE'
  | 'BUDGET_EXCEEDED'
  | 'POLICY_VIOLATION'
  | 'PREVIEW_NOT_FOUND'
  | 'PREVIEW_STALE'
  | 'APPROVAL_REQUIRED'
  | 'APPROVAL_MISMATCH'
  | 'APPROVAL_EXPIRED'
  | 'APPROVAL_REVOKED'
  | 'APPROVAL_REPLAYED'
  | 'STALE_WORLD_VERSION'
  | 'STALE_TOOL_SURFACE'
  | 'OUTCOME_ALREADY_VERIFIED'
  | 'OUTCOME_INCOMPLETE'
  | 'RESET_HASH_MISMATCH'
  | 'CHALLENGE_INTERNAL_ERROR'

export type HashString = string

export interface ChallengeResident {
  resident_id: string
  name: string
  cash_sc: number
  unpaid_wage_sc: number
  food_risk: 'LOW' | 'MEDIUM' | 'HIGH'
  food_credit_sc: number
  stabilized: boolean
}

export interface ChallengeEmployer {
  employer_id: string
  name: string
  overdue_payroll_sc: number
  repayment_claim_sc: number
  escrow_status: 'NONE' | 'PENDING' | 'MET' | 'MISSED'
}

export interface ChallengeRelationship {
  relationship_id: string
  source_id: string
  target_id: string
  direct_score: number
  tension: number
}

export interface ChallengeEvent {
  event_id: string
  event_type: string
  region_id: string
  title: string
  description: string
  occurs_at: string
}

export interface ChallengeMetrics {
  unpaid_residents: number
  high_food_risk_residents: number
  social_tension: number
  strike_risk_pct: number
  stabilized_residents: number
}

export interface ChallengeWorld {
  scenario_id: 'harbor-wage-crisis-v1'
  fixture_version: 1
  world_version: number
  world_time: string
  budget_sc: number
  harbor_open: boolean
  residents: ChallengeResident[]
  employers: ChallengeEmployer[]
  relationships: ChallengeRelationship[]
  events: ChallengeEvent[]
  metrics: ChallengeMetrics
}

export interface EvidenceItem {
  evidence_type: 'economic' | 'resident' | 'relationship' | 'event' | 'map'
  source_id: string
  title: string
  detail: string
  untrusted: boolean
}

export interface EvidenceSnapshot {
  evidence_id: string
  based_on_world_version: number
  crisis_id: 'harbor-wage-crisis'
  priority_score: number
  region_id: 'harbor'
  affected_resident_ids: string[]
  evidence: EvidenceItem[]
  enforced_constraints: string[]
}

export interface ResidentCashChange {
  resident_id: string
  before_sc: number
  delta_sc: number
  after_sc: number
}

export interface FoodCreditChange {
  resident_id: string
  before_sc: number
  delta_sc: number
  after_sc: number
}

export interface EmployerClaim {
  employer_id: string
  amount_sc: number
  status: 'PENDING'
}

export interface WorldDiff {
  scenario_id: 'harbor-wage-crisis-v1'
  session_generation: string
  preview_id: string
  based_on_world_version: number
  budget_before_sc: number
  budget_after_sc: number
  resident_cash_changes: ResidentCashChange[]
  food_credit_changes: FoodCreditChange[]
  employer_claims_created: EmployerClaim[]
  events_created: ChallengeEvent[]
  explicitly_unchanged: string[]
}

export interface MetricRange {
  min: number
  max: number
}

export interface ForecastResult {
  seeds: number[]
  high_food_risk_residents: MetricRange
  social_tension: MetricRange
  strike_risk_pct: MetricRange
  stabilized_residents: MetricRange
}

export interface RejectedAlternative {
  alternative_id: string
  title: string
  total_cost_sc: number | null
  rejected_reason: 'BUDGET_EXCEEDED' | 'POLICY_VIOLATION'
  violated_invariants: string[]
}

export interface InterventionPreview {
  preview_id: string
  crisis_id: 'harbor-wage-crisis'
  based_on_world_version: number
  intervention_id: 'harbor-wage-bridge'
  total_cost_sc: number
  remaining_budget_sc: number
  diff: WorldDiff
  diff_hash: HashString
  forecast: ForecastResult
  rejected_alternatives: RejectedAlternative[]
  created_at: string
}

export interface ExecutionReceipt {
  receipt_id: string
  scenario_id: 'harbor-wage-crisis-v1'
  session_generation: string
  preview_id: string
  approval_fingerprint: string
  approved_diff_hash: HashString
  world_before_version: number
  world_after_version: number
  world_before_hash: HashString
  world_after_hash: HashString
  budget_before_sc: number
  budget_delta_sc: number
  budget_after_sc: number
  affected_residents: string[]
  created_events: string[]
  verified_invariants: string[]
}

export interface OutcomeMetrics {
  high_food_risk_residents: number
  social_tension: number
  strike_risk_pct: number
  stabilized_residents: number
}

export interface NoActionOutcome extends OutcomeMetrics {
  strike_event_triggered: boolean
}

export interface TickSnapshot {
  tick_index: number
  elapsed_hours: number
  world_time: string
  metrics: OutcomeMetrics
  external_event_ids: string[]
}

export interface VerificationResult {
  receipt_id: string
  advance_hours: 72
  baseline_snapshot: TickSnapshot
  tick_snapshots: TickSnapshot[]
  forecast: ForecastResult
  actual: OutcomeMetrics
  no_action: NoActionOutcome
  notable_deviation: string
}

export interface ChallengeProjection {
  session_generation: string
  state: ChallengeState
  scenario_id: 'harbor-wage-crisis-v1'
  fixture_version: 1
  world_version: number
  world_hash: HashString
  world_time: string
  budget_sc: number
  tool_surface: string[]
  expires_at: string
  csrf_token: string
  world: ChallengeWorld
  evidence: EvidenceSnapshot | null
  preview: InterventionPreview | null
  approval_fingerprint: string | null
  approval_expires_at: string | null
  receipt: ExecutionReceipt | null
  verification: VerificationResult | null
}

export interface InvestigateInput {
  budget_cap_sc: number
}

export interface PreviewInput {
  crisis_id: 'harbor-wage-crisis'
  budget_cap_sc: 300
}

export interface ApproveInput {
  preview_id: string
  expected_world_version: number
  diff_hash: HashString
}

export type CommitInput = ApproveInput

export interface VerifyInput {
  receipt_id: string
  advance_hours: 72
}

export interface ResetInput {
  expected_generation: string
}

interface ChallengeErrorEnvelope {
  error?: {
    code?: unknown
    message?: unknown
    retryable?: unknown
    current_state?: unknown
    next_action?: unknown
  }
}

interface ChallengeRequestOptions {
  method: 'GET' | 'POST'
  body?: object
  csrfToken?: string
  signal?: AbortSignal
  retryNetwork?: boolean
}

const ERROR_CODES = new Set<ChallengeErrorCode>([
  'INVALID_INPUT',
  'CHALLENGE_SESSION_NOT_READY',
  'CHALLENGE_SESSION_EXPIRED',
  'INVALID_STATE_TRANSITION',
  'NO_ACTIONABLE_CRISIS',
  'EVIDENCE_STALE',
  'BUDGET_EXCEEDED',
  'POLICY_VIOLATION',
  'PREVIEW_NOT_FOUND',
  'PREVIEW_STALE',
  'APPROVAL_REQUIRED',
  'APPROVAL_MISMATCH',
  'APPROVAL_EXPIRED',
  'APPROVAL_REVOKED',
  'APPROVAL_REPLAYED',
  'STALE_WORLD_VERSION',
  'STALE_TOOL_SURFACE',
  'OUTCOME_ALREADY_VERIFIED',
  'OUTCOME_INCOMPLETE',
  'RESET_HASH_MISMATCH',
  'CHALLENGE_INTERNAL_ERROR',
])

const CHALLENGE_STATES = new Set<ChallengeState>([
  'INITIAL',
  'EVIDENCE_READY',
  'PREVIEW_READY',
  'APPROVED_ONCE',
  'COMMITTED',
  'VERIFIED',
  'FAILED',
  'EXPIRED',
])

export class ChallengeApiError extends Error {
  constructor(
    readonly code: ChallengeErrorCode,
    message = 'Challenge request failed.',
    readonly status = 0,
    readonly retryable = false,
    readonly currentState: ChallengeState | null = null,
    readonly nextAction: string | null = null,
  ) {
    super(message)
    this.name = 'ChallengeApiError'
  }
}

function timeoutSignal(callerSignal?: AbortSignal): {
  signal: AbortSignal
  didTimeout: () => boolean
  cleanup: () => void
} {
  const controller = new AbortController()
  let timedOut = false
  const timeout = window.setTimeout(() => {
    timedOut = true
    controller.abort(new DOMException('Challenge request timed out.', 'TimeoutError'))
  }, CHALLENGE_TIMEOUT_MS)
  const forwardAbort = () => controller.abort(callerSignal?.reason)
  if (callerSignal) {
    if (callerSignal.aborted) forwardAbort()
    else callerSignal.addEventListener('abort', forwardAbort, { once: true })
  }
  return {
    signal: controller.signal,
    didTimeout: () => timedOut,
    cleanup: () => {
      window.clearTimeout(timeout)
      callerSignal?.removeEventListener('abort', forwardAbort)
    },
  }
}

function asErrorCode(value: unknown): ChallengeErrorCode {
  return typeof value === 'string' && ERROR_CODES.has(value as ChallengeErrorCode)
    ? (value as ChallengeErrorCode)
    : 'CHALLENGE_INTERNAL_ERROR'
}

function asState(value: unknown): ChallengeState | null {
  return typeof value === 'string' && CHALLENGE_STATES.has(value as ChallengeState)
    ? (value as ChallengeState)
    : null
}

async function responseError(response: Response): Promise<ChallengeApiError> {
  let envelope: ChallengeErrorEnvelope = {}
  try {
    envelope = (await response.json()) as ChallengeErrorEnvelope
  } catch {
    // Fail closed to the stable generic envelope below.
  }
  const error = envelope.error
  return new ChallengeApiError(
    asErrorCode(error?.code),
    typeof error?.message === 'string' ? error.message : undefined,
    response.status,
    error?.retryable === true,
    asState(error?.current_state),
    typeof error?.next_action === 'string' ? error.next_action : null,
  )
}

async function challengeRequest(
  path: string,
  options: ChallengeRequestOptions,
): Promise<ChallengeProjection> {
  const attempts = options.retryNetwork ? 2 : 1
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const timeout = timeoutSignal(options.signal)
    const headers = new Headers()
    if (options.method === 'POST') headers.set('Content-Type', 'application/json')
    if (options.csrfToken !== undefined) headers.set(CSRF_HEADER, options.csrfToken)
    try {
      const response = await fetch(`${API_BASE}${path}`, {
        method: options.method,
        credentials: 'include',
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: timeout.signal,
      })
      if (!response.ok) throw await responseError(response)
      return (await response.json()) as ChallengeProjection
    } catch (error) {
      if (error instanceof ChallengeApiError) throw error
      if (options.signal?.aborted) throw options.signal.reason ?? error
      if (attempt + 1 < attempts) continue
      throw new ChallengeApiError(
        'CHALLENGE_INTERNAL_ERROR',
        timeout.didTimeout()
          ? 'Challenge request timed out after 15 seconds.'
          : 'Challenge network request failed.',
        0,
        true,
      )
    } finally {
      timeout.cleanup()
    }
  }
  throw new ChallengeApiError('CHALLENGE_INTERNAL_ERROR')
}

export function getChallengeSession(signal?: AbortSignal): Promise<ChallengeProjection> {
  return challengeRequest('/challenge/session', {
    method: 'GET',
    signal,
    retryNetwork: true,
  })
}

export function createChallengeSession(signal?: AbortSignal): Promise<ChallengeProjection> {
  return challengeRequest('/challenge/session', { method: 'POST', signal })
}

export function investigateChallenge(
  input: InvestigateInput,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<ChallengeProjection> {
  return challengeRequest('/challenge/investigate', {
    method: 'POST',
    body: input,
    csrfToken,
    signal,
    retryNetwork: true,
  })
}

export function previewChallenge(
  input: PreviewInput,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<ChallengeProjection> {
  return challengeRequest('/challenge/preview', {
    method: 'POST',
    body: input,
    csrfToken,
    signal,
  })
}

export function approveChallenge(
  input: ApproveInput,
  csrfToken: string,
): Promise<ChallengeProjection> {
  return challengeRequest('/challenge/approve', {
    method: 'POST',
    body: input,
    csrfToken,
  })
}

export function revokeChallenge(csrfToken: string): Promise<ChallengeProjection> {
  return challengeRequest('/challenge/revoke', {
    method: 'POST',
    csrfToken,
  })
}

export function commitChallenge(
  input: CommitInput,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<ChallengeProjection> {
  return challengeRequest('/challenge/commit', {
    method: 'POST',
    body: input,
    csrfToken,
    signal,
  })
}

export function verifyChallenge(
  input: VerifyInput,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<ChallengeProjection> {
  return challengeRequest('/challenge/verify', {
    method: 'POST',
    body: input,
    csrfToken,
    signal,
  })
}

export function resetChallenge(
  input: ResetInput,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<ChallengeProjection> {
  return challengeRequest('/challenge/reset', {
    method: 'POST',
    body: input,
    csrfToken,
    signal,
  })
}
