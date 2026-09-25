import Panel from '../ui/Panel.jsx'
import CodeBlock from '../ui/CodeBlock.jsx'
import CopyButton from '../ui/CopyButton.jsx'
import { extractChanges, parseDiff } from '../../utils/diff.js'

function DiffView({ diff }) {
  const rows = parseDiff(diff)
  if (!rows.length) return <p className="missing">Not provided by backend.</p>
  return (
    <div className="diffview" role="figure" aria-label="Code diff of the proposed fix">
      {rows.map((r, i) => (
        <span key={i} className={`diff-line diff-${r.type}`}>
          <span className="diff-marker" aria-hidden="true">{r.type === 'add' ? '+' : r.type === 'del' ? '-' : r.type === 'hunk' ? '@' : ' '}</span>
          {r.text}
        </span>
      ))}
    </div>
  )
}

// Compact "what actually changed" pair extracted from the backend diff.
function ChangePair({ dels, adds }) {
  if (!dels.length && !adds.length) return null
  return (
    <div className="change-pair" role="figure" aria-label="Changed lines of the proposed fix">
      <div className="cp-col cp-before">
        <span className="cp-label">Before</span>
        {dels.length
          ? dels.map((l, i) => <code key={i} className="cp-line">{l}</code>)
          : <code className="cp-line cp-none">—</code>}
      </div>
      <span className="cp-arrow" aria-hidden="true">→</span>
      <div className="cp-col cp-after">
        <span className="cp-label">After</span>
        {adds.length
          ? adds.map((l, i) => <code key={i} className="cp-line">{l}</code>)
          : <code className="cp-line cp-none">—</code>}
      </div>
    </div>
  )
}

export default function FixPanel({ fix, verification, onApply }) {
  if (!fix) return null
  const verified = Boolean(verification && verification.verified)
  const { dels, adds } = extractChanges(fix.diff)
  return (
    <Panel
      title="Fix"
      subtitle="What the proposal changes"
      step="03"
      className="fix-panel"
      actions={
        <>
          <CopyButton text={fix.patched_code} label="Copy Fix" />
          {onApply && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={onApply}>
              Apply to Editor
            </button>
          )}
        </>
      }
    >
      <p className="fix-description">
        {fix.description}
        <span className={`tag ${verified ? 'tag-ok' : 'tag-warn'}`}>
          {verified ? '✓ verified by validator' : 'proposed · not verified'}
        </span>
      </p>
      <ChangePair dels={dels} adds={adds} />
      <h3 className="sub-heading">Changed lines</h3>
      <DiffView diff={fix.diff} />
      <h3 className="sub-heading">Corrected code</h3>
      <CodeBlock code={fix.patched_code} maxHeight={320} />
    </Panel>
  )
}
