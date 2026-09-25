export const EXAMPLES = [
  {
    id: 'qiskit-invalid-qubit',
    label: 'Qiskit — Invalid Qubit',
    code: 'from qiskit import QuantumCircuit\n\nqc = QuantumCircuit(2)\nqc.h(0)\nqc.cx(0, 2)\nqc.measure_all()\n',
    errorText: '',
  },
  {
    id: 'cirq-duplicate-qubit',
    label: 'Cirq — Duplicate Qubit',
    code: 'import cirq\n\nq = cirq.LineQubit(0)\ncircuit = cirq.Circuit(cirq.CNOT(q, q))\nprint(circuit)\n',
    errorText: '',
  },
]

export default function EmptyState({ onStart, onLoadExample }) {
  return (
    <div className="empty-state">
      <svg className="empty-motif" viewBox="0 0 220 64" aria-hidden="true">
        <line x1="10" y1="20" x2="210" y2="20" className="wire" />
        <line x1="10" y1="44" x2="210" y2="44" className="wire" />
        <rect x="52" y="10" width="20" height="20" rx="3" className="gatebox" />
        <text x="62" y="24" textAnchor="middle" className="gatetext">H</text>
        <circle cx="128" cy="20" r="4" className="control" />
        <line x1="128" y1="20" x2="128" y2="44" className="conn" />
        <rect x="118" y="34" width="20" height="20" rx="3" className="gatebox" />
        <text x="128" y="48" textAnchor="middle" className="gatetext">X</text>
        <rect x="176" y="34" width="24" height="20" rx="3" className="gatebox" />
        <text x="188" y="48" textAnchor="middle" className="gatetext">M</text>
      </svg>
      <h2>Quantum debugging starts here.</h2>
      <p className="empty-tagline">Quantum debugging with execution-backed verification.</p>
      <p className="empty-copy">
        Paste your quantum code and an error. QResolve reproduces it in a real quantum runtime,
        diagnoses it, proposes a fix, then re-executes and verifies the patch.
      </p>
      <button type="button" className="btn btn-primary" onClick={onStart}>
        Start Debugging
      </button>
      <div className="empty-examples">
        <h3>Try an example</h3>
        <div className="example-buttons">
          {EXAMPLES.map((ex) => (
            <button key={ex.id} type="button" className="btn btn-secondary btn-sm" onClick={() => onLoadExample(ex)}>
              {ex.label}
            </button>
          ))}
        </div>
        <p className="help-text">These are bundled example cases — they will be sent to the backend for real execution.</p>
      </div>
    </div>
  )
}
