import { useEffect, useState } from 'react'
import { Navigate, NavLink, Outlet, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import { Activity, ArrowRight, Bell, BookOpen, Check, ChevronDown, CircleAlert, Database, ExternalLink, FileText, GitBranch, GitPullRequest, LayoutDashboard, LogOut, Map, Menu, RefreshCw, Search, Settings, Shield, SlidersHorizontal, Users, X, Zap } from 'lucide-react'
import { demoUsers, progress, useAtlas, type Role, type TransitionArea } from './store'
import { analyzeGitHubPullRequest, analyzeKnowledgeGap, generateGapQuestions, getAiConnectionStatus, getGitHubPullRequestEvidence, getGitHubPullRequests, getGitHubRepositories, getKnowledgeRecords, structureKnowledgeAnswer, testAiConnection, type ApiGapQuestions, type ApiKnowledgeRecord, type GitHubAnalysis, type GitHubEvidence, type GitHubPullRequest, type GitHubRepository } from './api'

const roleLabels: Record<Role, string> = { manager: 'Engineering Manager', holder: 'Knowledge Holder', incoming: 'Incoming Engineer', admin: 'Admin / CTO' }
const nav: Record<Role, { label: string; to: string; icon: typeof Map }[]> = {
  manager: [{ label: 'Overview', to: '/app/overview', icon: LayoutDashboard }, { label: 'Knowledge Map', to: '/app/knowledge-map', icon: Map }, { label: 'GitHub Evidence', to: '/app/github-evidence', icon: GitBranch }, { label: 'Risk Areas', to: '/app/risk-areas/payment-service', icon: Activity }, { label: 'Knowledge Gaps', to: '/app/knowledge-gaps', icon: CircleAlert }, { label: 'Active transitions', to: '/app/transitions/payment-service', icon: GitBranch }, { label: 'Integrations', to: '/app/integrations', icon: Zap }, { label: 'Settings', to: '/app/settings', icon: Settings }],
  holder: [{ label: 'My Knowledge', to: '/app/my-knowledge', icon: BookOpen }, { label: 'Knowledge Gaps', to: '/app/knowledge-gaps', icon: CircleAlert }, { label: 'Pending Validation', to: '/app/my-knowledge/pending-validation', icon: Check }, { label: 'Knowledge Records', to: '/app/my-knowledge/records', icon: FileText }, { label: 'My Profile', to: '/app/settings', icon: Users }],
  incoming: [{ label: 'My Transition', to: '/app/my-transition', icon: GitBranch }, { label: 'Knowledge Areas', to: '/app/my-transition/knowledge-areas', icon: BookOpen }, { label: 'Knowledge Check', to: '/app/my-transition/check', icon: Check }, { label: 'Completed', to: '/app/transitions/payment-service/complete', icon: Activity }, { label: 'My Profile', to: '/app/settings', icon: Users }],
  admin: [{ label: 'Organization', to: '/app/organization', icon: LayoutDashboard }, { label: 'Teams & Members', to: '/app/teams', icon: Users }, { label: 'Roles & Permissions', to: '/app/roles', icon: Shield }, { label: 'GitHub Evidence', to: '/app/github-evidence', icon: GitBranch }, { label: 'Integrations', to: '/app/integrations', icon: Zap }, { label: 'Data & Sync', to: '/app/data-sync', icon: Database }, { label: 'Security', to: '/app/security', icon: Shield }, { label: 'Audit Log', to: '/app/audit-log', icon: FileText }, { label: 'Settings', to: '/app/settings', icon: Settings }],
}

export function App() { return <Routes><Route path="/login" element={<Login />} /><Route path="/app" element={<ProtectedLayout />}><Route index element={<HomeRedirect />} /><Route path="*" element={<PageRoutes />} /></Route><Route path="*" element={<Navigate to="/app" replace />} /></Routes> }
function HomeRedirect() { const { user } = useAtlas(); return <Navigate to={user?.role === 'holder' ? 'my-knowledge' : user?.role === 'incoming' ? 'my-transition' : user?.role === 'admin' ? 'organization' : 'overview'} replace /> }
function ProtectedLayout() { const { user } = useAtlas(); return user ? <Shell /> : <Navigate to="/login" replace /> }

function AiConnectionStatus({ canCheck }: { canCheck: boolean }) {
  const [connection, setConnection] = useState<'checking' | 'online' | 'offline'>('checking')
  const [checking, setChecking] = useState(false)
  const [detail, setDetail] = useState('Loading last connection status')

  useEffect(() => {
    let active = true
    getAiConnectionStatus().then(status => {
      if (!active) return
      setConnection(status.connection_status)
      setDetail(status.checked_at ? `Last checked ${new Date(status.checked_at).toLocaleString()}` : status.message ?? 'No successful connection test has been run')
    }).catch(error => {
      if (!active) return
      setConnection('offline')
      setDetail(error instanceof Error ? error.message : 'Unable to read AI connection status')
    })
    return () => { active = false }
  }, [])

  async function checkConnection() {
    setChecking(true)
    setConnection('checking')
    setDetail('Testing the configured AI provider...')
    try {
      const result = await testAiConnection()
      setConnection('online')
      setDetail(`${result.message} Checked ${new Date(result.checked_at).toLocaleString()}`)
    } catch (error) {
      setConnection('offline')
      setDetail(error instanceof Error ? error.message : 'AI connection test failed')
    } finally {
      setChecking(false)
    }
  }

  const label = connection === 'online' ? 'AI Online' : connection === 'checking' ? 'AI Checking' : 'AI Offline'
  return <button className={`ai-connection-status ${connection}`} type="button" onClick={checkConnection} disabled={!canCheck || checking} title={canCheck ? detail : `${detail}. Admin access is required to test the connection.`} aria-label={`${label}. ${detail}`}>
    <span className="ai-connection-dot" />
    <span>{checking ? 'Checking...' : label}</span>
    {canCheck && <Activity size={14} />}
  </button>
}

function Shell() {
  const { user, logout, switchRole, unread, markRead } = useAtlas(); const [mobile, setMobile] = useState(false); const [menu, setMenu] = useState(false); const [search, setSearch] = useState(''); const navigate = useNavigate();
  const items = nav[user!.role];
  const searchResults = search ? ['Payment Service', 'Payment retry policy', 'Arun Kumar', 'payment-service'].filter(item => item.toLowerCase().includes(search.toLowerCase())) : []
  return <div className="shell"><aside className={mobile ? 'sidebar open' : 'sidebar'}><div className="brand"><span className="brand-mark">A</span><span>ATLAS</span><button className="icon-button mobile-only" onClick={() => setMobile(false)}><X size={18} /></button></div><div className="workspace"><span className="eyebrow">WORKSPACE</span><strong>FinPay / Engineering</strong><span className="demo-pill">Demo workspace</span></div><nav>{items.map(item => { const Icon = item.icon; return <NavLink key={item.to} to={item.to} onClick={() => setMobile(false)} className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}><Icon size={17} /><span>{item.label}</span></NavLink> })}</nav><div className="sidebar-footer"><button className="user-menu" onClick={() => setMenu(!menu)}><span className="avatar">{user!.name.split(' ').map(part => part[0]).join('').slice(0, 2)}</span><span><strong>{user!.name}</strong><small>{roleLabels[user!.role]}</small></span><ChevronDown size={15} /></button>{menu && <div className="role-popover"><span className="eyebrow">SWITCH DEMO ROLE</span>{demoUsers.map(account => <button key={account.role} onClick={() => { switchRole(account.role); setMenu(false); navigate('/app') }} className={account.role === user!.role ? 'role-option selected' : 'role-option'}>{account.name}<small>{account.email}</small></button>)}<button className="logout" onClick={logout}><LogOut size={15} /> Log out</button></div>}</div></aside><main className="main"><header className="topbar"><button className="icon-button mobile-only" onClick={() => setMobile(true)}><Menu size={19} /></button><div className="search-wrap"><Search size={17} /><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search systems, knowledge, people..." />{searchResults.length > 0 && <div className="search-results">{searchResults.map(result => <button key={result} onClick={() => { setSearch(''); navigate(result === 'Payment retry policy' ? '/app/knowledge/capture/payment-retry-policy' : result === 'Arun Kumar' ? '/app/my-knowledge' : '/app/risk-areas/payment-service') }}>{result}<ArrowRight size={14} /></button>)}</div>}</div><div className="top-actions"><AiConnectionStatus canCheck={user!.role === 'admin'} />
    <button className="icon-button notification" aria-label="Notifications" onClick={() => markRead()}><Bell size={18} />{unread > 0 && <span>{unread}</span>}</button><div className="top-role">{roleLabels[user!.role]}</div></div></header><div className="content"><Outlet /></div></main></div>
}

