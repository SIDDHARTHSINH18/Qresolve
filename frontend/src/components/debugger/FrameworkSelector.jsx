import { DETECTABLE_FRAMEWORKS } from '../../hooks/useFrameworks.js'

const DISPLAY = { qiskit: 'Qiskit', cirq: 'Cirq', pennylane: 'PennyLane', openqasm: 'OpenQASM' }

// Honest availability: only /api/frameworks (backend registry) decides
// whether a framework is executable. Everything else is analysis-only.
export default function FrameworkSelector({ value, onChange, availability }) {
  const selected = value === 'auto' ? null : availability[value]
  return (
    <div className="framework-selector">
      <label htmlFor="framework-select">Framework</label>
      <select
        id="framework-select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="auto">Auto-detect</option>
        {DETECTABLE_FRAMEWORKS.map((name) => {
          const rt = availability[name]
          const executable = Boolean(rt && rt.runtime_available)
          return (
            <option key={name} value={name}>
              {DISPLAY[name] || name} — {executable ? `Executable${rt.version ? ` (${rt.version})` : ''}` : 'Analysis only'}
            </option>
          )
        })}
      </select>
      {selected && !selected.runtime_available && (
        <p className="inline-note note-warn" role="note">
          This framework is currently analysis-only: no executable runtime is registered, so fixes
          cannot be verified by re-execution.
        </p>
      )}
      {selected && selected.runtime_available && (
        <p className="inline-note note-ok" role="note">
          Executable runtime available{selected.version ? ` · version ${selected.version}` : ''}.
        </p>
      )}
    </div>
  )
}
