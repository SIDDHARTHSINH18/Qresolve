// Execution timeline derived ONLY from the backend SolveResponse.
// Stages the response does not evidence are shown as "not performed" —
// never faked as completed.

function stage(state, label, note) {
  return { state, label, note } // state: 'done' | 'fail' | 'skipped'
}

export function deriveTimeline(response) {
  if (!response) return []
  const { status, framework, execution, error, diagnosis, fix, verification, attempts } = response
  const analysisOnly = Boolean(response.detail && response.detail.includes('No runtime available'))

  const stages = []

  stages.push(
    framework && framework.framework
      ? stage('done', 'Framework detected', `${framework.framework} · confidence ${Number(framework.confidence ?? 0).toFixed(2)}`)
      : stage('skipped', 'Framework detected', 'Not provided by backend.'),
  )

  if (status === 'no_error' && execution && execution.success) {
    stages.push(stage('done', 'Code executed', 'Executed successfully — no error to reproduce.'))
  } else if (analysisOnly) {
    stages.push(stage('skipped', 'Error reproduced', 'Runtime unavailable — no execution performed.'))
  } else if (execution && execution.success === false && (error || execution.exception_type)) {
    stages.push(stage('done', 'Error reproduced', `${execution.exception_type || error?.exception_type || 'error'} at runtime`))
  } else if (error) {
    stages.push(stage('done', 'Error analyzed', 'Supplied error parsed (no runtime reproduction).'))
  } else {
    stages.push(stage('skipped', 'Error reproduced', 'No reproduction evidence in response.'))
  }

  stages.push(
    diagnosis
      ? stage('done', 'Root cause analyzed', diagnosis.category || undefined)
      : stage('skipped', 'Root cause analyzed', 'No diagnosis returned.'),
  )

  const anyPatch = Boolean(fix) || (attempts || []).some((a) => a.patched_code && a.patched_code.trim())
  stages.push(
    anyPatch
      ? stage('done', 'Fix generated', fix ? 'Verified fix available' : `${(attempts || []).length} candidate attempt(s)`)
      : stage('skipped', 'Fix generated', response.detail || 'No fix was generated.'),
  )

  const executedPatch = verification || (attempts || []).some((a) => a.execution)
  stages.push(
    executedPatch
      ? stage('done', 'Patched code executed', 'Sandbox re-execution evidence present.')
      : stage('skipped', 'Patched code executed', analysisOnly ? 'Runtime unavailable.' : 'No patch was executed.'),
  )

  if (verification) {
    stages.push(
      verification.verified
        ? stage('done', 'Validator verification', 'Validator accepted the fix.')
        : stage('fail', 'Validator verification', verification.notes || 'Validator rejected the candidate.'),
    )
  } else {
    stages.push(stage('skipped', 'Validator verification', 'No verification performed.'))
  }

  const result =
    status === 'solved'
      ? stage('done', 'Result', 'VERIFIED')
      : status === 'no_error'
        ? stage('done', 'Result', 'CLEAN — nothing to fix')
        : stage('fail', 'Result', analysisOnly ? 'ANALYSIS ONLY' : 'UNSOLVED')
  stages.push(result)

  return stages
}

const SYMBOLS = { done: '✓', fail: '✗', skipped: '○' }

export default function Timeline({ response }) {
  const stages = deriveTimeline(response)
  if (!stages.length) return null
  return (
    <ol className="timeline" aria-label="Execution timeline">
      {stages.map((s, i) => (
        <li key={i} className={`timeline-item timeline-${s.state}`}>
          <span className="timeline-num" aria-hidden="true">{String(i + 1).padStart(2, '0')}</span>
          <span className={`timeline-symbol sym-${s.state}`} aria-hidden="true">{SYMBOLS[s.state]}</span>
          <span className="timeline-label">{s.label}</span>
          {s.note && <span className="timeline-note">{s.note}</span>}
          <span className="visually-hidden">{
            s.state === 'done' ? 'completed' : s.state === 'fail' ? 'failed' : 'not performed'
          }</span>
        </li>
      ))}
    </ol>
  )
}