function Login() { const { user, login } = useAtlas(); const navigate = useNavigate(); const [email, setEmail] = useState('manager@finpay.demo'); const [password, setPassword] = useState('demo-password'); const [error, setError] = useState(''); if (user) return <Navigate to="/app" replace />; return <main className="login-page"><div className="login-panel"><div className="brand login-brand"><span className="brand-mark">A</span><span>ATLAS</span></div><p className="eyebrow">ENGINEERING KNOWLEDGE CONTINUITY</p><h1>Make critical context visible.</h1><p className="login-copy">Know what engineering knowledge is at risk before it becomes a problem.</p><form onSubmit={async event => { event.preventDefault(); if (!(await login(email, password))) setError('Use a valid demo account and password.'); else navigate('/app') }}><label>Work email<input type="email" value={email} onChange={event => setEmail(event.target.value)} /></label><label>Password<input type="password" value={password} onChange={event => setPassword(event.target.value)} /></label>{error && <p className="error-text">{error}</p>}<button className="primary full">Sign in <ArrowRight size={16} /></button></form><div className="login-divider"><span>Demo accounts</span></div><div className="demo-accounts">{demoUsers.map(account => <button key={account.email} onClick={() => setEmail(account.email)}><span>{account.name}</span><small>{account.email}</small></button>)}</div></div><div className="login-aside"><div><span className="eyebrow">ATLAS / FINPAY</span><h2>Continuity is a team capability.</h2><p>Connect engineering activity, surface fragile knowledge, and make transitions verifiable.</p></div><div className="aside-stat"><strong>78%</strong><span>continuity health</span></div></div></main> }

function PageRoutes() {
  const { user } = useAtlas()
  const location = useLocation()
  const path = location.pathname.replace('/app/', '')
  const allowed = user?.role === 'admin'
    ? /^(organization|teams|roles|github-evidence|integrations|data-sync|security|audit-log|settings)/.test(path)
    : user?.role === 'incoming'
      ? /^(my-transition|transitions\/payment-service\/complete|settings)/.test(path)
      : user?.role === 'holder'
        ? /^(my-knowledge|knowledge-gaps|knowledge\/capture|settings)/.test(path)
        : /^(overview|knowledge-map|github-evidence|risk-areas|knowledge-gaps|knowledge\/capture|transitions|integrations|settings)/.test(path)
  if (!allowed) return <PermissionState />
  return <Routes><Route path="overview" element={<Overview />} /><Route path="knowledge-map" element={<KnowledgeMap />} /><Route path="github-evidence" element={<GitHubEvidencePage />} /><Route path="risk-areas/payment-service" element={<RiskArea />} /><Route path="knowledge-gaps" element={<KnowledgeGaps />} /><Route path="knowledge/capture/:id" element={<Capture />} /><Route path="transitions/new" element={<NewTransition />} /><Route path="transitions/payment-service" element={<TransitionPlan />} /><Route path="transitions/payment-service/check" element={<KnowledgeCheck />} /><Route path="transitions/payment-service/complete" element={<Complete />} /><Route path="my-knowledge" element={<MyKnowledge />} /><Route path="my-knowledge/pending-validation" element={<KnowledgeGaps />} /><Route path="my-knowledge/records" element={<Records />} /><Route path="my-transition" element={<MyTransition />} /><Route path="my-transition/knowledge-areas" element={<KnowledgeAreas />} /><Route path="my-transition/check" element={<KnowledgeCheck />} /><Route path="organization" element={<Organization />} /><Route path="teams" element={<Teams />} /><Route path="roles" element={<Roles />} /><Route path="integrations" element={<Integrations />} /><Route path="data-sync" element={<DataSync />} /><Route path="security" element={<Security />} /><Route path="audit-log" element={<AuditLog />} /><Route path="settings" element={<SettingsPage />} /><Route path="*" element={<HomeRedirect />} /></Routes>
}
function PermissionState() { const navigate = useNavigate(); return <div className="permission-state"><Shield size={28} /><h1>You don't have access to this area.</h1><p>Your current demo role has a different workspace view.</p><button className="primary" onClick={() => navigate('/app')}>Back to my workspace <ArrowRight size={16} /></button></div> }

function Page({ eyebrow, title, subtitle, action, children }: { eyebrow?: string; title: string; subtitle?: string; action?: React.ReactNode; children: React.ReactNode }) { return <><div className="page-heading"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>{action}</div>{children}</> }
function Badge({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: string }) { return <span className={`badge ${tone}`}>{children}</span> }
function Stat({ label, value, detail, tone }: { label: string; value: string; detail: string; tone?: string }) { return <div className="stat"><span>{label}</span><strong>{value}</strong><small className={tone}>{detail}</small></div> }
function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) { return <section className="section"><div className="section-title"><h2>{title}</h2>{action}</div>{children}</section> }

