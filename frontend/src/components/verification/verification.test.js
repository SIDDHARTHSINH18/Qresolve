import { describe, expect, it } from 'vitest'
import { verificationState } from './VerificationPanel.jsx'
import { deriveTimeline } from '../debugger/Timeline.jsx'
import { deriveProviderEvidence } from '../runtime/ProviderStatus.jsx'
import { analysisOnly, qiskitSolved, unsolved, verificationFailed } from '../../test/fixtures.js'

describe('verificationState', () => {
  it('returns null with no response', () => {
    expect(verificationState(null)).toBeNull()
    expect(verificationState(undefined)).toBeNull()
  })

  it('reports verified only when the backend validator accepted', () => {
    expect(verificationState(qiskitSolved())).toBe('verified')
  })

  it('reports verification FAILED when a candidate was rejected after execution', () => {
    expect(verificationState(verificationFailed())).toBe('failed')
  })

  it('reports analysis-only when no runtime was available', () => {
    expect(verificationState(analysisOnly())).toBe('analysis-only')
  })

  it('reports unsolved when nothing passed and nothing failed-at-runtime', () => {
    expect(verificationState(unsolved())).toBe('unsolved')
  })
})

describe('deriveTimeline', () => {
  it('marks validator verification done for a verified solve', () => {
    const stages = deriveTimeline(qiskitSolved())
    const validator = stages.find((s) => s.label === 'Validator verification')
    expect(validator.state).toBe('done')
    const result = stages.find((s) => s.label === 'Result')
    expect(result.note).toBe('VERIFIED')
  })

  it('does not claim patched-code execution when runtime was unavailable', () => {
    const stages = deriveTimeline(analysisOnly())
    const exec = stages.find((s) => s.label === 'Patched code executed')
    expect(exec.state).toBe('skipped')
    const repro = stages.find((s) => s.label === 'Error reproduced')
    expect(repro.state).toBe('skipped')
  })
})

describe('deriveProviderEvidence (honest provider status)', () => {
  it('is null before any solve', () => {
    expect(deriveProviderEvidence(null)).toBeNull()
  })
  it('reports AI only when an attempt actually came from the provider', () => {
    expect(deriveProviderEvidence({ response: qiskitSolved() }).kind).toBe('ai')
  })
  it('reports heuristic fallback when no AI proposal was produced', () => {
    expect(deriveProviderEvidence({ response: unsolved() }).kind).toBe('heuristic')
  })
  it('reports no-proposal when a solve produced zero candidates', () => {
    expect(deriveProviderEvidence({ response: analysisOnly() }).kind).toBe('no-proposal')
  })
})
