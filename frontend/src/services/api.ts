const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function getToken(): string | null {
  return localStorage.getItem('token')
}

function authHeaders(): Record<string, string> {
  const token = getToken()
  return token
    ? { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
    : { 'Content-Type': 'application/json' }
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers as Record<string, string> || {}) },
  })
  if (!resp.ok) {
    const body = await resp.text()
    throw new Error(`API ${resp.status}: ${body}`)
  }
  return resp.json() as Promise<T>
}

export interface ForgeStartResponse {
  forge_id: string
  step: number
  question: string
}

export interface ForgeAnswerResponse {
  forge_id: string
  step: number
  next_step: number | null
  question: string | null
  ability_md: string | null
  persona_md: string | null
  soul_md: string | null
}

export interface ForgeStatusResponse {
  forge_id: string
  status: 'collecting' | 'generating' | 'done' | 'error'
  step: number
  name: string
  answers: Record<string, string>
  ability_md: string
  persona_md: string
  soul_md: string
  star_rating: number
  district: string
  resident_id: string | null
  error: string | null
}

export function forgeStart(name: string): Promise<ForgeStartResponse> {
  return apiFetch('/forge/start', { method: 'POST', body: JSON.stringify({ name }) })
}

export function forgeAnswer(forge_id: string, answer: string): Promise<ForgeAnswerResponse> {
  return apiFetch('/forge/answer', { method: 'POST', body: JSON.stringify({ forge_id, answer }) })
}

export function forgeStatus(forge_id: string): Promise<ForgeStatusResponse> {
  return apiFetch(`/forge/status/${forge_id}`)
}

export function forgeQuick(name: string, raw_text: string): Promise<{ forge_id: string; status: string }> {
  return apiFetch('/forge/quick', { method: 'POST', body: JSON.stringify({ name, raw_text }) })
}

export interface DeepForgeStartResponse {
  forge_id: string
  status: string
}

export type DeepForgeStage =
  | 'routing'
  | 'researching'
  | 'extracting'
  | 'building'
  | 'validating'
  | 'refining'
  | 'done'
  | 'error'

export interface DeepForgeStatusResponse {
  forge_id: string
  status: DeepForgeStage
  stage: DeepForgeStage
  progress: number
  name: string
  ability_md: string | null
  persona_md: string | null
  soul_md: string | null
  star_rating: number
  district: string
  resident_id: string | null
  error: string | null
}

