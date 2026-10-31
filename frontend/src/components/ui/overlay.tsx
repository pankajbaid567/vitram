import clsx from 'clsx'
import { X } from 'lucide-react'
import { Dialog as D } from 'radix-ui'
import { useRef, type ReactNode } from 'react'

/* oxlint-disable react/refs -- deliberate: focus must be captured *during render*. Radix moves focus into the dialog in a child
   effect, before any parent effect or layout effect could read document.activeElement (verified by the axe/keyboard audit). */
/** Radix restores focus only to its own <Trigger>. Our overlays open programmatically, so remember what had
 * focus when they opened and return it on close (WCAG 2.4.3 focus order). */
function useReturnFocus(open: boolean) {
  const last = useRef<HTMLElement | null>(null)
  const wasOpen = useRef(false)
  // Capture during render: Radix moves focus into the dialog in a child effect, before any effect here runs.
  if (open && !wasOpen.current && typeof document !== 'undefined') last.current = document.activeElement as HTMLElement | null
  wasOpen.current = open
  return (e: Event) => {
    const el = last.current
    if (el && document.contains(el)) {
      e.preventDefault()
      el.focus()
    }
  }
}

/* oxlint-enable react/refs */

const OVERLAY = 'overlay-in fixed inset-0 z-50 bg-navy-900/35 backdrop-blur-[3px]'
const CLOSE = 'inline-flex size-11 shrink-0 items-center justify-center rounded-full text-muted transition-colors hover:bg-ink/5 hover:text-ink'

/** Floating side / bottom sheet built on Radix Dialog (focus trap, Esc, aria) — adapted from shadcn/ui v4 sheet.
 * On desktop the right sheet floats inset from the viewport edge as a glass window; on phones it is full-height. */
export const SheetClose = D.Close

export function Sheet({ open, onOpenChange, title, description, children, side = 'right', wide, bare }: {
  open: boolean; onOpenChange: (v: boolean) => void; title: ReactNode; description?: ReactNode; children: ReactNode
  side?: 'right' | 'bottom' | 'left'; wide?: boolean
  /** No header chrome: children render edge to edge and provide their own close button (title stays for screen readers). */
  bare?: boolean
}) {
  const onCloseAutoFocus = useReturnFocus(open)
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className={OVERLAY} />
        <D.Content onCloseAutoFocus={onCloseAutoFocus}
          className={clsx('window-in glass-strong fixed z-50 flex flex-col outline-none',
            side === 'right'
              ? clsx('inset-y-0 right-0 h-full w-full sm:inset-y-3 sm:right-3 sm:h-auto sm:rounded-[var(--radius-window)]', wide ? 'sm:max-w-2xl' : 'sm:max-w-md')
              : side === 'left' ? 'inset-y-0 left-0 h-full w-[min(20rem,88vw)] rounded-r-[var(--radius-window)]'
              : 'inset-x-0 bottom-0 max-h-[92vh] rounded-t-[var(--radius-window)]')}>
          {bare ? (<>
            <D.Title className="sr-only">{title}</D.Title>
            {description ? <D.Description className="sr-only">{description}</D.Description> : <D.Description className="sr-only">Details</D.Description>}
            <div className="relative flex-1 overflow-y-auto overscroll-contain">{children}</div>
          </>) : (<>
          {side === 'bottom' && <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-ink/15" aria-hidden />}
          <div className="flex items-start justify-between gap-3 border-b border-[var(--glass-hairline)] px-6 py-4">
            <div className="min-w-0 pt-1">
              <D.Title className="text-lg font-semibold tracking-[-0.01em]">{title}</D.Title>
              {description ? <D.Description className="mt-0.5 text-sm text-muted">{description}</D.Description> : <D.Description className="sr-only">Details</D.Description>}
            </div>
            <D.Close className={clsx(CLOSE, '-mr-2')} aria-label="Close"><X className="size-5" /></D.Close>
          </div>
          <div className="flex-1 overflow-y-auto overscroll-contain px-6 py-5">{children}</div>
          </>)}
        </D.Content>
      </D.Portal>
    </D.Root>
  )
}

/** Centred floating dialog. Destructive confirmations put the danger action last in `footer`. */
export function Modal({ open, onOpenChange, title, description, children, footer }: {
  open: boolean; onOpenChange: (v: boolean) => void; title: ReactNode; description?: ReactNode; children: ReactNode; footer?: ReactNode
}) {
  const onCloseAutoFocus = useReturnFocus(open)
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className={OVERLAY} />
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center p-4">
          <D.Content onCloseAutoFocus={onCloseAutoFocus}
            className="window-in glass-strong pointer-events-auto flex max-h-[90vh] w-full max-w-lg flex-col rounded-[var(--radius-window)] outline-none">
            <div className="flex items-start justify-between gap-3 px-6 pt-5">
              <div className="min-w-0 pt-1">
                <D.Title className="text-lg font-semibold tracking-[-0.01em]">{title}</D.Title>
                {description ? <D.Description className="mt-1 text-sm text-muted">{description}</D.Description> : <D.Description className="sr-only">Dialog</D.Description>}
              </div>
              <D.Close className={clsx(CLOSE, '-mr-3 -mt-1')} aria-label="Close"><X className="size-5" /></D.Close>
            </div>
            <div className="overflow-y-auto overscroll-contain px-6 py-4">{children}</div>
            {footer && <div className="flex flex-col-reverse gap-2 border-t border-[var(--glass-hairline)] px-6 py-4 sm:flex-row sm:justify-end">{footer}</div>}
          </D.Content>
        </div>
      </D.Portal>
    </D.Root>
  )
}

/** Explicit confirmation for destructive or consequential actions. Nothing happens until the confirm button is pressed. */
export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel, cancelLabel = 'Cancel', onConfirm, busy, danger = true, children, confirmDisabled }: {
  open: boolean; onOpenChange: (v: boolean) => void; title: ReactNode; description?: ReactNode; confirmLabel: string; cancelLabel?: string
  onConfirm: () => void; busy?: boolean; danger?: boolean; children?: ReactNode; confirmDisabled?: boolean
}) {
  return (
    <Modal open={open} onOpenChange={onOpenChange} title={title} description={description}
      footer={<>
        <button type="button" onClick={() => onOpenChange(false)} className="inline-flex min-h-11 items-center justify-center rounded-[var(--radius-control)] px-4 text-[0.95rem] font-medium text-muted transition-colors hover:bg-ink/5 hover:text-ink">{cancelLabel}</button>
        <button type="button" onClick={onConfirm} disabled={busy || confirmDisabled} aria-busy={busy || undefined}
          className={clsx('inline-flex min-h-11 items-center justify-center gap-2 rounded-[var(--radius-control)] px-4 text-[0.95rem] font-medium text-white transition-[filter,opacity] hover:brightness-110 disabled:opacity-55',
            danger ? 'bg-critical shadow-[0_6px_16px_rgb(179_38_30/0.25)]' : 'bg-[image:var(--grad-indigo)] shadow-[0_6px_16px_rgb(52_67_181/0.28)]')}>
          {busy && <span className="size-4 animate-spin rounded-full border-2 border-white/40 border-t-white" aria-hidden />}{confirmLabel}
        </button>
      </>}>
      {children}
    </Modal>
  )
}
