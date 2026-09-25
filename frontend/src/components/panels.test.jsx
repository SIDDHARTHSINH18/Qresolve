import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import DiagnosisPanel from './diagnosis/DiagnosisPanel.jsx'
import FixPanel from './fix/FixPanel.jsx'
import { qiskitSolved } from '../test/fixtures.js'

describe('"What went wrong?" panel', () => {
  it('shows the plain-language summary by default; technical details are hidden until requested', () => {
    const d = qiskitSolved()
    render(<DiagnosisPanel diagnosis={d.diagnosis} error={d.error} />)
    expect(screen.getByText(/Qubit index 2 is outside/i)).toBeInTheDocument()
    expect(screen.queryByText('Root cause')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Show technical details/i }))
    expect(screen.getByText(/references qubit 2 in a 2-qubit register/i)).toBeInTheDocument()
    expect(screen.getByText('Affected operation')).toBeInTheDocument()
    expect(screen.getByText('qc.cx(0, 2)')).toBeInTheDocument()
    // collapse again
    fireEvent.click(screen.getByRole('button', { name: /Hide technical details/i }))
    expect(screen.queryByText('Root cause')).not.toBeInTheDocument()
  })

  it('renders nothing when the backend provided neither diagnosis nor error', () => {
    const { container } = render(<DiagnosisPanel diagnosis={null} error={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('falls back to the backend error message when there is no diagnosis', () => {
    const d = qiskitSolved()
    render(<DiagnosisPanel diagnosis={null} error={d.error} />)
    expect(screen.getByText(/Index 2 out of range for size 2/)).toBeInTheDocument()
  })
})

describe('Fix panel changed lines', () => {
  it('shows a compact BEFORE/AFTER pair extracted from the backend diff', () => {
    const d = qiskitSolved()
    render(<FixPanel fix={d.fix} verification={d.verification} />)
    const figure = screen.getByRole('figure', { name: /Changed lines/i })
    expect(within(figure).getByText('Before')).toBeInTheDocument()
    expect(within(figure).getByText('After')).toBeInTheDocument()
    expect(within(figure).getByText('qc.cx(0, 2)')).toBeInTheDocument()
    expect(within(figure).getByText('qc.cx(0, 1)')).toBeInTheDocument()
  })

  it('marks a validator-accepted fix as verified', () => {
    const d = qiskitSolved()
    render(<FixPanel fix={d.fix} verification={d.verification} />)
    expect(screen.getByText('✓ verified by validator')).toBeInTheDocument()
  })

  it('labels a rejected proposal as not verified — never as verified', () => {
    const d = qiskitSolved()
    render(<FixPanel fix={d.fix} verification={{ ...d.verification, verified: false }} />)
    expect(screen.getByText('proposed · not verified')).toBeInTheDocument()
    expect(screen.queryByText(/verified by validator/)).not.toBeInTheDocument()
  })

  it('omits the changed-line pair when the diff has no changes', () => {
    const d = { ...qiskitSolved().fix, diff: '' }
    render(<FixPanel fix={d} verification={null} />)
    expect(screen.queryByRole('figure', { name: /Changed lines/i })).not.toBeInTheDocument()
  })
})
