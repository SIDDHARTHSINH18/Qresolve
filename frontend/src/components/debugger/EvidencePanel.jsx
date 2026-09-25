import Panel from '../ui/Panel.jsx'

// Renders ONLY fields present in the backend response. Missing fields show
// "Not provided by backend." — no fabricated evidence.
export default function EvidencePanel({ response }) {
  if (!response) return null
  const { framework, execution, error, diagnosis, verification, attempts } = response

  const reproduction = execution
    ? execution.success
      ? { text: `Executed successfully (${formatMsLite(execution.execution_time_ms)})`, state: 'ok' }
      : {
          text: `Failed at runtime: ${execution.exception_type || 'unknown'}${execution.timed_out ? ' (timed out)' : ''} (${formatMsLite(execution.execution_time_ms)})`,
          state: 'err',
        }
    : null

  const validator = verification
    ? verification.verified
      ? { text: verification.notes || 'Validator accepted the fix.', state: 'ok' }
      : { text: verification.notes || 'Validator rejected the candidate.', state: 'err' }
    : null

  return (
    <Panel title="Why QResolve thinks this" subtitle="Evidence actually returned by the backend">
      <dl className="evidence-list">
        <EvidenceRow label="Framework"
          value={framework && framework.framework
            ? `${framework.framework} (confidence ${Number(framework.confidence ?? 0).toFixed(2)}, ${framework.matched_patterns?.length ?? 0} pattern match(es))`
            : null} />
        <EvidenceRow label="Runtime reproduction" value={reproduction ? reproduction.text : null} state={reproduction?.state} />
        <EvidenceRow label="Error location"
          value={error ? `${error.exception_type || '?'}: ${error.message || ''}${error.line_number ? ` — line ${error.line_number}` : ''}` : null} />
        <EvidenceRow label="Knowledge-base match"
          value={diagnosis ? `category "${diagnosis.category}" — ${diagnosis.summary}` : null} />
        <EvidenceRow label="Hypotheses"
          value={diagnosis && diagnosis.hypotheses?.length
            ? diagnosis.hypotheses.map((h) => `${h.cause} (${h.confidence?.toFixed?.(2) ?? h.confidence})`).join(' • ')
            : null} />
        <EvidenceRow label="Fix source"
          value={attempts && attempts.length
            ? attempts.map((a) => `attempt ${a.attempt}: ${a.source} (level ${a.level})`).join(' • ')
            : null} />
        <EvidenceRow label="Validator result" value={validator ? validator.text : null} state={validator?.state} />
      </dl>
    </Panel>
  )
}

function formatMsLite(ms) {
  if (ms === null || ms === undefined) return 'time not reported'
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(2)} s`
}

function EvidenceRow({ label, value, state }) {
  return (
    <div className="evidence-row">
      <dt>{label}</dt>
      <dd className={state ? `evidence-${state}` : undefined}>
        {value || <span className="missing">Not provided by backend.</span>}
      </dd>
    </div>
  )
}
