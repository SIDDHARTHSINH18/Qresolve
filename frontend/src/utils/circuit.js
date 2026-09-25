// Conservative circuit preview parser.
//
// IMPORTANT (honesty contract): the backend does not return circuit structure,
// so this parses ONLY the user's own submitted code for unambiguous, common
// gate patterns. When anything is unrecognized it returns null and the UI says
// "Circuit visualization unavailable" — it never invents circuit semantics.
// The result is always labeled a preview of the submitted code, not a
// runtime-derived fact.

const QISKIT_GATES = {
  h: { name: 'H', arity: 1 }, x: { name: 'X', arity: 1 }, y: { name: 'Y', arity: 1 },
  z: { name: 'Z', arity: 1 }, s: { name: 'S', arity: 1 }, t: { name: 'T', arity: 1 },
  cx: { name: 'X', arity: 2, control: true }, cz: { name: 'Z', arity: 2, control: true },
  swap: { name: 'SWAP', arity: 2 }, measure: { name: 'M', arity: 1, measure: true },
}

const CIRQ_GATES = {
  X: { name: 'X', arity: 1 }, Y: { name: 'Y', arity: 1 }, Z: { name: 'Z', arity: 1 },
  H: { name: 'H', arity: 1 }, S: { name: 'S', arity: 1 }, T: { name: 'T', arity: 1 },
  CNOT: { name: 'X', arity: 2, control: true }, CX: { name: 'X', arity: 2, control: true },
  CZ: { name: 'Z', arity: 2, control: true }, SWAP: { name: 'SWAP', arity: 2 },
  measure: { name: 'M', arity: -1, measure: true },
}

function parseQiskit(code) {
  const decl = code.match(/(\w+)\s*=\s*QuantumCircuit\s*\(\s*(\d+)/)
  if (!decl) return null
  const [, varName, sizeStr] = decl
  const wires = parseInt(sizeStr, 10)
  if (!wires || wires > 32) return null

  const ops = []
  const lines = code.split('\n')
  const callRe = new RegExp(`\\b${varName}\\.(\\w+)\\s*\\(([^)]*)\\)`)
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(callRe)
    if (!m) continue
    const gateName = m[1]
    if (gateName === 'measure_all') {
      for (let q = 0; q < wires; q++) ops.push({ gate: 'M', qubits: [q], measure: true, line: i + 1 })
      continue
    }
    if (gateName === 'barrier' || gateName === 'draw') continue
    const gate = QISKIT_GATES[gateName]
    if (!gate) return null // unknown gate -> refuse to guess
    const args = m[2].split(',').map((a) => a.trim()).filter(Boolean)
    const qubits = []
    for (const a of args) {
      if (!/^\d+$/.test(a)) return null // non-literal qubit -> refuse
      const q = parseInt(a, 10)
      if (q >= wires) return null
      qubits.push(q)
    }
    if (gate.arity > 0 && qubits.length !== gate.arity) return null
    ops.push({ gate: gate.name, qubits, control: !!gate.control, measure: !!gate.measure, line: i + 1 })
  }
  if (!ops.length) return null
  return { wires: Array.from({ length: wires }, (_, q) => `q${q}`), ops }
}

function parseCirq(code) {
  // Collect qubit variables: `q = cirq.LineQubit(k)` or `a, b = cirq.LineQubit.range(n)`
  const qubitOf = new Map() // varName -> wire index
  let wireCount = 0
  const rangeRe = /([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*=\s*cirq\.LineQubit\.range\(\s*(\d+)\s*\)/g
  let m
  while ((m = rangeRe.exec(code)) !== null) {
    const names = m[1].split(',').map((s) => s.trim())
    const n = parseInt(m[2], 10)
    if (names.length !== n || n > 32) return null
    names.forEach((name, idx) => {
      if (qubitOf.has(name)) return
      qubitOf.set(name, wireCount++)
    })
  }
  const singleRe = /([A-Za-z_]\w*)\s*=\s*cirq\.LineQubit\(\s*(\d+)\s*\)/g
  const singles = []
  while ((m = singleRe.exec(code)) !== null) singles.push([m[1], parseInt(m[2], 10)])
  for (const [name, idx] of singles) {
    if (qubitOf.has(name)) continue
    qubitOf.set(name, wireCount++)
  }
  if (!qubitOf.size) return null

  const ops = []
  const lines = code.split('\n')
  const gateRe = /cirq\.([A-Za-z_]\w*)\s*\(([^)]*)\)/g
  for (let i = 0; i < lines.length; i++) {
    gateRe.lastIndex = 0
    let gm
    while ((gm = gateRe.exec(lines[i])) !== null) {
      const gateName = gm[1]
      if (['LineQubit', 'Circuit', 'Simulator', 'Moment', 'measure_each'].includes(gateName)) {
        if (gateName === 'Circuit' || gateName === 'Simulator' || gateName === 'LineQubit') continue
        if (gateName === 'Moment') return null // moment layout: refuse to guess ordering
        if (gateName === 'measure_each') return null
      }
      const gate = CIRQ_GATES[gateName]
      if (!gate) return null
      const args = gm[2].split(',').map((a) => a.trim()).filter((a) => a && !a.startsWith('key'))
      if (gate.measure) {
        for (const a of args) {
          const w = qubitOf.get(a)
          if (w === undefined) return null
          ops.push({ gate: 'M', qubits: [w], measure: true, line: i + 1 })
        }
        continue
      }
      const qubits = []
      for (const a of args) {
        const w = qubitOf.get(a)
        if (w === undefined) return null
        qubits.push(w)
      }
      if (gate.arity > 0 && qubits.length !== gate.arity) return null
      ops.push({ gate: gate.name, qubits, control: !!gate.control, measure: !!gate.measure, line: i + 1 })
    }
  }
  if (!ops.length) return null
  const wires = [...qubitOf.entries()].sort((a, b) => a[1] - b[1]).map(([name]) => name)
  return { wires, ops }
}

export function parseCircuitPreview(code, framework) {
  if (!code) return null
  try {
    if (framework === 'cirq' || /import\s+cirq\b/.test(code)) return parseCirq(code)
    if (framework === 'qiskit' || /qiskit/i.test(code)) return parseQiskit(code)
  } catch {
    return null
  }
  return null
}

// Place ops into columns (greedy: first column where all involved wires are free).
export function layoutCircuit(parsed) {
  if (!parsed) return null
  const cursor = new Array(parsed.wires.length).fill(0)
  const placed = []
  for (const op of parsed.ops) {
    const col = Math.max(...op.qubits.map((q) => cursor[q]))
    for (const q of op.qubits) cursor[q] = col + 1
    placed.push({ ...op, col })
  }
  const cols = Math.max(0, ...cursor)
  return { wires: parsed.wires, cols, placed }
}
