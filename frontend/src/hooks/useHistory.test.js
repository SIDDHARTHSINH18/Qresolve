import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { useHistory } from './useHistory.js'

const KEY = 'qresolve.history.v1'

beforeEach(() => localStorage.clear())

describe('useHistory', () => {
  it('adds to the front and persists to localStorage', () => {
    const { result } = renderHook(() => useHistory())
    act(() => result.current.add({ id: 'a', ts: 1, response: {} }))
    act(() => result.current.add({ id: 'b', ts: 2, response: {} }))
    expect(result.current.entries.map((e) => e.id)).toEqual(['b', 'a'])
    expect(JSON.parse(localStorage.getItem(KEY)).map((e) => e.id)).toEqual(['b', 'a'])
  })

  it('caps stored entries at 20', () => {
    const { result } = renderHook(() => useHistory())
    act(() => {
      for (let i = 0; i < 25; i++) result.current.add({ id: String(i), ts: i, response: {} })
    })
    expect(result.current.entries.length).toBe(20)
    expect(result.current.entries[0].id).toBe('24')
  })

  it('removes by id and clears', () => {
    const { result } = renderHook(() => useHistory())
    act(() => result.current.add({ id: 'x', ts: 1, response: {} }))
    act(() => result.current.add({ id: 'y', ts: 2, response: {} }))
    act(() => result.current.remove('x'))
    expect(result.current.entries.map((e) => e.id)).toEqual(['y'])
    act(() => result.current.clear())
    expect(result.current.entries).toEqual([])
    expect(localStorage.getItem(KEY)).toBe('[]')
  })

  it('degrades silently on malformed stored JSON', () => {
    localStorage.setItem(KEY, '{not json')
    const { result } = renderHook(() => useHistory())
    expect(result.current.entries).toEqual([])
  })
})
