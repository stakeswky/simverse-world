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
    if (resp.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      window.location.href = '/login'
      throw new Error('Session expired')
    }
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

// ─── Admin API ───────────────────────────────────────────────────

export interface AdminDashboardStats {
  online_users: number
  today_registrations: number
  active_chats: number
  soul_coin_net_flow: number
}

export interface AdminDashboardHealth {
  searxng: 'ok' | 'error'
  llm_api: 'ok' | 'error'
  details: Record<string, string | null>
}

export interface AdminDashboardTrend {
  date: string
  registrations: number
  active_users: number
  sc_spent: number
}

export function getAdminDashboardStats(token: string): Promise<AdminDashboardStats> {
  return apiFetch('/admin/dashboard/stats', {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function getAdminDashboardHealth(token: string): Promise<AdminDashboardHealth> {
  const arr: { service: string; status: string; detail?: string | null }[] = await apiFetch('/admin/dashboard/health', {
    headers: { Authorization: `Bearer ${token}` },
  })
  // Transform array to keyed object
  const result: AdminDashboardHealth = { searxng: 'error', llm_api: 'error', details: {} }
  for (const item of arr) {
    const key = item.service as keyof Omit<AdminDashboardHealth, 'details'>
    if (key in result) {
      result[key] = item.status as 'ok' | 'error'
    }
    result.details[item.service] = item.detail ?? null
  }
  return result
}

export function getAdminDashboardTrends(token: string): Promise<AdminDashboardTrend[]> {
  return apiFetch('/admin/dashboard/trends', {
    headers: { Authorization: `Bearer ${token}` },
  })
}

// ─── Admin Economy API ───────────────────────────────────────────

export interface AdminEconomyStats {
  total_issued: number
  total_consumed: number
  net_circulation: number
  total_users: number
  avg_balance: number
}

export interface AdminTransaction {
  id: string
  user_id: string
  amount: number
  reason: string
  created_at: string
}

export interface AdminTransactionsResponse {
  items: AdminTransaction[]
  total: number
  offset: number
  limit: number
}

export interface AdminEconomyConfig {
  signup_bonus: number
  daily_reward: number
  chat_cost_per_turn: number
  creator_reward: number
  rating_bonus: number
}

export function getAdminEconomyStats(token: string): Promise<AdminEconomyStats> {
  return apiFetch('/admin/economy/stats', {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function getAdminTransactions(
  token: string,
  params: { page?: number; per_page?: number; reason?: string },
): Promise<AdminTransactionsResponse> {
  const qs = new URLSearchParams()
  const offset = ((params.page ?? 1) - 1) * (params.per_page ?? 20)
  qs.set('offset', String(offset))
  qs.set('limit', String(params.per_page ?? 20))
  if (params.reason) qs.set('reason', params.reason)
  const query = qs.toString() ? `?${qs.toString()}` : ''
  return apiFetch(`/admin/economy/transactions${query}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function getAdminEconomyConfig(token: string): Promise<AdminEconomyConfig> {
  return apiFetch('/admin/economy/config', {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function updateAdminEconomyConfig(token: string, data: Partial<AdminEconomyConfig>): Promise<AdminEconomyConfig> {
  return apiFetch('/admin/economy/config', {
    method: 'PUT',
    body: JSON.stringify(data),
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function getAdminSystemConfig(token: string, group: string): Promise<Record<string, unknown>> {
  return apiFetch(`/admin/system/groups/${group}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function updateAdminSystemConfig(
  token: string,
  key: string,
  value: unknown,
  group: string,
): Promise<{ key: string; value: unknown; group: string }> {
  return apiFetch('/admin/system/entry', {
    method: 'PUT',
    body: JSON.stringify({ key, value, group }),
    headers: { Authorization: `Bearer ${token}` },
  })
}

// ─── Admin Residents & Forge Monitor API ─────────────────────────

export interface AdminResident {
  id: string
  slug: string
  name: string
  district: string
  status: string
  heat: number
  star_rating: number
  sprite_key: string
  type: 'NPC' | 'Player'
  creator: string | null
  ability_md: string | null
  persona_md: string | null
  soul_md: string | null
  meta_json: Record<string, unknown> | null
}

export interface AdminResidentsResponse {
  items: AdminResident[]
  total: number
  page: number
  per_page: number
}

export function getAdminResidents(
  token: string,
  params: { page?: number; per_page?: number; search?: string; district?: string; status?: string },
): Promise<AdminResidentsResponse> {
  const qs = new URLSearchParams()
  if (params.page != null) qs.set('page', String(params.page))
  if (params.per_page != null) qs.set('per_page', String(params.per_page))
  if (params.search) qs.set('search', params.search)
  if (params.district) qs.set('district', params.district)
  if (params.status) qs.set('status', params.status)
  const query = qs.toString() ? `?${qs.toString()}` : ''
  return apiFetch(`/admin/residents${query}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function adminEditResident(
  token: string,
  residentId: string,
  data: Record<string, unknown>,
): Promise<AdminResident> {
  return apiFetch(`/admin/residents/${residentId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
    headers: { Authorization: `Bearer ${token}` },
  })
}

export interface AdminForgeSession {
  forge_id: string
  character_name: string
  mode: 'quick' | 'deep'
  current_stage: string
  status: string
  started_at: string
  elapsed_seconds: number
}

export interface AdminForgeHistoryItem {
  forge_id: string
  character_name: string
  mode: 'quick' | 'deep'
  status: string
  stage: string
  started_at: string
  finished_at: string | null
  resident_id: string | null
}

export interface AdminForgeHistoryResponse {
  items: AdminForgeHistoryItem[]
  total: number
  page: number
  per_page: number
}

export function getAdminForgeActive(token: string): Promise<AdminForgeSession[]> {
  return apiFetch('/admin/forge/active', {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function getAdminForgeHistory(
  token: string,
  params: { page?: number; per_page?: number; status?: string },
): Promise<AdminForgeHistoryResponse> {
  const qs = new URLSearchParams()
  if (params.page != null) qs.set('page', String(params.page))
  if (params.per_page != null) qs.set('per_page', String(params.per_page))
  if (params.status) qs.set('status', params.status)
  const query = qs.toString() ? `?${qs.toString()}` : ''
  return apiFetch(`/admin/forge${query}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
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

// ─── Admin Users API ─────────────────────────────────────────────

export interface AdminUserListParams {
  page?: number
  per_page?: number
  search?: string
  sort_by?: string
}

export interface AdminUserListItem {
  id: string
  name: string
  email: string
  login_methods: string[]
  soul_coin_balance: number
  resident_count: number
  created_at: string
  is_banned: boolean
  is_admin: boolean
}

export interface AdminUserListResponse {
  items: AdminUserListItem[]
  total: number
  page: number
  per_page: number
}

export interface AdminUserDetail extends AdminUserListItem {
  last_login_at: string | null
}

export interface AdminAdjustCoinData {
  amount: number
  reason: string
}

export interface AdminPatchUserData {
  is_banned?: boolean
  is_admin?: boolean
}

export function getAdminUsers(token: string, params: AdminUserListParams): Promise<AdminUserListResponse> {
  const qs = new URLSearchParams()
  if (params.page !== undefined) qs.set('page', String(params.page))
  if (params.per_page !== undefined) qs.set('per_page', String(params.per_page))
  if (params.search) qs.set('search', params.search)
  if (params.sort_by) qs.set('sort_by', params.sort_by)
  const query = qs.toString() ? `?${qs.toString()}` : ''
  return apiFetch(`/admin/users${query}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function getAdminUserDetail(token: string, userId: string): Promise<AdminUserDetail> {
  return apiFetch(`/admin/users/${userId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function adminAdjustCoin(
  token: string,
  userId: string,
  data: AdminAdjustCoinData,
): Promise<{ new_balance: number }> {
  return apiFetch(`/admin/users/${userId}/adjust-coin`, {
    method: 'POST',
    body: JSON.stringify(data),
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function adminPatchUser(
  token: string,
  userId: string,
  data: AdminPatchUserData,
): Promise<{ user_id: string; is_banned: boolean; is_admin: boolean }> {
  return apiFetch(`/admin/users/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
    headers: { Authorization: `Bearer ${token}` },
  })
}

// ─── Player Position API ─────────────────────────────────────────

export function updatePlayerPosition(tileX: number, tileY: number): Promise<{ tile_x: number; tile_y: number }> {
  return apiFetch('/residents/player/position', {
    method: 'PUT',
    body: JSON.stringify({ tile_x: tileX, tile_y: tileY }),
  })
}
