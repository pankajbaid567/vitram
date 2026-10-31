import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { CalendarDays, CreditCard, Crown, Gift, Lock, Plus, ShoppingCart, Trash2 } from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Button, LinkButton } from '../../components/ui/button'
import { Badge, FeatureTile, KeyValue, Money, PageHeader, PageHero, Panel, SampleBadge, TrustMark } from '../../components/ui/data'
import { CardStackArt } from '../../components/illustrations'
import { Field, Input, Select, Textarea } from '../../components/ui/field'
import { Callout, EmptyState, errorMessage, ErrorState, PageSkeleton, useToast } from '../../components/ui/feedback'
import { FileDrop } from '../../components/ui/filedrop'
import { Modal, Sheet } from '../../components/ui/overlay'
import { ApiError, del, get, patch, post, upload } from '../../lib/api'
import type { DocumentRow } from '../../lib/types'
import { ConsentGate, DOC_CONSENT_BODY } from '../onboarding/Onboarding'
import { date, dayMonth, daysFromToday, inr, num, parseAmountInput, relDays } from '../../lib/format'
import { useSaathi, useSaathiPage } from '../saathi/context'
import { SaathiMark } from '../saathi/SaathiPanel'

function CardForm({ initial, onDone }: { initial?: any; onDone: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const cat = useQuery({ queryKey: ['card-cat'], queryFn: () => get<any>('/cards/catalogue') })
  const [f, setF] = useState({
    catalogue_id: initial?.catalogue_id ?? '', nickname: initial?.nickname ?? '', last4: initial?.last4 ?? '', credit_limit: initial?.credit_limit ?? '',
    outstanding: initial?.outstanding ?? '', due_date: initial?.due_date ?? '', points: initial?.points?.balance ?? '',
    exp_amt: initial?.points?.expiring?.[0]?.amount ?? '', exp_date: initial?.points?.expiring?.[0]?.date ?? '',
    benefits: (initial?.user_benefits ?? []).join('\n'),
  })
  const [err, setErr] = useState<ApiError | null>(null)
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value })
  const m = useMutation({
    mutationFn: () => {
      const body = {
        catalogue_id: f.catalogue_id || null, nickname: f.nickname, last4: f.last4 || null,
        credit_limit: f.credit_limit === '' ? null : parseAmountInput(String(f.credit_limit)), outstanding: f.outstanding === '' ? null : parseAmountInput(String(f.outstanding)),
        due_date: f.due_date || null, points_balance: f.points === '' ? null : parseAmountInput(String(f.points)),
        expiring: f.exp_amt && f.exp_date ? [{ amount: parseAmountInput(String(f.exp_amt)), date: f.exp_date }] : [],
        cycle_spend: initial?.cycle_spend ?? {},
        user_benefits: f.benefits.split('\n').map((b: string) => b.trim()).filter(Boolean),
      }
      return initial ? patch(`/cards/${initial.id}`, body) : post('/cards', body)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cards'] }); qc.invalidateQueries({ queryKey: ['dashboard'] }); toast({ title: initial ? 'Card updated' : 'Card added', tone: 'positive' }); onDone() },
    onError: (e) => setErr(e instanceof ApiError ? e : null),
  })
  const fe = (k: string) => (err?.field === k ? err.message : null)
  return (
    <form id="card-form" onSubmit={(e: FormEvent) => { e.preventDefault(); if (!f.nickname.trim()) { setErr(new ApiError(422, 'X', 'Give the card a name.', 'nickname')); return } m.mutate() }} className="grid gap-4 sm:grid-cols-2" noValidate>
      <Field label="Card programme" className="sm:col-span-2" hint="Pick from the sample catalogue to get reward rules, or leave as 'Other' to track it without reward estimates.">
        <Select value={f.catalogue_id} onChange={(e) => { const p = cat.data?.products.find((x: any) => x.id === e.target.value); setF({ ...f, catalogue_id: e.target.value, nickname: f.nickname || p?.card_name || '' }) }}>
          <option value="">Other / not listed</option>
          {cat.data?.products.map((p: any) => <option key={p.id} value={p.id}>{p.card_name} — {p.issuer}</option>)}
        </Select>
      </Field>
      <Field label="Name for this card" error={fe('nickname')}><Input value={f.nickname} onChange={set('nickname')} /></Field>
      <Field label="Last 4 digits" optional hint="Never your full card number, CVV or PIN." error={fe('last4')}><Input inputMode="numeric" maxLength={4} value={f.last4} onChange={(e) => setF({ ...f, last4: e.target.value.replace(/\D/g, '') })} /></Field>
      <Field label="Credit limit" optional><Input prefix="₹" inputMode="numeric" value={f.credit_limit} onChange={set('credit_limit')} /></Field>
      <Field label="Current outstanding" optional><Input prefix="₹" inputMode="numeric" value={f.outstanding} onChange={set('outstanding')} /></Field>
      <Field label="Payment due date" optional><Input type="date" value={f.due_date} onChange={set('due_date')} /></Field>
      <Field label="Reward balance" optional hint="From your latest statement or the issuer app."><Input inputMode="numeric" value={f.points} onChange={set('points')} /></Field>
      <Field label="Rewards expiring" optional><Input inputMode="numeric" value={f.exp_amt} onChange={set('exp_amt')} /></Field>
      <Field label="Expiry date" optional><Input type="date" value={f.exp_date} onChange={set('exp_date')} /></Field>
      <Field label="Benefits you know about" optional className="sm:col-span-2" error={fe('user_benefits')}
        hint="One per line, e.g. 'Airport lounge 4 times a year'. Shown as “You entered”, separate from the catalogue terms.">
        <Textarea rows={3} value={f.benefits} onChange={set('benefits')} />
      </Field>
      {err && !err.field && <p role="alert" className="text-sm text-critical sm:col-span-2">{err.message}</p>}
      <div className="flex gap-2 sm:col-span-2"><Button type="submit" loading={m.isPending}>{initial ? 'Save' : 'Add card'}</Button><Button variant="quiet" onClick={onDone}>Cancel</Button></div>
    </form>
  )
}

