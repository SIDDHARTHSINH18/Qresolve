import Panel from '../ui/Panel.jsx'
import { parseCircuitPreview, layoutCircuit } from '../../utils/circuit.js'

// Circuit VIEWER honesty contract: the backend does not return circuit
// structure. We parse only the user's own submitted code conservatively; if
// anything is unrecognized the panel says visualization is unavailable.
// The drawing is labeled a preview of the submitted code — never a
// runtime-derived fact.
export default function CircuitViewer({ code, framework, errorLine }) {
  const parsed = parseCircuitPreview(code, framework)
  if (!parsed) {
    return (
      <Panel title="Circuit" subtitle="Preview of the submitted code">
        <p className="missing">Circuit visualization unavailable for this result.</p>
        <p className="help-text">
          The backend does not return circuit structure, and the submitted code could not be parsed
          with full confidence. Nothing is guessed or invented.
        </p>
      </Panel>
    )
  }

  const layout = layoutCircuit(parsed)
  const { wires, cols, placed } = layout
  // wire rows interleaved with connector rows (for controlled gates)
  const rows = wires.length * 2 - 1
  const grid = Array.from({ length: rows }, () => new Array(cols).fill(null))
  const connectors = {} // col -> [connectorRowIdx...]

  for (const op of placed) {
    if (op.qubits.length === 1) {
      grid[op.qubits[0] * 2][op.col] = { kind: 'gate', label: op.gate, line: op.line }
    } else if (op.qubits.length === 2) {
      const [a, b] = op.qubits
      const lo = Math.min(a, b)
      const hi = Math.max(a, b)
      grid[lo * 2][op.col] = { kind: op.control ? 'control' : 'gate', label: op.control ? '●' : op.gate, line: op.line }
      grid[hi * 2][op.col] = { kind: 'gate', label: op.gate, line: op.line }
      if (op.control) {
        connectors[op.col] = connectors[op.col] || []
        for (let r = lo * 2 + 1; r < hi * 2; r += 2) connectors[op.col].push(r)
      }
    } else {
      for (const q of op.qubits) grid[q * 2][op.col] = { kind: 'gate', label: op.gate, line: op.line }
    }
  }

  return (
    <Panel title="Circuit" subtitle="Preview parsed from the submitted code — not runtime-derived">
      <div className="circuit" role="img" aria-label={`Circuit preview with ${wires.length} qubit wires and ${placed.length} operations`}>
        {grid.map((row, r) => (
          <div key={r} className={r % 2 === 0 ? 'circuit-wire-row' : 'circuit-conn-row'}>
            <span className="circuit-wire-label">{r % 2 === 0 ? wires[r / 2] : ''}</span>
            <div className="circuit-cells">
              {row.map((cell, c) => {
                const isConnector = r % 2 === 1 && connectors[c] && connectors[c].includes(r)
                return (
                  <span
                    key={c}
                    className={
                      'circuit-cell' +
                      (r % 2 === 0 ? ' cell-wire' : ' cell-gap') +
                      (isConnector ? ' cell-connector' : '')
                    }
                  >
                    {cell ? (
                      <span
                        className={
                          'gate' + (cell.kind === 'control' ? ' gate-control' : '') +
                          (errorLine != null && cell.line === errorLine ? ' gate-error' : '')
                        }
                        title={errorLine != null && cell.line === errorLine ? `failing line ${cell.line}` : undefined}
                      >
                        {cell.label}
                      </span>
                    ) : r % 2 === 0 ? '─' : ''}
                  </span>
                )
              })}
            </div>
          </div>
        ))}
      </div>
      {errorLine != null && (
        <p className="help-text">
          Gate on the backend-reported failing line {errorLine} is highlighted (when derivable).
        </p>
      )}
    </Panel>
  )
}
