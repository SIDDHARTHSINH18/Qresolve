import StatusDot from '../ui/StatusDot.jsx'

// Honest provider status: the backend exposes no provider-introspection
// endpoint, so we NEVER claim "AI connected" speculatively. What we show is
// derived from real solve evidence: attempts with source "ai" mean a
// configured provider actually answered; "heuristic" means no AI proposal
// was available for that solve (unconfigured, unreachable, or rejected).
export function deriveProviderEvidence(session) {
  if (!session || !session.response) return null
  const attempts = session.response.attempts || []
  if (!attempts.length) return { kind: 'no-proposal', label: 'No proposal produced' }
  if (attempts.some((a) => a.source === 'ai')) return { kind: 'ai', label: 'AI provider responded' }
  return { kind: 'heuristic', label: 'Heuristic fallback used' }
}

export default function ProviderStatus({ session, compact = false }) {
  const evidence = deriveProviderEvidence(session)

  let state = 'unknown'
  let label = 'Not exercised yet'
  let detail = 'Run a solve to see whether a configured AI provider contributes proposals. QResolve never guesses this status.'

  if (evidence) {
    if (evidence.kind === 'ai') { state = 'ok'; label = 'AI connected'; detail = 'At least one proposal in the last solve came from the configured AI provider.' }
    else if (evidence.kind === 'heuristic') {
      state = 'warn'
      label = 'Heuristic mode'
      detail = 'AI provider unavailable. QResolve may fall back to heuristic analysis where supported.'
    } else { state = 'idle'; label = 'No proposals'; detail = 'The last solve produced no candidate (bounded retry stopped).' }
  }

  if (compact) return <StatusDot state={state} label={label} title={detail} />

  return (
    <div className="provider-status">
      <StatusDot state={state} label={label} title={detail} />
      <p className="help-text">{detail}</p>
    </div>
  )
}