/** Visual card face. Shows only the masked last 4 digits — VITTRM never stores the full number, CVV or PIN.
 * The tint is stable per card (derived from its id), not by rank. */
const FACES = [
  'linear-gradient(135deg,#2b3690 0%,#161d45 70%)',
  'linear-gradient(135deg,#1f4f6e 0%,#131b3f 72%)',
  'linear-gradient(135deg,#4a3a8c 0%,#171c47 72%)',
  'linear-gradient(135deg,#34406f 0%,#0f1538 72%)',
]
function faceFor(id: string) {
  let h = 0
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return FACES[h % FACES.length]
}
export function CardFace({ card, className }: { card: any; className?: string }) {
  return (
    <div className={clsx('relative isolate flex flex-col justify-between overflow-hidden rounded-[var(--radius-card)] p-4 text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.14),var(--elev-2)]', className)}
      style={{ backgroundImage: faceFor(card.id) }}>
      <span className="pointer-events-none absolute -right-10 -top-12 -z-10 size-40 rounded-full bg-white/[0.07]" aria-hidden />
      <span className="pointer-events-none absolute -bottom-16 right-10 -z-10 size-36 rounded-full bg-indigo-300/10" aria-hidden />
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold">{card.nickname}</p>
          <p className="truncate text-sm text-white/70">{card.issuer ?? card.card_name ?? 'Card'}</p>
        </div>
        <span className="h-6 w-8 shrink-0 rounded-[6px] bg-gradient-to-br from-[#f3d48a] to-[#c8973c] shadow-[inset_0_0_0_1px_rgb(0_0_0/0.15)]" aria-hidden />
      </div>
      <div className="mt-6 flex items-end justify-between gap-2">
        <p className="num whitespace-nowrap text-[1.05rem] tracking-[0.18em] text-white/90">{card.last4 ? <><span aria-hidden>••••</span><span className="sr-only">ending</span> {card.last4}</> : <span className="text-sm tracking-normal text-white/65">Last 4 not added</span>}</p>
        {(card.network || (card.issuer && card.card_name)) && <p className="truncate text-xs font-medium text-white/70">{card.network ?? card.card_name}</p>}
      </div>
    </div>
  )
}