function Overview() { const navigate = useNavigate(); const { lastSync } = useAtlas(); return <Page eyebrow="FINPAY / ENGINEERING" title="Engineering Overview" subtitle={`Last synced ${lastSync}`} action={<button className="primary" onClick={() => navigate('/app/transitions/new')}>Start transition <ArrowRight size={16} /></button>}><div className="stats-grid"><Stat label="Continuity status" value="78%" detail="Healthy" tone="healthy" /><Stat label="High-risk areas" value="3" detail="Needs attention" tone="critical" /><Stat label="Knowledge gaps" value="12" detail="3 critical" tone="attention" /><Stat label="Active transitions" value="1" detail="In progress" /></div><div className="dashboard-grid"><Section title="Engineering knowledge risk"><div className="risk-list">{[['Payment Service','HIGH','critical',92],['Identity Service','MEDIUM','attention',67],['Order Service','MEDIUM','attention',54],['Notification Service','LOW','healthy',29],['Analytics','LOW','healthy',20]].map(([name, level, tone, width]) => <button className="risk-row" key={name as string} onClick={() => name === 'Payment Service' && navigate('/app/risk-areas/payment-service')}><span><strong>{name}</strong><Badge tone={tone as string}>{level}</Badge></span><span className="bar"><i style={{ width: `${width}%` }} /></span></button>)}</div></Section><Section title="Attention needed"><div className="attention-list"><button onClick={() => navigate('/app/risk-areas/payment-service')}><CircleAlert size={18} /><span><strong>Payment Service</strong><small>High knowledge concentration · 3 gaps</small></span><ArrowRight size={16} /></button><button onClick={() => navigate('/app/risk-areas/payment-service')}><FileText size={18} /><span><strong>Identity Service</strong><small>Documentation appears outdated</small></span><ArrowRight size={16} /></button><button onClick={() => navigate('/app/risk-areas/payment-service')}><Users size={18} /><span><strong>Order Service</strong><small>Limited backup contributors</small></span><ArrowRight size={16} /></button></div></Section></div></Page> }

