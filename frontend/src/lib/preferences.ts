import { useCallback, useState } from 'react'

/** A per-browser preference (e.g. chart vs table). Storage can be blocked, so every access is guarded and the app works without it. */
export function usePreference<T extends string | boolean>(key: string, initial: T): [T, (v: T) => void] {
  const full = `vitram:${key}`
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = window.localStorage.getItem(full)
      return raw === null ? initial : (JSON.parse(raw) as T)
    } catch { return initial }
  })
  const set = useCallback((v: T) => {
    setValue(v)
    try { window.localStorage.setItem(full, JSON.stringify(v)) } catch { /* private mode or blocked: keep it for this visit only */ }
  }, [full])
  return [value, set]
}
