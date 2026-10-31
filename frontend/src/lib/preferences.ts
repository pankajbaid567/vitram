import { useCallback, useState } from 'react'

/** A per-browser preference (e.g. chart vs table). Storage can be blocked, so every access is guarded and the app works without it. */
type Widen<T> = T extends boolean ? boolean : T extends string ? string : T

export function usePreference<T extends string | boolean>(key: string, initial: T): [Widen<T>, (v: Widen<T>) => void] {
  const full = `vitram:${key}`
  const [value, setValue] = useState<Widen<T>>(() => {
    try {
      const raw = window.localStorage.getItem(full)
      return raw === null ? (initial as Widen<T>) : (JSON.parse(raw) as Widen<T>)
    } catch { return initial as Widen<T> }
  })
  const set = useCallback((v: Widen<T>) => {
    setValue(v)
    try { window.localStorage.setItem(full, JSON.stringify(v)) } catch { /* private mode or blocked: keep it for this visit only */ }
  }, [full])
  return [value, set]
}