function GitHubEvidencePage() {
  const { refreshGaps } = useAtlas()
  const navigate = useNavigate()
  const [repositories, setRepositories] = useState<GitHubRepository[]>([])
  const [pullRequests, setPullRequests] = useState<GitHubPullRequest[]>([])
  const [selectedRepository, setSelectedRepository] = useState<GitHubRepository | null>(null)
  const [selectedPullRequest, setSelectedPullRequest] = useState<GitHubPullRequest | null>(null)
  const [evidence, setEvidence] = useState<GitHubEvidence | null>(null)
  const [analysis, setAnalysis] = useState<GitHubAnalysis | null>(null)
  const [loading, setLoading] = useState('repositories')
  const [error, setError] = useState('')
  const [refreshCount, setRefreshCount] = useState(0)

  async function refreshRepositories() {
    setLoading('repositories')
    setError('')
    setSelectedRepository(null)
    setSelectedPullRequest(null)
    setEvidence(null)
    setAnalysis(null)
    try {
      setRepositories(await getGitHubRepositories())
      setRefreshCount(count => count + 1)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to retrieve GitHub repositories.')
    } finally {
      setLoading('')
    }
  }

  useEffect(() => { void refreshRepositories() }, [])

  async function chooseRepository(repository: GitHubRepository) {
    setSelectedRepository(repository)
    setSelectedPullRequest(null)
    setEvidence(null)
    setAnalysis(null)
    setLoading('pull-requests')
    setError('')
    try {
      setPullRequests(await getGitHubPullRequests(repository.id))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to retrieve pull requests.')
    } finally {
      setLoading('')
    }
  }

  async function choosePullRequest(pullRequest: GitHubPullRequest) {
    if (!selectedRepository) return
    setSelectedPullRequest(pullRequest)
    setEvidence(null)
    setAnalysis(null)
    setLoading('evidence')
    setError('')
    try {
      setEvidence(await getGitHubPullRequestEvidence(selectedRepository.id, pullRequest.number))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to retrieve pull request evidence.')
    } finally {
      setLoading('')
    }
  }

  async function analyzeSelectedPullRequest() {
    if (!selectedRepository || !selectedPullRequest) return
    setLoading('analysis')
    setError('')
    setAnalysis(null)
    try {
      const result = await analyzeGitHubPullRequest(selectedRepository.id, selectedPullRequest.number)
      setAnalysis(result)
      await refreshGaps()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'GitHub evidence analysis failed.')
    } finally {
      setLoading('')
    }
  }

  return <Page eyebrow="LIVE SOURCE DATA" title="GitHub Engineering Evidence" subtitle="Repositories, pull requests, changed files, and Claude analysis retrieved by the backend." action={<button className="secondary" onClick={refreshRepositories} disabled={loading !== ''}><RefreshCw size={15} /> Refresh from GitHub</button>}>
    {error && <p className="error-text" role="alert">{error}</p>}
    <div className="github-evidence-layout">
      <section className="github-source-column">
        <Section title={`Repositories${repositories.length ? ` · ${repositories.length}` : ''}`}>
          {loading === 'repositories' ? <p>Retrieving repositories from GitHub...</p> : repositories.length === 0 ? <p>No repositories returned by the configured GitHub account.</p> : <div className="github-repository-list">{repositories.map(repository => <button className={`github-repository-row ${selectedRepository?.id === repository.id ? 'selected' : ''}`} key={repository.id} onClick={() => chooseRepository(repository)}>
            <span><strong>{repository.full_name}</strong><small>{repository.language ?? 'Language not reported'} · Updated {repository.updated_at ? new Date(repository.updated_at).toLocaleDateString() : 'date unavailable'}</small></span><ExternalLink size={15} />
          </button>)}</div>}
        </Section>
        {selectedRepository && <Section title={`Pull requests · ${selectedRepository.full_name}`}>
          {loading === 'pull-requests' ? <p>Retrieving pull requests from GitHub...</p> : pullRequests.length === 0 ? <p>No pull requests were returned for this repository.</p> : <div className="github-pr-list">{pullRequests.map(pullRequest => <button className={`github-pr-row ${selectedPullRequest?.number === pullRequest.number ? 'selected' : ''}`} key={pullRequest.number} onClick={() => choosePullRequest(pullRequest)}>
            <GitPullRequest size={16} /><span><strong>#{pullRequest.number} {pullRequest.title}</strong><small>{pullRequest.author ?? 'Author unavailable'} · {pullRequest.merged ? 'Merged' : pullRequest.state} · {pullRequest.changed_files} files · {pullRequest.commits} commits</small></span>
          </button>)}</div>}
        </Section>}
      </section>

      <section className="github-detail-column">
        {!selectedPullRequest && <div className="github-empty-state"><GitBranch size={22} /><h2>Select a pull request</h2><p>Repository and pull request lists above come directly from the configured GitHub source.</p></div>}
        {selectedPullRequest && <>
          <Section title={`PR #${selectedPullRequest.number}`} action={<a className="quiet" href={selectedPullRequest.html_url} target="_blank" rel="noreferrer">Open on GitHub <ExternalLink size={14} /></a>}>
            <h2 className="github-pr-title">{selectedPullRequest.title}</h2>
            <p>{selectedPullRequest.body || 'No pull request description was supplied by GitHub.'}</p>
            <div className="github-metadata"><span>Author <strong>{selectedPullRequest.author ?? 'Unavailable'}</strong></span><span>Status <strong>{selectedPullRequest.merged ? 'Merged' : selectedPullRequest.state}</strong></span><span>Changed files <strong>{selectedPullRequest.changed_files}</strong></span><span>Commits <strong>{selectedPullRequest.commits}</strong></span><span>+{selectedPullRequest.additions} / -{selectedPullRequest.deletions}</span></div>
          </Section>
          {loading === 'evidence' && <p>Retrieving actual files, patches, reviews, commits, and related repository signals from GitHub...</p>}
          {evidence && <>
            <Section title="ATLAS evidence">
              <div className="evidence-facts"><div><span>Repository</span><strong>{evidence.repository.full_name}</strong></div><div><span>Pull request</span><strong>#{evidence.pull_request.number} · {evidence.pull_request.title}</strong></div><div><span>Source evidence IDs</span><strong>{evidence.files.length} changed files · {evidence.reviews.length} reviews · {evidence.commits.length} commits</strong></div><div><span>Related Jira</span><strong>Not connected; no Jira evidence supplied</strong></div></div>
            </Section>
            <Section title={`Changed files · ${evidence.files.length}`}>
              {evidence.files.length === 0 ? <p>GitHub returned no changed files for this pull request.</p> : <div className="github-files">{evidence.files.map(file => <details className="github-file" key={file.filename}>
                <summary><code>{file.filename}</code><span>{file.status} · +{file.additions} / -{file.deletions}</span></summary>
                {file.patch_available && file.patch ? <><pre>{file.patch}</pre>{file.patch_truncated && <small>Patch display capped at 6,000 characters; the API indicated additional patch content.</small>}</> : <p>GitHub did not provide a patch for this file. <a href={file.blob_url ?? undefined} target="_blank" rel="noreferrer">Open file on GitHub</a></p>}
              </details>)}</div>}
            </Section>
            <Section title="Deterministic ATLAS signals">
              <p className="muted">Calculated from GitHub account and PR metadata. These are source-specific indicators, not employee competence scores.</p>
              <div className="signal-grid">{Object.entries(evidence.signals).map(([key, value]) => <div className="signal-item" key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{typeof value === 'object' && value !== null && 'status' in value ? String((value as { status: unknown }).status) : typeof value === 'string' ? value : JSON.stringify(value)}</strong><small>{typeof value === 'object' && value !== null && 'scope' in value ? String((value as { scope: unknown }).scope) : typeof value === 'object' && value !== null && 'source' in value ? String((value as { source: unknown }).source) : ''}</small></div>)}</div>
            </Section>
            {!analysis && <Section title="ATLAS AI Trace"><ol className="ai-trace-list">
              <li className="complete"><span className="ai-trace-marker">✓</span><span><strong>GitHub evidence retrieved</strong><small>Selected PR, {evidence.files.length} files, {evidence.reviews.length} reviews, and {evidence.commits.length} commits from GitHub.</small></span></li>
              <li className="complete"><span className="ai-trace-marker">✓</span><span><strong>Deterministic signals calculated</strong><small>Signals use the source-specific scopes shown above; unconnected sources remain unavailable.</small></span></li>
              <li className="complete"><span className="ai-trace-marker">✓</span><span><strong>Bounded AI context built</strong><small>Backend confirmed {evidence.ai_context_record_count} evidence records; context excludes full-repository contents.</small></span></li>
              <li className={loading === 'analysis' ? 'active' : 'pending'}><span className="ai-trace-marker">{loading === 'analysis' ? '●' : '○'}</span><span><strong>{loading === 'analysis' ? 'Backend analysis request in progress' : 'Claude analysis not started'}</strong><small>{loading === 'analysis' ? 'FastAPI is re-fetching evidence, invoking Agent Router, validating citations, and persisting a supported finding.' : 'Click Analyze with Claude to start the real backend workflow.'}</small></span></li>
              <li className="pending"><span className="ai-trace-marker">○</span><span><strong>Validate structured response and citations</strong><small>Awaiting backend response.</small></span></li>
              <li className="pending"><span className="ai-trace-marker">○</span><span><strong>Persist potential gap</strong><small>A row is created only if validated Claude output reports a potential gap.</small></span></li>
            </ol></Section>}
            <div className="github-analysis-action"><button className="primary" disabled={loading !== ''} onClick={analyzeSelectedPullRequest}>{loading === 'analysis' ? 'Retrieving evidence and analyzing...' : 'Analyze with Claude'} <ArrowRight size={16} /></button><p>FastAPI re-fetches the selected PR and files, builds bounded evidence context, routes to Claude, validates citations, then persists a positive potential gap.</p></div>
          </>}
          {analysis && <>
            <Section title="ATLAS AI Trace">
              <div className="ai-trace-meta"><span>Provider <strong>{analysis.provider}</strong></span><span>Model <strong>{analysis.model}</strong></span><span>Task <strong>{analysis.task}</strong></span><span>Input records <strong>{analysis.input_record_count}</strong></span></div>
              <ol className="ai-trace-list">{analysis.stages.map(stage => <li className={stage.status} key={stage.id}><span className="ai-trace-marker">{stage.status === 'complete' ? '✓' : '–'}</span><span><strong>{stage.label}</strong><small>{stage.detail}</small></span></li>)}</ol>
            </Section>
            <Section title="Claude structured result">
              <div className="ai-result-card"><div className="card-meta"><Badge tone={analysis.analysis.potential_gap ? 'attention' : 'neutral'}>{analysis.analysis.potential_gap ? 'Potential knowledge gap' : 'No potential gap supported'}</Badge><span>Confidence {Math.round(analysis.analysis.confidence * 100)}%</span></div><h2>{analysis.analysis.title}</h2><p>{analysis.analysis.summary}</p><p><strong>Why it matters:</strong> {analysis.analysis.reason}</p><div className="generated-question"><span className="eyebrow">TARGETED QUESTION</span><p>{analysis.analysis.targeted_question}</p></div><small>Verified evidence IDs: {analysis.evidence_ids.join(', ')}</small>{analysis.persisted ? <p className="success-text">Persisted knowledge gap: {analysis.knowledge_gap_id}</p> : <p>No knowledge gap row was created because Claude did not identify a supported potential gap.</p>}{analysis.persisted && <button className="secondary" onClick={() => navigate('/app/knowledge-gaps')}>Open Knowledge Gaps <ArrowRight size={15} /></button>}</div>
            </Section>
          </>}
        </>}
      </section>
    </div>
  </Page>
}

