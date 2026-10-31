import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { ArrowRight, AudioLines, BarChart3, CalendarDays, CheckCircle2, Clock3, Database, ExternalLink, Eye, FileSearch, FileText, Info, Landmark, Lightbulb, Loader2, KeyRound, Lock, MessageCircle, MessagesSquare, ReceiptText, ScanText, OctagonAlert, Pencil, Phone, Plug, Plus, RotateCw, Search, Settings2, ShieldCheck, Trash2, Upload, UserRound, UsersRound, X } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Button, IconButton, LinkButton } from '../../components/ui/button'
import { Avatar, Badge, FeatureTile, IconTile, PageHeader, PageHero, Panel, SourceLink, StatCard, TrustMark } from '../../components/ui/data'
import { DocStack, FamilyArt } from '../../components/illustrations'
import { Field, Input, Select } from '../../components/ui/field'
import { Callout, errorMessage, ErrorState, PageSkeleton, Skeleton, useToast } from '../../components/ui/feedback'
import { ConfirmDialog, Modal, Sheet } from '../../components/ui/overlay'
import { del, get, patch, post } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { date, inr, num, relDays } from '../../lib/format'
import type { DocFact, DocumentRow } from '../../lib/types'
import { MemberForm, RELATIONS } from '../onboarding/Onboarding'
import { useSaathi, useSaathiPage } from '../saathi/context'
import { useVision } from '../../lib/vision'
import { ExtractedReview } from './ExtractedReview'

/** Status labels say only what the pipeline knows: "Ready" means processed, not confirmed by the user. */
const STATUS: Record<string, { label: string; tone: any; icon: ReactNode }> = {
  queued: { label: 'Uploaded', tone: 'neutral', icon: <Clock3 className="size-3.5" aria-hidden /> },
  processing: { label: 'Processing', tone: 'indigo', icon: <Loader2 className="size-3.5 animate-spin" aria-hidden /> },
  needs_review: { label: 'Ready for review', tone: 'caution', icon: <Eye className="size-3.5" aria-hidden /> },
  ready: { label: 'Ready', tone: 'positive', icon: <CheckCircle2 className="size-3.5" aria-hidden /> },
  failed: { label: "Couldn't read", tone: 'critical', icon: <OctagonAlert className="size-3.5" aria-hidden /> },
}
const TYPE_ICON: Record<DocumentRow['type'], { icon: ReactNode; tone: 'indigo' | 'green' | 'violet' | 'amber' }> = {
  bank_statement: { icon: <Landmark />, tone: 'indigo' }, insurance_policy: { icon: <ShieldCheck />, tone: 'green' }, loan_document: { icon: <FileText />, tone: 'violet' },
  receipt: { icon: <ReceiptText />, tone: 'amber' },
  card_document: { icon: <FileText />, tone: 'indigo' },
}

/** Count the purchases the user has *confirmed* on a card statement toward one card's reward estimate (preview first, undoable). */
function SpendReconcile({ doc, card }: { doc: DocumentRow; card: any }) {
  const qc = useQueryClient()
  const toast = useToast()
  const key = ['spend-preview', card.id, doc.id]
  const preview = useQuery({ queryKey: key, queryFn: () => get<any>(`/cards/${card.id}/spend-reconciliation?document_id=${doc.id}`) })
  const done = () => { qc.invalidateQueries({ queryKey: ['cards'] }); qc.invalidateQueries({ queryKey: key }) }
  const apply = useMutation({
    mutationFn: () => post(`/cards/${card.id}/spend-reconciliation`, { document_id: doc.id, replace_existing: true }),
    onSuccess: () => { done(); toast({ title: 'Purchases now count toward this card’s reward estimate', tone: 'positive' }) },
    onError: (e) => toast({ title: errorMessage(e), tone: 'critical' }),
  })
  const undo = useMutation({
    mutationFn: () => del(`/cards/${card.id}/spend-reconciliation`),
    onSuccess: () => { done(); toast({ title: 'Statement purchases no longer counted', tone: 'positive' }) },
    onError: (e) => toast({ title: errorMessage(e), tone: 'critical' }),
  })
  const counted = card.imported_spend?.document_id === doc.id
  if (preview.isLoading) return <Skeleton className="h-16 w-full" />
  if (preview.isError) return <ErrorState error={preview.error} onRetry={() => preview.refetch()} />
  const p = preview.data
  return (
    <div className="space-y-3">
      {p.counted_rows.length === 0
        ? <p className="text-sm text-caution">No purchase rows are confirmed yet. Confirm the ones that are right above; unconfirmed rows are never counted.</p>
        : <>
          <ul className="divide-y divide-line rounded-xl border border-line text-sm">
            {p.counted_rows.map((r: any) => (
              <li key={r.fact_id} className="flex items-center justify-between gap-3 px-3 py-2">
                <span className="min-w-0 truncate">{r.merchant} <span className="text-muted">· {r.category_label}</span></span>
                <span className="num shrink-0 font-medium">{inr(r.amount)}</span>
              </li>
            ))}
          </ul>
          <p className="text-sm text-muted">Total {inr(p.total)} across {Object.keys(p.by_category).length} categories. {p.unconfirmed_rows > 0 && `${p.unconfirmed_rows} unconfirmed row(s) are not counted.`}</p>
        </>}
      <div className="flex flex-wrap gap-2">
        <Button disabled={p.counted_rows.length === 0 || counted} loading={apply.isPending} onClick={() => apply.mutate()}>{counted ? 'Counted' : 'Count these purchases'}</Button>
        {counted && <Button variant="secondary" loading={undo.isPending} onClick={() => undo.mutate()}>Undo</Button>}
      </div>
    </div>
  )
}

