import { useState } from 'react'
import Panel from '../ui/Panel.jsx'
import { humanizeCategory } from '../../utils/format.js'

// "WHAT WENT WRONG?" — the compact plain-language explanation required by the
// product flow (CODE → ERROR → WHAT WENT WRONG? → FIX → VERIFY).
// Every sentence here is backend-supplied (diagnosis summary / hypothesis
// cause / exception message). The frontend never invents explanations;
// missing fields are labelled as such.
export default function DiagnosisPanel({ diagnosis, error }) {
  const [tech, setTech] = useState(false)
  if (!diagnosis && !error) return null

  const plain = diagnosis?.summary || error?.message || null
  const eyebrow = diagnosis?.category ? humanizeCategory(diagnosis.category) : null

  return (
    <Panel title="What went wrong?" subtitle={eyebrow || undefined} step="02" className="wwww-panel">
      {plain ? (
        <p className="wwww-summary">{plain}</p>
      ) : (
        <p className="missing">Not provided by backend.</p>
      )}
      {diagnosis?.hypotheses?.[0]?.cause && !plain && (
        <p className="wwww-summary">{diagnosis.hypotheses[0].cause}</p>
      )}

      <button
        type="button"
        className="btn btn-ghost btn-sm disclosure wwww-toggle"
        onClick={() => setTech((v) => !v)}
        aria-expanded={tech}
        aria-controls="wwww-tech-details"
      >
        {tech ? '▾' : '▸'} {tech ? 'Hide technical details' : 'Show technical details'}
      </button>

      {tech && (
        <div id="wwww-tech-details" className="wwww-tech">
          {diagnosis ? (
            <>
              <h3 className="sub-heading">Root cause</h3>
              {diagnosis.hypotheses && diagnosis.hypotheses.length ? (
                <ul className="hypothesis-list">
                  {diagnosis.hypotheses.map((h, i) => (
                    <li key={i}>
                      <p className="hypothesis-cause">{h.cause}</p>
                      {h.suggestion && <p className="hypothesis-suggestion">→ {h.suggestion}</p>}
                      {typeof h.confidence === 'number' && (
                        <p className="hypothesis-confidence">confidence {h.confidence.toFixed(2)}</p>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="missing">Not provided by backend.</p>
              )}
              {diagnosis.category && (
                <p className="wwww-category">KB category: <code>{diagnosis.category}</code></p>
              )}
            </>
          ) : (
            <p className="missing">Diagnosis not provided by backend.</p>
          )}

          {error && (
            <>
              <h3 className="sub-heading">Error location</h3>
              <div className="kv-grid">
                <span className="kv-key">Exception</span>
                <span className="kv-val mono">{error.exception_type || 'Not provided by backend.'}</span>
                <span className="kv-key">Line</span>
                <span className="kv-val mono">{error.line_number ?? 'Not provided by backend.'}</span>
                <span className="kv-key">Message</span>
                <span className="kv-val mono">{error.message || 'Not provided by backend.'}</span>
              </div>
              {error.source_snippet && (
                <>
                  <p className="kv-key wwww-op-label">Affected operation</p>
                  <pre className="source-snippet">{error.source_snippet}</pre>
                </>
              )}
            </>
          )}
        </div>
      )}
    </Panel>
  )
}
