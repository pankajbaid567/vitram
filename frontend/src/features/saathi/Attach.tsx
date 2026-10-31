import { CircleAlert, FileText, Loader2, Paperclip, ReceiptText, ShieldCheck } from 'lucide-react'
import { DropdownMenu } from 'radix-ui'
import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { IMAGE_EXT, useVision } from '../../lib/vision'
import type { AttachKind, AttachState } from './useAttach'

type Kind = AttachKind
const KINDS: { kind: Kind; label: string; icon: typeof ReceiptText }[] = [
  { kind: 'receipt', label: 'Receipt or invoice', icon: ReceiptText },
  { kind: 'insurance_policy', label: 'Insurance policy', icon: ShieldCheck },
  { kind: 'loan_document', label: 'Loan document', icon: FileText },
]

export function AttachButton({ onPick, disabled }: { onPick: (kind: Kind, file: File) => void; disabled?: boolean }) {
  const vision = useVision()
  const input = useRef<HTMLInputElement>(null)
  const [kind, setKind] = useState<Kind>('receipt')
  const accept = vision?.configured ? `.pdf,${IMAGE_EXT}` : '.pdf'
  return (
    <>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger disabled={disabled} aria-label="Attach a document"
          className="inline-flex size-11 shrink-0 items-center justify-center rounded-full text-muted transition-colors hover:bg-ink/5 hover:text-ink disabled:opacity-40">
          <Paperclip className="size-5" aria-hidden />
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content side="top" align="start" sideOffset={8} className="window-in z-[60] w-64 rounded-[var(--radius-card)] border border-[var(--glass-hairline)] bg-white p-1.5 shadow-[var(--elev-4)]">
            <p className="px-3 pb-1 pt-2 text-xs text-muted">{vision?.configured ? 'PDF or photo' : 'PDF (photos need OCR on this server)'}</p>
            {KINDS.map(({ kind: k, label, icon: Icon }) => (
              <DropdownMenu.Item key={k} onSelect={() => { setKind(k); setTimeout(() => input.current?.click(), 0) }}
                className="flex min-h-11 cursor-pointer items-center gap-3 rounded-[var(--radius-control)] px-3 text-[0.95rem] outline-none data-[highlighted]:bg-indigo-soft/70">
                <Icon className="size-4 text-muted" aria-hidden />{label}
              </DropdownMenu.Item>
            ))}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
      <input ref={input} type="file" accept={accept} className="sr-only" tabIndex={-1} aria-hidden
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onPick(kind, f); e.target.value = '' }} />
    </>
  )
}

const STAGE_TEXT: Record<string, string> = { reading: 'Opening it…', reading_scan: 'Reading the photo…', extracting: 'Finding the key values…', linking: 'Linking it up…' }

export function AttachStatus({ state, stage, onClear }: { state: AttachState | null; stage?: string; onClear: () => void }) {
  if (!state) return null
  return (
    <div className="mx-3 mb-2 flex items-start gap-2 rounded-[var(--radius-control)] border border-[var(--glass-hairline)] bg-white/90 px-3 py-2 text-sm" role="status">
      {state.error ? <CircleAlert className="mt-0.5 size-4 shrink-0 text-critical" aria-hidden /> : <Loader2 className="mt-0.5 size-4 shrink-0 animate-spin text-indigo" aria-hidden />}
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{state.name}</p>
        <p className={state.error ? 'text-critical' : 'text-muted'}>
          {state.error ?? (state.progress != null ? `Uploading… ${state.progress}%` : STAGE_TEXT[stage ?? ''] ?? 'Reading…')}
        </p>
        {state.consent && <Link to="/settings" className="text-xs font-medium text-indigo underline underline-offset-2">Allow document processing in Settings</Link>}
      </div>
      {state.error && <button type="button" onClick={onClear} className="-my-1 min-h-8 rounded-full px-2 text-xs font-medium text-indigo hover:bg-indigo-soft">Dismiss</button>}
    </div>
  )
}