function FactsSheet({ doc, onClose }: { doc: DocumentRow | null; onClose: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const q = useQuery({ queryKey: ['facts', doc?.id], queryFn: () => get<any>(`/documents/${doc!.id}/facts`), enabled: !!doc && doc.type !== 'bank_statement' })
  const cards = useQuery({ queryKey: ['cards'], queryFn: () => get<any>('/cards'), enabled: doc?.type === 'card_document' })
  const [edit, setEdit] = useState<string | null>(null)
  const [val, setVal] = useState('')
  const [selectedCard, setSelectedCard] = useState('')
  const [confirmReplace, setConfirmReplace] = useState(false)
  const save = useMutation({
    mutationFn: ({ id, value, confirmOnly }: { id: string; value?: string; confirmOnly?: boolean }) => patch(`/documents/${doc!.id}/facts/${id}`, confirmOnly ? { confirm_only: true } : { value }),
    onSuccess: () => { qc.invalidateQueries(); setEdit(null); toast({ title: 'Fact review saved', tone: 'positive' }) },
    onError: (e) => toast({ title: errorMessage(e), tone: 'critical' }),
  })
  const linkCard = useMutation({
    mutationFn: () => post(`/cards/${selectedCard}/import-document`, { document_id: doc!.id, replace_existing: true }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cards'] }); qc.invalidateQueries({ queryKey: ['dashboard'] }); setConfirmReplace(false); toast({ title: 'Reviewed card facts imported', tone: 'positive' }) },
    onError: (e) => toast({ title: errorMessage(e), tone: 'critical' }),
  })
  const confirmedLast4 = q.data?.facts.find((f: DocFact) => f.key === 'last4' && f.user_verified)?.value
  const matchingCards = (cards.data?.cards ?? []).filter((c: any) => c.last4 && c.last4 === confirmedLast4)
  const selectedCardMatches = matchingCards.some((c: any) => c.id === selectedCard)
  const confirmedValues = q.data?.facts.filter((f: DocFact) => f.user_verified && ['outstanding', 'due_date', 'points_balance'].includes(f.key)).length ?? 0
  return (
    <Sheet open={!!doc} onOpenChange={(o) => !o && onClose()} title={doc?.display_name ?? ''} description="Values VITTRM extracted, with where each came from." wide>
      {doc?.type === 'bank_statement' ? (
        <div className="flex flex-col gap-3 text-[0.95rem]">
          <p>{doc.transactions_found ?? 0} transactions from {date(doc.period_start)} to {date(doc.period_end)}.</p>
          <LinkButton to="/profile/review" variant="secondary" className="w-fit">Review and correct in your profile</LinkButton>
        </div>
      ) : !doc ? null : doc.type !== 'card_document' ? <ExtractedReview docId={doc.id} /> : q.isLoading ? <p className="text-sm text-muted">Loading…</p> : (<>
        <dl className="divide-y divide-line">
          {q.data?.facts.map((f: DocFact) => (
            <div key={f.id} className="flex flex-col gap-1 py-3">
              <dt className="text-sm text-muted">{f.label}</dt>
              <dd className="flex flex-col gap-1.5 text-[0.95rem]">
                {edit === f.id ? (
                  <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); save.mutate({ id: f.id, value: val }) }}>
                    <Input value={val} onChange={(e) => setVal(e.target.value)} aria-label={f.label} />
                    <Button type="submit" size="sm" loading={save.isPending}>Save</Button>
                  </form>
                ) : (
                  <span>{f.fact_type === 'card_spend' && f.value && typeof f.value === 'object'
                    ? `${date(f.value.date)} · ${f.value.merchant} · ${inr(f.value.amount_inr)}`
                    : Array.isArray(f.value) ? (typeof f.value[0] === 'object' ? f.value.map((m: any) => m.name).join(', ') : `${f.value.length} items`) : f.unit === 'INR' ? inr(f.value) : String(f.value)}</span>
                )}
                <span className="flex flex-wrap items-center gap-1.5">
                  <TrustMark state={f.state} /><SourceLink citation={f.citation} />
                  {f.fact_type === 'card_spend' && f.state !== 'confirmed' && <button type="button" className="min-h-6 px-1 text-xs font-medium text-muted hover:text-indigo" onClick={() => save.mutate({ id: f.id, confirmOnly: true })}>Confirm purchase</button>}
                  {!Array.isArray(f.value) && (f.value === null || typeof f.value !== 'object') && edit !== f.id && <button type="button" className="min-h-6 px-1 text-xs font-medium text-muted hover:text-indigo" onClick={() => { setEdit(f.id); setVal(String(f.value)) }}>Correct</button>}
                </span>
              </dd>
            </div>
          ))}
        </dl>
        {doc?.type === 'card_document' && <div className="mt-5 space-y-3 border-t border-line pt-4">
          <h3 className="font-semibold">Use reviewed facts on a saved card</h3>
          <p className="text-sm text-muted">Confirm the card ending and each value you want to use above. Only cards with matching last four digits appear. This replaces current outstanding, due date or reward balance where those facts are confirmed. Re-reading or deleting this document removes only values imported from it.</p>
          {!confirmedLast4 || confirmedValues === 0 ? <p className="text-sm text-caution">Confirm the last four digits and at least one value first.</p>
            : matchingCards.length === 0 ? <p className="text-sm text-caution">No saved card has these last four digits. <Link to="/cards" className="underline">Add it in Cards</Link>, then return here.</p>
            : <>
              <Field label="Saved card"><Select value={selectedCard} onChange={(e) => { setSelectedCard(e.target.value); setConfirmReplace(false) }}>
                <option value="">Choose a card</option>
                {matchingCards.map((c: any) => <option key={c.id} value={c.id}>{c.nickname} · ending {c.last4}</option>)}
              </Select></Field>
              <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={confirmReplace} onChange={(e) => setConfirmReplace(e.target.checked)} className="mt-1" />I agree to replace the selected card’s values with these confirmed document facts.</label>
              <Button disabled={!selectedCardMatches || !confirmReplace || linkCard.isPending} loading={linkCard.isPending} onClick={() => linkCard.mutate()}>Import reviewed facts</Button>
            </>}
        </div>}
        {doc?.type === 'card_document' && confirmedLast4 && matchingCards.length > 0 && <div className="mt-5 space-y-3 border-t border-line pt-4">
          <h3 className="font-semibold">Count confirmed purchases toward rewards</h3>
          <p className="text-sm text-muted">Only the purchases you confirmed above are used, grouped by category, to work out how much of a monthly reward cap is already used. Your own entries are never overwritten, and you can undo this.</p>
          <Field label="Saved card"><Select value={selectedCard} onChange={(e) => setSelectedCard(e.target.value)}>
            <option value="">Choose a card</option>
            {matchingCards.map((c: any) => <option key={c.id} value={c.id}>{c.nickname} · ending {c.last4}</option>)}
          </Select></Field>
          {selectedCardMatches && <SpendReconcile doc={doc} card={matchingCards.find((c: any) => c.id === selectedCard)} />}
        </div>}
      </>)}
    </Sheet>
  )
}

