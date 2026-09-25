// Realistic SolveResponse fixtures mirroring backend/models.py. Used across
// component tests so the frontend is exercised against the true contract.

export function qiskitSolved() {
  return {
    status: 'solved',
    framework: { framework: 'qiskit', confidence: 0.95, matched_patterns: ['from qiskit import'] },
    execution: {
      success: false, exit_code: 1, stdout: '', stderr: 'IndexError...', timed_out: false,
      exception_type: 'IndexError', exception_message: 'Index 2 out of range for size 2.',
      traceback_text: '  File "user_code.py", line 5, in <module>\n    qc.cx(0, 2)\nIndexError: ...',
      error: { exception_type: 'IndexError', message: 'Index 2 out of range for size 2.', line_number: 5 },
    },
    error: { exception_type: 'IndexError', message: 'Index 2 out of range for size 2.', line_number: 5, source_snippet: 'qc.cx(0, 2)' },
    diagnosis: {
      summary: 'Qubit index 2 is outside the 2-qubit circuit range.',
      category: 'qubit_index_out_of_range',
      hypotheses: [{ cause: 'qc.cx references qubit 2 in a 2-qubit register', suggestion: 'Use qc.cx(0, 1)', confidence: 0.9 }],
    },
    fix: {
      description: 'Clamp the CNOT target to an in-range qubit.',
      strategy: 'index_correction',
      patched_code: 'from qiskit import QuantumCircuit\n\nqc = QuantumCircuit(2)\nqc.h(0)\nqc.cx(0, 1)\nqc.measure_all()\n',
      diff: '--- a/user_code.py\n+++ b/user_code.py\n@@ -2,3 +2,3 @@\n- qc.cx(0, 2)\n+ qc.cx(0, 1)\n',
      confidence: 0.9,
    },
    verification: {
      verified: true,
      execution: { success: true, exit_code: 0, stdout: '', stderr: '', timed_out: false, execution_time_ms: 210 },
      notes: 'Patched program executed successfully in the sandbox.',
    },
    attempts: [
      { attempt: 1, level: 1, source: 'ai', hypothesis: 'Out-of-range qubit index', fix_description: 'qc.cx(0, 1)', patched_code: 'qc.cx(0, 1)', verified: true, execution: { success: true } },
    ],
    final_level: 1,
    detail: null,
  }
}

export function verificationFailed() {
  const base = qiskitSolved()
  base.status = 'unsolved'
  base.verification = {
    verified: false,
    execution: { success: false, exception_type: 'NameError', exception_message: 'name foo is not defined', timed_out: false },
    notes: 'Candidate patch introduced a new runtime error.',
  }
  base.attempts = [
    { attempt: 1, level: 1, source: 'ai', hypothesis: 'bad guess', fix_description: 'renamed symbol', patched_code: 'x = foo', verified: false, execution: { success: false, exception_type: 'NameError' }, why_failed: 'NameError after patch' },
  ]
  base.fix = { ...base.fix, description: 'Bad AI patch', confidence: 0.4 }
  return base
}

export function analysisOnly() {
  return {
    status: 'unsolved',
    framework: { framework: 'pennylane', confidence: 0.6, matched_patterns: ['import pennylane'] },
    execution: null,
    error: { exception_type: 'WireError', message: 'unknown wire', line_number: null },
    diagnosis: { summary: 'Wire referenced before allocation.', category: 'pennylane_wire_error', hypotheses: [] },
    fix: null,
    verification: null,
    attempts: [],
    final_level: 1,
    detail: 'No runtime available for pennylane: analysis only.',
  }
}

export function unsolved() {
  const base = qiskitSolved()
  base.status = 'unsolved'
  base.verification = null
  base.fix = null
  base.attempts = [
    { attempt: 1, level: 1, source: 'heuristic', hypothesis: 'maybe index', fix_description: 'guess', patched_code: 'qc.cx(0,1)', verified: false, execution: null, why_failed: 'Rejected before execution' },
  ]
  return base
}
