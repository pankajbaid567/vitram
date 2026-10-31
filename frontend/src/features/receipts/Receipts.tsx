import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Camera, Check, Link2, Link2Off, MessageCircle, ReceiptText, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Button, LinkButton } from '../../components/ui/button'
import { Badge, IconTile, Money, PageHeader, Panel } from '../../components/ui/data'
import { Callout, errorMessage, ErrorState, PageSkeleton, useToast } from '../../components/ui/feedback'
import { FileDrop } from '../../components/ui/filedrop'
import { ApiError, get, post, upload } from '../../lib/api'
import { date } from '../../lib/format'
import type { DocumentRow } from '../../lib/types'
import { IMAGE_EXT, useVision } from '../../lib/vision'
import { DuplicateNotice } from '../documents/DuplicateNotice'
import { isDuplicate } from '../documents/duplicates'
import { ExtractedReview } from '../documents/ExtractedReview'
import { ConsentGate, DOC_CONSENT_BODY, ProcessingSteps, useDocumentPoll } from '../onboarding/Onboarding'
import { useSaathi, useSaathiPage } from '../saathi/context'

const CRUMBS = [{ label: 'Home', to: '/' }, { label: 'Documents & data', to: '/documents' }]

export function ReceiptScan() {
  useSaathiPage('dashboard')
  const vision = useVision()
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [progress, setProgress] = useState<number | null>(null)
  const [docId, setDocId] = useState<string | null>(null)
  const [dup, setDup] = useState<ApiError | null>(null)
  const poll = useDocumentPoll(docId ?? undefined)
  const m = useMutation({
    mutationFn: () => { const fd = new FormData(); fd.append('file', file!); fd.append('type', 'receipt'); return upload<DocumentRow>('/documents', fd, setProgress) },
    onSuccess: (d) => setDocId(d.id),
    onError: (e) => { if (isDuplicate(e)) { setDup(e as ApiError); setErr(null) } else setErr(errorMessage(e)) },
    onSettled: () => setProgress(null),
  })
  useEffect(() => {
    if (poll.data && ['ready', 'needs_review'].includes(poll.data.status)) navigate(`/documents/receipts/${poll.data.id}`, { replace: true })
  }, [poll.data, navigate])
  const accept = vision?.configured ? `.pdf,${IMAGE_EXT}` : '.pdf'
  return (
    <>
      <PageHeader crumbs={CRUMBS} title="Scan a receipt or invoice"
        description="Photograph a bill or upload an e-invoice. VITTRM reads the merchant, date, total, GST and items, and you check them before anything is used." />
      <div className="grid max-w-5xl gap-6 @4xl:grid-cols-[1.3fr_1fr]">
        {poll.data ? (
          <Panel className="p-6">
            <ProcessingSteps doc={poll.data} />
            {poll.data.status === 'failed' && <>
              <Callout tone="critical" className="mt-4" title="Couldn't read this receipt">{poll.data.error_message}</Callout>
              <Button className="mt-4" variant="secondary" onClick={() => { setDocId(null); setFile(null) }}>Try another photo</Button>
            </>}
          </Panel>
        ) : (
          <ConsentGate purpose="financial_documents" title="Before you upload" body={DOC_CONSENT_BODY}>
            <Panel className="flex flex-col gap-4 p-6">
              {!vision?.configured && vision && (
                <Callout tone="info" title="Photos can't be read on this server yet">
                  Digital PDF invoices (from email or apps) still work. {vision.note}
                </Callout>
              )}
              {dup && <DuplicateNotice expectedType="receipt" error={dup} onReread={(d) => { setDup(null); setDocId(d.id) }} />}
              <FileDrop accept={accept} file={file} onFile={(f) => { setFile(f); setDup(null) }} error={err} camera={vision?.configured} progress={progress} scanNote={vision?.configured ? (vision.on_device ? 'Photos and scans are read on this device' : 'Photos and scans are read by Gemini') : undefined}
                hint={vision?.configured ? 'Photo (JPG, PNG) or PDF · up to 15 MB' : 'PDF invoice · up to 15 MB'} />
              <Button size="lg" className="w-fit" disabled={!file} loading={m.isPending} onClick={() => { setErr(null); m.mutate() }}>Read receipt</Button>
            </Panel>
          </ConsentGate>
        )}
        <aside className="flex flex-col gap-4">
          <Panel className="p-5">
            <h2 className="mb-3 flex items-center gap-2 font-semibold"><Camera className="size-5 text-indigo" aria-hidden />For a clear photo</h2>
            <ul className="flex flex-col gap-2 text-sm text-ink/80">
              <li>Lay the receipt flat in good light, without shadows.</li>
              <li>Fit the whole bill in the frame, top to bottom.</li>
              <li>Long receipts: photograph them in parts as separate uploads.</li>
            </ul>
          </Panel>
          <div className="wash-positive flex items-start gap-3 rounded-[var(--radius-card)] p-4 text-sm">
            <ShieldCheck className="mt-0.5 size-5 shrink-0 text-positive" aria-hidden />
            <p>{vision?.on_device ? 'Photos are read on this device. ' : ''}Location and camera details are removed from photos before they're stored. Card numbers on a bill are cut to the last 4 digits.</p>
          </div>
        </aside>
      </div>
    </>
  )
}

