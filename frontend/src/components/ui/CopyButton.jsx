import { useEffect, useRef, useState } from 'react'

export default function CopyButton({ text, label = 'Copy', className = '' }) {
  const [copied, setCopied] = useState(false)
  const timer = useRef(null)

  useEffect(() => () => clearTimeout(timer.current), [])

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(text ?? '')
    } catch {
      // Clipboard API unavailable (permissions/insecure context): inert no-op.
      return
    }
    setCopied(true)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setCopied(false), 1500)
  }

  return (
    <button type="button" className={`btn btn-ghost btn-sm ${className}`} onClick={onCopy}
      aria-label={`${label}${copied ? ' (copied)' : ''}`}>
      {copied ? '✓ Copied' : label}
      <span className="visually-hidden" role="status" aria-live="polite">
        {copied ? `${label} succeeded` : ''}
      </span>
    </button>
  )
}