export function Optimizer({ categories, compact }: { categories: { key: string; label: string }[]; compact?: boolean }) {
  const [params] = useSearchParams()
  const [amount, setAmount] = useState(params.get('amount') ?? '')
  const [category, setCategory] = useState(params.get('category') ?? 'travel')
  const [merchant, setMerchant] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const m = useMutation({ mutationFn: (b: any) => post<any>('/cards/best-for-spend', b), onError: (e) => setErr(errorMessage(e)) })
  function run(e: FormEvent) {
    e.preventDefault()
    const a = parseAmountInput(amount)
    if (!a) { setErr('Enter the purchase amount.'); return }
    setErr(null)
    m.mutate({ amount: a, category, merchant: merchant || null })
  }
  const r = m.data
  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={run} className={clsx('grid gap-3', compact ? '@xl:grid-cols-[1fr_1fr_auto]' : '@xl:grid-cols-2 @4xl:grid-cols-[1fr_1fr_1fr_auto]')} noValidate>
        <Field label="Purchase amount" error={err}><Input prefix="₹" inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="30,000" /></Field>
        <Field label="What for"><Select value={category} onChange={(e) => setCategory(e.target.value)}>{categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</Select></Field>
        {!compact && <Field label="Merchant" optional><Input value={merchant} onChange={(e) => setMerchant(e.target.value)} placeholder="e.g. MakeMyTrip" /></Field>}
        <div className="flex items-end"><Button type="submit" loading={m.isPending} className="w-full sm:w-auto">Compare my cards</Button></div>
      </form>
      {r && (
        <div className="flex flex-col gap-3" aria-live="polite">
          {r.ranked.length === 0 && r.unranked.length === 0 && <Callout tone="caution">None of your cards have reward rules VITTRM can use.</Callout>}
          <ol className="flex flex-col gap-2">
            {r.ranked.map((x: any, i: number) => (
              <li key={x.card_id} className={clsx('rounded-[var(--radius-card)] p-4', i === 0 && x.value_inr > 0 ? 'border border-positive/40 bg-positive-soft/80 shadow-[var(--elev-2)]' : 'surface-card')}>
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="font-semibold">{i === 0 && x.value_inr > 0 && <Badge tone="positive" className="mr-2">Best for this</Badge>}{x.card_name}</p>
                  <p className="num text-right"><span className="text-lg font-semibold"><Money value={x.value_inr} /></span><span className="block text-sm text-muted">{num(x.reward_units)} {x.unit_name}</span></p>
                </div>
                {x.why.length > 0 && <ul className="mt-2 text-[0.95rem] text-ink/85">{x.why.map((w: string) => <li key={w}>{w}</li>)}</ul>}
                {x.caveats.length > 0 && <ul className="mt-1 text-sm text-caution">{x.caveats.map((w: string) => <li key={w}>{w}</li>)}</ul>}
                {x.incomplete?.length > 0 && <p className="mt-1 text-xs text-muted">Estimate incomplete: {x.incomplete.join('; ')}</p>}
              </li>
            ))}
          </ol>
          {r.unranked.length > 0 && (
            <div className="rounded-[var(--radius-card)] border border-dashed border-line-strong bg-white/60 p-4">
              <p className="text-sm font-medium">Can't be ranked in rupees</p>
              {r.unranked.map((x: any) => <p key={x.card_id} className="text-[0.95rem] text-muted">{x.card_name}: {x.reward_units != null ? `${num(x.reward_units)} ${x.unit_name}` : 'no reward rules'} — {x.incomplete?.[0] ?? x.caveats?.[0] ?? 'no rupee value available'}</p>)}
            </div>
          )}
          {r.ranked.flatMap((x: any) => (x.milestones ?? []).map((m: string) => ({ card: x.card_name, m }))).slice(0, 2).map((x: any) => (
            <p key={x.card + x.m} className="text-sm text-muted">{x.card}: {x.m}</p>
          ))}
          {r.category_inferred && <p className="text-sm text-muted">Category inferred from the merchant as {r.category_label}.</p>}
          <p className="text-xs text-muted">Uses each card's sample reward rules, caps and exclusions. Issuers change rules — check before a big purchase.</p>
        </div>
      )}
    </div>
  )
}

