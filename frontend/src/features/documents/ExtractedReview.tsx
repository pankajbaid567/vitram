import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Check, Pencil, X } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Button } from '../../components/ui/button'
import { SourceLink, TrustMark } from '../../components/ui/data'
import { Input } from '../../components/ui/field'
import { errorMessage, Skeleton, useToast } from '../../components/ui/feedback'
import { get, patch, post } from '../../lib/api'
import { date, inr } from '../../lib/format'
import type { DocFact, DocumentRow } from '../../lib/types'

/** Review what VITRAM read from one document: confirm, correct or reject each value. Nothing is confirmed in bulk. */
export function ExtractedReview({ docId, compact }: { docId: string; compact?: boolean }) {
  const q = useQuery({ queryKey: ['facts', docId], queryFn: () => get<{ document: DocumentRow; facts: DocFact[] }>(`/documents/${docId}/facts`) })
  if (q.isLoading) return <div className="flex flex-col gap-2"><Skeleton className="h-16" /><Skeleton className="h-16" /><Skeleton className="h-16" /></div>
  if (q.isError || !q.data) return <p className="text-sm text-critical">{errorMessage(q.error)}</p>
  const { document: doc, facts } = q.data
  const checked = facts.filter((f) => f.state === 'confirmed' || f.state === 'rejected').length
  const groups = new Map<string, DocFact[]>()
  for (const f of facts) {
    const g = f.citation.section && f.fact_type !== 'receipt' ? f.citation.section : f.key === 'items' ? 'Items' : ['cgst', 'sgst', 'igst', 'cess', 'gst', 'vat', 'gst_total', 'utgst'].some((k) => f.key.startsWith(k)) ? 'Taxes' : 'Details'
    groups.set(g, [...(groups.get(g) ?? []), f])
  }
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted"><span className="num font-semibold text-ink">{checked}</span> of {facts.length} values checked</p>
        <span role="progressbar" aria-label="Values checked" aria-valuemin={0} aria-valuemax={facts.length} aria-valuenow={checked}
          className="h-1.5 w-40 overflow-hidden rounded-full bg-ink/[0.08]"><span className="block h-full rounded-full bg-positive" style={{ width: `${facts.length ? (checked / facts.length) * 100 : 0}%` }} /></span>
      </div>
      {doc.read_from_scan && (
        <p className="rounded-[var(--radius-control)] border border-dashed border-indigo/35 bg-indigo-soft/40 px-3 py-2 text-sm">
          Read from a {doc.mime?.startsWith('image/') ? 'photo' : 'scan'}{doc.ocr?.on_device ? ' on this device' : doc.ocr?.provider === 'gemini' ? ' by Gemini' : ''}. OCR can misread digits — check each value against the document.
        </p>
      )}
      {facts.length === 0 && <p className="text-sm text-muted">VITRAM didn't find any values in this document.</p>}
      {[...groups.entries()].map(([g, fs]) => (
        <section key={g} aria-label={g}>
          {groups.size > 1 && <h3 className="mb-1.5 text-sm font-semibold text-muted">{g}</h3>}
          <ul className="flex flex-col gap-2">{fs.map((f) => <FactRow key={f.id} fact={f} doc={doc} compact={compact} />)}</ul>
        </section>
      ))}
    </div>
  )
}

function display(f: DocFact): string {
  const v = f.value
  if (v == null || v === '') return 'Not found'
  if (typeof v === 'number') return f.unit === 'INR' ? inr(v, { paise: !Number.isInteger(v) }) : String(v)
  if (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v)) return date(v)
  if (Array.isArray(v)) return typeof v[0] === 'object' && v[0]?.name ? v.map((x: any) => x.name).join(', ') : `${v.length} items`
  if (typeof v === 'boolean') return v ? 'Yes' : 'No'
  return String(v)
}

