// Read-only highlighted code block (also used inside the editor overlay).
import { highlightLines } from '../../utils/highlight.js'

export default function CodeBlock({ code, errorLine = null, highlightOpLine = null, maxHeight }) {
  const lines = highlightLines(code || '')
  return (
    <div className="codeblock" style={maxHeight ? { maxHeight } : undefined}>
      <div className="code-gutter" aria-hidden="true">
        {lines.map((_, i) => (
          <span
            key={i}
            className={
              'code-lineno' +
              (errorLine === i + 1 ? ' is-error' : '') +
              (highlightOpLine === i + 1 ? ' is-opline' : '')
            }
          >
            {i + 1}
          </span>
        ))}
      </div>
      <pre className="code-pre">
        <code>
          {lines.map((tokens, i) => (
            <span
              key={i}
              className={
                'code-line' +
                (errorLine === i + 1 ? ' is-error' : '') +
                (highlightOpLine === i + 1 ? ' is-opline' : '')
              }
            >
              {tokens.length === 0 ? '\u200b' : tokens.map((t, j) => (
                <span key={j} className={`tok tok-${t.cls}`}>{t.text}</span>
              ))}
              {'\n'}
            </span>
          ))}
        </code>
      </pre>
    </div>
  )
}
