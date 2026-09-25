// Parse the unified-diff string returned by the backend (ProposedFix.diff).
export function parseDiff(diffText) {
  if (!diffText) return []
  return diffText.split('\n').map((text) => {
    let type = 'ctx'
    if (text.startsWith('+++') || text.startsWith('---')) type = 'meta'
    else if (text.startsWith('@@')) type = 'hunk'
    else if (text.startsWith('+')) type = 'add'
    else if (text.startsWith('-')) type = 'del'
    return { type, text }
  })
}

// Compact before/after view: only the changed lines from the backend diff.
// Returns { dels: [...], adds: [...] } with the diff marker trimmed off.
export function extractChanges(diffText) {
  const dels = []
  const adds = []
  for (const r of parseDiff(diffText)) {
    if (r.type === 'del') dels.push(r.text.slice(1).trim())
    else if (r.type === 'add') adds.push(r.text.slice(1).trim())
  }
  return { dels, adds }
}
