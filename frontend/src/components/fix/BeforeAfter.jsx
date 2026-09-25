import Panel from '../ui/Panel.jsx'
import CodeBlock from '../ui/CodeBlock.jsx'

// Before/After comparison backed only by response evidence:
// BEFORE  = original code + original execution result
// AFTER   = patched code + verification execution result
export default function BeforeAfter({ response }) {
  const { code, execution, fix, verification } = response || {}
  if (!fix) return null

  const beforeState =
    execution && execution.success === false
      ? { cls: 'ba-bad', label: `✗ Runtime error${execution.exception_type ? `: ${execution.exception_type}` : ''}` }
      : execution && execution.success
        ? { cls: 'ba-good', label: '✓ Executes' }
        : { cls: 'ba-unknown', label: '○ Not executed' }

  const afterState =
    verification && verification.execution
      ? verification.execution.success
        ? { cls: 'ba-good', label: '✓ Executes' }
        : {
            cls: 'ba-bad',
            label: `✗ Runtime error${verification.execution.exception_type ? `: ${verification.execution.exception_type}` : ''}`,
          }
      : { cls: 'ba-unknown', label: '○ Not verified by backend' }

  return (
    <Panel title="Before / After">
      <div className="beforeafter">
        <div className="ba-col">
          <h3 className="sub-heading">Before</h3>
          <p className={`ba-state ${beforeState.cls}`}><span aria-hidden="true">{beforeState.label}</span></p>
          <CodeBlock code={code || ''} errorLine={response.error?.line_number ?? null} maxHeight={220} />
        </div>
        <div className="ba-col">
          <h3 className="sub-heading">After</h3>
          <p className={`ba-state ${afterState.cls}`}><span aria-hidden="true">{afterState.label}</span></p>
          <CodeBlock code={fix.patched_code || ''} maxHeight={220} />
        </div>
      </div>
    </Panel>
  )
}
