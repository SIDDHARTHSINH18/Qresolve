import { useCallback, useEffect, useState } from 'react'
import { getFrameworks, getHealth } from '../api/qresolve.js'

// Frameworks the QResolve detector knows. Runtime availability is NEVER
// assumed from this list — it comes from /api/frameworks (source of truth).
export const DETECTABLE_FRAMEWORKS = ['qiskit', 'cirq', 'pennylane', 'openqasm']

export function useFrameworks() {
  const [state, setState] = useState({
    loading: true,
    apiOk: false,
    health: null,
    runtimes: [], // [{name, runtime_available, version}]
    error: null,
  })

  const load = useCallback(async () => {
    try {
      const [health, fw] = await Promise.all([getHealth(), getFrameworks()])
      setState({
        loading: false,
        apiOk: true,
        health,
        runtimes: (fw && fw.frameworks) || [],
        error: null,
      })
    } catch (error) {
      setState((s) => ({ ...s, loading: false, apiOk: false, error }))
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const availability = {}
  for (const rt of state.runtimes) availability[rt.name] = rt
  return { ...state, availability, refresh: load }
}
