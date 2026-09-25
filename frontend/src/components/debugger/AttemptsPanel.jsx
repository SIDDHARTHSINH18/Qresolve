import Panel from '../ui/Panel.jsx'

// Makes the core principle visible: every attempt is labelled by its source,
// and "verified" only ever comes from the backend validator.
export default function AttemptsPanel({ attempts }) {
  if (!attempts || !attempts.length) return null
  return (
    <Panel title="Reasoning attempts" subtitle="AI proposes. The validator decides.">
      <ul className="attempt-list">
        {attempts.map((a) => (
          <li key={a.attempt} className="attempt-item">
            <div className="attempt-head">
              <span className="tag">#{a.attempt}</span>
              <span className={`tag ${a.source === 'ai' ? 'tag-ai' : 'tag-heuristic'}`}>
                {a.source === 'ai' ? 'AI suggestion' : 'Heuristic fallback'}
              </span>
              <span className="tag">level {a.level}</span>
              <span className={`tag ${a.verified ? 'tag-ok' : 'tag-err'}`}>
                {a.verified ? '✓ validator accepted' : '✗ not verified'}
              </span>
            </div>
            <p className="attempt-hypothesis">{a.hypothesis}</p>
            {a.fix_description && <p className="attempt-fix">→ {a.fix_description}</p>}
            {a.why_failed && <p className="attempt-fail">Failure evidence: {a.why_failed}</p>}
            {a.execution === null && a.why_failed && a.verified === false && (
              <p className="help-text">Not re-executed (rejected before execution).</p>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  )
}
