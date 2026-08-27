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
