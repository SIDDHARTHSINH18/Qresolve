const SYMBOLS = { ok: '●', warn: '◐', error: '✗', idle: '○', unknown: '?' }

// Status indicator that never relies on color alone: symbol + text label.
export default function StatusDot({ state = 'unknown', label, title }) {
  return (
    <span className={`status status-${state}`} title={title || label}>
      <span className="status-symbol" aria-hidden="true">{SYMBOLS[state] || SYMBOLS.unknown}</span>
      <span className="status-label">{label}</span>
    </span>
  )
}
