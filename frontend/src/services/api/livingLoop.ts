import { apiFetch } from './core'

export type LivingLoopChoiceKey =
  | 'public_support'
  | 'private_mediation'
  | 'collect_evidence'

export type LivingLoopDecisionState =
  | 'pending'
  | 'chosen'
  | 'result_ready'
  | 'result_viewed'

export interface LivingLoopExperiment {
  key: 'living_loop_p0'
  enabled: boolean
}

export interface LivingLoopPlayerResident {
  id: string
  slug: string
  name: string
  district: string
  sprite_key: string
}

export interface LivingLoopTimelineItem {
  id: string
  kind: 'previous_result' | 'notification' | 'digest'
  title: string
  summary: string
  occurred_at: string
  deep_link: string | null
}

export interface LivingLoopCityPulse {
  title: string
  summary: string
  date: string
  deep_link: string
  is_fallback?: boolean
}

export interface LivingLoopChoice {
  key: LivingLoopChoiceKey
  label: string
  summary: string
  risk: string
  tradeoffs: string[]
}

export interface LivingLoopImmediateResult {
  title: string
  summary: string
  effects?: Record<string, number>
  impacts?: string[]
}

export interface LivingLoopDelayedResult {
  title: string
  summary: string
}

export interface LivingLoopDecision {
  id: string
  scenario_key: 'harbor_wage_dispute_v1'
  scenario_version: 1
  state: LivingLoopDecisionState
  title: string
  context: string
  stakes: string[]
  choices: LivingLoopChoice[]
  selected_choice: LivingLoopChoiceKey | null
  immediate_result: LivingLoopImmediateResult | null
  result_available_at: string | null
  delayed_result: LivingLoopDelayedResult | null
}

export interface LivingLoopTodayResponse {
  experiment: LivingLoopExperiment
  server_now: string
  status: 'ready' | 'feature_disabled' | 'setup_required'
  setup_required?: boolean
  player_resident: LivingLoopPlayerResident | null
  since_you_left: LivingLoopTimelineItem[]
  city_pulse: LivingLoopCityPulse | null
  decision: LivingLoopDecision | null
  journey: {
    town_path: string
    profile_path: string
  }
}

export interface LivingLoopChooseRequest {
  choice_key: LivingLoopChoiceKey
  idempotency_key: string
}

export type LivingLoopClientEventName =
  | 'living_loop_today_viewed'
  | 'living_loop_decision_viewed'
  | 'living_loop_choice_previewed'
  | 'living_loop_immediate_result_viewed'
  | 'living_loop_delayed_result_viewed'
  | 'living_loop_enter_town_clicked'
  | 'living_loop_city_pulse_opened'

export interface LivingLoopProductEvent {
  event_id: string
  session_id?: string | null
  event_name: LivingLoopClientEventName
  client_occurred_at?: string
  properties: Record<string, string | number>
}

export interface LivingLoopProductEventBatch {
  events: LivingLoopProductEvent[]
}

export interface LivingLoopProductEventResult {
  accepted: number
  duplicates: number
}

export interface LivingLoopChoiceDistribution {
  choice_key: LivingLoopChoiceKey
  count: number
  share: number
}

export interface AdminLivingLoopMetrics {
  window: {
    from: string
    to: string
  }
  generated_at: string
  today_unique_users: number
  decision_viewed_unique_users: number
  choice_confirmed_unique_users: number
  choice_completion_rate: number | null
  settled_result_count: number
  delayed_result_viewed_unique_users: number
  return_within_48h_rate: number | null
  median_choice_seconds: number | null
  choice_distribution: LivingLoopChoiceDistribution[]
}

interface LivingLoopDecisionEnvelope {
  decision: LivingLoopDecision
}

function unwrapDecision(
  response: LivingLoopDecision | LivingLoopDecisionEnvelope,
): LivingLoopDecision {
  return 'decision' in response ? response.decision : response
}

export function getLivingLoopToday(signal?: AbortSignal): Promise<LivingLoopTodayResponse> {
  return apiFetch('/living-loop/today', { signal })
}

export async function chooseLivingLoopDecision(
  decisionId: string,
  request: LivingLoopChooseRequest,
): Promise<LivingLoopDecision> {
  const response = await apiFetch<LivingLoopDecision | LivingLoopDecisionEnvelope>(
    `/living-loop/decisions/${decisionId}/choose`,
    {
      method: 'POST',
      body: JSON.stringify(request),
    },
  )
  return unwrapDecision(response)
}

export async function markLivingLoopResultViewed(
  decisionId: string,
): Promise<LivingLoopDecision> {
  const response = await apiFetch<LivingLoopDecision | LivingLoopDecisionEnvelope>(
    `/living-loop/decisions/${decisionId}/result-viewed`,
    { method: 'POST' },
  )
  return unwrapDecision(response)
}

export function postProductEventsBatch(
  batch: LivingLoopProductEventBatch,
): Promise<LivingLoopProductEventResult> {
  return apiFetch('/product-events/batch', {
    method: 'POST',
    body: JSON.stringify(batch),
  })
}

export function getAdminLivingLoopMetrics(
  token: string,
  params: { from?: string; to?: string } = {},
): Promise<AdminLivingLoopMetrics> {
  const search = new URLSearchParams()
  if (params.from) search.set('from', params.from)
  if (params.to) search.set('to', params.to)
  const query = search.size > 0 ? `?${search.toString()}` : ''
  return apiFetch(`/admin/product-metrics/living-loop-p0${query}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}
