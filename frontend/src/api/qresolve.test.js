import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, getFrameworks, getHealth, solve, validate } from './qresolve.js'

function ok(data) {
  return { ok: true, status: 200, json: async () => data }
}
function err(status, body) {
  return { ok: false, status, json: async () => body }
}

beforeEach(() => {
  global.fetch = vi.fn()
})
afterEach(() => {
  vi.restoreAllMocks()
})

describe('getFrameworks', () => {
  it('parses the frameworks payload from the backend', async () => {
    const payload = { frameworks: [{ name: 'qiskit', runtime_available: true, version: '2.5.2' }] }
    global.fetch.mockResolvedValue(ok(payload))
    const res = await getFrameworks()
    expect(res.frameworks[0]).toMatchObject({ name: 'qiskit', runtime_available: true })
    expect(global.fetch).toHaveBeenCalledWith('/api/frameworks', expect.objectContaining({ headers: { 'Content-Type': 'application/json' } }))
  })
})

describe('getHealth', () => {
  it('hits /health', async () => {
    global.fetch.mockResolvedValue(ok({ status: 'ok', service: 'qresolve', version: '0.1.0' }))
    const res = await getHealth()
    expect(res.service).toBe('qresolve')
    expect(global.fetch).toHaveBeenCalledWith('/health', expect.any(Object))
  })
})

describe('solve', () => {
  it('sends code and a traceback-derived error body', async () => {
    global.fetch.mockResolvedValue(ok({ status: 'solved' }))
    await solve({ code: 'x=1', errorText: 'IndexError: boom', framework: 'qiskit' })
    const [url, opts] = global.fetch.mock.calls[0]
    expect(url).toBe('/api/solve')
    expect(opts.method).toBe('POST')
    const body = JSON.parse(opts.body)
    expect(body.code).toBe('x=1')
    expect(body.error).toEqual({ traceback_text: 'IndexError: boom' })
    expect(body.framework).toBe('qiskit')
  })

  it('omits framework when auto-detect and drops empty error text', async () => {
    global.fetch.mockResolvedValue(ok({ status: 'solved' }))
    await solve({ code: 'x=1', errorText: '   ', framework: 'auto' })
    const body = JSON.parse(global.fetch.mock.calls[0][1].body)
    expect(body).not.toHaveProperty('framework')
    expect(body).not.toHaveProperty('error')
  })

  it('throws a network ApiError when fetch rejects', async () => {
    global.fetch.mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(solve({ code: 'x=1' })).rejects.toMatchObject({ kind: 'network' })
  })
})

describe('error mapping', () => {
  it('maps HTTP 422 to a validation ApiError with backend detail', async () => {
    global.fetch.mockResolvedValue(err(422, { detail: 'field required' }))
    const e = await validate({ code: 'x=1' }).catch((x) => x)
    expect(e).toBeInstanceOf(ApiError)
    expect(e.kind).toBe('validation')
    expect(e.status).toBe(422)
    expect(e.message).toBe('field required')
  })

  it('maps HTTP 500 to an http ApiError', async () => {
    global.fetch.mockResolvedValue(err(500, { detail: 'internal crash' }))
    const e = await getHealth().catch((x) => x)
    expect(e.kind).toBe('http')
    expect(e.status).toBe(500)
  })

  it('tolerates a non-JSON error body', async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 503, json: async () => { throw new Error('nope') } })
    const e = await getFrameworks().catch((x) => x)
    expect(e.kind).toBe('http')
    expect(e.message).toContain('503')
  })
})
