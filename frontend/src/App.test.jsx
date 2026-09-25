import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.jsx'
import { analysisOnly, qiskitSolved, verificationFailed } from './test/fixtures.js'

const HEALTH = { status: 'ok', service: 'qresolve', version: '0.1.0' }
const FRAMEWORKS = {
  frameworks: [
    { name: 'qiskit', runtime_available: true, version: '2.5.2' },
    { name: 'cirq', runtime_available: true, version: '1.7.0' },
    { name: 'pennylane', runtime_available: false, version: null },
    { name: 'openqasm', runtime_available: false, version: null },
  ],
}

let solveResponse = qiskitSolved()
let solveCalls = []

function json(data, status = 200) {
  return { ok: status < 400, status, json: async () => data }
}

beforeEach(() => {
  localStorage.clear()
  solveResponse = qiskitSolved()
  solveCalls = []
  global.fetch = vi.fn(async (url, opts) => {
    if (url === '/health') return json(HEALTH)
    if (url === '/api/frameworks') return json(FRAMEWORKS)
    if (url === '/api/solve') {
      solveCalls.push(JSON.parse(opts.body))
      return json(typeof solveResponse === 'function' ? solveResponse() : solveResponse)
    }
    if (url === '/api/validate') return json({ verified: true, execution: { success: true } })
    return json({}, 404)
  })
})
afterEach(() => vi.restoreAllMocks())

async function fillCodeAndSolve(code) {
  const editor = await screen.findByLabelText('Quantum code')
  fireEvent.change(editor, { target: { value: code } })
  fireEvent.click(await screen.findByRole('button', { name: /Analyze & Solve/i }))
}

describe('App — empty + framework state', () => {
  it('shows the empty state and honest framework availability', async () => {
    render(<App />)
    expect(await screen.findByText(/Quantum debugging starts here/i)).toBeInTheDocument()
    const btn = await screen.findByRole('button', { name: /Analyze & Solve/i })
    expect(btn).toBeDisabled()
    await waitFor(() => {
      const sel = screen.getByLabelText(/^Framework$/i)
      const text = within(sel).getAllByRole('option').map((o) => o.textContent).join(' | ')
      expect(text).toMatch(/Qiskit — Executable/)
      expect(text).toMatch(/PennyLane — Analysis only/)
    })
  })
})

describe('App — verified solve flow', () => {
  it('renders VERIFIED with diagnosis, fix and timeline only after backend evidence', async () => {
    render(<App />)
    await fillCodeAndSolve('from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.cx(0, 2)\n')
    expect(await screen.findAllByText('✓ VERIFIED')).not.toHaveLength(0)
    expect(screen.getAllByText(/Qubit index 2 is outside/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Validator accepted/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/\+ qc\.cx\(0, 1\)/)).toBeInTheDocument()
    await waitFor(() => expect(solveCalls.length).toBe(1))
    expect(solveCalls[0].code).toContain('qc.cx(0, 2)')
    expect(solveCalls[0]).not.toHaveProperty('framework')
  })

  it('shows a loading state while solving and results when the backend answers', async () => {
    let resolveSolve
    solveResponse = () => new Promise((r) => { resolveSolve = r })
    render(<App />)
    await fillCodeAndSolve('x = 1')
    expect(await screen.findByText(/Sending code to the backend/i)).toBeInTheDocument()
    resolveSolve(qiskitSolved())
    expect(await screen.findAllByText('✓ VERIFIED')).not.toHaveLength(0)
  })

  it('presents results in the debugging hierarchy: what failed → what went wrong → what changed → did it work', async () => {
    const { container } = render(<App />)
    await fillCodeAndSolve('x = 1')
    await screen.findAllByText('✓ VERIFIED')
    const sections = [...container.querySelectorAll('main .debugger-result-col .panel[aria-label]')].map((s) => s.getAttribute('aria-label'))
    expect(sections.slice(0, 4)).toEqual(['What went wrong?', 'Fix', 'Verification', 'Before / After'])
  })
})

describe('App — failure + analysis-only honesty', () => {
  it('renders VERIFICATION FAILED, never a green badge', async () => {
    solveResponse = verificationFailed()
    render(<App />)
    await fillCodeAndSolve('bad patch demo')
    expect(await screen.findAllByText('✗ VERIFICATION FAILED')).not.toHaveLength(0)
    expect(screen.queryByText('✓ VERIFIED')).not.toBeInTheDocument()
  })

  it('renders ANALYSIS ONLY when backend has no runtime', async () => {
    solveResponse = analysisOnly()
    render(<App />)
    await fillCodeAndSolve('import pennylane')
    expect(await screen.findAllByText('○ ANALYSIS ONLY')).not.toHaveLength(0)
    expect(screen.queryByText('✓ VERIFIED')).not.toBeInTheDocument()
  })

  it('surfaces a network failure honestly', async () => {
    global.fetch = vi.fn(async (url) => {
      if (url === '/health' || url === '/api/frameworks') return json(FRAMEWORKS)
      throw new TypeError('Failed to fetch')
    })
    render(<App />)
    await fillCodeAndSolve('x = 1')
    expect(await screen.findByText(/Unable to reach QResolve backend/i)).toBeInTheDocument()
  })
})

describe('App — security (backend output is inert)', () => {
  it('does not create img/script/iframe elements from backend strings', async () => {
    const payload = qiskitSolved()
    payload.diagnosis.summary = '<img src=x onerror="window.__pwn=1">MARKER'
    payload.error.message = '<script>MARKER2</script>'
    payload.verification.notes = '<iframe src="javascript:alert(1)">'
    solveResponse = payload
    const { container } = render(<App />)
    await fillCodeAndSolve('x')
    await screen.findAllByText(/MARKER/)
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('iframe')).toBeNull()
    expect(window.__pwn).toBeUndefined()
    // the literal markup is present as text
    expect(screen.getAllByText(/<img src=x/).length).toBeGreaterThan(0)
  })
})

describe('App — history persistence', () => {
  it('records a solved session and reopens it from the sidebar', async () => {
    render(<App />)
    await fillCodeAndSolve('from qiskit import QuantumCircuit\nqc.cx(0, 2)')
    await screen.findAllByText('✓ VERIFIED')
    const stored = JSON.parse(localStorage.getItem('qresolve.history.v1'))
    expect(stored.length).toBe(1)
    expect(stored[0].response.status).toBe('solved')
    // reset via New Debug, then reopen from history
    fireEvent.click(screen.getAllByRole('button', { name: /New Debug/i })[0])
    expect(await screen.findByText(/Quantum debugging starts here/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Qubit Index Out Of Range/ }))
    expect(await screen.findAllByText('✓ VERIFIED')).not.toHaveLength(0)
  })
})