export function ReceiptDetail() {
  const { id } = useParams()
  useSaathiPage('document', id)
  const { ask } = useSaathi()
  const qc = useQueryClient()
  const toast = useToast()
  const q = useQuery({ queryKey: ['receipt', id], queryFn: () => get<any>(`/documents/${id}/receipt`),
    retry: (n, e) => !(e instanceof ApiError && e.status === 404) && n < 2 })
  const link = useMutation({
    mutationFn: (txn: string | null) => post(`/documents/${id}/receipt/link`, { transaction_id: txn }),
    onSuccess: (_d, txn) => { qc.invalidateQueries({ queryKey: ['receipt', id] }); toast({ title: txn ? 'Matched to the transaction' : 'Match removed', tone: 'positive' }) },
    onError: (e) => toast({ title: errorMessage(e), tone: 'critical' }),
  })
  if (q.isLoading) return <PageSkeleton />
  if (q.isError) {
    const notReceipt = q.error instanceof ApiError && q.error.status === 404
    return notReceipt ? (
      <>
        <PageHeader crumbs={CRUMBS} title="Receipt not found" description="This document isn't a receipt in your workspace — it may have been uploaded as another type, or deleted." />
        <LinkButton to="/documents" variant="secondary">Go to Documents & data</LinkButton>
      </>
    ) : <ErrorState error={q.error} onRetry={() => q.refetch()} />
  }
  const { document: doc, receipt: r, linked_transaction: linked, candidates, note } = q.data
  const confirmedAll = ['merchant', 'total', 'purchase_date'].every((k) => r.confirmed?.[k])
  return (
    <>
      <PageHeader crumbs={[...CRUMBS, { label: 'Receipts' }]} title={r.merchant ?? 'Receipt'}
        description={<span className="flex flex-wrap items-center gap-2">{doc.display_name} · uploaded {date(doc.upload_time)}{doc.read_from_scan && <Badge tone="indigo">Read from a {doc.mime?.startsWith('image/') ? 'photo' : 'scan'}</Badge>}</span>}
        actions={<>
          <Button variant="secondary" icon={<MessageCircle className="size-4" />} onClick={() => ask('Summarise this receipt')}>Ask about this receipt</Button>
          <a href={`/api/documents/${doc.id}/file`} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center rounded-[var(--radius-control)] px-4 text-[0.95rem] font-medium text-indigo hover:bg-indigo-soft">Open original<span className="sr-only"> (opens in a new tab)</span></a>
        </>} />

      <section className="mb-6 grid gap-4 @xl:grid-cols-2 @5xl:grid-cols-4" aria-label="Receipt summary">
        {[
          { label: 'Total', value: r.total != null ? <Money value={r.total} paise /> : 'Not found', ok: r.confirmed?.total },
          { label: 'Date', value: r.purchase_date ? date(r.purchase_date) : 'Not found', ok: r.confirmed?.purchase_date },
          { label: 'Tax (GST)', value: r.gst_total != null ? <Money value={r.gst_total} paise /> : 'Not shown', ok: r.confirmed?.gst_total },
          { label: 'Paid by', value: r.payment_method ?? 'Not shown', ok: r.confirmed?.payment_method },
        ].map((x) => (
          <div key={x.label} className="surface-card rounded-[var(--radius-card)] p-4">
            <p className="flex items-center justify-between gap-2 text-sm text-muted">{x.label}{x.ok ? <Badge tone="positive"><Check className="size-3" aria-hidden />Checked</Badge> : <Badge tone="caution">To check</Badge>}</p>
            <p className="num mt-1 text-[1.25rem] font-semibold">{x.value}</p>
          </div>
        ))}
      </section>

      <div className="grid items-start gap-6 @5xl:grid-cols-[1.4fr_1fr]">
        <Panel className="p-5 sm:p-6" aria-labelledby="rv-h">
          <div className="mb-4 flex items-start gap-3">
            <IconTile tone="indigo"><ReceiptText /></IconTile>
            <div><h2 id="rv-h" className="text-[1.1rem] font-semibold">Check what VITTRM read</h2>
              <p className="text-sm text-muted">Confirm, correct or reject each value. Rejected values are never used.</p></div>
          </div>
          <ExtractedReview docId={doc.id} />
          {doc.warnings?.length > 0 && <div className="mt-4 flex flex-col gap-2">{doc.warnings.map((w: string) => <Callout key={w} tone="caution">{w}</Callout>)}</div>}
        </Panel>

        <Panel className="p-5 sm:p-6" aria-labelledby="match-h">
          <div className="mb-3 flex items-start gap-3">
            <IconTile tone="green"><Link2 /></IconTile>
            <div><h2 id="match-h" className="text-[1.1rem] font-semibold">Match to a bank transaction</h2>
              <p className="text-sm text-muted">{note}</p></div>
          </div>
          {linked ? (
            <div className="rounded-[var(--radius-card)] border border-positive/30 bg-positive-soft/60 p-4">
              <p className="text-sm font-medium text-positive">Matched</p>
              <p className="mt-1 font-semibold">{linked.description}</p>
              <p className="num text-sm text-muted">{date(linked.date)} · <Money value={linked.amount} paise /></p>
              <Button size="sm" variant="quiet" className="mt-2" icon={<Link2Off className="size-4" />} loading={link.isPending} onClick={() => link.mutate(null)}>Remove match</Button>
            </div>
          ) : r.total == null ? (
            <p className="text-sm text-muted">Add or confirm the total first, then VITTRM can look for the payment.</p>
          ) : candidates.length === 0 ? (
            <p className="text-sm text-muted">No bank transaction matches this total within a few days of the bill. That's fine — the payment may be on a card or statement you haven't uploaded. Nothing is added automatically.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {candidates.map((c: any) => (
                <li key={c.id} className="rounded-[var(--radius-card)] border border-white/80 bg-white/75 p-3.5">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0"><p className="truncate font-medium">{c.description}</p><p className="num text-sm text-muted">{date(c.date)} · <Money value={c.amount} paise /></p></div>
                    <Button size="sm" loading={link.isPending && link.variables === c.id} onClick={() => link.mutate(c.id)}>This one</Button>
                  </div>
                  <p className="mt-1.5 text-xs text-muted">{c.reasons.join(' · ')}</p>
                </li>
              ))}
            </ul>
          )}
          {!confirmedAll && <p className="mt-4 text-xs text-muted">Tip: confirm the merchant, date and total first so the suggestions use checked values.</p>}
          <div className="mt-5 border-t border-[var(--glass-hairline)] pt-4">
            <LinkButton to="/documents/receipts/new" variant="secondary" size="sm" icon={<Camera className="size-4" />}>Scan another receipt</LinkButton>
            <Link to="/documents?type=receipt" className="ml-3 text-sm font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">All receipts</Link>
          </div>
        </Panel>
      </div>
    </>
  )
}
