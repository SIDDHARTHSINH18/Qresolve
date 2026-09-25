export function humanizeCategory(category) {
  if (!category) return 'Unknown'
  return category
    .split('_')
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(' ')
}

export function formatMs(ms) {
  if (ms === null || ms === undefined) return null
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(2)} s`
}

export function formatTimestamp(ts) {
  const d = new Date(ts)
  const now = new Date()
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  const sameDay = d.toDateString() === now.toDateString()
  return sameDay ? `Today · ${time}` : `${d.toLocaleDateString()} · ${time}`
}

export function truncate(text, max = 200) {
  if (!text) return ''
  return text.length > max ? text.slice(0, max) + '…' : text
}
