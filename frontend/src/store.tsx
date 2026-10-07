import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { captureKnowledge, clearSession, getCurrentUser, getKnowledgeGaps, getWorkspace, login as apiLogin, syncIntegration } from './api'

export type Role = 'manager' | 'holder' | 'incoming' | 'admin'
export type User = { name: string; email: string; role: Role }
export type Gap = { id: string; title: string; description: string; service: string; ref: string; status: 'Open' | 'Validated' }
export type TransitionArea = { name: string; status: 'Verified' | 'Needs review' }

export const demoUsers: User[] = [
  { name: 'Engineering Manager', email: 'manager@finpay.demo', role: 'manager' },
  { name: 'Arun Kumar', email: 'arun@finpay.demo', role: 'holder' },
  { name: 'Priya Sharma', email: 'priya@finpay.demo', role: 'incoming' },
  { name: 'Admin / CTO', email: 'admin@finpay.demo', role: 'admin' },
]

const initialGaps: Gap[] = [
  { id: 'payment-retry-policy', title: 'Payment retry policy', description: 'Decision exists, rationale not found', service: 'Payment Service', ref: 'PR-1823 · PAY-421', status: 'Open' },
  { id: 'gateway-timeout', title: 'Gateway timeout behaviour', description: 'Implementation exists, context unclear', service: 'Payment Service', ref: 'PR-1774', status: 'Open' },
  { id: 'refund-reconciliation', title: 'Refund reconciliation behaviour', description: 'Operational context unclear', service: 'Refund Engine', ref: 'PAY-398', status: 'Open' },
]

const initialAreas: TransitionArea[] = [
  { name: 'Payment architecture', status: 'Verified' }, { name: 'Retry mechanism', status: 'Verified' },
  { name: 'Gateway behaviour', status: 'Needs review' }, { name: 'Refund reconciliation', status: 'Needs review' }, { name: 'Deployment', status: 'Verified' },
]

type AtlasContextValue = {
  user: User | null; gaps: Gap[]; areas: TransitionArea[]; lastSync: string; syncing: boolean; unread: number
  login: (email: string, password: string) => Promise<boolean>; logout: () => void; switchRole: (role: Role) => void
  validateGap: (id: string, answer?: string) => Promise<void>; createTransition: () => void; verifyArea: (name: string) => void; sync: () => void; markRead: () => void
}
const AtlasContext = createContext<AtlasContextValue | null>(null)

export function AtlasProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => { const email = localStorage.getItem('atlas-user'); return demoUsers.find(item => item.email === email) ?? null })
  const [gaps, setGaps] = useState(initialGaps)
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
    login: async (email: string, password: string) => { try { setUser(await apiLogin(email, password) as User); return true } catch { return false } },
    logout: () => { clearSession(); setUser(null) },
    switchRole: (role: Role) => setUser(demoUsers.find(item => item.role === role) ?? null),
    validateGap: async (id: string, answer = 'Validated technical context') => { await captureKnowledge(id, answer); setGaps(current => current.map(gap => gap.id === id ? { ...gap, status: 'Validated' } : gap)) },
    createTransition: () => setAreas(initialAreas),
    verifyArea: (name: string) => setAreas(current => current.map(area => area.name === name ? { ...area, status: 'Verified' } : area)),
    sync: () => { setSyncing(true); syncIntegration('github').then(() => { setLastSync('Just now'); setUnread(current => current + 1) }).catch(() => undefined).finally(() => setSyncing(false)) },
    markRead: () => setUnread(0),
  }), [user, gaps, areas, lastSync, syncing, unread])
  return <AtlasContext.Provider value={value}>{children}</AtlasContext.Provider>
}
export function useAtlas() { const context = useContext(AtlasContext); if (!context) throw new Error('useAtlas must be used inside AtlasProvider'); return context }
export function progress(areas: TransitionArea[]) { return Math.round(areas.filter(area => area.status === 'Verified').length / areas.length * 100) }
