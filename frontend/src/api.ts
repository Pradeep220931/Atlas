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
export type ApiGap = { id: string; title: string; description: string; service: string; ref: string; status: string; ai_analysis?: { potential_gap: boolean; title: string; summary: string; targeted_question: string; reason: string; confidence: number; evidence_ids: string[] } | null }
export type ApiGapQuestions = { questions: { question: string; rationale: string; evidence_ids: string[] }[] }
export type ApiKnowledgeRecord = { id: number; gap_id: string; decision: string; reason: string; affected_system: string; status: 'proposed' | 'validated' | 'rejected' | 'needs_clarification'; submitted_by: string | null; validated_by: string | null; validated_at: string | null; created_at: string }
export type IntegrationStatus = { provider: string; configured: boolean; status: string; details: string }
export type AiConnectionStatus = {
  provider: string
  configured: boolean
  credentials_configured: boolean
  model_configured: boolean
  model: string | null
  base_url: string | null
  connection_status: 'online' | 'offline'
  checked_at: string | null
  message: string | null
}
export type GitHubRepository = { id: number; full_name: string; description: string | null; language: string | null; default_branch: string; html_url: string; updated_at: string | null; private: boolean }
export type GitHubPullRequest = { number: number; title: string; body: string | null; state: string; merged: boolean; author: string | null; author_avatar_url: string | null; html_url: string; created_at: string | null; updated_at: string | null; merged_at: string | null; changed_files: number; commits: number; additions: number; deletions: number }
export type GitHubEvidence = {
  repository: GitHubRepository
  pull_request: GitHubPullRequest
  files: { filename: string; status: string; additions: number; deletions: number; changes: number; patch: string | null; patch_available: boolean; patch_truncated: boolean; blob_url: string | null }[]
  reviews: { user: string | null; state: string | null; submitted_at: string | null; body: string }[]
  commits: { sha: string | null; message: string; author: string | null }[]
  signals: Record<string, unknown>
  ai_context_ready: boolean
  ai_context_record_count: number
  jira_status: 'not_connected'
  incident_status: 'not_connected'
  source_note: string
}
export type GitHubAnalysis = {
  knowledge_gap_id: string
  persisted: boolean
  provider: string
  model: string
  task: string
  input_record_count: number
  evidence_ids: string[]
  signals: Record<string, unknown>
  analysis: NonNullable<ApiGap['ai_analysis']>
  stages: { id: string; label: string; status: 'complete' | 'skipped'; detail: string }[]
}

export async function login(email: string, password: string) {
  const result = await request<{ access_token: string; user: ApiUser }>('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
  localStorage.setItem('atlas-token', result.access_token)
  return result.user
}

export function getCurrentUser() { return request<ApiUser>('/api/me') }
export function getKnowledgeGaps() { return request<ApiGap[]>('/api/knowledge-gaps') }
export function analyzeKnowledgeGap(id: string) { return request<{ analysis: NonNullable<ApiGap['ai_analysis']>; persisted: boolean }>(`/api/knowledge-gaps/${id}/analyze`, { method: 'POST' }) }
export function generateGapQuestions(id: string) { return request<ApiGapQuestions>(`/api/knowledge-gaps/${id}/questions`, { method: 'POST' }) }
export function captureKnowledge(id: string, answer: string) { return request<ApiGap>(`/api/knowledge-gaps/${id}/capture`, { method: 'POST', body: JSON.stringify({ answer }) }) }
export function structureKnowledgeAnswer(id: string, question: string, answer: string) {
  return request<ApiKnowledgeRecord>(`/api/knowledge-gaps/${id}/structure-answer`, { method: 'POST', body: JSON.stringify({ question, answer }) })
}
export function getKnowledgeRecords(id: string) { return request<ApiKnowledgeRecord[]>(`/api/knowledge-gaps/${id}/records`) }
export function reviewKnowledge(id: string, recordId: number, decision: 'approve' | 'reject' | 'request_clarification', comment = '') {
  return request<ApiKnowledgeRecord>(`/api/knowledge-gaps/${id}/records/${recordId}/validate`, { method: 'POST', body: JSON.stringify({ decision, comment }) })
}
export function getIntegrations() { return request<IntegrationStatus[]>('/api/integrations') }
export function syncIntegration(provider: string) { return request<Record<string, unknown>>(`/api/integrations/${provider}/sync`, { method: 'POST' }) }
export function getWorkspace() { return request<{ last_synced: string }>('/api/workspace') }
export function getAiConnectionStatus() { return request<AiConnectionStatus>('/api/ai/status') }
export function testAiConnection() { return request<{ provider: string; message: string; connection_status: 'online'; checked_at: string }>('/api/ai/test', { method: 'POST' }) }
export function getGitHubRepositories() { return request<GitHubRepository[]>('/api/github/repositories') }
export function getGitHubPullRequests(repositoryId: number) { return request<GitHubPullRequest[]>(`/api/github/repositories/${repositoryId}/pull-requests`) }
export function getGitHubPullRequestEvidence(repositoryId: number, number: number) { return request<GitHubEvidence>(`/api/github/repositories/${repositoryId}/pull-requests/${number}/evidence`) }
export function analyzeGitHubPullRequest(repositoryId: number, number: number) { return request<GitHubAnalysis>(`/api/github/repositories/${repositoryId}/pull-requests/${number}/analyze`, { method: 'POST' }) }
export function clearSession() { localStorage.removeItem('atlas-token') }
