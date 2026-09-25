import { useCallback, useState } from 'react'

const STORAGE_KEY = 'qresolve.history.v1'
const MAX_ENTRIES = 20

function read() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function write(entries) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries))
  } catch {
    // storage unavailable (private mode / quota) — history degrades silently
  }
}

// Local-only debugging history. Stores the request + backend response so a
// session can be reopened exactly; never stores credentials (none exist
// client-side). Bounded to MAX_ENTRIES with an explicit clear action.
export function useHistory() {
  const [entries, setEntries] = useState(read)

  const add = useCallback((entry) => {
    setEntries((prev) => {
      const next = [entry, ...prev].slice(0, MAX_ENTRIES)
      write(next)
      return next
    })
  }, [])

  const remove = useCallback((id) => {
    setEntries((prev) => {
      const next = prev.filter((e) => e.id !== id)
      write(next)
      return next
    })
  }, [])

  const clear = useCallback(() => {
    write([])
    setEntries([])
  }, [])

  return { entries, add, remove, clear }
}