export function CardsHome() {
  useSaathiPage('card')
  const [adding, setAdding] = useState(false)
  const q = useQuery({ queryKey: ['cards'], queryFn: () => get<any>('/cards') })
  const ins = useQuery({ queryKey: ['card-insights'], queryFn: () => get<any>('/cards/insights/categories'), enabled: (q.data?.cards?.length ?? 0) > 1 })
  if (q.isLoading) return <PageSkeleton />
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Cards' }]} title="Credit cards" description="All your cards in one place — due dates, rewards, and which card earns the most for each purchase."
        actions={<div className="flex flex-wrap gap-2"><LinkButton to="/cards/upload" variant="secondary">Read a statement</LinkButton><LinkButton to="/cards/explore" variant="secondary">Explore sample cards</LinkButton><Button size="lg" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>Add a card</Button></div>} />
      {d.cards.length === 0 ? (
        <div className="flex flex-col gap-7">
          <PageHero pill={<><CreditCard />No cards yet</>} title="Bring your cards together" art={<CardStackArt className="w-80" />}
            body="Add cards using a nickname and the last 4 digits to track due dates, rewards, and which card fits a purchase."
            actions={<Button size="lg" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>Add a card</Button>}
            note={<><Lock />Never enter your full card number, CVV or PIN.</>} />
          <CardCapabilities />
          <CardSaathiBanner />
        </div>
      ) : (
        <>
          <Panel className="mb-7 p-5 sm:p-6">
            <h2 className="mb-1 text-[1.05rem] font-semibold">Which card should I use?</h2>
            <p className="mb-4 text-sm text-muted">Compares your own cards for one purchase.</p>
            <Optimizer categories={d.categories} />
          </Panel>
          <div className="grid gap-4 @xl:grid-cols-2 @4xl:grid-cols-3">
            {d.cards.map((c: any) => (
              <Link key={c.id} to={`/cards/${c.id}`} className="surface-card lift flex flex-col gap-4 rounded-[var(--radius-panel)] p-2.5 pb-4">
                <CardFace card={c} />
                <div className="flex items-center justify-between gap-2 px-2">
                  <p className="truncate text-sm text-muted">{c.card_name ?? 'Card'}</p>
                  {c.catalogue ? <TrustMark state="sample" /> : <Badge>No reward rules</Badge>}
                </div>
                <div className="grid grid-cols-2 gap-3 px-2 text-[0.95rem]">
                  <div><p className="text-sm text-muted">Outstanding</p><Money value={c.outstanding} className="font-medium" /></div>
                  <div><p className="text-sm text-muted">Due</p><p className={clsx('font-medium', c.due_date && daysFromToday(c.due_date) >= 0 && daysFromToday(c.due_date) <= 5 && 'text-caution')}>{c.due_date ? `${dayMonth(c.due_date)} · ${relDays(c.due_date)}` : 'Not added'}</p></div>
                  <div className="col-span-2"><p className="text-sm text-muted">Rewards</p><p className="font-medium">{c.points?.balance != null ? `${num(c.points.balance)} ${c.reward_unit ?? 'points'}` : 'Not added'}</p></div>
                </div>
              </Link>
            ))}
          </div>
          <div className="mt-7 grid items-start gap-6 @3xl:grid-cols-2">
            <Panel className="p-5">
              <h2 className="font-semibold">Reward balances</h2>
              <p className="mb-3 text-sm text-muted">{d.reward_totals_note}</p>
              {d.reward_totals.map((t: any) => <p key={t.unit} className="flex justify-between py-1 text-[0.95rem]"><span>{t.unit}</span><span className="num font-medium">{num(t.balance)}</span></p>)}
              {d.expiring.length > 0 && <>
                <h3 className="mt-4 text-sm font-medium">Expiring soon</h3>
                {d.expiring.map((e: any) => <p key={e.card_id + e.date} className="text-[0.95rem] text-caution">{num(e.amount)} {e.unit} on {e.card} expire {date(e.date)}</p>)}
              </>}
            </Panel>
            {ins.data?.insights?.length > 0 && (
              <Panel className="p-5">
                <h2 className="font-semibold">Use the right card for your usual spending</h2>
                <p className="mb-3 text-sm text-muted">{ins.data.note}</p>
                <ul className="divide-y divide-line">
                  {ins.data.insights.map((i: any) => (
                    <li key={i.category} className="py-2.5 text-[0.95rem]">
                      <p><b>{i.label}</b> (about <Money value={i.monthly_spend} /> a month): {i.best_card} earns about <Money value={i.best_value_inr} /> a month{i.difference_inr > 0 && <>, <Money value={i.difference_inr} /> more than {i.next_card}</>}.</p>
                      {i.caveats[0] && <p className="text-sm text-muted">{i.caveats[0]}</p>}
                    </li>
                  ))}
                </ul>
              </Panel>
            )}
          </div>
        </>
      )}
      {d.cards.length > 0 && <div className="mt-7"><CardSaathiBanner /></div>}
      <Sheet open={adding} onOpenChange={setAdding} wide title="Add a card" description="A nickname and the last 4 digits are enough. Everything else is optional."><CardForm onDone={() => setAdding(false)} /></Sheet>
    </>
  )
}