export function deepForgeStart(
  token: string,
  data: { character_name: string; raw_text?: string; user_material?: string },
): Promise<DeepForgeStartResponse> {
  return apiFetch('/forge/deep-start', {
    method: 'POST',
    body: JSON.stringify(data),
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function deepForgeStatus(token: string, forgeId: string): Promise<DeepForgeStatusResponse> {
  return apiFetch(`/forge/deep-status/${forgeId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export interface ImportSkillResponse {
  id: string
  slug: string
  name: string
  district: string
  star_rating: number
  ability_md: string
  persona_md: string
  soul_md: string
  meta_json: Record<string, unknown> | null
}

// ─── Onboarding API ──────────────────────────────────────────────

export interface OnboardingCheckResponse {
  needs_onboarding: boolean
  player_resident_id: string | null
}

export interface ResidentListItem {
  id: string
  slug: string
  name: string
  district: string
  status: string
  heat: number
  sprite_key: string
  tile_x: number
  tile_y: number
  star_rating: number
  token_cost_per_turn: number
  meta_json: Record<string, unknown> | null
}

export interface OnboardingResidentResponse {
  id: string
  slug: string
  name: string
  sprite_key: string
  tile_x: number
  tile_y: number
}

export function checkOnboarding(token: string): Promise<OnboardingCheckResponse> {
  return apiFetch('/onboarding/check', {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function getResidents(): Promise<ResidentListItem[]> {
  return apiFetch('/residents')
}

export function loadPreset(token: string, preset_slug: string): Promise<OnboardingResidentResponse> {
  return apiFetch('/onboarding/load-preset', {
    method: 'POST',
    body: JSON.stringify({ preset_slug }),
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function skipOnboarding(token: string): Promise<OnboardingResidentResponse> {
  return apiFetch('/onboarding/skip', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
}

// ─── Settings API ────────────────────────────────────────────────

export interface AccountSettings {
  display_name: string
  email: string
  has_password: boolean
  github_bound: boolean
  linuxdo_bound: boolean
  linuxdo_trust_level: number | null
}

export interface CharacterSettings {
  resident_id: string
  name: string
  sprite_key: string
  portrait_url: string | null
  ability_md: string
  persona_md: string
  soul_md: string
}

export interface SpriteTemplate {
  key: string
  gender: string
  age_group: string
  vibe: string
  tags: string[]
}

export interface AllSettings {
  account: AccountSettings
  character: CharacterSettings | null
  interaction: Record<string, unknown>
  privacy: Record<string, unknown>
  llm: Record<string, unknown>
  economy: Record<string, unknown>
}

export function getSettings(): Promise<AllSettings> {
  return apiFetch('/settings')
}

export function updateAccount(data: { display_name?: string }): Promise<{ display_name: string; email: string }> {
  return apiFetch('/settings/account', { method: 'PATCH', body: JSON.stringify(data) })
}

export function updateCharacter(data: { name?: string; sprite_key?: string }): Promise<CharacterSettings> {
  return apiFetch('/settings/character', { method: 'PATCH', body: JSON.stringify(data) })
}

export function updateInteraction(data: {
  reply_mode?: 'manual' | 'auto'
  offline_auto_reply?: boolean
  notification_chat?: boolean
  notification_system?: boolean
}): Promise<{ interaction: Record<string, unknown> }> {
  return apiFetch('/settings/interaction', { method: 'PATCH', body: JSON.stringify(data) })
}

export function updatePrivacy(data: {
  map_visible?: boolean
  persona_visibility?: 'full' | 'identity_card_only' | 'hidden'
  allow_conversation_stats?: boolean
}): Promise<{ privacy: Record<string, unknown> }> {
  return apiFetch('/settings/privacy', { method: 'PATCH', body: JSON.stringify(data) })
}

export function getSpriteTemplates(): Promise<SpriteTemplate[]> {
  return apiFetch('/sprites/templates')
}

export interface LLMSettings {
  system_allows_custom?: boolean
  custom_llm_enabled?: boolean
  api_format?: 'openai' | 'anthropic'
  base_url?: string
  api_key?: string
  model?: string
}

export interface LLMTestResult {
  success: boolean
  message: string
}

export function updateLLM(data: LLMSettings): Promise<{ llm: Record<string, unknown> }> {
  return apiFetch('/settings/llm', { method: 'PATCH', body: JSON.stringify(data) })
}

export function testLLMConnection(data: {
  api_format: string
  base_url: string
  api_key: string
  model: string
}): Promise<LLMTestResult> {
  return apiFetch('/settings/llm/test', { method: 'POST', body: JSON.stringify(data) })
}

export function updateEconomy(data: { low_balance_alert?: number }): Promise<{ economy: Record<string, unknown> }> {
  return apiFetch('/settings/economy', { method: 'PATCH', body: JSON.stringify(data) })
}

// ─── Import Skill ────────────────────────────────────────────────

export async function importSkill(file: File, name: string, slug: string): Promise<ImportSkillResponse> {
  const token = getToken()
  const formData = new FormData()
  formData.append('file', file)
  formData.append('name', name)
  formData.append('slug', slug)

  const resp = await fetch(`${API_BASE}/residents/import`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  })
  if (!resp.ok) {
    const body = await resp.text()
    throw new Error(`API ${resp.status}: ${body}`)
  }
  return resp.json() as Promise<ImportSkillResponse>
}
