import Panel from '../ui/Panel.jsx'
import StatusDot from '../ui/StatusDot.jsx'

const DISPLAY = { qiskit: 'Qiskit', cirq: 'Cirq', pennylane: 'PennyLane', openqasm: 'OpenQASM' }

export default function RuntimeStatus({ runtimes = [], availability }) {
  return (
    <Panel title="Runtime status" subtitle="Live from /api/frameworks">
      <ul className="runtime-list">
        {Object.keys(DISPLAY).map((name) => {
          const rt = availability[name]
          const executable = Boolean(rt && rt.runtime_available)
          return (
            <li key={name} className="runtime-item">
              <span className="runtime-name">{DISPLAY[name]}</span>
              {executable
                ? <StatusDot state="ok" label="Executable" />
                : <StatusDot state="idle" label="Analysis only" title="Detected by QResolve, but no executable runtime is registered" />}
              {executable && rt.version && <span className="runtime-version mono">v{rt.version}</span>}
            </li>
          )
        })}
      </ul>
      <p className="help-text">
        Frameworks without an executable runtime are analyzed from your pasted error only; fixes for
        them are never marked verified.
      </p>
    </Panel>
  )
}
