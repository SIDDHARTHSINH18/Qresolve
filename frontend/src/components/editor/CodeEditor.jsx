import { useRef } from 'react'
import CopyButton from '../ui/CopyButton.jsx'
import { highlightLines } from '../../utils/highlight.js'

// Editor = transparent <textarea> layered over a highlighted <pre>.
// The textarea holds the real value (exact code sent to the backend, never
// modified); the pre is aria-hidden decoration. Scroll positions are synced.
export default function CodeEditor({
  value, onChange, onClear, errorLine = null, label = 'Quantum code', id = 'code-editor', minHeight = 260,
}) {
  const preRef = useRef(null)
  const gutterRef = useRef(null)
  const lines = highlightLines(value)

  function syncScroll(e) {
    const { scrollTop, scrollLeft } = e.target
    if (preRef.current) {
      preRef.current.scrollTop = scrollTop
      preRef.current.scrollLeft = scrollLeft
    }
    if (gutterRef.current) gutterRef.current.scrollTop = scrollTop
  }

  return (
    <div className="editor-wrap">
      <div className="editor-toolbar">
        <label className="editor-label" htmlFor={id}>{label}</label>
        <div className="editor-tools">
          <CopyButton text={value} label="Copy" />
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClear} aria-label="Clear code">
            Clear
          </button>
        </div>
      </div>
      <div className="editor" style={{ minHeight }}>
        <div className="code-gutter editor-gutter" ref={gutterRef} aria-hidden="true">
          {lines.map((_, i) => (
            <span key={i} className={'code-lineno' + (errorLine === i + 1 ? ' is-error' : '')}>
              {i + 1}
            </span>
          ))}
        </div>
        <div className="editor-body">
          <pre className="code-pre editor-pre" ref={preRef} aria-hidden="true">
            <code>
              {lines.map((tokens, i) => (
                <span key={i} className={'code-line' + (errorLine === i + 1 ? ' is-error' : '')}>
                  {tokens.length === 0 ? '\u200b' : tokens.map((t, j) => (
                    <span key={j} className={`tok tok-${t.cls}`}>{t.text}</span>
                  ))}
                  {'\n'}
                </span>
              ))}
            </code>
          </pre>
          <textarea
            id={id}
            className="editor-textarea"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onScroll={syncScroll}
            spellCheck={false}
            autoCapitalize="off"
            autoCorrect="off"
            wrap="off"
            aria-label={label}
            aria-describedby="code-editor-help"
          />
        </div>
      </div>
      <p id="code-editor-help" className="help-text">
        Your code is sent to the backend exactly as written and executed only inside the QResolve sandbox.
      </p>
    </div>
  )
}
