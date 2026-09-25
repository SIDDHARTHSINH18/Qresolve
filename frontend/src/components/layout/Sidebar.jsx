import StatusDot from '../ui/StatusDot.jsx'
import HistoryList from '../history/HistoryList.jsx'

const DISPLAY = { qiskit: 'Qiskit', cirq: 'Cirq', pennylane: 'PennyLane', openqasm: 'OpenQASM' }

export default function Sidebar({
  page, onNavigate, onNewSession, runtimes, frameworkPick, onPickFramework,
  historyEntries, onOpenSession,
}) {
  const availability = {}
  for (const rt of runtimes) availability[rt.name] = rt

  return (
    <nav className="sidebar" aria-label="Workspace navigation">
      <button type="button" className="btn btn-primary sidebar-new" onClick={onNewSession}>
        + New Debug
      </button>

      <div className="sidebar-nav" role="tablist" aria-label="Views">
        <button role="tab" aria-selected={page === 'debugger'} className={page === 'debugger' ? 'nav-btn is-active' : 'nav-btn'} onClick={() => onNavigate('debugger')}>
          Debugger
        </button>
        <button role="tab" aria-selected={page === 'history'} className={page === 'history' ? 'nav-btn is-active' : 'nav-btn'} onClick={() => onNavigate('history')}>
          History
        </button>
        <button role="tab" aria-selected={page === 'system'} className={page === 'system' ? 'nav-btn is-active' : 'nav-btn'} onClick={() => onNavigate('system')}>
          System
        </button>
      </div>

      <section className="sidebar-section" aria-label="Debugging history">
        <h2 className="sidebar-heading">History</h2>
        <HistoryList entries={historyEntries} onOpen={onOpenSession} limit={5} />
      </section>

      <section className="sidebar-section" aria-label="Supported frameworks">
        <h2 className="sidebar-heading">Frameworks</h2>
        <ul className="sidebar-frameworks">
          {Object.keys(DISPLAY).map((name) => {
            const rt = availability[name]
            const executable = Boolean(rt && rt.runtime_available)
            return (
              <li key={name}>
                <button
                  type="button"
                  className={frameworkPick === name ? 'fw-btn is-active' : 'fw-btn'}
                  onClick={() => onPickFramework(name)}
                  aria-pressed={frameworkPick === name}
                >
                  <span className="fw-name">{DISPLAY[name]}</span>
                  {executable
                    ? <StatusDot state="ok" label="Executable" title={rt.version ? `v${rt.version}` : undefined} />
                    : <StatusDot state="idle" label="Analysis only" />}
                </button>
              </li>
            )
          })}
        </ul>
        <p className="help-text">Status source: GET /api/frameworks (backend registry).</p>
      </section>
    </nav>
  )
}
