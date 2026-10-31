import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { usePreference } from '../lib/preferences'

describe('usePreference', () => {
  beforeEach(() => window.localStorage.clear())

  it('starts from the default, persists a change and restores it next time', () => {
    const first = renderHook(() => usePreference('t', false))
    expect(first.result.current[0]).toBe(false)
    act(() => first.result.current[1](true))
    expect(first.result.current[0]).toBe(true)
    expect(renderHook(() => usePreference('t', false)).result.current[0]).toBe(true)
  })

  it('still works when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    const { result } = renderHook(() => usePreference('t', false))
    act(() => result.current[1](true))
    expect(result.current[0]).toBe(true)
    vi.restoreAllMocks()
  })
})
