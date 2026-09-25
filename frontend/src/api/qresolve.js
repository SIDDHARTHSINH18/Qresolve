// Centralized API layer for the QResolve backend.
// Base URL is configurable (browser dev-proxy, static host, Electron, ENMA):
//   - build-time: VITE_API_BASE_URL
//   - runtime:    setBaseUrl()
// Empty base URL means same-origin (Vite dev proxy in development).

export class ApiError extends Error {
  constructor(kind, message, { status = null, detail = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind // 'network' | 'http' | 'validation'
    this.status = status
    this.detail = detail
  }
}

let baseUrl = normalizeBase(
  (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_BASE_URL) || '',
)

function normalizeBase(url) {
  return String(url || '').replace(/\/+$/, '')
}

export function setBaseUrl(url) {
  baseUrl = normalizeBase(url)
}

export function getBaseUrl() {
  return baseUrl
}

async function request(path, options = {}) {
  let res
  try {
    res = await fetch(baseUrl + path, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
  } catch {
    throw new ApiError(
      'network',
      'Unable to reach the QResolve backend. Check that the backend is running.',
    )
  }

  let data = null
  try {
    data = await res.json()
  } catch {
    data = null // non-JSON body; handled below
  }

  if (!res.ok) {
    const detail = data && (data.detail ?? data.message)
    const message = detail
      ? String(detail)
      : `Backend responded with HTTP ${res.status}.`
    throw new ApiError(res.status === 422 ? 'validation' : 'http', message, {
      status: res.status,
      detail: detail ?? null,
    })
  }
  return data
}

export function getHealth() {
  return request('/health')
}

export function getFrameworks() {
  return request('/api/frameworks')
}

// POST /api/solve — the single primary debugging action.
// errorText (raw traceback paste) is sent as ErrorInput.traceback_text.
export function solve({ code, errorText, framework }) {
  const body = { code }
  if (errorText && errorText.trim()) body.error = { traceback_text: errorText }
  if (framework && framework !== 'auto') body.framework = framework
  return request('/api/solve', { method: 'POST', body: JSON.stringify(body) })
}

// POST /api/validate — explicit re-verification of candidate code.
export function validate({ code, framework }) {
  const body = framework ? { code, framework } : { code }
  return request('/api/validate', { method: 'POST', body: JSON.stringify(body) })
}
