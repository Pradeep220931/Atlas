import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { captureKnowledge, clearSession, getCurrentUser, getKnowledgeGaps, getWorkspace, login as apiLogin, reviewKnowledge, syncIntegration } from './api'

export type Role = 'manager' | 'holder' | 'incoming' | 'admin'
export type User = { name: string; email: string; role: Role }
export type Gap = { id: string; title: string; description: string; service: string; ref: string; status: 'Open' | 'Validated'; ai_analysis?: import('./api').ApiGap['ai_analysis'] }
export type TransitionArea = { name: string; status: 'Verified' | 'Needs review' }

export const demoUsers: User[] = [
  { name: 'Engineering Manager', email: 'manager@finpay.demo', role: 'manager' },
  { name: 'Arun Kumar', email: 'arun@finpay.demo', role: 'holder' },
  { name: 'Priya Sharma', email: 'priya@finpay.demo', role: 'incoming' },
  { name: 'Admin / CTO', email: 'admin@finpay.demo', role: 'admin' },
]

const initialAreas: TransitionArea[] = [
  { name: 'Payment architecture', status: 'Verified' }, { name: 'Retry mechanism', status: 'Verified' },
  { name: 'Gateway behaviour', status: 'Needs review' }, { name: 'Refund reconciliation', status: 'Needs review' }, { name: 'Deployment', status: 'Verified' },
]

type AtlasContextValue = {
  user: User | null; gaps: Gap[]; areas: TransitionArea[]; lastSync: string; syncing: boolean; unread: number
  login: (email: string, password: string) => Promise<boolean>; logout: () => void; switchRole: (role: Role) => void
  refreshGaps: () => Promise<void>; validateGap: (id: string, answer: string) => Promise<void>; reviewKnowledge: (id: string, recordId: number, decision: 'approve' | 'reject' | 'request_clarification', comment?: string) => Promise<void>; createTransition: () => void; verifyArea: (name: string) => void; sync: () => void; markRead: () => void
}
const AtlasContext = createContext<AtlasContextValue | null>(null)

export function AtlasProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => { const email = localStorage.getItem('atlas-user'); return demoUsers.find(item => item.email === email) ?? null })
  const [gaps, setGaps] = useState<Gap[]>([])
  const [areas, setAreas] = useState(initialAreas)
  const [lastSync, setLastSync] = useState('8 min ago')
  const [syncing, setSyncing] = useState(false)
  const [unread, setUnread] = useState(3)
  useEffect(() => {
    if (!user) { localStorage.removeItem('atlas-user'); return }
    localStorage.setItem('atlas-user', user.email)
  }, [user])
  useEffect(() => {
    if (!localStorage.getItem('atlas-token')) return
    getCurrentUser().then(apiUser => setUser(apiUser as User)).catch(() => { clearSession(); setUser(null) })
    getKnowledgeGaps().then(apiGaps => setGaps(apiGaps.map(gap => ({ ...gap, status: gap.status.toLowerCase() === 'validated' ? 'Validated' : 'Open' })))).catch(() => undefined)
    getWorkspace().then(workspace => setLastSync(workspace.last_synced)).catch(() => undefined)
  }, [])
  const value = useMemo(() => ({ user, gaps, areas, lastSync, syncing, unread,
    refreshGaps: async () => { const apiGaps = await getKnowledgeGaps(); setGaps(apiGaps.map(gap => ({ ...gap, status: gap.status.toLowerCase() === 'validated' ? 'Validated' : 'Open' }))) },
    login: async (email: string, password: string) => { try { setUser(await apiLogin(email, password) as User); const apiGaps = await getKnowledgeGaps(); setGaps(apiGaps.map(gap => ({ ...gap, status: gap.status.toLowerCase() === 'validated' ? 'Validated' : 'Open' }))); const workspace = await getWorkspace(); setLastSync(workspace.last_synced); return true } catch { return false } },
    logout: () => { clearSession(); setUser(null) },
    switchRole: (role: Role) => setUser(demoUsers.find(item => item.role === role) ?? null),
    validateGap: async (id: string, answer: string) => { await captureKnowledge(id, answer); const apiGaps = await getKnowledgeGaps(); setGaps(apiGaps.map(gap => ({ ...gap, status: gap.status.toLowerCase() === 'validated' ? 'Validated' : 'Open' }))) },
    reviewKnowledge: async (id: string, recordId: number, decision: 'approve' | 'reject' | 'request_clarification', comment = '') => { await reviewKnowledge(id, recordId, decision, comment); const apiGaps = await getKnowledgeGaps(); setGaps(apiGaps.map(gap => ({ ...gap, status: gap.status.toLowerCase() === 'validated' ? 'Validated' : 'Open' }))) },
    createTransition: () => setAreas(initialAreas),
    verifyArea: (name: string) => setAreas(current => current.map(area => area.name === name ? { ...area, status: 'Verified' } : area)),
    sync: () => { setSyncing(true); syncIntegration('github').then(() => { setLastSync('Just now'); setUnread(current => current + 1) }).catch(() => undefined).finally(() => setSyncing(false)) },
    markRead: () => setUnread(0),
  }), [user, gaps, areas, lastSync, syncing, unread])
  return <AtlasContext.Provider value={value}>{children}</AtlasContext.Provider>
}
export function useAtlas() { const context = useContext(AtlasContext); if (!context) throw new Error('useAtlas must be used inside AtlasProvider'); return context }
export function progress(areas: TransitionArea[]) { return Math.round(areas.filter(area => area.status === 'Verified').length / areas.length * 100) }
