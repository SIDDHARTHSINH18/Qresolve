import Panel from '../components/ui/Panel.jsx'
import StatusDot from '../components/ui/StatusDot.jsx'
import RuntimeStatus from '../components/runtime/RuntimeStatus.jsx'
import ProviderStatus from '../components/runtime/ProviderStatus.jsx'

const DISPLAY = { qiskit: 'Qiskit', cirq: 'Cirq', pennylane: 'PennyLane', openqasm: 'OpenQASM' }

export default function Settings({ fw, session }) {
  return (
    <div className="page page-settings">
      <div className="settings-grid">
        <Panel
          title="QResolve System"
          actions={
            <button type="button" className="btn btn-ghost btn-sm" onClick={fw.refresh}>
              Refresh
            </button>
          }
        >
          <ul className="system-list">
            <li>
              <span>API</span>
              <StatusDot
                state={fw.apiOk ? 'ok' : 'error'}
                label={fw.apiOk ? 'Connected' : 'Disconnected'}
                title={fw.error ? fw.error.message : undefined}
              />
            </li>
            <li>
              <span>Service</span>
              <span className="mono">{fw.health ? `${fw.health.service} v${fw.health.version}` : 'Not provided by backend.'}</span>
            </li>
            <li>
              <span>Sandbox</span>
              <StatusDot
                state={fw.apiOk ? ((fw.runtimes || []).some((r) => r.runtime_available) ? 'ok' : 'idle') : 'unknown'}
                label={fw.apiOk ? ((fw.runtimes || []).some((r) => r.runtime_available) ? 'Ready (executing runtimes registered)' : 'No executable runtime') : 'Unknown (API offline)'}
              />
            </li>
            <li>
              <span>Validator</span>
              <StatusDot
                state={fw.apiOk ? ((fw.runtimes || []).some((r) => r.runtime_available) ? 'ok' : 'idle') : 'unknown'}
                label={fw.apiOk ? ((fw.runtimes || []).some((r) => r.runtime_available) ? 'Ready (verifies via sandbox re-execution)' : 'Cannot verify (no runtime)') : 'Unknown (API offline)'}
              />
            </li>
            <li>
              <span>AI Provider</span>
              <ProviderStatus session={session} compact />
            </li>
          </ul>
          {!fw.apiOk && (
            <p className="inline-note note-err" role="alert">
              Unable to reach QResolve backend. Check that the backend is running.
            </p>
          )}
          <p className="help-text">
            No credentials are stored or displayed in the frontend. Provider configuration lives
            exclusively in backend environment variables.
          </p>
        </Panel>

        <RuntimeStatus runtimes={fw.runtimes} availability={fw.availability} />

        <Panel title="Supported frameworks" subtitle="Live capability, never hardcoded">
          <ul className="fw-table" role="list">
            {Object.keys(DISPLAY).map((name) => {
              const rt = fw.availability[name]
              const executable = Boolean(rt && rt.runtime_available)
              return (
                <li key={name} className="fw-row">
                  <strong>{DISPLAY[name]}</strong>
                  {executable
                    ? <StatusDot state="ok" label={`Executable · v${rt.version}`} />
                    : <StatusDot state="idle" label="Analysis only" />}
                </li>
              )
            })}
          </ul>
        </Panel>
      </div>
    </div>
  )
}
