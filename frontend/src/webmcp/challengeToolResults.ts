import type { ChallengeProjection } from '../services/api/challenge'

export interface InvestigateToolOutput {
  readonly state: 'EVIDENCE_READY'
  readonly world_version: number
  readonly top_crisis: {
    readonly crisis_id: 'harbor-wage-crisis'
    readonly priority_score: number
    readonly region_id: 'harbor'
    readonly affected_resident_count: number
  }
  readonly evidence_domains: string[]
  readonly constraints: string[]
  readonly next_tool: string | null
}

interface CompactMetricRange {
  readonly min: number
  readonly max: number
}

export interface PreviewToolOutput {
  readonly preview_id: string
  readonly world_version: number
  readonly diff_hash: string
  readonly cost_sc: number
  readonly remaining_sc: number
  readonly forecast_72h: {
    readonly seed_count: number
    readonly high_food_risk_residents: CompactMetricRange
    readonly social_tension: CompactMetricRange
    readonly strike_risk_pct: CompactMetricRange
    readonly stabilized_residents: CompactMetricRange
  }
  readonly rejected_codes: Array<'BUDGET_EXCEEDED' | 'POLICY_VIOLATION'>
  readonly approval_status: 'REVIEW_REQUIRED' | 'APPROVED_ONCE'
}

export interface CommitToolOutput {
  readonly state: 'COMMITTED'
  readonly receipt_id: string
  readonly world: {
    readonly version_before: number
    readonly version_after: number
    readonly hash_before: string
    readonly hash_after: string
  }
  readonly budget: {
    readonly before_sc: number
    readonly delta_sc: number
    readonly after_sc: number
  }
  readonly affected_resident_count: number
  readonly verified_invariants: string[]
  readonly next_tool: string | null
}

interface CompactOutcomeMetrics {
  readonly high_food_risk_residents: number
  readonly social_tension: number
  readonly strike_risk_pct: number
  readonly stabilized_residents: number
}

export interface VerifyToolOutput {
  readonly state: 'VERIFIED'
  readonly receipt_id: string
  readonly world: {
    readonly version_before: number
    readonly version_after: number
    readonly time_before: string
    readonly time_after: string
  }
  readonly prediction: {
    readonly high_food_risk_residents: CompactMetricRange
    readonly social_tension: CompactMetricRange
    readonly strike_risk_pct: CompactMetricRange
    readonly stabilized_residents: CompactMetricRange
  }
  readonly actual: CompactOutcomeMetrics
  readonly no_action_control: CompactOutcomeMetrics & {
    readonly strike_event_triggered: boolean
  }
  readonly deviation: string
  readonly tick_count: number
  readonly next_tool: string | null
}

export interface ResetToolOutput {
  readonly state: 'INITIAL'
  readonly session_generation: string
  readonly world_version: 7
  readonly world_hash: string
  readonly next_tool: string | null
}

export function buildInvestigateToolOutput(
  projection: ChallengeProjection,
): InvestigateToolOutput {
  const evidence = projection.evidence
  if (projection.state !== 'EVIDENCE_READY' || !evidence) {
    throw new Error('Investigation did not produce an evidence projection.')
  }
  const output: InvestigateToolOutput = {
    state: 'EVIDENCE_READY',
    world_version: projection.world_version,
    top_crisis: {
      crisis_id: evidence.crisis_id,
      priority_score: evidence.priority_score,
      region_id: evidence.region_id,
      affected_resident_count: evidence.affected_resident_ids.length,
    },
    evidence_domains: [...new Set(
      evidence.evidence.map((item) => item.evidence_type),
    )].sort(),
    constraints: [...evidence.enforced_constraints].sort(),
    next_tool: projection.tool_surface.find(
      (name) => name !== 'simverse_investigate_crisis',
    ) ?? null,
  }
  if (JSON.stringify(output).length >= 1500) {
    throw new Error('Investigate tool output exceeded its safety budget.')
  }
  return output
}