export function Documents() {
  useSaathiPage('dashboard')
  const [params] = useSearchParams()
  const qc = useQueryClient()
  const toast = useToast()
  const q = useQuery({ queryKey: ['documents'], queryFn: () => get<DocumentRow[]>('/documents'), refetchInterval: (q) => (q.state.data?.some((d) => ['queued', 'processing'].includes(d.status)) ? 2000 : false) })
  const [open, setOpen] = useState<DocumentRow | null>(null)
  const [toDelete, setToDelete] = useState<DocumentRow | null>(null)
  const [term, setTerm] = useState('')
  const vision = useVision()
  const [cat, setCat] = useState<'all' | DocumentRow['type']>(() => (['bank_statement', 'insurance_policy', 'loan_document', 'card_document', 'receipt'].includes(params.get('type') ?? '') ? params.get('type') as DocumentRow['type'] : 'all'))
  const { ask, setCtx } = useSaathi()
  const [sort, setSort] = useState<'new' | 'old' | 'name'>('new')
  const remove = useMutation({ mutationFn: (id: string) => del(`/documents/${id}`), onSuccess: () => { qc.invalidateQueries(); setToDelete(null); toast({ title: 'Document and its data deleted', tone: 'positive' }) } })
  const reprocess = useMutation({ mutationFn: (id: string) => post(`/documents/${id}/reprocess`), onSuccess: () => { qc.invalidateQueries({ queryKey: ['documents'] }); toast({ title: 'Reading the document again', tone: 'info' }) } })
  const rows = useMemo(() => {
    const t = term.trim().toLowerCase()
    const list = (q.data ?? []).filter((d) => (cat === 'all' || d.type === cat) && (!t || d.display_name.toLowerCase().includes(t) || d.type_label.toLowerCase().includes(t)))
    return [...list].sort((a, b) => sort === 'name' ? a.display_name.localeCompare(b.display_name) : sort === 'old' ? a.upload_time.localeCompare(b.upload_time) : b.upload_time.localeCompare(a.upload_time))
  }, [q.data, term, cat, sort])
  if (q.isLoading) return <PageSkeleton />
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const docs = q.data!
  const focus = params.get('focus')
  const link = (d: DocumentRow) => (d.type === 'insurance_policy' && d.policy_id ? `/insurance/policies/${d.policy_id}` : d.type === 'loan_document' ? `/loans/documents/${d.id}`
    : d.type === 'receipt' ? `/documents/receipts/${d.id}` : d.type === 'card_document' ? `/documents?focus=${d.id}` : '/profile/review')
  const askAbout = (d: DocumentRow) => { setCtx({ type: 'document', objectId: d.id }); ask(d.type === 'receipt' ? 'Summarise this receipt' : 'Summarise this document') }
  const points = docs.reduce((n, d) => n + (d.transactions_found ?? 0) + (d.facts_found ?? 0), 0)
  const last = docs.reduce<string | null>((m, d) => (!m || d.upload_time > m ? d.upload_time : m), null)
  const counts = { all: docs.length, bank_statement: 0, insurance_policy: 0, loan_document: 0, card_document: 0, receipt: 0 } as Record<string, number>
  docs.forEach((d) => { counts[d.type] += 1 })
  const UPLOADS = [
    { to: '/onboarding/statement', label: 'Bank statement', body: vision?.configured ? 'PDF, CSV or photo' : 'PDF or CSV · builds your profile', icon: <Landmark />, tone: 'indigo' as const },
    { to: '/insurance/upload', label: 'Insurance policy', body: vision?.configured ? 'PDF or photos of the pages' : 'PDF schedule or wording', icon: <ShieldCheck />, tone: 'green' as const },
    { to: '/loans/analyze', label: 'Loan document', body: 'Sanction letter, KFS or agreement', icon: <FileText />, tone: 'violet' as const },
    { to: '/documents/receipts/new', label: 'Receipt or invoice', body: vision?.configured ? 'Photo or PDF' : 'PDF invoice', icon: <ReceiptText />, tone: 'amber' as const },
    { to: '/cards/upload', label: 'Card document', body: 'Redacted digital PDF statement', icon: <FileText />, tone: 'indigo' as const },
  ]
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Documents & data' }]} title="Documents & data"
        description="Everything you've uploaded, what VITTRM extracted from it, and controls to correct, re-read or delete it."
        actions={<><LinkButton to="/onboarding/statement" icon={<Landmark className="size-4" />}>Bank statement</LinkButton><LinkButton to="/insurance/upload" variant="secondary" icon={<ShieldCheck className="size-4" />}>Policy</LinkButton><LinkButton to="/loans/analyze" variant="secondary" icon={<FileText className="size-4" />}>Loan document</LinkButton></>} />

      <div className="grid gap-5 @5xl:grid-cols-[1fr_21rem]">
        <section className="glass relative isolate overflow-hidden rounded-[var(--radius-window)] p-3" aria-labelledby="up-h">
          <div className="flex h-full flex-col gap-5 rounded-[calc(var(--radius-window)-0.5rem)] border-2 border-dashed border-indigo/20 p-5 sm:p-6 @3xl:flex-row @3xl:items-center">
            <div className="min-w-0 flex-1">
              <h2 id="up-h" className="text-[1.35rem] font-semibold tracking-[-0.015em]">Your financial documents, in one place</h2>
              <p className="mt-1 max-w-[56ch] text-[0.95rem] text-ink/75">Choose what you're adding. Each type has its own check-in so VITTRM reads it correctly — account for statements, people covered for policies.</p>
              <ul className="mt-4 grid gap-2.5 @xl:grid-cols-2 @6xl:grid-cols-4">
                {UPLOADS.map((u) => (
                  <li key={u.to}>
                    <Link to={u.to} className="group flex h-full items-center gap-3 rounded-[var(--radius-card)] border border-white/80 bg-white/80 p-3.5 shadow-[var(--elev-1)] transition-[box-shadow,background-color] hover:bg-white hover:shadow-[var(--elev-2)] @xl:flex-col @xl:items-start">
                      <IconTile tone={u.tone} size="sm">{u.icon}</IconTile>
                      <span className="min-w-0"><span className="flex items-center gap-1 font-semibold">{u.label}<Upload className="size-3.5 text-muted group-hover:text-indigo" aria-hidden /></span><span className="block text-xs text-muted">{u.body}</span></span>
                    </Link>
                  </li>
                ))}
              </ul>
              <p className="mt-4 flex items-center gap-2 text-xs text-muted"><Lock className="size-3.5" aria-hidden />Up to 15 MB per file. Encrypted in your workspace and never shared without your consent.</p>
              {vision && <p className="mt-1.5 flex items-center gap-2 text-xs text-muted"><ScanText className="size-3.5" aria-hidden />{vision.note}</p>}
            </div>
            <DocStack className="hidden w-44 shrink-0 @7xl:block" />
          </div>
        </section>

        <aside className="surface-card rounded-[var(--radius-window)] p-5" aria-labelledby="how-h">
          <h2 id="how-h" className="mb-4 flex items-center gap-2 font-semibold"><Info className="size-5 text-indigo" aria-hidden />How VITTRM uses your data</h2>
          <ol className="flex flex-col gap-4">
            {[['Upload', 'Add bank statements, policies or loan documents.', <Upload key="u" />], ['Review what was found', 'Income, EMIs, coverage and terms — each with the page it came from.', <FileSearch key="r" />], ['Use the answers', 'Plans and comparisons use only what you confirmed.', <BarChart3 key="a" />]].map(([t, b, icon], i) => (
              <li key={t as string} className="flex items-start gap-3">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-indigo-soft text-sm font-semibold text-indigo-dark" aria-hidden>{i + 1}</span>
                <span className="min-w-0 flex-1"><span className="flex items-center gap-2 font-medium [&_svg]:size-4 [&_svg]:text-muted">{icon}{t}</span><span className="block text-sm text-muted">{b}</span></span>
              </li>
            ))}
          </ol>
          <div className="wash-positive mt-5 flex items-start gap-3 rounded-[var(--radius-card)] p-3.5">
            <Lock className="mt-0.5 size-5 shrink-0 text-positive" aria-hidden />
            <p className="text-sm"><b className="block font-semibold text-positive">You stay in control</b>Delete a file or read it again at any time. Deleting a file removes everything extracted from it.</p>
          </div>
        </aside>
      </div>

      <ul className="mt-5 grid gap-4 @xl:grid-cols-3" aria-label="Totals">
        <li><StatCard icon={<FileText className="size-5" />} label="Documents" value={num(docs.length)} hint={docs.length ? `${counts.bank_statement} bank · ${counts.insurance_policy} policies · ${counts.loan_document} loan · ${counts.card_document} card` : 'No files uploaded yet'} /></li>
        <li><StatCard icon={<Database className="size-5" />} label="Data points extracted" value={num(points)} hint={points ? 'transactions and document terms' : 'Nothing extracted yet'} /></li>
        <li><StatCard icon={<CalendarDays className="size-5" />} label="Last upload" value={last ? date(last) : '—'} hint={last ? relDays(last.slice(0, 10)) : 'No documents yet'} /></li>
      </ul>

      <section className="surface-card mt-7 overflow-hidden rounded-[var(--radius-window)]" aria-labelledby="docs-h">
        <div className="flex flex-col gap-3 border-b border-[var(--glass-hairline)] p-5 @4xl:flex-row @4xl:items-end @4xl:justify-between">
          <div>
            <h2 id="docs-h" className="text-[1.1rem] font-semibold">Your documents</h2>
            <p className="text-sm text-muted">Every file, its status and what was extracted.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="relative">
              <span className="sr-only">Search documents</span>
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
              <input value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Search documents…"
                className="min-h-10 w-56 rounded-full border border-[var(--glass-hairline)] bg-white/90 pl-9 pr-3 text-sm shadow-[inset_0_1px_2px_rgb(22_29_69/0.04)] focus:outline-none focus-visible:shadow-[var(--ring)]" />
            </label>
            <label className="flex items-center gap-2 text-sm text-muted">Sort
              <select value={sort} onChange={(e) => setSort(e.target.value as any)} className="min-h-10 rounded-full border border-[var(--glass-hairline)] bg-white/90 px-3 text-sm font-medium text-ink">
                <option value="new">Newest</option><option value="old">Oldest</option><option value="name">Name</option>
              </select>
            </label>
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5 px-5 pt-4" role="group" aria-label="Filter by type">
          {([['all', 'All'], ['bank_statement', 'Bank statements'], ['insurance_policy', 'Policies'], ['loan_document', 'Loan documents'], ['card_document', 'Card documents'], ['receipt', 'Receipts']] as const).map(([k, l]) => (
            <button key={k} type="button" aria-pressed={cat === k} onClick={() => setCat(k)}
              className={clsx('inline-flex min-h-9 items-center gap-1.5 rounded-full px-3.5 text-sm font-medium transition-[background-color,color,box-shadow]',
                cat === k ? 'bg-[image:var(--grad-indigo)] text-white shadow-[0_4px_12px_rgb(52_67_181/0.28)]' : 'bg-ink/[0.05] text-muted hover:bg-ink/[0.08] hover:text-ink')}>
              {l}<span className={clsx('num rounded-full px-1.5 text-xs', cat === k ? 'bg-white/20' : 'bg-white/80')}>{counts[k]}</span>
            </button>
          ))}
        </div>

        {docs.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
            <IconTile tone="indigo"><FileText /></IconTile>
            <p className="mt-1 font-semibold">No documents yet</p>
            <p className="max-w-sm text-sm text-muted">Start with a bank statement — it powers your profile. Policies and loan documents add detail.</p>
            <LinkButton to="/onboarding/statement" className="mt-2" icon={<Upload className="size-4" />}>Upload a statement</LinkButton>
          </div>
        ) : rows.length === 0 ? (
          <p className="px-5 py-10 text-center text-sm text-muted">No documents match. <button type="button" className="font-medium text-indigo underline underline-offset-2" onClick={() => { setTerm(''); setCat('all') }}>Clear filters</button></p>
        ) : (
          <ul className="flex flex-col gap-2 p-3 sm:p-4">
            {rows.map((d) => {
              const st = STATUS[d.status]
              const ti = TYPE_ICON[d.type]
              return (
                <li key={d.id} className={clsx('flex flex-col gap-3 rounded-[var(--radius-card)] border p-4 transition-colors @3xl:flex-row @3xl:items-center',
                  focus === d.id ? 'border-indigo/35 bg-indigo-soft/50' : 'border-white/80 bg-white/70 hover:bg-white')}>
                  <div className="flex min-w-0 flex-1 items-start gap-3">
                    <IconTile tone={ti.tone} size="sm">{ti.icon}</IconTile>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <Link to={link(d)} className="truncate font-medium hover:text-indigo-dark">{d.display_name}</Link>
                        <Badge tone={st.tone}>{st.icon}{st.label}</Badge>
                        {d.read_from_scan && <Badge tone="indigo"><ScanText className="size-3.5" aria-hidden />Read from {d.mime?.startsWith('image/') ? 'photo' : 'scan'}</Badge>}
                      </div>
                      <p className="text-sm text-muted">{d.type_label}{d.account_label && ` · ${d.account_label}`} · uploaded {date(d.upload_time)}{d.period_start && ` · ${date(d.period_start)} – ${date(d.period_end)}`}{d.page_count ? ` · ${d.page_count} page${d.page_count > 1 ? 's' : ''}` : ''}</p>
                      {d.status === 'processing' && <p className="mt-1 text-sm text-indigo-dark">{d.stage ? `Now: ${d.stage.replaceAll('_', ' ')}` : 'Reading…'}</p>}
                      {d.status === 'failed' && <p className="mt-1 text-sm text-critical">{d.error_message}</p>}
                      {d.warnings.map((w) => <p key={w} className="mt-1 text-sm text-caution">{w}</p>)}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-1 @3xl:justify-end">
                    {d.status !== 'failed' && d.status !== 'processing' && d.status !== 'queued' && <Button size="sm" variant="secondary" icon={<Eye className="size-4" />} onClick={() => setOpen(d)}>{d.type === 'bank_statement' ? 'Extracted data' : 'Review values'}</Button>}
                    {d.status !== 'failed' && d.status !== 'processing' && d.status !== 'queued' && d.type !== 'bank_statement' && <Button size="sm" variant="quiet" icon={<MessageCircle className="size-4" />} onClick={() => askAbout(d)} aria-label={`Ask Vitt Saathi about ${d.display_name}`}>Ask</Button>}
                    <a href={`/api/documents/${d.id}/file`} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-9 items-center gap-1.5 rounded-[var(--radius-control)] px-3 text-sm font-medium text-indigo hover:bg-indigo-soft"><ExternalLink className="size-4" aria-hidden />Open file<span className="sr-only"> {d.display_name} (opens in a new tab)</span></a>
                    <Button size="sm" variant="quiet" icon={<RotateCw className="size-4" />} disabled={d.status === 'processing' || d.status === 'queued'} loading={reprocess.isPending && reprocess.variables === d.id} onClick={() => reprocess.mutate(d.id)}>Re-read</Button>
                    <Button size="sm" variant="quiet" icon={<Trash2 className="size-4" />} className="hover:text-critical" onClick={() => setToDelete(d)} aria-label={`Delete ${d.display_name}`}>Delete</Button>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </section>
      <FactsSheet key={open?.id ?? 'closed'} doc={open} onClose={() => setOpen(null)} />
      <ConfirmDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)} title="Delete this document?" confirmLabel="Delete document" cancelLabel="Keep it"
        description="The file and everything extracted from it — transactions, facts, detected EMIs, policy summary — are removed. This can't be undone."
        busy={remove.isPending} onConfirm={() => toDelete && remove.mutate(toDelete.id)}>
        <p className="font-medium">{toDelete?.display_name}</p>
        {remove.isError && <p role="alert" className="mt-2 text-sm text-critical">{errorMessage(remove.error)}</p>}
      </ConfirmDialog>
    </>
  )
}

export function Family() {
  useSaathiPage('insurance')
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['family'], queryFn: () => get<any>('/family') })
  const [editing, setEditing] = useState<any | 'new' | null>(null)
  const [preset, setPreset] = useState<string | undefined>()
  const [removing, setRemoving] = useState<any>(null)
  const [sort, setSort] = useState<'relation' | 'name'>('relation')
  const remove = useMutation({ mutationFn: (id: string) => del(`/family/${id}`), onSuccess: () => { qc.invalidateQueries(); setRemoving(null) } })
  if (q.isLoading) return <PageSkeleton />
  if (q.isError) return <ErrorState error={q.error} />
  const order = RELATIONS.map((r) => r[0] as string)
  const members = [...q.data.members].sort((a: any, b: any) => sort === 'name' ? a.name.localeCompare(b.name) : order.indexOf(a.relation) - order.indexOf(b.relation))
  const all = [{ ...q.data.self, relation: 'self' }, ...members]
  const has = (rels: string[]) => q.data.members.some((m: any) => rels.includes(m.relation))
  const add = (rel?: string) => { setPreset(rel); setEditing('new') }
  const tips = [
    { rel: 'spouse', title: 'Add your spouse', body: 'Keep their insurance and nominations in one place.', show: !has(['spouse']) },
    { rel: 'child', title: 'Add your children', body: 'Track their health cover and education plans.', show: !has(['child']) },
    { rel: 'mother', title: 'Add your parents', body: 'Help them stay covered and never miss a renewal.', show: !has(['mother', 'father']) },
  ].filter((t) => t.show)
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Family' }]} title="Family"
        description="People whose insurance and obligations you organise. Each person's data stays separate, and VITTRM always shows whose data it's using."
        actions={<Button size="lg" icon={<Plus className="size-4" />} onClick={() => add()}>Add a member</Button>} />

      <PageHero title="Manage your family, together" art={<FamilyArt className="w-80" />}
        body="Keep track of everyone's insurance and obligations in one place. Each person's data stays separate and visible only to you.">
        <ul className="mt-1 flex flex-wrap gap-x-5 gap-y-2 text-sm font-medium">
          {['Separate data for each member', "See who's covered", 'Never shared without your consent'].map((t) => (
            <li key={t} className="flex items-center gap-2"><CheckCircle2 className="size-4 text-indigo" aria-hidden />{t}</li>
          ))}
        </ul>
      </PageHero>

      <section className="mt-9" aria-labelledby="fam-h">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <h2 id="fam-h" className="text-[1.2rem] font-semibold">Family members <span className="font-normal text-muted">({all.length})</span></h2>
          {members.length > 1 && (
            <label className="flex items-center gap-2 text-sm text-muted">Sort by
              <select value={sort} onChange={(e) => setSort(e.target.value as any)} className="min-h-10 rounded-full border border-white/80 bg-white/80 px-3 text-sm font-medium text-ink shadow-[var(--elev-1)]">
                <option value="relation">Relation</option><option value="name">Name</option>
              </select>
            </label>
          )}
        </div>
        <ul className="grid items-stretch gap-4 @3xl:grid-cols-2 @5xl:grid-cols-3">
          {all.map((m: any) => (
            <li key={m.id}>
              <Panel className="flex h-full flex-col gap-4 p-5" aria-label={m.relation === 'self' ? `${m.name}, you` : m.name}>
                <div className="flex items-start gap-3">
                  <Avatar name={m.name} size="lg" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold">{m.relation === 'self' ? `${m.name} (you)` : m.name}</p>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                      <Badge tone={m.relation === 'self' ? 'indigo' : 'neutral'}>{m.relation === 'self' ? 'Account holder' : RELATIONS.find((r) => r[0] === m.relation)?.[1]}</Badge>
                      {m.age != null && <span className="text-sm text-muted">{m.age} years</span>}
                      {m.relation !== 'self' && m.age == null && <span className="text-sm text-caution">Add age for insurance checks</span>}
                    </div>
                  </div>
                  {m.relation !== 'self' && (
                    <div className="-mr-2 -mt-1 flex">
                      <IconButton label={`Edit ${m.name}`} onClick={() => { setPreset(undefined); setEditing(m) }}><Pencil className="size-4" /></IconButton>
                      <IconButton label={`Remove ${m.name}`} onClick={() => setRemoving(m)} className="hover:text-critical"><Trash2 className="size-4" /></IconButton>
                    </div>
                  )}
                </div>
                <div className="mt-auto flex items-center gap-3 rounded-[var(--radius-card)] border border-white/80 bg-white/65 p-3">
                  <IconTile tone="indigo" size="sm"><ShieldCheck /></IconTile>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">Policies</p>
                    {m.policies.length ? (
                      <ul className="text-sm">{m.policies.map((p: any) => <li key={p.id} className="truncate"><Link to={`/insurance/policies/${p.id}`} className="text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">{p.product_name}</Link> <span className="text-muted">· {p.insurer}</span></li>)}</ul>
                    ) : <p className="text-sm text-muted">No policy linked.</p>}
                  </div>
                  {!m.policies.length && <Link to="/insurance/upload" className="inline-flex min-h-9 shrink-0 items-center gap-1 rounded-full px-2 text-sm font-medium text-indigo hover:bg-indigo-soft">Upload one<ArrowRight className="size-3.5" aria-hidden /></Link>}
                </div>
              </Panel>
            </li>
          ))}
          <li>
            <button type="button" onClick={() => add()} className="flex h-full min-h-48 w-full flex-col items-center justify-center gap-2 rounded-[var(--radius-panel)] border-2 border-dashed border-indigo/25 bg-white/40 p-6 text-center transition-[background-color,border-color] hover:border-indigo/55 hover:bg-white/70">
              <span className="flex size-12 items-center justify-center rounded-full bg-indigo-soft text-indigo" aria-hidden><Plus className="size-6" /></span>
              <span className="font-semibold">Add a family member</span>
              <span className="max-w-xs text-sm text-muted">Your spouse, children, parents or anyone whose finances you help manage.</span>
            </button>
          </li>
        </ul>
      </section>

      {tips.length > 0 && (
        <section className="surface-card mt-9 rounded-[var(--radius-window)] p-5 sm:p-6" aria-labelledby="fam-tips">
          <div className="mb-4 flex items-start gap-3">
            <IconTile tone="amber"><Lightbulb /></IconTile>
            <div><h2 id="fam-tips" className="font-semibold">Suggestions</h2><p className="text-sm text-muted">A few people you might want to add next.</p></div>
          </div>
          <ul className="grid gap-3 @3xl:grid-cols-3">
            {tips.map((t) => <li key={t.rel}><FeatureTile icon={<UsersRound />} title={t.title} body={t.body} onClick={() => add(t.rel)} className="h-full" /></li>)}
          </ul>
        </section>
      )}

      <ConfirmDialog open={!!removing} onOpenChange={(o) => !o && setRemoving(null)} title={`Remove ${removing?.name ?? 'this person'}?`}
        description="Their details are deleted from VITTRM. Policies stay, but they won't be linked to this person." confirmLabel="Remove" cancelLabel="Keep"
        busy={remove.isPending} onConfirm={() => remove.mutate(removing.id)}>
        {remove.isError && <p role="alert" className="text-sm text-critical">{errorMessage(remove.error)}</p>}
      </ConfirmDialog>
      <Modal open={!!editing} onOpenChange={(o) => !o && setEditing(null)} title={editing === 'new' ? 'Add a family member' : 'Edit family member'}
        description={editing === 'new' ? 'Only their name and relation are needed. Age helps check insurance limits.' : undefined}>
        <MemberForm key={editing === 'new' ? `new-${preset}` : editing?.id} initial={editing === 'new' ? undefined : editing} defaultRelation={preset} onDone={() => setEditing(null)} />
      </Modal>
    </>
  )
}

