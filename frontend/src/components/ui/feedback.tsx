import clsx from 'clsx'
import { AlertTriangle, CheckCircle2, Info, OctagonAlert, RotateCw, X } from 'lucide-react'
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { ApiError } from '../../lib/api'
import { Button } from './button'

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx('skeleton rounded-[var(--radius-control)]', className)} aria-hidden />
}

export function PageSkeleton() {
  return (
    <div className="flex flex-col gap-4" role="status" aria-label="Loading">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-4 w-96 max-w-full" />
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <Skeleton className="h-28" /><Skeleton className="h-28" /><Skeleton className="h-28" />
      </div>
      <Skeleton className="h-64" />
    </div>
  )
}

/** An empty screen is an invitation to act: say what's missing and offer the one next step. */
export function EmptyState({ icon, title, body, action, className, headingLevel = 3 }: { icon?: ReactNode; title: string; body?: ReactNode; action?: ReactNode; className?: string; headingLevel?: 2 | 3 }) {
  const H = headingLevel === 2 ? 'h2' : 'h3'
  return (
    <div className={clsx('surface-card flex flex-col items-start gap-4 rounded-[var(--radius-panel)] p-6 sm:p-7', className)}>
      {icon && <div className="flex size-12 items-center justify-center rounded-[var(--radius-card)] bg-indigo-soft text-indigo [&_svg]:size-6" aria-hidden>{icon}</div>}
      <div>
        <H className="text-[1.05rem] font-semibold">{title}</H>
        {body && <p className="mt-1 max-w-prose text-[0.95rem] leading-relaxed text-muted">{body}</p>}
      </div>
      {action}
    </div>
  )
}

export function ErrorState({ error, onRetry, title }: { error: unknown; onRetry?: () => void; title?: string }) {
  const msg = error instanceof ApiError ? error.message : 'Something went wrong while loading this.'
  return (
    <div role="alert" className="flex flex-col items-start gap-3 rounded-[var(--radius-panel)] border border-critical/25 bg-critical-soft/90 p-5 shadow-[var(--elev-1)]">
      <div className="flex items-center gap-2 font-semibold text-critical"><OctagonAlert className="size-5" aria-hidden />{title ?? "Couldn't load this"}</div>
      <p className="text-[0.95rem]">{msg}</p>
      {onRetry && <Button variant="secondary" size="sm" icon={<RotateCw className="size-4" />} onClick={onRetry}>Try again</Button>}
    </div>
  )
}

type Tone = 'info' | 'caution' | 'critical' | 'positive' | 'saathi'
const toneStyles: Record<Tone, string> = {
  info: 'bg-indigo-soft border-indigo/20',
  caution: 'bg-caution-soft border-caution/25',
  critical: 'bg-critical-soft border-critical/25',
  positive: 'bg-positive-soft border-positive/25',
  saathi: 'bg-marigold-soft border-marigold/40',
}
const toneIcon: Record<Tone, ReactNode> = {
  info: <Info className="size-5 text-indigo" aria-hidden />,
  caution: <AlertTriangle className="size-5 text-caution" aria-hidden />,
  critical: <OctagonAlert className="size-5 text-critical" aria-hidden />,
  positive: <CheckCircle2 className="size-5 text-positive" aria-hidden />,
  saathi: <Info className="size-5 text-marigold-deep" aria-hidden />,
}

export function Callout({ tone = 'info', title, children, action, className }: { tone?: Tone; title?: ReactNode; children?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={clsx('flex gap-3 rounded-[var(--radius-card)] border p-4', toneStyles[tone], className)}>
      <div className="mt-0.5 shrink-0">{toneIcon[tone]}</div>
      <div className="flex min-w-0 flex-1 flex-col gap-1 text-[0.95rem]">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className="text-ink/90">{children}</div>}
        {action && <div className="mt-2">{action}</div>}
      </div>
    </div>
  )
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return <span role="status" aria-label={label} className="inline-block size-5 animate-spin rounded-full border-2 border-line border-t-indigo" />
}

/* --- toasts ------------------------------------------------------------ */

type ToastItem = { id: number; title: string; tone: 'positive' | 'critical' | 'info' }
const ToastCtx = createContext<(t: Omit<ToastItem, 'id'>) => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const push = useCallback((t: Omit<ToastItem, 'id'>) => {
    const id = Date.now() + Math.random()
    setItems((s) => [...s, { ...t, id }])
    setTimeout(() => setItems((s) => s.filter((x) => x.id !== id)), 4500)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-20 z-[60] flex flex-col items-center gap-2 px-4 lg:bottom-6" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={clsx('window-in pointer-events-auto flex max-w-md items-center gap-3 rounded-full py-2.5 pl-4 pr-2 text-[0.95rem] text-white',
            t.tone === 'critical' ? 'bg-critical shadow-[var(--elev-3)]' : 'glass-dark')}>
            {t.tone === 'positive' && <CheckCircle2 className="size-5 text-marigold" aria-hidden />}
            <span>{t.title}</span>
            <button className="ml-1 inline-flex size-8 items-center justify-center rounded-full opacity-75 hover:bg-white/10 hover:opacity-100" aria-label="Dismiss" onClick={() => setItems((s) => s.filter((x) => x.id !== t.id))}><X className="size-4" /></button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

export const useToast = () => useContext(ToastCtx)

export function errorMessage(e: unknown): string {
  return e instanceof ApiError ? e.message : 'Something went wrong. Try again.'
}
