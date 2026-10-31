import { useMutation } from '@tanstack/react-query'
import { ArrowRight, RotateCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '../../components/ui/button'
import { Callout, errorMessage } from '../../components/ui/feedback'
import { type ApiError, post } from '../../lib/api'
import type { DocumentRow } from '../../lib/types'
import { documentLink } from './duplicates'

/** A duplicate upload isn't an error the user can fix by retrying: say which document it is, and offer to open it
 * or read it again (which re-runs the latest pipeline, including OCR for photos and scans). */
const TYPE_LABEL: Record<string, string> = { bank_statement: 'a bank statement', insurance_policy: 'an insurance policy', loan_document: 'a loan document', receipt: 'a receipt' }

export function DuplicateNotice({ error, onReread, expectedType }: { error: ApiError; onReread: (d: DocumentRow) => void; expectedType?: string }) {
  const d = error.details ?? {}
  const otherType = !!expectedType && !!d.type && d.type !== expectedType
  const again = useMutation({ mutationFn: () => post<DocumentRow>(`/documents/${d.document_id}/reprocess`), onSuccess: onReread })
  return (
    <Callout tone="caution" title="You've already uploaded this file"
      action={d.document_id && (
        <div className="flex flex-wrap items-center gap-2">
          <Link to={documentLink(d as any)} className="inline-flex min-h-10 items-center gap-1 rounded-[var(--radius-control)] bg-white/80 px-3 text-sm font-medium text-indigo shadow-[var(--elev-1)] hover:text-indigo-dark">Open it<ArrowRight className="size-4" aria-hidden /></Link>
          {!otherType && <Button size="sm" variant="secondary" icon={<RotateCw className="size-4" />} loading={again.isPending} onClick={() => again.mutate()}>Read it again</Button>}
        </div>
      )}>
      {otherType ? (
        <p>It was uploaded as {TYPE_LABEL[d.type] ?? 'another type'} (<b>{d.display_name}</b>). Open it there — or delete it in Documents & data first if you want to add it as {TYPE_LABEL[expectedType!] ?? 'this type'}.</p>
      ) : (
        <p>It's in Documents & data as <b>{d.display_name ?? 'an earlier upload'}</b>. Reading it again uses VITRAM's latest reader{d.read_from_scan ? '' : ', including photos and scans'}. Values you already checked will need checking again.</p>
      )}
      {again.isError && <p className="mt-1 text-critical">{errorMessage(again.error)}</p>}
    </Callout>
  )
}