const PURPOSE_ICON: Record<string, { icon: ReactNode; tone: 'indigo' | 'green' | 'amber' | 'violet' }> = {
  financial_documents: { icon: <FileText />, tone: 'indigo' }, ai_processing: { icon: <UserRound />, tone: 'violet' },
  whatsapp_reminders: { icon: <MessageCircle />, tone: 'green' }, consultation_calls: { icon: <Phone />, tone: 'amber' },
}

export function Settings() {
  useSaathiPage('dashboard')
  const { user, refresh } = useAuth()
  const qc = useQueryClient()
  const toast = useToast()
  const navigate = useNavigate()
  const q = useQuery({ queryKey: ['consents'], queryFn: () => get<any>('/consents') })
  const ai = useQuery({ queryKey: ['ai-status'], queryFn: () => get<any>('/ai/status') })
  const [confirm, setConfirm] = useState('')
  const [delOpen, setDelOpen] = useState(false)
  const [accOpen, setAccOpen] = useState(false)
  const [accPw, setAccPw] = useState('')
  const toggle = useMutation({
    mutationFn: ({ purpose, on }: any) => (on ? post('/consents', { purpose }) : del(`/consents/${purpose}`)),
    onSuccess: (_d, v: any) => { qc.invalidateQueries({ queryKey: ['consents'] }); refresh(); toast({ title: v.on ? 'Permission allowed' : 'Permission withdrawn', tone: 'positive' }) },
    onError: (e) => toast({ title: errorMessage(e), tone: 'critical' }),
  })
  const wipe = useMutation({ mutationFn: () => post('/profile/delete-all', { confirm: 'DELETE' }), onSuccess: () => { qc.clear(); refresh(); navigate('/') } })
  const removeAccount = useMutation({
    mutationFn: () => post('/auth/account/delete', { password: accPw, confirm: 'DELETE' }),
    onSuccess: () => { qc.clear(); refresh(); navigate('/welcome') },
  })
  const reset = useQuery({ queryKey: ['reset-status'], queryFn: () => get<{ email_configured: boolean }>('/auth/password-reset/status') })
  const vision = ai.data?.vision
  const services = [
    { key: 'chat', icon: <MessagesSquare />, label: 'Vitt Saathi chat', ok: ai.data?.chat_mode === 'gemini', okLabel: 'Gemini configured', offLabel: 'Tool mode · Gemini not configured', offTone: 'saathi' as const,
      note: ai.data?.chat_mode === 'gemini' ? 'A Gemini key and model are set on the server. Answers still use VITTRM’s calculators for every number.' : 'Answers come from VITTRM’s calculators and your data. Free-form AI turns on when the server has a Gemini key and model.' },
    { key: 'voice', icon: <AudioLines />, label: 'Vitt Saathi voice', ok: !!ai.data?.voice_available, okLabel: 'Gemini Live configured', offLabel: 'Not configured', offTone: 'neutral' as const,
      note: ai.data?.voice_available ? 'Voice uses Gemini Live with short-lived tokens; audio is not stored.' : (ai.data?.voice_note ?? 'Voice needs a Gemini Live model configured on the server.') },
    { key: 'vision', icon: <ScanText />, label: 'Reading photos and scans', ok: !!vision?.configured,
      okLabel: vision?.on_device ? 'On this device (Apple Vision)' : 'Gemini vision', offLabel: 'Not configured', offTone: 'neutral' as const,
      note: vision?.note ?? 'Photos and scanned PDFs need an OCR provider on the server.' },
    { key: 'email', icon: <KeyRound />, label: 'Password-reset email', ok: !!reset.data?.email_configured, okLabel: 'Email configured', offLabel: 'Not configured', offTone: 'neutral' as const,
      note: reset.data?.email_configured ? 'Reset links are emailed and work for 30 minutes.' : 'No email server is set up, so reset links can’t be sent. You can still change your password in your profile.' },
  ]
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Settings' }]} title="Settings" description="Your permissions, connected services and data controls."
        aside={
          <div className="glass flex items-center gap-3 rounded-[var(--radius-card)] px-4 py-3">
            <IconTile tone="indigo"><ShieldCheck /></IconTile>
            <div><p className="font-semibold">You're in control</p><p className="text-sm text-muted">Nothing changes here unless you press a button.</p></div>
          </div>
        } />
      <div className="grid max-w-4xl gap-6">
        <Panel className="p-5 sm:p-6" aria-labelledby="perm-h">
          <div className="mb-4 flex items-start gap-3">
            <IconTile tone="indigo" size="lg"><Lock /></IconTile>
            <div><h2 id="perm-h" className="text-[1.1rem] font-semibold">Your permissions</h2><p className="text-sm text-muted">Control how VITTRM can use your information and when it may contact you.</p></div>
          </div>
          {q.isLoading ? <div className="flex flex-col gap-2"><Skeleton className="h-14" /><Skeleton className="h-14" /><Skeleton className="h-14" /></div> : (
            <ul className="flex flex-col gap-2">
              {q.data?.purposes.map((p: any) => {
                const pi = PURPOSE_ICON[p.purpose] ?? { icon: <ShieldCheck />, tone: 'indigo' as const }
                return (
                  <li key={p.purpose} className="flex flex-col gap-3 rounded-[var(--radius-card)] border border-white/80 bg-white/70 p-3.5 sm:flex-row sm:items-center">
                    <div className="flex min-w-0 flex-1 items-start gap-3">
                      <IconTile tone={pi.tone} size="sm">{pi.icon}</IconTile>
                      <div className="min-w-0">
                        <p className="text-[0.95rem] font-medium">{p.description}</p>
                        <p className="mt-0.5 flex items-center gap-1.5 text-xs">
                          {p.granted ? <><CheckCircle2 className="size-3.5 text-positive" aria-hidden /><span className="font-medium text-positive">Allowed</span><span className="text-muted">since {date(p.granted_at)}</span></>
                            : <><span className="size-2 rounded-full border border-line-strong" aria-hidden /><span className="text-muted">Not allowed</span></>}
                        </p>
                      </div>
                    </div>
                    <Button size="sm" variant={p.granted ? 'secondary' : 'primary'} className="sm:min-w-24" loading={toggle.isPending && toggle.variables?.purpose === p.purpose}
                      aria-label={`${p.granted ? 'Withdraw' : 'Allow'}: ${p.description}`}
                      onClick={() => toggle.mutate({ purpose: p.purpose, on: !p.granted })}>{p.granted ? 'Withdraw' : 'Allow'}</Button>
                  </li>
                )
              })}
            </ul>
          )}
          {!user?.phone_masked && <p className="mt-3 flex items-center gap-2 text-sm text-muted"><Info className="size-4 shrink-0" aria-hidden /><span>WhatsApp and call permissions need a mobile number — add it in <Link to="/profile" className="font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">your profile</Link>.</span></p>}
        </Panel>

        <Panel className="p-5 sm:p-6" aria-labelledby="svc-h">
          <div className="mb-4 flex items-start gap-3">
            <IconTile tone="indigo" size="lg"><Plug /></IconTile>
            <div><h2 id="svc-h" className="text-[1.1rem] font-semibold">Connected services</h2><p className="text-sm text-muted">What is set up on this VITTRM server right now.</p></div>
          </div>
          <ul className="flex flex-col gap-2">
            {services.map((sv) => (
              <li key={sv.key} className="flex flex-col gap-2 rounded-[var(--radius-card)] border border-white/80 bg-white/70 p-3.5 sm:flex-row sm:items-start">
                <div className="flex min-w-0 flex-1 items-start gap-3">
                  <IconTile tone="indigo" size="sm">{sv.icon}</IconTile>
                  <div className="min-w-0"><p className="font-medium">{sv.label}</p><p className="text-sm text-muted">{sv.note}</p></div>
                </div>
                {ai.isLoading ? <Skeleton className="h-6 w-40" /> : sv.ok ? <Badge tone="indigo"><CheckCircle2 className="size-3.5" aria-hidden />{sv.okLabel}</Badge> : <Badge tone={sv.offTone}>{sv.offLabel}</Badge>}
              </li>
            ))}
          </ul>
          <Link to="/settings/reminders" className="mt-3 inline-flex min-h-10 items-center gap-2 text-sm font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo"><Settings2 className="size-4" aria-hidden />Reminder & WhatsApp settings<ArrowRight className="size-4" aria-hidden /></Link>
        </Panel>

        <section className="wash-danger flex flex-col gap-4 rounded-[var(--radius-panel)] p-5 sm:flex-row sm:items-center sm:p-6" aria-labelledby="danger-zone">
          <IconTile tone="red" size="lg"><Trash2 /></IconTile>
          <div className="min-w-0 flex-1">
            <h2 id="danger-zone" className="text-[1.1rem] font-semibold text-critical">Delete all my data</h2>
            <p className="mt-1 text-[0.95rem] text-ink/75">Removes every uploaded file, transaction, policy, card, EMI, family member and conversation. Your login stays so you can start again.</p>
          </div>
          <Button variant="danger" onClick={() => { setConfirm(''); setDelOpen(true) }}>Delete all data</Button>
        </section>

        <Panel className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:p-6">
          <div className="min-w-0 flex-1">
            <h2 className="text-[1.05rem] font-semibold">Your data, your copy</h2>
            <p className="mt-1 text-[0.95rem] text-muted">Download everything VITTRM holds about you as a JSON file: profile, transactions, extracted facts, cards, EMIs, policies, reminders and conversations. Passwords and uploaded files are not included.</p>
          </div>
          <Button variant="secondary" onClick={() => window.location.assign('/api/profile/export')}>Download my data</Button>
        </Panel>

        <section className="wash-danger flex flex-col gap-4 rounded-[var(--radius-panel)] p-5 sm:flex-row sm:items-center sm:p-6" aria-labelledby="delete-account">
          <div className="min-w-0 flex-1">
            <h2 id="delete-account" className="text-[1.05rem] font-semibold text-critical">Delete my account</h2>
            <p className="mt-1 text-[0.95rem] text-ink/75">Permanently removes your login and everything under it. This can't be undone.</p>
          </div>
          <Button variant="danger" onClick={() => { setAccPw(''); setConfirm(''); setAccOpen(true) }}>Delete account</Button>
        </section>
      </div>
      <ConfirmDialog open={accOpen} onOpenChange={setAccOpen} title="Delete your account?" confirmLabel="Delete my account" busy={removeAccount.isPending}
        description="Your login, files and all data are erased immediately. We can't recover them."
        confirmDisabled={confirm !== 'DELETE' || (!user?.is_sample && accPw.length === 0)} onConfirm={() => removeAccount.mutate()}>
        {!user?.is_sample && <Field label="Your password"><Input type="password" value={accPw} onChange={(e) => setAccPw(e.target.value)} autoComplete="current-password" /></Field>}
        <Field label="Type DELETE to confirm" className="mt-3"><Input value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" /></Field>
        {removeAccount.isError && <p role="alert" className="mt-3 text-sm text-critical">{errorMessage(removeAccount.error)}</p>}
      </ConfirmDialog>
      <ConfirmDialog open={delOpen} onOpenChange={setDelOpen} title="Delete all your data?" confirmLabel="Delete everything" busy={wipe.isPending}
        description="This can't be undone. Nothing is deleted until you type DELETE and press the button."
        confirmDisabled={confirm !== 'DELETE'} onConfirm={() => wipe.mutate()}>
        <ul className="mb-4 grid gap-1 text-sm text-ink/80 sm:grid-cols-2">
          {['Uploaded files and extracted data', 'Transactions and your profile', 'Policies, cards and EMIs', 'Family members and conversations'].map((t) => <li key={t} className="flex items-center gap-2"><X className="size-3.5 text-critical" aria-hidden />{t}</li>)}
        </ul>
        <Field label="Type DELETE to confirm"><Input value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" /></Field>
        <Callout tone="caution" className="mt-4">Download any documents you want to keep first. Your email and password stay so you can start again.</Callout>
        {wipe.isError && <p role="alert" className="mt-3 text-sm text-critical">{errorMessage(wipe.error)}</p>}
      </ConfirmDialog>
    </>
  )
}
