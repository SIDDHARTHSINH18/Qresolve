import { useCallback, useState } from 'react'
import TopBar from './components/layout/TopBar.jsx'
import Sidebar from './components/layout/Sidebar.jsx'
import StatusBar from './components/layout/StatusBar.jsx'
import ProviderStatus, { deriveProviderEvidence } from './components/runtime/ProviderStatus.jsx'
import Debugger from './pages/Debugger.jsx'
import HistoryPage from './pages/History.jsx'
import Settings from './pages/Settings.jsx'
import { useFrameworks } from './hooks/useFrameworks.js'
import { useHistory } from './hooks/useHistory.js'
import * as api from './api/qresolve.js'

function providerBadge(session) {
  const evidence = deriveProviderEvidence(session)
  if (!evidence) return { state: 'unknown', label: 'Not exercised' }
  if (evidence.kind === 'ai') return { state: 'ok', label: 'AI responded' }
  if (evidence.kind === 'heuristic') return { state: 'warn', label: 'Heuristic mode' }
  return { state: 'idle', label: 'No proposals' }
}

export default function App() {
  const fw = useFrameworks()
  const history = useHistory()

  const [page, setPage] = useState('debugger')
  const [code, setCode] = useState('')
  const [errorText, setErrorText] = useState('')
  const [frameworkPick, setFrameworkPick] = useState('auto')
  const [session, setSession] = useState(null) // { request, response }
  const [solving, setSolving] = useState(false)
  const [solveError, setSolveError] = useState(null)
  const [validateState, setValidateState] = useState(null) // null | 'loading' | {result} | {error}

  const newSession = useCallback(() => {
    setCode('')
    setErrorText('')
    setFrameworkPick('auto')
    setSession(null)
    setSolveError(null)
    setValidateState(null)
    setPage('debugger')
  }, [])

  const focusEditor = useCallback(() => {
    const el = document.getElementById('code-editor')
    if (el) el.focus()
  }, [])

  const loadExample = useCallback((ex) => {
    setCode(ex.code)
    setErrorText(ex.errorText || '')
    setSession(null)
    setSolveError(null)
    setValidateState(null)
    focusEditor()
  }, [focusEditor])

  const handleSolve = useCallback(async () => {
    if (!code.trim() || solving) return
    setSolving(true)
    setSolveError(null)
    setValidateState(null)
    const request = { code, errorText, frameworkPick }
    try {
      const response = await api.solve({ code, errorText, framework: frameworkPick })
      setSession({ request, response })
      history.add({
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        ts: Date.now(),
        request,
        response,
      })
    } catch (error) {
      setSolveError(error)
      setSession(null)
    } finally {
      setSolving(false)
    }
  }, [code, errorText, frameworkPick, solving, history])

  const openSession = useCallback((entry) => {
    if (!entry || !entry.response) return
    setCode(entry.request?.code ?? '')
    setErrorText(entry.request?.errorText ?? '')
    setFrameworkPick(entry.request?.frameworkPick ?? 'auto')
    setSession({ request: entry.request, response: entry.response })
    setSolveError(null)
    setValidateState(null)
    setPage('debugger')
  }, [])

  const applyFix = useCallback((patchedCode) => {
    if (typeof patchedCode === 'string') setCode(patchedCode)
  }, [])

  const handleValidate = useCallback(async () => {
    const fix = session?.response?.fix
    if (!fix) return
    setValidateState('loading')
    try {
      const result = await api.validate({
        code: fix.patched_code,
        framework: session.response.framework?.framework,
      })
      setValidateState({ result })
    } catch (error) {
      setValidateState({ error })
    }
  }, [session])

  const detectedFramework = session?.response?.framework?.framework || null
  const activeFramework = detectedFramework || (frameworkPick !== 'auto' ? frameworkPick : null)
  const activeRuntime = activeFramework ? fw.availability[activeFramework] : null

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-workspace">Skip to workspace</a>
      <TopBar
        frameworkPick={frameworkPick}
        detectedFramework={detectedFramework}
        availability={fw.availability}
        apiOk={fw.apiOk}
        providerNode={<ProviderStatus session={session} compact />}
        onNewSession={newSession}
      />
      <div className="app-body">
        <Sidebar
          page={page}
          onNavigate={setPage}
          onNewSession={newSession}
          runtimes={fw.runtimes}
          frameworkPick={frameworkPick}
          onPickFramework={setFrameworkPick}
          historyEntries={history.entries}
          onOpenSession={openSession}
        />
        <main className="main-workspace" id="main-workspace" tabIndex={-1}>
          {page === 'debugger' && (
            <Debugger
              code={code}
              onCode={setCode}
              errorText={errorText}
              onErrorText={setErrorText}
              frameworkPick={frameworkPick}
              onFramework={setFrameworkPick}
              availability={fw.availability}
              solving={solving}
              solveError={solveError}
              session={session}
              onSolve={handleSolve}
              onValidate={handleValidate}
              validateState={validateState}
              onApplyFix={applyFix}
              onLoadExample={loadExample}
              onStartDebugging={focusEditor}
            />
          )}
          {page === 'history' && (
            <HistoryPage
              entries={history.entries}
              onOpen={openSession}
              onRemove={history.remove}
              onClear={history.clear}
            />
          )}
          {page === 'system' && <Settings fw={fw} session={session} />}
        </main>
      </div>
      <StatusBar
        frameworkLabel={activeFramework ? activeFramework[0].toUpperCase() + activeFramework.slice(1) : 'No framework'}
        frameworkVersion={activeRuntime?.version || null}
        apiOk={fw.apiOk}
        runtimes={fw.runtimes}
        providerState={providerBadge(session)}
      />
    </div>
  )
}