function KnowledgeMap() { const navigate = useNavigate(); const [filter, setFilter] = useState('Services'); return <Page eyebrow="KNOWLEDGE" title="Knowledge Map" subtitle="A focused view of the people, systems, and teams behind critical work."><div className="toolbar"><div className="segmented">{['Services','People','Repositories','Teams'].map(item => <button className={filter === item ? 'selected' : ''} onClick={() => setFilter(item)} key={item}>{item}</button>)}</div><button className="secondary" onClick={() => navigate('/app/github-evidence')}><GitBranch size={15} /> Engineering Evidence</button></div><div className="map-layout"><div className="map-canvas"><div className="map-header"><span className="eyebrow">{filter.toUpperCase()}</span><span>5 entities connected</span></div>{['Payment Service','Identity API','Order Service','Refund Engine','Notification Service'].map((item, index) => <button className={`map-node node-${index + 1}`} onClick={() => item === 'Payment Service' && navigate('/app/risk-areas/payment-service')} key={item}><span className="node-dot" /><strong>{item}</strong><small>{index === 0 ? 'High continuity risk' : 'Connected service'}</small></button>)}</div><div className="map-detail"><span className="eyebrow">SELECTED SERVICE</span><h2>Payment Service</h2><Badge tone="critical">HIGH RISK</Badge><div className="mini-metrics"><span><strong>68%</strong><small>Arun Kumar</small></span><span><strong>62%</strong><small>Documented</small></span><span><strong>LOW</strong><small>Backup coverage</small></span></div><button className="primary" onClick={() => navigate('/app/risk-areas/payment-service')}>View risk area <ArrowRight size={15} /></button></div></div></Page> }

function RiskArea() { const navigate = useNavigate(); return <Page eyebrow="RISK AREA / PAYMENT SERVICE" title="Payment Service" subtitle="Potential continuity risk" action={<Badge tone="critical">HIGH</Badge>}><div className="stats-grid three"><Stat label="Critical changes associated with Arun" value="68%" detail="Concentration" tone="critical" /><Stat label="Critical reviews associated with Arun" value="74%" detail="Review concentration" tone="attention" /><Stat label="Active contributors" value="3" detail="4 potential gaps" /></div><div className="two-col"><Section title="Contributor distribution"><div className="distribution"><div><span>Arun Kumar <b>68%</b></span><i><em style={{ width: '68%' }} /></i></div><div><span>Priya Sharma <b>18%</b></span><i><em style={{ width: '18%' }} /></i></div><div><span>Others <b>14%</b></span><i><em style={{ width: '14%' }} /></i></div></div></Section><Section title="Knowledge evidence coverage"><div className="distribution"><div><span>Documented <b>62%</b></span><i><em className="healthy-fill" style={{ width: '62%' }} /></i></div><div><span>Partially known <b>23%</b></span><i><em className="attention-fill" style={{ width: '23%' }} /></i></div><div><span>Uncaptured <b>15%</b></span><i><em className="critical-fill" style={{ width: '15%' }} /></i></div></div></Section></div><Section title="Evidence"><div className="evidence-list">{[['18','critical PRs'],['74%','reviewed by one contributor'],['6','related production incidents'],['4','decisions lack supporting rationale'],['Limited','secondary contributors']].map(([value, label]) => <button key={label} onClick={() => label.includes('rationale') && navigate('/app/knowledge-gaps')}><strong>{value}</strong><span>{label}</span><ArrowRight size={15} /></button>)}</div></Section></Page> }

