import StatusDot from '../ui/StatusDot.jsx'

// Bottom status strip. Sandbox/Validator readiness is tied to whether an
// executable runtime is registered (both run through it); if no runtime is
// available the strip says "Unknown" rather than claiming readiness.
export default function StatusBar({ frameworkLabel, frameworkVersion, apiOk, runtimes, providerState }) {
  const anyExecutable = (runtimes || []).some((r) => r.runtime_available)
  const execState = apiOk ? (anyExecutable ? 'ok' : 'idle') : 'error'
  const execLabel = apiOk ? (anyExecutable ? 'Ready' : 'No runtime') : 'Unknown (API offline)'
  const provider = providerState || { state: 'unknown', label: 'Not exercised' }

  return (
    <footer className="statusbar" aria-label="System status">
      <span className="sb-item">{frameworkLabel}{frameworkVersion ? ` ${frameworkVersion}` : ''}</span>
      <span className="sb-sep" aria-hidden="true">│</span>
      <span className="sb-item"><StatusDot state={execState} label={`Sandbox ${execLabel}`} /></span>
      <span className="sb-sep" aria-hidden="true">│</span>
      <span className="sb-item"><StatusDot state={execState} label={`Validator ${execLabel}`} /></span>
      <span className="sb-sep" aria-hidden="true">│</span>
      <span className="sb-item"><StatusDot state={provider.state} label={`Provider ${provider.label}`} /></span>
      <span className="sb-sep" aria-hidden="true">│</span>
      <span className="sb-item"><StatusDot state={apiOk ? 'ok' : 'error'} label={apiOk ? 'API connected' : 'API offline'} /></span>
    </footer>
  )
}
