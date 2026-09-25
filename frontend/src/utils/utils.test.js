import { describe, expect, it } from 'vitest'
import { highlightLines, tokenize } from './highlight.js'
import { parseDiff, extractChanges } from './diff.js'
import { humanizeCategory, formatMs, truncate } from './format.js'
import { layoutCircuit, parseCircuitPreview } from './circuit.js'

describe('highlight', () => {
  it('classifies keywords, strings, numbers and comments', () => {
    const toks = tokenize('def f(x):  # note\n    return "hi" + 3')
    const cls = toks.filter((t) => t.cls !== 'ws').map((t) => t.cls)
    expect(cls).toContain('kw')
    expect(cls).toContain('str')
    expect(cls).toContain('num')
    expect(cls).toContain('com')
  })

  it('produces per-line arrays without embedded newlines (editor overlay safety)', () => {
    const lines = highlightLines('a = 1\nb = 2\nc = 3')
    expect(lines).toHaveLength(3)
    for (const line of lines) for (const tok of line) expect(tok.text).not.toContain('\n')
  })

  it('is inert: token text is preserved verbatim (no HTML escaping surprises)', () => {
    const lines = highlightLines('x = "<script>alert(1)</script>"')
    const all = lines.flat().map((t) => t.text).join('')
    expect(all).toContain('<script>alert(1)</script>')
  })
})

describe('parseDiff', () => {
  it('classifies diff line kinds', () => {
    const rows = parseDiff('--- a\n+++ b\n@@ -1 +1 @@\n-gone\n+added\n same')
    expect(rows.map((r) => r.type)).toEqual(['meta', 'meta', 'hunk', 'del', 'add', 'ctx'])
  })
  it('returns [] for empty input', () => {
    expect(parseDiff('')).toEqual([])
    expect(parseDiff(null)).toEqual([])
  })
})

describe('extractChanges', () => {
  it('returns only the changed del/add lines without diff markers', () => {
    const { dels, adds } = extractChanges('--- a/x.py\n+++ b/y.py\n@@ -2,3 +2,3 @@\n keep me\n-qc.cx(0, 2)\n+qc.cx(0, 1)\n')
    expect(dels).toEqual(['qc.cx(0, 2)'])
    expect(adds).toEqual(['qc.cx(0, 1)'])
  })
  it('handles empty and missing diffs', () => {
    expect(extractChanges('')).toEqual({ dels: [], adds: [] })
    expect(extractChanges(null)).toEqual({ dels: [], adds: [] })
  })
})

describe('format', () => {
  it('humanizes categories', () => {
    expect(humanizeCategory('qubit_index_out_of_range')).toBe('Qubit Index Out Of Range')
    expect(humanizeCategory('')).toBe('Unknown')
  })
  it('formats durations and truncates', () => {
    expect(formatMs(210)).toBe('210 ms')
    expect(formatMs(1500)).toBe('1.50 s')
    expect(formatMs(null)).toBeNull()
    expect(truncate('abcdef', 4)).toBe('abcd…')
  })
})

describe('circuit preview', () => {
  it('parses a simple qiskit circuit', () => {
    const parsed = parseCircuitPreview('from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.h(0)\nqc.cx(0, 1)\nqc.measure_all()\n', 'qiskit')
    expect(parsed).not.toBeNull()
    expect(parsed.wires).toEqual(['q0', 'q1'])
    const layout = layoutCircuit(parsed)
    expect(layout.cols).toBeGreaterThan(0)
  })

  it('refuses (returns null) when an out-of-range qubit is referenced — never invents', () => {
    // cx(0, 2) on a 2-qubit circuit is the bug under test; parser must not guess.
    const parsed = parseCircuitPreview('from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.cx(0, 2)\n', 'qiskit')
    expect(parsed).toBeNull()
  })

  it('refuses unknown gates', () => {
    const parsed = parseCircuitPreview('qc = QuantumCircuit(2)\nqc.mystery(0, 1)\n', 'qiskit')
    expect(parsed).toBeNull()
  })

  it('parses a standalone cirq CNOT', () => {
    const parsed = parseCircuitPreview('import cirq\nq = cirq.LineQubit(0)\nr = cirq.LineQubit(1)\nop = cirq.CNOT(q, r)\n', 'cirq')
    expect(parsed).not.toBeNull()
    expect(parsed.ops.some((o) => o.control)).toBe(true)
  })

  it('refuses nested Circuit(CNOT(...)) layouts rather than guessing ordering', () => {
    // The bundled cirq example nests the gate inside cirq.Circuit(...) on one
    // line; the conservative parser declines it and the UI shows "unavailable".
    const parsed = parseCircuitPreview('import cirq\nq = cirq.LineQubit(0)\ncircuit = cirq.Circuit(cirq.CNOT(q, q))\n', 'cirq')
    expect(parsed).toBeNull()
  })
})