export function buildPreviewToolOutput(
  projection: ChallengeProjection,
): PreviewToolOutput {
  const preview = projection.preview
  if (projection.state !== 'PREVIEW_READY' || !preview) {
    throw new Error('Preview did not produce an immutable diff projection.')
  }
  const output: PreviewToolOutput = {
    preview_id: preview.preview_id,
    world_version: preview.based_on_world_version,
    diff_hash: preview.diff_hash,
    cost_sc: preview.total_cost_sc,
    remaining_sc: preview.remaining_budget_sc,
    forecast_72h: {
      seed_count: preview.forecast.seeds.length,
      high_food_risk_residents: preview.forecast.high_food_risk_residents,
      social_tension: preview.forecast.social_tension,
      strike_risk_pct: preview.forecast.strike_risk_pct,
      stabilized_residents: preview.forecast.stabilized_residents,
    },
    rejected_codes: [...new Set(
      preview.rejected_alternatives.map(
        (alternative) => alternative.rejected_reason,
      ),
    )].sort(),
    approval_status: projection.approval_fingerprint
      ? 'APPROVED_ONCE'
      : 'REVIEW_REQUIRED',
  }
  if (JSON.stringify(output).length >= 1500) {
    throw new Error('Preview tool output exceeded its safety budget.')
  }
  return output
}

export function buildCommitToolOutput(
  projection: ChallengeProjection,
): CommitToolOutput {
  const receipt = projection.receipt
  if (projection.state !== 'COMMITTED' || !receipt) {
    throw new Error('Commit did not produce an execution receipt.')
  }
  const output: CommitToolOutput = {
    state: 'COMMITTED',
    receipt_id: receipt.receipt_id,
    world: {
      version_before: receipt.world_before_version,
      version_after: receipt.world_after_version,
      hash_before: receipt.world_before_hash,
      hash_after: receipt.world_after_hash,
    },
    budget: {
      before_sc: receipt.budget_before_sc,
      delta_sc: receipt.budget_delta_sc,
      after_sc: receipt.budget_after_sc,
    },
    affected_resident_count: receipt.affected_residents.length,
    verified_invariants: [...receipt.verified_invariants],
    next_tool: projection.tool_surface[0] ?? null,
  }
  if (JSON.stringify(output).length >= 1500) {
    throw new Error('Commit tool output exceeded its safety budget.')
  }
  return output
}

export function buildVerifyToolOutput(
  projection: ChallengeProjection,
): VerifyToolOutput {
  const receipt = projection.receipt
  const verification = projection.verification
  if (
    projection.state !== 'VERIFIED'
    || !receipt
    || !verification
    || receipt.receipt_id !== verification.receipt_id
  ) {
    throw new Error('Verification did not produce a bound paired outcome.')
  }
  const output: VerifyToolOutput = {
    state: 'VERIFIED',
    receipt_id: receipt.receipt_id,
    world: {
      version_before: receipt.world_after_version,
      version_after: projection.world_version,
      time_before: verification.baseline_snapshot.world_time,
      time_after: projection.world_time,
    },
    prediction: {
      high_food_risk_residents: verification.forecast.high_food_risk_residents,
      social_tension: verification.forecast.social_tension,
      strike_risk_pct: verification.forecast.strike_risk_pct,
      stabilized_residents: verification.forecast.stabilized_residents,
    },
    actual: { ...verification.actual },
    no_action_control: { ...verification.no_action },
    deviation: verification.notable_deviation,
    tick_count: verification.tick_snapshots.length + 1,
    next_tool: projection.tool_surface[0] ?? null,
  }
  if (JSON.stringify(output).length >= 1500) {
    throw new Error('Verify tool output exceeded its safety budget.')
  }
  return output
}

export function buildResetToolOutput(
  projection: ChallengeProjection,
): ResetToolOutput {
  if (projection.state !== 'INITIAL' || projection.world_version !== 7) {
    throw new Error('Reset did not restore the locked initial projection.')
  }
  const output: ResetToolOutput = {
    state: 'INITIAL',
    session_generation: projection.session_generation,
    world_version: 7,
    world_hash: projection.world_hash,
    next_tool: projection.tool_surface[0] ?? null,
  }
  if (JSON.stringify(output).length >= 1500) {
    throw new Error('Reset tool output exceeded its safety budget.')
  }
  return output
}