function KnowledgeGaps() {
  const { gaps, user } = useAtlas()
  const navigate = useNavigate()
  const [busyGap, setBusyGap] = useState('')
  const [error, setError] = useState('')
  const [questions, setQuestions] = useState<{ gapId: string; result: ApiGapQuestions } | null>(null)
  const [analysisByGap, setAnalysisByGap] = useState<Record<string, NonNullable<import('./api').ApiGap['ai_analysis']>>>({})

  async function analyze(id: string) {
    setBusyGap(id)
    setError('')
    try {
      const result = await analyzeKnowledgeGap(id)
      setAnalysisByGap(current => ({ ...current, [id]: result.analysis }))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'AI analysis failed.')
    } finally {
      setBusyGap('')
    }
  }

  async function askQuestions(id: string) {
    setBusyGap(id)
    setError('')
    try {
      setQuestions({ gapId: id, result: await generateGapQuestions(id) })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Question generation failed.')
    } finally {
      setBusyGap('')
    }
  }

  return <Page eyebrow="KNOWLEDGE" title="Knowledge Gaps" subtitle="Potential gaps must be grounded in connected source evidence.">
    <div className="toolbar"><div className="segmented"><button className="selected">All <span>{gaps.length}</span></button><button>Open</button><button>Validated</button></div></div>
    {error && <p className="error-text" role="alert">{error}</p>}
    {gaps.length === 0 ? <p>No knowledge gaps are available from the backend.</p> : <div className="gap-list">{gaps.map(gap => { const analysis = analysisByGap[gap.id] ?? gap.ai_analysis; return <article className="gap-card" key={gap.id}>
      <div><div className="card-meta"><Badge tone={gap.status === 'Validated' ? 'healthy' : 'attention'}>{gap.status}</Badge><span>{gap.service}</span></div><h2>{gap.title}</h2><p>{gap.description}</p><small>{gap.ref}</small>
        {analysis && <div className="proposed"><div className="card-meta"><Badge tone={analysis.potential_gap ? 'attention' : 'neutral'}>{analysis.potential_gap ? 'Potential gap' : 'No gap supported'}</Badge><span>Claude · confidence {Math.round(analysis.confidence * 100)}%</span></div><h3>{analysis.title}</h3><p>{analysis.summary}</p><p><strong>Question:</strong> {analysis.targeted_question}</p><small>Evidence: {analysis.evidence_ids.join(', ')}</small></div>}
        {questions?.gapId === gap.id && <div className="proposed"><h3>Targeted questions</h3>{questions.result.questions.map((item, index) => <div key={`${item.question}-${index}`}><p>{item.question}</p><small>{item.rationale} · Evidence: {item.evidence_ids.join(', ')}</small></div>)}</div>}
      </div>
      <div className="proposal-actions">{user?.role === 'manager' && <button className="secondary" disabled={!!busyGap} onClick={() => analyze(gap.id)}>{busyGap === gap.id ? 'Analyzing...' : 'Analyze with AI'}</button>}{(user?.role === 'manager' || user?.role === 'holder') && <button className="secondary" disabled={!!busyGap} onClick={() => askQuestions(gap.id)}>{busyGap === gap.id ? 'Generating...' : 'Generate questions'}</button>}<button className="secondary" onClick={() => navigate(`/app/knowledge/capture/${gap.id}`)}>{gap.status === 'Validated' ? 'View record' : 'Capture'} <ArrowRight size={15} /></button></div>
    </article>})}</div>}
  </Page>
}

