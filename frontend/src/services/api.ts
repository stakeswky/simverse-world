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
