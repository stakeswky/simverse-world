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