export function ExploreCards() {
  useSaathiPage('card')
  const q = useQuery({ queryKey: ['card-explore'], queryFn: () => get<any>('/cards/explore') })
  if (q.isLoading) return <PageSkeleton />
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  return <>
    <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Cards', to: '/cards' }, { label: 'Explore' }]}
      title="Explore sample cards" description="See illustrative rewards and fees. Issuer eligibility and live offers are not checked." />
    <Callout tone="info" className="mb-5" title="Sample data, not an application">{q.data.notice}</Callout>
    <div className="grid gap-4 @3xl:grid-cols-2">
      {q.data.products.map((card: any) => <Panel key={card.id} className="p-5">
        <div className="flex items-start justify-between gap-2"><div><h2 className="text-lg font-semibold">{card.card_name}</h2><p className="text-sm text-muted">{card.issuer}</p></div><TrustMark state="sample" /></div>
        <p className="mt-3 text-sm">Eligibility: <b>Unknown</b> · Approval is decided by the issuer.</p>
        <p className="mt-2 text-sm">Annual fee: <Money value={card.fees?.annual} />{card.fees?.gst_applicable && ' + applicable GST'}</p>
        <p className="mt-1 text-sm">Reward currency: {card.reward_currency ?? 'Not specified'}</p>
        {card.matched_spend_categories.length > 0 ? <p className="mt-3 text-sm text-positive">Your statement shows spending in {card.matched_spend_categories.map((c: any) => c.label).join(', ')}. Review caps and exclusions below before judging fit.</p>
          : <p className="mt-3 text-sm text-muted">No matching spending category is known from your profile.</p>}
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">{card.category_rules.map((rule: any) => <li key={rule.label}>{rule.label}</li>)}</ul>
        <p className="mt-3 text-sm text-muted">Excluded categories: {card.exclusions?.categories?.join(', ') || 'None listed'}</p>
        <p className="mt-1 text-sm text-muted">Source: {card.catalogue?.source} · Updated {card.catalogue?.last_updated}</p>
      </Panel>)}
    </div>
  </>
}

