import { supabase } from './supabase'

const API_URL = (import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const { data } = supabase ? await supabase.auth.getSession() : { data: { session: null } }
  const token = data.session?.access_token ?? localStorage.getItem('atlas-token')
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers },
  })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? `Request failed (${response.status})`)
  return response.json() as Promise<T>
}

export type ApiUser = { name: string; email: string; role: 'manager' | 'holder' | 'incoming' | 'admin' }
export type ApiGap = { id: string; title: string; description: string; service: string; ref: string; status: string }
export type IntegrationStatus = { provider: string; configured: boolean; status: string; details: string }

export async function login(email: string, password: string) {
  if (!supabase) throw new Error('Supabase authentication is not configured')
  const { data, error } = await supabase.auth.signInWithPassword({ email, password })
  if (error || !data.session) throw new Error(error?.message ?? 'Unable to sign in')
  localStorage.setItem('atlas-token', data.session.access_token)
  return request<ApiUser>('/api/me')
}

export function getCurrentUser() { return request<ApiUser>('/api/me') }
export function getKnowledgeGaps() { return request<ApiGap[]>('/api/knowledge-gaps') }
export function captureKnowledge(id: string, answer: string) { return request<ApiGap>(`/api/knowledge-gaps/${id}/capture`, { method: 'POST', body: JSON.stringify({ answer }) }) }
export function getIntegrations() { return request<IntegrationStatus[]>('/api/integrations') }
export function syncIntegration(provider: string) { return request<Record<string, unknown>>(`/api/integrations/${provider}/sync`, { method: 'POST' }) }
export function getWorkspace() { return request<{ last_synced: string }>('/api/workspace') }
export async function clearSession() { localStorage.removeItem('atlas-token'); if (supabase) await supabase.auth.signOut() }
