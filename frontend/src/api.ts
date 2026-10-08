const API_URL = (import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('atlas-token')
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers },
  })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? `Request failed (${response.status})`)
  return response.json() as Promise<T>
}

export type ApiUser = { name: string; email: string; role: 'manager' | 'holder' | 'incoming' | 'admin' }
export type ApiGap = { id: string; title: string; description: string; service: string; ref: string; status: string }
export type ApiKnowledgeRecord = { id: number; gap_id: string; decision: string; reason: string; affected_system: string; status: 'proposed' | 'validated' | 'rejected' | 'needs_clarification'; submitted_by: string | null; validated_by: string | null; validated_at: string | null; created_at: string }
export type IntegrationStatus = { provider: string; configured: boolean; status: string; details: string }

export async function login(email: string, password: string) {
  const result = await request<{ access_token: string; user: ApiUser }>('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
  localStorage.setItem('atlas-token', result.access_token)
  return result.user
}

export function getCurrentUser() { return request<ApiUser>('/api/me') }
export function getKnowledgeGaps() { return request<ApiGap[]>('/api/knowledge-gaps') }
export function captureKnowledge(id: string, answer: string) { return request<ApiGap>(`/api/knowledge-gaps/${id}/capture`, { method: 'POST', body: JSON.stringify({ answer }) }) }
export function getKnowledgeRecords(id: string) { return request<ApiKnowledgeRecord[]>(`/api/knowledge-gaps/${id}/records`) }
export function reviewKnowledge(id: string, recordId: number, decision: 'approve' | 'reject' | 'request_clarification', comment = '') {
  return request<ApiKnowledgeRecord>(`/api/knowledge-gaps/${id}/records/${recordId}/validate`, { method: 'POST', body: JSON.stringify({ decision, comment }) })
}
export function getIntegrations() { return request<IntegrationStatus[]>('/api/integrations') }
export function syncIntegration(provider: string) { return request<Record<string, unknown>>(`/api/integrations/${provider}/sync`, { method: 'POST' }) }
export function getWorkspace() { return request<{ last_synced: string }>('/api/workspace') }
export function clearSession() { localStorage.removeItem('atlas-token') }