export function CardDocumentUpload() {
  useSaathiPage('card')
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const mutation = useMutation({
    mutationFn: () => { const form = new FormData(); form.append('file', file!); form.append('type', 'card_document'); return upload<DocumentRow>('/documents', form) },
    onSuccess: (doc) => navigate(`/documents?focus=${doc.id}`),
    onError: (e) => setError(errorMessage(e)),
  })
  return <>
    <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Cards', to: '/cards' }]}
      title="Read a card statement" description="Extract a due date, amount due, rewards and clear purchase rows for review. Nothing changes on a saved card until you confirm facts and explicitly import them." />
    <div className="max-w-2xl"><ConsentGate purpose="financial_documents" title="Before you upload" body={DOC_CONSENT_BODY}>
      <Panel className="flex flex-col gap-4 p-5">
        <Callout tone="caution">Use a digital PDF with the full card number, CVV and PIN redacted. Scanned card PDFs are not accepted.</Callout>
        <FileDrop accept=".pdf" file={file} onFile={setFile} error={error} />
        <Button disabled={!file} loading={mutation.isPending} onClick={() => { setError(null); mutation.mutate() }}>Read document</Button>
      </Panel>
    </ConsentGate></div>
  </>
}

function CardCapabilities() {
  const items: { icon: ReactNode; tone: 'sky' | 'amber' | 'violet' | 'green'; title: string; body: string }[] = [
    { icon: <CalendarDays />, tone: 'sky', title: 'Due-date overview', body: 'See upcoming dues and set reminders.' },
    { icon: <Gift />, tone: 'amber', title: 'Rewards & points', body: 'Track balances, expiry and redemption value.' },
    { icon: <ShoppingCart />, tone: 'violet', title: 'Best card for a purchase', body: 'A ranking for every purchase, from each card’s rules.' },
    { icon: <Crown />, tone: 'green', title: 'Card benefits', body: 'Key benefits and fees across your cards.' },
  ]
  return (
    <section aria-labelledby="card-can">
      <h2 id="card-can" className="mb-3 text-[1.1rem] font-semibold">What you can do with VITTRM</h2>
      <ul className="grid gap-4 @xl:grid-cols-2 @5xl:grid-cols-4">
        {items.map((f) => <li key={f.title} className="surface-card rounded-[var(--radius-card)] p-5"><FeatureTile icon={f.icon} tone={f.tone} title={f.title} body={f.body} /></li>)}
      </ul>
    </section>
  )
}

function CardSaathiBanner() {
  const { ask } = useSaathi()
  const qs = ['Which card should I use for a ₹30,000 flight?', 'How do I redeem my reward points?', 'Compare my cards for groceries']
  return (
    <section aria-labelledby="card-saathi" className="wash-amber flex flex-col gap-5 rounded-[var(--radius-window)] p-5 sm:p-6 @4xl:flex-row @4xl:items-center">
      <SaathiMark className="size-14 shrink-0 shadow-[var(--glow-saathi)]" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-marigold-deep">Ask Vitt Saathi</p>
        <h2 id="card-saathi" className="text-[1.15rem] font-semibold">Not sure which card to use?</h2>
        <p className="mt-1 text-[0.95rem] text-ink/75">Ask about the best card for a purchase, how to redeem rewards, or how to get more from the cards you have.</p>
      </div>
      <ul className="flex flex-col gap-2 @4xl:w-80" aria-label="Example questions">
        {qs.map((q) => (
          <li key={q}><button type="button" onClick={() => ask(q)} className="w-full rounded-[14px] border border-white/80 bg-white/80 px-3.5 py-2 text-left text-sm shadow-[var(--elev-1)] transition-[box-shadow,color] hover:text-indigo-dark hover:shadow-[var(--elev-2)]">“{q}”</button></li>
        ))}
      </ul>
    </section>
  )
}

