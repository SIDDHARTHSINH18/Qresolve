import StatusDot from '../ui/StatusDot.jsx'
import { verificationState } from '../verification/VerificationPanel.jsx'

const FRAMEWORK_DISPLAY = { qiskit: 'Qiskit', cirq: 'Cirq', pennylane: 'PennyLane', openqasm: 'OpenQASM' }

export function caseTitle(entry) {
  const cat = entry.response?.diagnosis?.category
  if (cat && cat !== 'none' && cat !== 'unknown') return humanize(cat)
  if (entry.response?.status === 'no_error') return 'Clean run'
  return entry.request?.frameworkPick || entry.response?.framework?.framework || 'Debug session'
}

function humanize(cat) {
  return cat.split('_').map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w)).join(' ')
}

export function statusChip(entry) {
  const st = verificationState(entry.response)
  switch (st) {
    case 'verified': return { state: 'ok', label: 'VERIFIED' }
    case 'failed': return { state: 'error', label: 'VERIFICATION FAILED' }
    case 'analysis-only': return { state: 'idle', label: 'ANALYSIS ONLY' }
    case 'clean': return { state: 'ok', label: 'CLEAN' }
    default: return { state: 'warn', label: 'UNSOLVED' }
  }
}

function when(ts) {
  const d = new Date(ts)
  const now = new Date()
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  return d.toDateString() === now.toDateString() ? `Today · ${time}` : `${d.toLocaleDateString()} · ${time}`
}

export default function HistoryList({ entries, onOpen, onRemove, limit }) {
  const shown = limit ? entries.slice(0, limit) : entries
  if (!shown.length) return <p className="missing">No saved debugging sessions yet.</p>
  return (
    <ul className="history-list">
      {shown.map((entry) => {
        const chip = statusChip(entry)
        return (
          <li key={entry.id} className="history-item">
            <button type="button" className="history-open" onClick={() => onOpen(entry)}>
              <span className="history-title">{caseTitle(entry)}</span>
              <span className="history-meta">
                {FRAMEWORK_DISPLAY[entry.response?.framework?.framework] || entry.response?.framework?.framework || entry.request?.frameworkPick || '—'}
                {' · '}
                {when(entry.ts)}
              </span>
              <StatusDot state={chip.state} label={chip.label} />
            </button>
            {onRemove && (
              <button
                type="button"
                className="btn btn-ghost btn-sm history-remove"
                aria-label={`Remove session ${caseTitle(entry)} from history`}
                onClick={() => onRemove(entry.id)}
              >
                ✕
              </button>
            )}
          </li>
        )
      })}
    </ul>
  )
}
