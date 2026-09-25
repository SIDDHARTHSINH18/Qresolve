import CodeEditor from '../components/editor/CodeEditor.jsx'
import ErrorPanel from '../components/editor/ErrorPanel.jsx'
import FrameworkSelector from '../components/debugger/FrameworkSelector.jsx'
import Timeline from '../components/debugger/Timeline.jsx'
import EvidencePanel from '../components/debugger/EvidencePanel.jsx'
import AttemptsPanel from '../components/debugger/AttemptsPanel.jsx'
import DiagnosisPanel from '../components/diagnosis/DiagnosisPanel.jsx'
import FixPanel from '../components/fix/FixPanel.jsx'
import BeforeAfter from '../components/fix/BeforeAfter.jsx'
import VerificationPanel, { verificationState } from '../components/verification/VerificationPanel.jsx'
import CircuitViewer from '../components/circuit/CircuitViewer.jsx'
import EmptyState, { EXAMPLES } from '../components/ui/EmptyState.jsx'
import Panel from '../components/ui/Panel.jsx'

const BANNER = {
  verified: { cls: 'banner-verified', label: '✓ VERIFIED', note: 'Validator accepted: the fix executes in the real quantum runtime.' },
  failed: { cls: 'banner-failed', label: '✗ VERIFICATION FAILED', note: 'The proposed correction did not pass validation. No verified fix was reported.' },
  unsolved: { cls: 'banner-unsolved', label: '○ UNSOLVED', note: 'No candidate passed runtime verification.' },
  'analysis-only': { cls: 'banner-analysis', label: '○ ANALYSIS ONLY', note: 'Runtime unavailable — diagnosis without verification.' },
  clean: { cls: 'banner-verified', label: '✓ CLEAN RUN', note: 'The program executes successfully — nothing to fix.' },
}

export default function Debugger({
  code, onCode, errorText, onErrorText, frameworkPick, onFramework,
  availability, solving, solveError, session, onSolve, onValidate, validateState, onApplyFix, onLoadExample, onStartDebugging,
}) {
  const response = session?.response
  const vstate = verificationState(response)
  const banner = vstate ? BANNER[vstate] : null
  const editorErrorLine =
    session && code === session.request.code ? session.response?.error?.line_number ?? null : null

  return (
    <div className="debugger">
      <div className="debugger-input-col">
        <Panel title="Workspace" subtitle="Diagnose. Fix. Execute. Verify.">
          <FrameworkSelector value={frameworkPick} onChange={onFramework} availability={availability} />
          <CodeEditor
            value={code}
            onChange={onCode}
            onClear={() => onCode('')}
            errorLine={editorErrorLine}
            id="code-editor"
          />
          <ErrorPanel value={errorText} onChange={onErrorText} onClear={() => onErrorText('')} />
          <div className="solve-row">
            <button
              type="button"
              className="btn btn-primary btn-lg"
              onClick={onSolve}
              disabled={solving || !code.trim()}
              aria-busy={solving}
            >
              {solving ? 'Solving…' : 'Analyze & Solve'}
            </button>
            <span className="help-text" role="status" aria-live="polite">
              {solving
                ? 'Backend is executing, diagnosing and verifying — this runs your code in the sandbox.'
                : 'Calls POST /api/solve once. No simulated progress: results appear when the backend answers.'}
            </span>
          </div>

          {solveError && (
            <div className="error-banner" role="alert">
              <h3>{solveError.kind === 'network' ? 'Unable to reach QResolve backend' : 'Backend returned an error'}</h3>
              <p>{solveError.message}</p>
              {solveError.kind === 'network' && <p className="help-text">Check that the backend is running.</p>}
            </div>
          )}
        </Panel>

        {!code.trim() && (
          <Panel title="Try an example" subtitle="Clearly marked example cases">
            <div className="example-buttons">
              {EXAMPLES.map((ex) => (
                <button key={ex.id} type="button" className="btn btn-secondary btn-sm" onClick={() => onLoadExample(ex)}>
                  {ex.label}
                </button>
              ))}
            </div>
            <p className="help-text">Examples are pre-filled inputs, not results — they are sent to the backend for real execution.</p>
          </Panel>
        )}
      </div>

      <div className="debugger-result-col">
        {!response && !solving && !solveError && (
          <Panel className="empty-panel">
            <EmptyState
              onStart={onStartDebugging}
              onLoadExample={onLoadExample}
            />
          </Panel>
        )}
        {solving && !response && (
          <Panel title="Analyzing" className="loading-panel">
            <div className="loading-state" role="status" aria-live="polite">
              <span className="spinner" aria-hidden="true" />
              <div className="loading-copy">
                <p>Sending code to the backend…</p>
                <ul className="pipeline" aria-label="Pipeline stages performed server-side">
                  <li>Detecting framework</li>
                  <li>Reproducing error in sandbox</li>
                  <li>Analyzing root cause</li>
                  <li>Generating candidate fix</li>
                  <li>Re-executing patched code</li>
                  <li>Validating result</li>
                </ul>
                <p className="help-text">
                  All stages run inside one backend request — the backend does not stream
                  per-stage progress, so nothing here is ticked off early. Results appear when
                  the response arrives.
                </p>
              </div>
            </div>
          </Panel>
        )}

        {response && (
          <>
            {banner && (
              <div className={`result-banner ${banner.cls}`} role="status">
                <span className="banner-step" aria-hidden="true">01</span>
                <span className="banner-label">{banner.label}</span>
                <span className="banner-note">{banner.note}</span>
              </div>
            )}
            <DiagnosisPanel diagnosis={response.diagnosis} error={response.error} />
            <FixPanel
              fix={response.fix}
              verification={response.verification}
              onApply={response.fix ? () => onApplyFix(response.fix.patched_code) : undefined}
            />
            <VerificationPanel
              response={response}
              onValidate={onValidate}
              validateState={validateState}
            />
            <BeforeAfter
              response={{ ...response, code: session.request.code }}
            />
            <Panel title="Execution timeline" subtitle="Only stages evidenced by the backend response">
              <Timeline response={response} />
            </Panel>
            <EvidencePanel response={response} />
            <AttemptsPanel attempts={response.attempts} />
            <CircuitViewer
              code={session.request.code}
              framework={response.framework?.framework}
              errorLine={response.error?.line_number ?? null}
            />
          </>
        )}
      </div>
    </div>
  )
}
