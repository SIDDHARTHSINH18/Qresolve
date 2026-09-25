import StatusDot from '../ui/StatusDot.jsx'

const DISPLAY = { qiskit: 'Qiskit', cirq: 'Cirq', pennylane: 'PennyLane', openqasm: 'OpenQASM' }

export default function TopBar({ frameworkPick, detectedFramework, availability, apiOk, providerNode, onNewSession }) {
  const active = detectedFramework || (frameworkPick !== 'auto' ? frameworkPick : null)
  const rt = active ? availability[active] : null
  const runtimeState = !apiOk
    ? { state: 'error', label: 'Backend offline' }
    : rt && rt.runtime_available
      ? { state: 'ok', label: `Ready${rt.version ? ` · ${rt.version}` : ''}` }
      : active
        ? { state: 'idle', label: 'Analysis only' }
        : { state: 'unknown', label: 'No framework' }

  return (
    <header className="topbar">
      <div className="brand">
        <svg className="brand-mark" viewBox="0 0 28 28" aria-hidden="true">
          <circle cx="8" cy="8" r="3" className="qm-qm" />
          <circle cx="20" cy="20" r="3" className="qm-qm" />
          <path d="M8 11v9h9" className="qm-path" />
        </svg>
        <div>
          <span className="brand-name">QRESOLVE</span>
          <span className="brand-sub">Quantum Software Debugging &amp; Verification</span>
        </div>
      </div>
      <div className="topbar-status">
        <span className="topbar-framework">
          Framework: <strong>{DISPLAY[active] || 'Auto-detect'}</strong>
        </span>
        <StatusDot state={runtimeState.state} label={`Runtime ${runtimeState.label}`} />
        <span className="topbar-api">
          <StatusDot state={apiOk ? 'ok' : 'error'} label={apiOk ? 'API connected' : 'API offline'} />
        </span>
        <span className="topbar-provider">{providerNode}</span>
        <button type="button" className="btn btn-primary btn-sm" onClick={onNewSession}>
          + New Debug
        </button>
      </div>
    </header>
  )
}
