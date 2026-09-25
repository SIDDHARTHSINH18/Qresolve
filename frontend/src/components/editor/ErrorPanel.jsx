import { useState } from 'react'
import CopyButton from '../ui/CopyButton.jsx'

export default function ErrorPanel({ value, onChange, onClear }) {
  const [expanded, setExpanded] = useState(true)
  const hasContent = Boolean(value && value.trim())

  return (
    <div className="error-panel">
      <div className="editor-toolbar">
        <button
          type="button"
          className="btn btn-ghost btn-sm disclosure"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          aria-controls="error-input"
        >
          {expanded ? '▾' : '▸'} Error / Stack Trace
          <span className="tag tag-optional">optional</span>
        </button>
        {expanded && (
          <div className="editor-tools">
            <CopyButton text={value} label="Copy" />
            <button type="button" className="btn btn-ghost btn-sm" onClick={onClear} aria-label="Clear error text">
              Clear
            </button>
          </div>
        )}
      </div>
      {expanded && (
        <>
          <textarea
            id="error-input"
            className="error-textarea"
            rows={hasContent ? 6 : 3}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={'Paste the exception or traceback, e.g.\nCircuitError: Index 2 out of range for size 2.\n\nLeave empty to let QResolve run the code and reproduce the error itself.'}
            aria-label="Error or stack trace (optional)"
            spellCheck={false}
          />
          <p className="help-text">
            Optional. When empty, the backend reproduces the error by executing the code in its sandbox.
          </p>
        </>
      )}
    </div>
  )
}