function Capture() {
  const { id = '' } = useParams()
  const { gaps, validateGap, reviewKnowledge, user } = useAtlas()
  const gap = gaps.find(item => item.id === id)
  const [answer, setAnswer] = useState('')
  const [records, setRecords] = useState<ApiKnowledgeRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [structuring, setStructuring] = useState(false)
  const [error, setError] = useState('')

  async function refreshRecords() {
    setRecords(await getKnowledgeRecords(id))
  }

  useEffect(() => {
    let active = true
    getKnowledgeRecords(id).then(items => { if (active) setRecords(items) }).catch(reason => { if (active) setError(String(reason)) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [id])

  async function submitAnswer() {
    setSaving(true)
    setError('')
    try {
      await validateGap(id, answer)
      await refreshRecords()
      setAnswer('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to submit knowledge.')
    } finally {
      setSaving(false)
    }
  }

  async function review(recordId: number, decision: 'approve' | 'reject' | 'request_clarification') {
    setSaving(true)
    setError('')
    try {
      await reviewKnowledge(id, recordId, decision)
      await refreshRecords()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to review this proposal.')
    } finally {
      setSaving(false)
    }
  }

  async function structureAnswer() {
    setStructuring(true)
    setError('')
    try {
      await structureKnowledgeAnswer(id, `What context should the next engineer understand about ${gap?.title ?? 'this change'}?`, answer)
      await refreshRecords()
      setAnswer('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to structure this answer.')
    } finally {
      setStructuring(false)
    }
  }

  if (!gap) return <Page eyebrow="KNOWLEDGE CAPTURE" title="Knowledge gap unavailable" subtitle="The gap could not be loaded from the API."><p>Return to Knowledge Gaps and try again after the list loads.</p></Page>
  return <Page eyebrow="KNOWLEDGE CAPTURE" title="Capture knowledge" subtitle={`${gap.service} / ${gap.title}`}>
    <div className="capture-layout">
      <div className="capture-main">
        <div className="notice"><CircleAlert size={18} /><span>No supporting evidence is linked to this gap. Submitted context remains a proposal until a manager reviews it.</span></div>
        <div className="question-block"><span className="eyebrow">TARGETED QUESTION</span><h2>What context should the next engineer understand about {gap.title.toLowerCase()}?</h2><textarea value={answer} onChange={event => setAnswer(event.target.value)} placeholder="Share the technical reasoning, constraints, and trade-offs..." /></div>
        {error && <p className="error-text" role="alert">{error}</p>}
        <div className="proposal-actions"><button className="primary" onClick={submitAnswer} disabled={!answer.trim() || saving || structuring}>{saving ? 'Submitting...' : 'Submit answer'} <ArrowRight size={16} /></button><button className="secondary" onClick={structureAnswer} disabled={!answer.trim() || saving || structuring}>{structuring ? 'Structuring...' : 'Structure with AI'}</button></div>
        <Section title="Submitted knowledge">
          {loading ? <p>Loading submitted knowledge...</p> : records.length === 0 ? <p>No answers have been submitted for this gap.</p> : records.map(record => <article className="proposed" key={record.id}>
            <div className="card-meta"><Badge tone={record.status === 'validated' ? 'healthy' : record.status === 'proposed' ? 'info' : 'attention'}>{record.status.replace('_', ' ')}</Badge><span>{record.submitted_by ? `Submitted by ${record.submitted_by}` : 'Submitter unavailable'}</span></div>
            <h3>{record.decision}</h3><p>{record.reason}</p>
            {record.status === 'validated' && <small>Validated by {record.validated_by ?? 'manager'}</small>}
            {user?.role === 'manager' && record.status === 'proposed' && <div className="proposal-actions"><button className="primary" disabled={saving} onClick={() => review(record.id, 'approve')}>Approve <Check size={15} /></button><button className="secondary" disabled={saving} onClick={() => review(record.id, 'request_clarification')}>Request clarification</button><button className="secondary" disabled={saving} onClick={() => review(record.id, 'reject')}>Reject</button></div>}
          </article>)}
        </Section>
      </div>
      <aside className="capture-side"><span className="eyebrow">EVIDENCE</span><h3>Source references</h3><p>{gap.ref}</p><small className="muted">Only linked source records are shown here.</small></aside>
    </div>
  </Page>
}

function NewTransition() { const navigate = useNavigate(); const { createTransition } = useAtlas(); return <Page eyebrow="TRANSITIONS" title="Start transition" subtitle="Create a focused transfer plan for a critical system."><div className="form-card"><div className="form-grid"><label>Outgoing engineer<input value="Arun Kumar" readOnly /></label><label>Incoming engineer<input value="Priya Sharma" readOnly /></label><label>System<select defaultValue="Payment Service"><option>Payment Service</option><option>Refund Engine</option></select></label></div><Section title="Knowledge areas"><div className="check-list">{['Payment architecture','Retry mechanism','Gateway behaviour','Refund reconciliation','Deployment'].map((area, index) => <div key={area}><span className={index < 3 ? 'check checked' : 'check'}>{index < 3 && <Check size={13} />}</span><span>{area}</span><Badge tone={index < 3 ? 'healthy' : 'attention'}>{index < 3 ? 'Ready' : 'Needs review'}</Badge></div>)}</div></Section><button className="primary" onClick={() => { createTransition(); navigate('/app/transitions/payment-service') }}>Create transition plan <ArrowRight size={16} /></button></div></Page> }

function TransitionPlan() { const { areas } = useAtlas(); const navigate = useNavigate(); const percent = progress(areas); return <Page eyebrow="ACTIVE TRANSITION" title="Payment Service" subtitle="Arun Kumar → Priya Sharma" action={<Badge tone={percent === 100 ? 'healthy' : 'info'}>{percent}% complete</Badge>}><div className="progress-card"><div className="progress-label"><span>Knowledge transfer progress</span><strong>{percent}%</strong></div><div className="progress-track"><i style={{ width: `${percent}%` }} /></div></div><Section title="Knowledge areas"><div className="area-list">{areas.map(area => <button className="area-row" key={area.name} onClick={() => area.status === 'Needs review' && navigate('/app/transitions/payment-service/check')}><span><span className={area.status === 'Verified' ? 'check checked' : 'check'}>{area.status === 'Verified' && <Check size={13} />}</span><strong>{area.name}</strong></span><Badge tone={area.status === 'Verified' ? 'healthy' : 'attention'}>{area.status}</Badge></button>)}</div></Section><div className="page-actions"><button className="primary" onClick={() => navigate('/app/transitions/payment-service/check')}>Continue knowledge check <ArrowRight size={16} /></button></div></Page> }

function KnowledgeCheck() { const { areas, verifyArea } = useAtlas(); const navigate = useNavigate(); const [answer, setAnswer] = useState(''); const target = areas.find(area => area.status === 'Needs review')?.name ?? 'Gateway behaviour'; return <Page eyebrow="KNOWLEDGE CHECK" title="Verify understanding" subtitle="Payment Service · Question 1 of 4"><div className="check-card"><span className="eyebrow">{target.toUpperCase()}</span><h2>Why is the retry limit set to three?</h2><textarea value={answer} onChange={event => setAnswer(event.target.value)} placeholder="Explain the decision in your own words..." /><button className="primary" disabled={!answer.trim()} onClick={() => { verifyArea(target); navigate('/app/transitions/payment-service') }}>Submit answer <ArrowRight size={16} /></button></div></Page> }

function Complete() { const navigate = useNavigate(); return <Page eyebrow="TRANSITIONS" title="Knowledge transfer complete" subtitle="Payment Service · Arun Kumar → Priya Sharma"><div className="complete-card"><div className="complete-icon"><Check size={26} /></div><h2>Ownership can move forward.</h2><p>The critical knowledge areas have been verified and the transfer record is ready.</p><div className="stats-grid three"><Stat label="Critical areas verified" value="4 / 4" detail="Complete" tone="healthy" /><Stat label="Knowledge captured" value="5 / 5" detail="Complete" tone="healthy" /><Stat label="Remaining gaps" value="0" detail="Clear" tone="healthy" /></div><button className="primary" onClick={() => navigate('/app/my-knowledge/records')}>View knowledge record <ArrowRight size={16} /></button></div></Page> }

function MyKnowledge() { const navigate = useNavigate(); const { gaps } = useAtlas(); return <Page eyebrow="MY WORK" title="My Knowledge" subtitle="Technical context that needs your explanation or validation."><div className="stats-grid three"><Stat label="Assigned knowledge gaps" value="2" detail="Open" tone="attention" /><Stat label="Pending validation" value="1" detail="Needs your review" tone="critical" /><Stat label="Active transitions" value="1" detail="In progress" /></div><Section title="Assigned knowledge gaps"><div className="gap-list compact">{gaps.slice(0, 2).map(gap => <article className="gap-card" key={gap.id}><div><h2>{gap.title}</h2><p>{gap.description}</p></div><button className="secondary" onClick={() => navigate(`/app/knowledge/capture/${gap.id}`)}>Capture <ArrowRight size={15} /></button></article>)}</div></Section><Section title="Recent records"><div className="record-row"><FileText size={18} /><span><strong>Payment architecture</strong><small>Validated 2 days ago</small></span><Badge tone="healthy">Validated</Badge></div></Section></Page> }
function MyTransition() { const { areas } = useAtlas(); const navigate = useNavigate(); return <TransitionPreview title="My Transition" action={() => navigate('/app/my-transition/knowledge-areas')} areas={areas} /> }
function TransitionPreview({ title, action, areas }: { title: string; action: () => void; areas: TransitionArea[] }) { return <Page eyebrow="MY TRANSITION" title={title} subtitle="Payment Service · Arun Kumar → Priya Sharma"><div className="progress-card"><div className="progress-label"><span>Transfer progress</span><strong>{progress(areas)}</strong></div><div className="progress-track"><i style={{ width: `${progress(areas)}%` }} /></div></div><Section title="Knowledge areas"><div className="area-list">{areas.map(area => <div className="area-row" key={area.name}><span><span className={area.status === 'Verified' ? 'check checked' : 'check'}>{area.status === 'Verified' && <Check size={13} />}</span><strong>{area.name}</strong></span><Badge tone={area.status === 'Verified' ? 'healthy' : 'attention'}>{area.status}</Badge></div>)}</div></Section><button className="primary" onClick={action}>Continue transition <ArrowRight size={16} /></button></Page> }
function KnowledgeAreas() { const navigate = useNavigate(); return <Page eyebrow="KNOWLEDGE" title="Knowledge areas" subtitle="Select an area to review the evidence and verify your understanding."><div className="area-list">{['Payment architecture','Retry mechanism','Gateway behaviour','Refund reconciliation','Deployment'].map((area, index) => <button className="area-row" key={area} onClick={() => index > 1 && navigate('/app/my-transition/check')}><span><strong>{area}</strong><small>{index > 1 ? 'Validated knowledge needs review' : 'Supporting evidence available'}</small></span><Badge tone={index > 1 ? 'attention' : 'healthy'}>{index > 1 ? 'Needs review' : 'Verified'}</Badge></button>)}</div></Page> }

function AdminPage({ title, eyebrow, children }: { title: string; eyebrow: string; children: React.ReactNode }) { return <Page eyebrow={eyebrow} title={title} subtitle="FinPay / Engineering · Demo workspace">{children}</Page> }
function Organization() { return <AdminPage eyebrow="ADMINISTRATION" title="Organization"><div className="stats-grid"><Stat label="Engineers" value="64" detail="5 teams" /><Stat label="Services" value="18" detail="3 high risk" tone="critical" /><Stat label="Knowledge gaps" value="12" detail="3 critical" tone="attention" /><Stat label="Active transition" value="1" detail="In progress" /></div><div className="two-col"><Section title="Connected sources"><div className="integration-list"><div><GitBranch size={17} /><span>GitHub<small>Connected · 12 repositories</small></span><Badge tone="healthy">Connected</Badge></div><div><FileText size={17} /><span>Jira<small>Connected · 3 projects</small></span><Badge tone="healthy">Connected</Badge></div><div><BookOpen size={17} /><span>Confluence<small>Documentation source</small></span><Badge>Not connected</Badge></div></div></Section><Section title="Workspace health"><div className="health-list"><p><span className="status-dot healthy-dot" />Data sync <strong>Healthy</strong></p><p><span className="status-dot healthy-dot" />Permissions <strong>Configured</strong></p><p><span className="status-dot healthy-dot" />Audit logging <strong>Active</strong></p></div></Section></div></AdminPage> }
function Teams() { return <AdminPage eyebrow="PEOPLE" title="Teams & Members"><div className="table"><div className="table-head"><span>Team</span><span>Engineers</span><span>Lead</span></div>{[['Payments','16','Arun Kumar'],['Identity','12','Rahul Menon'],['Orders','14','Sneha Iyer'],['Infrastructure','10','Vikram Rao'],['Platform','12','Priya Sharma']].map(row => <div className="table-row" key={row[0]}><strong>{row[0]}</strong><span>{row[1]} engineers</span><span>{row[2]}</span></div>)}</div></AdminPage> }
function Roles() { return <AdminPage eyebrow="PEOPLE" title="Roles & Permissions"><div className="table permission"><div className="table-head"><span>Role</span><span>View</span><span>Create</span><span>Manage</span></div>{['Engineering Manager','Knowledge Holder','Incoming Engineer','Admin / CTO'].map((role, index) => <div className="table-row" key={role}><strong>{role}</strong><span><Check size={15} /></span><span>{index === 1 ? '—' : <Check size={15} />}</span><span>{index === 3 ? <Check size={15} /> : '—'}</span></div>)}</div></AdminPage> }
function Integrations() { return <AdminPage eyebrow="DATA" title="Integrations"><div className="integration-list large">{[['GitHub','12 repositories','Connected'],['Jira','3 projects','Connected'],['Confluence','Documentation','Not connected'],['Notion','Knowledge source','Not connected']].map(([name, detail, status]) => <div key={name}><div className="integration-icon"><GitBranch size={18} /></div><span><strong>{name}</strong><small>{detail}</small></span><Badge tone={status === 'Connected' ? 'healthy' : 'neutral'}>{status}</Badge><button className="secondary">{status === 'Connected' ? 'Manage' : 'Connect'}</button></div>)}</div></AdminPage> }
function DataSync() { const { sync, syncing, lastSync } = useAtlas(); return <AdminPage eyebrow="DATA" title="Data & Sync"><div className="sync-card"><div><span className="eyebrow">SYNC STATUS</span><h2>{syncing ? 'Syncing GitHub...' : 'Healthy'}</h2><p>Last GitHub sync: {lastSync} · Last Jira sync: 12 min ago</p></div><button className="primary" onClick={sync} disabled={syncing}>{syncing ? 'Working...' : 'Sync now'} <Zap size={15} /></button></div><div className="stats-grid three"><Stat label="Repositories" value="12" detail="GitHub" /><Stat label="Pull requests" value="1,842" detail="Indexed" /><Stat label="Contributors" value="214" detail="Across workspace" /></div><Section title="Latest sync"><div className="sync-results"><p><Check size={15} /> 12 repositories</p><p><Check size={15} /> 1,842 pull requests</p><p><Check size={15} /> 8,421 commits</p><p><Check size={15} /> 214 contributors</p></div></Section></AdminPage> }
function Security() { return <AdminPage eyebrow="SECURITY" title="Security"><div className="security-list">{[['Authentication','Configured','Demo session authentication is enabled.'],['Access control','Configured','Roles and workspace permissions are active.'],['Audit log','Active','Important actions create traceable events.'],['Data retention','90 days','Workspace retention policy.']].map(item => <div key={item[0]}><span><strong>{item[0]}</strong><small>{item[2]}</small></span><Badge tone={item[1] === 'Active' || item[1] === 'Configured' ? 'healthy' : 'info'}>{item[1]}</Badge></div>)}</div></AdminPage> }
function AuditLog() { return <AdminPage eyebrow="SECURITY" title="Audit log"><div className="table audit"><div className="table-head"><span>Timestamp</span><span>User</span><span>Action</span><span>Status</span></div>{[['10:42 AM','Arun Kumar','Validated knowledge'],['10:31 AM','Engineering Manager','Created transition'],['9:58 AM','Admin / CTO','Updated integration'],['Yesterday','Priya Sharma','Completed knowledge check']].map(row => <div className="table-row" key={row[0]}><span>{row[0]}</span><strong>{row[1]}</strong><span>{row[2]}</span><Badge tone="healthy">Success</Badge></div>)}</div></AdminPage> }
function SettingsPage() { return <AdminPage eyebrow="WORKSPACE" title="Settings"><div className="settings-list">{['Workspace','Members','Roles','Connected sources','Sync settings','Data retention','Permissions','Audit log'].map(item => <button key={item}><span>{item}</span><ArrowRight size={16} /></button>)}</div></AdminPage> }
function Records() { return <Page eyebrow="RECORDS" title="Knowledge records" subtitle="Validated technical context for the organization."><div className="record-list"><div className="record-row"><FileText size={18} /><span><strong>Payment architecture</strong><small>Payment Service · Validated 2 days ago</small></span><Badge tone="healthy">Validated</Badge></div><div className="record-row"><FileText size={18} /><span><strong>Retry limit decision</strong><small>Payment Service · Validated today</small></span><Badge tone="healthy">Validated</Badge></div></div></Page> }