export function CardOptimizerPage() {
  useSaathiPage('card')
  const q = useQuery({ queryKey: ['cards'], queryFn: () => get<any>('/cards') })
  if (q.isLoading) return <PageSkeleton />
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Cards', to: '/cards' }]} title="Which card should I use?" description="Enter a purchase and VITTRM ranks your cards by the rewards they'd earn, using each card's rules, caps and exclusions." />
      {q.data?.cards?.length ? <Panel className="p-5"><Optimizer categories={q.data.categories} /></Panel> : <EmptyState title="Add a card first" action={<LinkButton to="/cards">Go to cards</LinkButton>} />}
    </>
  )
}

export function CardDetail() {
  const { id } = useParams()
  useSaathiPage('card', id)
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const q = useQuery({ queryKey: ['card', id], queryFn: () => get<any>(`/cards/${id}/benefits`) })
  const remove = useMutation({ mutationFn: () => del(`/cards/${id}`), onSuccess: () => { qc.invalidateQueries({ queryKey: ['cards'] }); navigate('/cards') } })
  const [confirmDel, setConfirmDel] = useState(false)
  if (q.isLoading) return <PageSkeleton />
  if (q.isError) return <ErrorState error={q.error} />
  const d = q.data
  const c = d.card
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Cards', to: '/cards' }]} title={c.nickname}
        description={<span className="flex flex-wrap items-center gap-2">{c.card_name ?? 'Card'} {c.issuer && `· ${c.issuer}`} {c.masked && `· ${c.masked}`} {c.catalogue && <SampleBadge meta={c.catalogue} />}</span>}
        actions={<><Button variant="secondary" onClick={() => setEditing(true)}>Edit</Button><Button variant="quiet" icon={<Trash2 className="size-4" />} onClick={() => setConfirmDel(true)}>Remove</Button></>} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel className="p-5">
          <CardFace card={c} className="mb-4 max-w-sm" />
          <h2 className="font-semibold">Card details</h2>
          <KeyValue items={[
            { k: 'Outstanding', v: <Money value={c.outstanding} />, extra: c.outstanding != null && <TrustMark state="user" /> },
            { k: 'Credit limit', v: <Money value={c.credit_limit} /> },
            { k: 'Payment due', v: c.due_date ? `${date(c.due_date)} (${relDays(c.due_date)})` : 'Not added' },
            { k: 'Annual fee', v: d.fees ? <span><Money value={d.fees.annual} />{d.fees.annual_waiver_spend && <span className="block text-xs text-muted">waived above {inr(d.fees.annual_waiver_spend)} spend</span>}</span> : 'Not available' },
            { k: 'Reward balance', v: c.points?.balance != null ? `${num(c.points.balance)} ${c.reward_unit ?? ''}` : 'Not added', extra: c.points?.balance != null && <span className="text-xs text-muted">{c.points.as_of ? `as of ${date(c.points.as_of)}` : 'Statement date not extracted'}</span> },
            { k: 'Reward expiry', v: d.expiry ?? 'Not available' },
          ]} />
          {c.source_document_id && <p className="mt-3 text-sm text-muted">Reviewed document supplied: {c.source_fields.map((f: string) => f.replaceAll('_', ' ')).join(', ')}. <Link to={`/documents?focus=${c.source_document_id}`} className="font-medium text-indigo underline">View the source</Link></p>}
          {c.due_date && <Button variant="secondary" size="sm" className="mt-3" onClick={() => post('/reminders/send-now', { object_type: 'card', object_id: c.id }).then(() => qc.invalidateQueries({ queryKey: ['notifications'] }))}>Send me a due-date reminder now</Button>}
        </Panel>
        <Panel className="p-5">
          <h2 className="font-semibold">How it earns</h2>
          {!d.rules?.reward_currency ? <p className="mt-2 text-sm text-muted">No reward rules for this card. Choose its programme in Edit to see estimates.</p> : (
            <ul className="mt-2 flex flex-col gap-2 text-[0.95rem]">
              <li>Base: {d.rules.base_rate?.earn_per_100} {d.rules.currency_name} per ₹100</li>
              {d.rules.category_rules.map((r: any) => <li key={r.label}>{r.label}</li>)}
              {d.rules.exclusions?.categories?.length > 0 && <li className="text-muted">No rewards on: {d.rules.exclusions.categories.join(', ').replaceAll('_', ' ')}</li>}
              {d.rules.milestones?.map((m: any) => <li key={m.label} className="text-muted">{m.label}</li>)}
              {d.benefits.map((b: any) => <li key={b.label}>{b.label}</li>)}
            </ul>
          )}
        </Panel>
        {c.user_benefits?.length > 0 && (
          <Panel className="p-5">
            <h2 className="flex flex-wrap items-center gap-2 font-semibold">Benefits you entered <TrustMark state="user" /></h2>
            <p className="mb-2 text-sm text-muted">From you, not checked against the issuer. Confirm with your issuer before relying on them.</p>
            <ul className="flex flex-col gap-1.5 text-[0.95rem]">{c.user_benefits.map((b: string) => <li key={b} className="flex gap-2"><span className="mt-2 size-1.5 shrink-0 rounded-full bg-positive" aria-hidden />{b}</li>)}</ul>
          </Panel>
        )}
        {d.redemption?.length > 0 && (
          <Panel className="p-5">
            <h2 className="font-semibold">Ways to redeem</h2>
            <ul className="mt-2 divide-y divide-line">
              {d.redemption.map((r: any) => (
                <li key={r.type} className="flex flex-col gap-0.5 py-2.5 text-[0.95rem]">
                  <span className="font-medium">{r.label}</span><span className="text-muted">{r.detail}</span>
                  {r.value_per_unit_inr != null && c.points?.balance != null && <span className="text-sm">Your {num(c.points.balance)} → about <Money value={c.points.balance * r.value_per_unit_inr} /></span>}
                </li>
              ))}
            </ul>
          </Panel>
        )}
        {d.spend_fit?.length > 0 && d.rules?.reward_currency && (
          <Panel className="p-5">
            <h2 className="font-semibold">If you used this card for your usual spending</h2>
            <p className="mb-2 text-sm text-muted">{d.spend_fit_note}</p>
            <ul className="divide-y divide-line">
              {d.spend_fit.slice(0, 8).map((s: any) => (
                <li key={s.category} className="flex justify-between gap-3 py-2 text-[0.95rem]">
                  <span>{s.label}<span className="block text-xs text-muted"><Money value={s.monthly_spend} /> a month</span></span>
                  <span className="text-right">{s.estimated_value_inr != null ? <Money value={s.estimated_value_inr} /> : `${num(s.estimated_units)} ${c.reward_unit}`}{s.caveats[0] && <span className="block text-xs text-muted">{s.caveats[0]}</span>}</span>
                </li>
              ))}
            </ul>
          </Panel>
        )}
      </div>
      <Sheet open={editing} onOpenChange={setEditing} wide title="Edit card"><CardForm initial={c} onDone={() => { setEditing(false); q.refetch() }} /></Sheet>
      <Modal open={confirmDel} onOpenChange={setConfirmDel} title="Remove this card?" description="Its balances and due dates are deleted from VITTRM."
        footer={<><Button variant="quiet" onClick={() => setConfirmDel(false)}>Keep</Button><Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>Remove card</Button></>}>
        <p className="text-[0.95rem]">{c.nickname}</p>
      </Modal>
    </>
  )
}
