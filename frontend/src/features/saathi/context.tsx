import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

export type SaathiContextType = 'dashboard' | 'loan' | 'card' | 'emi' | 'insurance' | 'emergency' | 'document'

export interface SaathiCtx {
  type: SaathiContextType
  objectId?: string | null
  memberKey?: string | null
}

interface State {
  ctx: SaathiCtx
  setCtx: (c: SaathiCtx) => void
  open: boolean
  setOpen: (v: boolean) => void
  /** Wider assistant window (desktop). */
  expanded: boolean
  setExpanded: (v: boolean) => void
  /** Send a prompt into the panel (e.g. from a page CTA) */
  pending: string | null
  ask: (text: string) => void
  consumePending: () => void
}

const Ctx = createContext<State | null>(null)

export function SaathiProvider({ children }: { children: ReactNode }) {
  const [ctx, setCtx] = useState<SaathiCtx>({ type: 'dashboard' })
  const [open, setOpenState] = useState(false)
  const [pending, setPending] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(false)
  const opener = useRef<HTMLElement | null>(null)
  // The opener button unmounts while the panel is open; on close, focus it again once it is back (WCAG 2.4.3).
  const setOpen = useCallback((v: boolean) => {
    if (v) opener.current = document.activeElement as HTMLElement | null
    setOpenState(v)
    if (!v) {
      requestAnimationFrame(() => {
        const el = opener.current && document.contains(opener.current) ? opener.current
          : (document.querySelector('[data-saathi-opener]') as HTMLElement | null)
        el?.focus()
      })
    }
  }, [])
  const value = useMemo<State>(() => ({
    ctx, setCtx, open, setOpen, pending, expanded, setExpanded,
    ask: (t) => { setPending(t); setOpen(true) },
    consumePending: () => setPending(null),
  }), [ctx, open, pending, expanded, setOpen])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useSaathi() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useSaathi outside provider')
  return v
}

/** Pages declare which context Vitt Saathi should use (RD §11.1). */
export function useSaathiPage(type: SaathiContextType, objectId?: string | null, memberKey?: string | null) {
  const { setCtx } = useSaathi()
  useEffect(() => {
    setCtx({ type, objectId: objectId ?? null, memberKey: memberKey ?? null })
  }, [type, objectId, memberKey, setCtx])
}
