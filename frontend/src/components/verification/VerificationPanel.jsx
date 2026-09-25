import Panel from '../ui/Panel.jsx'

// The verification verdict comes ONLY from the backend validator.
// States: VERIFIED / VERIFICATION FAILED / UNSOLVED / ANALYSIS ONLY / CLEAN.
export function verificationState(response) {
  if (!response) return null
  const { status, verification, attempts, detail } = response
  const analysisOnly = Boolean(detail && detail.includes('No runtime available'))
  if (analysisOnly) return 'analysis-only'
  if (status === 'solved' && verification && verification.verified) return 'verified'
  const proposedButRejected =
    status === 'unsolved' && (attempts || []).some((a) => a.execution && !a.verified)
  if (proposedButRejected) return 'failed'
  if (status === 'unsolved') return 'unsolved'
  if (status === 'no_error') return 'clean'
  return 'unsolved'
}

const VIEWS = {
  verified: { badge: '✓ VERIFIED', cls: 'ver-verified', note: 'The patched program executed successfully in the sandbox and the validator accepted the result.' },
  failed: { badge: '✗ VERIFICATION FAILED', cls: 'ver-failed', note: 'The proposed correction did not pass validation.\n\nNo verified fix was reported.' },
  unsolved: { badge: '○ UNSOLVED', cls: 'ver-unsolved', note: 'QResolve could not produce a fix that passes runtime verification for this error.' },
  'analysis-only': { badge: '○ ANALYSIS ONLY', cls: 'ver-analysis', note: 'Runtime unavailable — diagnosis was performed without execution, so nothing is verified.' },
  clean: { badge: '✓ CLEAN RUN', cls: 'ver-verified', note: 'The code executed successfully; there was nothing to fix.' },
}

export default function VerificationPanel({ response, onValidate, validateState }) {
  const state = verificationState(response)
  if (!state) return null
  const view = VIEWS[state]
  const verification = response.verification
  const checks = buildChecks(response, state)

  return (
    <Panel title="Verification" subtitle="Did it work?" step="04" className="verification-panel">
      <p className={`verdict ${view.cls}`} role="status">
        <span className="verdict-badge">{view.badge}</span>
        <span className="verdict-note">{view.note}</span>
      </p>
      <ul className="check-list" aria-label="Verification checks">
        {checks.map((c, i) => (
          <li key={i} className={`check check-${c.state}`}>
            <span aria-hidden="true">{c.state === 'pass' ? '✓' : c.state === 'fail' ? '✗' : '○'}</span>
            <span>{c.label}</span>
          </li>
        ))}
      </ul>
      {verification && verification.execution && (
        <div className="kv-grid">
          <span className="kv-key">Sandbox run</span>
          <span className="kv-val mono">
            {verification.execution.success ? 'success' : 'failed'}
            {verification.execution.execution_time_ms != null
              ? ` · ${Math.round(verification.execution.execution_time_ms)} ms` : ''}
            {verification.execution.timed_out ? ' · timed out' : ''}
          </span>
          {verification.execution.exception_type && (
            <>
              <span className="kv-key">Runtime exception</span>
              <span className="kv-val mono">{verification.execution.exception_type}: {verification.execution.exception_message}</span>
            </>
          )}
        </div>
      )}
      {state !== 'verified' && state !== 'analysis-only' && response.fix && onValidate && (
        <button type="button" className="btn btn-secondary" onClick={onValidate}>
          {validateState === 'loading' ? 'Running…' : 'Run Verification'}
        </button>
      )}
      {validateState === 'loading' && <p className="help-text" role="status">Executing candidate in the backend sandbox…</p>}
      {validateState && validateState !== 'loading' && validateState.error && (
        <p className="inline-note note-err" role="alert">
          {`✗ Independent /api/validate run failed: ${validateState.error.message}`}
        </p>
      )}
      {validateState && validateState !== 'loading' && validateState.result && (
        <p className={`inline-note ${validateState.result.verified ? 'note-ok' : 'note-err'}`} role="status">
          {validateState.result.verified
            ? '✓ Independent /api/validate run: code executes successfully in the sandbox.'
            : `✗ Independent /api/validate run: ${validateState.result.execution?.exception_type || 'execution failed'} — validator did not accept.`}
        </p>
      )}
    </Panel>
  )
}

function buildChecks(response, state) {
  const checks = []
  const { execution, error, fix, verification, attempts } = response
  if (state === 'analysis-only') {
    checks.push({ state: 'pass', label: 'Error parsed from supplied traceback' })
    checks.push({ state: 'pass', label: 'Diagnosis generated' })
    checks.push({ state: 'fail', label: 'Runtime reproduction (no executable runtime)' })
    checks.push({ state: 'fail', label: 'Validator (not performed — analysis only)' })
    return checks
  }
  checks.push({
    state: execution && execution.success === false ? 'pass' : execution && execution.success ? 'pass' : 'fail',
    label: execution && execution.success === false ? 'Error reproduced in sandbox' : error ? 'Error parsed from supplied traceback' : 'Error reproduced',
  })
  const hasCandidate = Boolean(fix) || (attempts || []).some((a) => a.patched_code && a.patched_code.trim())
  checks.push({ state: hasCandidate ? 'pass' : 'fail', label: 'Candidate fix generated' })
  checks.push({
    state: verification && verification.execution ? 'pass' : 'fail',
    label: 'Patched program executed in sandbox',
  })
  checks.push({
    state: verification ? (verification.verified ? 'pass' : 'fail') : 'fail',
    label: verification ? (verification.verified ? 'Validator accepted result' : 'Validator rejected result') : 'Validator verification',
  })
  return checks
}