function FactRow({ fact: f, doc, compact }: { fact: DocFact; doc: DocumentRow; compact?: boolean }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  const isDate = typeof f.value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(f.value)
  const editable = !Array.isArray(f.value) && typeof f.value !== 'object'
  const [val, setVal] = useState(f.value == null ? '' : String(f.value))
  const refresh = () => ['facts', 'doc', 'documents', 'receipt', 'policy', 'loan-doc'].forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
  const confirm = useMutation({ mutationFn: () => patch(`/documents/${doc.id}/facts/${f.id}`, { confirm_only: true }), onSuccess: refresh, onError: (e) => toast({ title: errorMessage(e), tone: 'critical' }) })
  const correct = useMutation({
    mutationFn: () => patch(`/documents/${doc.id}/facts/${f.id}`, { value: val }),
    onSuccess: () => { refresh(); setEditing(false); toast({ title: 'Correction saved', tone: 'positive' }) },
    onError: (e) => toast({ title: errorMessage(e), tone: 'critical' }),
  })
  const reject = useMutation({ mutationFn: () => post(`/documents/${doc.id}/facts/${f.id}/reject`), onSuccess: refresh, onError: (e) => toast({ title: errorMessage(e), tone: 'critical' }) })
  const mark = f.state === 'extracted' && doc.read_from_scan ? 'scan' : f.state
  const low = f.state === 'extracted' && f.confidence < 0.6
  return (
    <li className={clsx('rounded-[var(--radius-card)] border p-3.5 transition-colors', f.state === 'rejected' ? 'border-dashed border-line-strong bg-white/40' : low ? 'border-caution/35 bg-caution-soft/40' : 'border-white/80 bg-white/75')}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-sm text-muted">{f.label}</p>
          {editing ? (
            <form className="mt-1 flex flex-wrap gap-2" onSubmit={(e: FormEvent) => { e.preventDefault(); correct.mutate() }}>
              <Input aria-label={`Correct ${f.label}`} type={isDate ? 'date' : 'text'} inputMode={typeof f.value === 'number' ? 'decimal' : undefined}
                value={val} onChange={(e) => setVal(e.target.value)} className="min-h-10 max-w-xs" autoFocus />
              <Button type="submit" size="sm" loading={correct.isPending}>Save</Button>
              <Button size="sm" variant="quiet" onClick={() => { setEditing(false); setVal(f.value == null ? '' : String(f.value)) }}>Cancel</Button>
            </form>
          ) : (
            <p className={clsx('num mt-0.5 font-semibold', f.state === 'rejected' && 'text-muted line-through')}>{display(f)}</p>
          )}
          {Array.isArray(f.value) && typeof f.value[0] === 'object' && !compact && (
            <table className="num mt-2 w-full max-w-md text-sm">
              <thead className="sr-only"><tr><th>Item</th><th>Quantity</th><th>Amount</th></tr></thead>
              <tbody className="divide-y divide-[var(--glass-hairline)]">
                {f.value.map((it: any, i: number) => <tr key={i}><td className="py-1 pr-2">{it.name}</td><td className="py-1 pr-2 text-muted">{it.quantity != null ? `×${it.quantity}` : ''}</td><td className="py-1 text-right">{inr(it.amount, { paise: true })}</td></tr>)}
              </tbody>
            </table>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <TrustMark state={mark as any} />
          {low && <span className="text-xs font-medium text-caution">Low confidence</span>}
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <span className="min-w-0 truncate text-xs text-muted">{f.citation.snippet ? <>“{f.citation.snippet}”</> : 'No source line stored'}</span>
        <span className="flex flex-wrap items-center gap-1">
          <SourceLink citation={f.citation} label={f.citation.page ? 'Source' : 'Source'} />
          {f.state !== 'confirmed' && f.state !== 'rejected' && !editing && (
            <Button size="sm" variant="secondary" icon={<Check className="size-4" />} loading={confirm.isPending} onClick={() => confirm.mutate()} aria-label={`Confirm ${f.label}`}>Confirm</Button>
          )}
          {editable && f.state !== 'rejected' && !editing && (
            <Button size="sm" variant="quiet" icon={<Pencil className="size-4" />} onClick={() => setEditing(true)} aria-label={`Correct ${f.label}`}>Correct</Button>
          )}
          {f.state !== 'rejected' && !editing && (
            <Button size="sm" variant="quiet" icon={<X className="size-4" />} loading={reject.isPending} onClick={() => reject.mutate()} aria-label={`Reject ${f.label}`} className="hover:text-critical">Reject</Button>
          )}
        </span>
      </div>
    </li>
  )
}
