import { useMutation, useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { ArrowRight, BarChart3, Car, Check, CheckCircle2, ChevronRight, CloudUpload, FileSearch, FileText, GraduationCap, Hammer, Home as HomeIcon, Landmark, Lightbulb, MessageCircle, Scale, Search, ShieldCheck, Upload, UserRound } from 'lucide-react'
import { useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Button, buttonClass, LinkButton } from '../../components/ui/button'
import { Badge, IconTile, KeyValue, Money, PageHeader, Panel, SampleBadge, SourceLink, TrustMark } from '../../components/ui/data'
import { Checkbox, Field, Input, Segmented, Select } from '../../components/ui/field'
import { Callout, EmptyState, errorMessage, ErrorState, PageSkeleton, Skeleton } from '../../components/ui/feedback'
import { FileDrop } from '../../components/ui/filedrop'
import { ApiError, get, post, upload } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { acceptFor, useVision } from '../../lib/vision'
import { DuplicateNotice } from '../documents/DuplicateNotice'
import { isDuplicate } from '../documents/duplicates'
import { date, inr, months, parseAmountInput, pct } from '../../lib/format'
import type { DocumentRow } from '../../lib/types'
import { ConsentGate, DOC_CONSENT_BODY, ProcessingSteps, useDocumentPoll } from '../onboarding/Onboarding'
import { useSaathi, useSaathiPage } from '../saathi/context'
import { Clauses, PURPOSES, RealCost, WhatIf } from './components'

function intentFromParams(p: URLSearchParams) {
  const collateral = p.get('collateral')
  return {
    purpose: p.get('purpose') ?? 'personal',
    amount: Number(p.get('amount') ?? 0),
    tenure_months: p.get('tenure') ? Number(p.get('tenure')) : null,
    emi_comfort: p.get('emi') ? Number(p.get('emi')) : null,
    prepayment_important: p.get('prepay') === '1',
    monthly_income_override: p.get('income') ? Number(p.get('income')) : null,
    collateral: collateral ? { available: collateral !== 'none', type: collateral === 'none' || collateral === 'unsure' ? null : collateral, value: p.get('cval') ? Number(p.get('cval')) : null, ...(collateral === 'unsure' ? { available: null } : {}) } : null,
  }
}

/* --- S10 Loans home ------------------------------------------------------ */

export function LoansHome() {
  useSaathiPage('loan')
  const { ask } = useSaathi()
  const docs = useQuery({ queryKey: ['loan-docs'], queryFn: () => get<DocumentRow[]>('/loans/documents') })
  const TYPES: { purpose: string; label: string; body: string; icon: ReactNode; tone: 'indigo' | 'red' | 'green' | 'violet' | 'amber' }[] = [
    { purpose: 'home', label: 'Home loan', body: 'Buy or build your home', icon: <HomeIcon />, tone: 'indigo' },
    { purpose: 'vehicle', label: 'Vehicle loan', body: 'New or used car or two-wheeler', icon: <Car />, tone: 'red' },
    { purpose: 'personal', label: 'Personal loan', body: 'For your goals and needs', icon: <UserRound />, tone: 'green' },
    { purpose: 'education', label: 'Education loan', body: 'Fees, study abroad and more', icon: <GraduationCap />, tone: 'violet' },
    { purpose: 'home_renovation', label: 'Home renovation', body: 'Repairs, upgrades, interiors', icon: <Hammer />, tone: 'amber' },
  ]
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Loans' }]} title="Loans"
        description="See what a loan really costs — interest, fees, GST and the conditions that matter — before you commit."
        aside={
          <div className="glass flex max-w-sm items-start gap-3 rounded-[var(--radius-card)] p-4">
            <IconTile tone="amber" size="sm"><Lightbulb /></IconTile>
            <div className="min-w-0">
              <p className="font-semibold">Need help choosing?</p>
              <p className="text-sm text-muted">Ask Vitt Saathi for a comparison based on your profile.</p>
              <button type="button" onClick={() => ask('Compare personal loan options for ₹3 lakh over 3 years')}
                className="mt-1 inline-flex min-h-9 items-center gap-1 text-sm font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">Try a sample question<ArrowRight className="size-4" aria-hidden /></button>
            </div>
          </div>
        } />
      <ul className="-mt-3 mb-7 flex flex-wrap gap-2" aria-label="What this journey does">
        {[[<Scale key="a" />, 'Compare real costs', 'indigo'], [<ShieldCheck key="b" />, 'Check what your profile supports', 'green'], [<FileSearch key="c" />, 'Understand the terms', 'amber'], [<Check key="d" />, 'Decide with the full picture', 'violet']].map(([icon, label, tone]) => (
          <li key={label as string} className="inline-flex items-center gap-2 rounded-full border border-white/80 bg-white/70 py-1 pl-1 pr-3.5 text-sm font-medium shadow-[var(--glass-highlight)]"><IconTile tone={tone as any} size="sm" className="size-7 rounded-full [&_svg]:size-3.5">{icon}</IconTile>{label}</li>
        ))}
      </ul>

      <div className="grid gap-5 @5xl:grid-cols-[1fr_20rem]">
        <div className="flex min-w-0 flex-col gap-5">
          <div className="grid gap-5 @3xl:grid-cols-2">
            <Panel variant="hero" className="relative isolate flex flex-col gap-3 overflow-hidden p-6 sm:p-7">
              <span className="pointer-events-none absolute -right-20 -top-24 -z-10 size-72 rounded-full bg-indigo/45 blur-3xl" aria-hidden />
              <div className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-2.5">
                  <span className="flex size-11 items-center justify-center rounded-[14px] bg-white/10 text-indigo-300 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.12)]" aria-hidden><Landmark className="size-5" /></span>
                  <Badge className="border-white/15 bg-white/10 text-white/85">Explore loans</Badge>
                </span>
              </div>
              <h2 className="mt-2 text-[1.45rem] font-semibold leading-tight">Find the right loan for your goals</h2>
              <p className="text-[0.95rem] leading-relaxed text-white/75">Tell VITRAM the purpose, amount and whether you can offer collateral. It checks what it can from your profile and compares options on their full cost.</p>
              <div className="mt-auto flex flex-wrap gap-2 pt-3">
                <Link to="/loans/need" className={buttonClass('secondary', 'md', 'border-transparent')}><Search className="size-4" aria-hidden />Start exploring</Link>
                <button type="button" onClick={() => ask('I need a loan')}
                  className="inline-flex min-h-11 items-center gap-2 rounded-[var(--radius-control)] px-4 text-[0.95rem] font-medium text-white/90 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.22)] transition-colors hover:bg-white/10 hover:text-white">
                  <MessageCircle className="size-4" aria-hidden />Ask Vitt Saathi instead
                </button>
              </div>
            </Panel>
            <Panel className="flex flex-col gap-3 p-6 sm:p-7">
              <span className="flex items-center gap-2.5"><IconTile tone="indigo"><FileText /></IconTile><Badge tone="indigo">Analyse a loan document</Badge></span>
              <h2 className="mt-2 text-[1.45rem] font-semibold leading-tight">Understand a loan you already have or were offered</h2>
              <p className="text-[0.95rem] leading-relaxed text-muted">Upload a sanction letter, Key Facts Statement or agreement. VITRAM extracts the terms with page references, works out the real cost and flags clauses to read.</p>
              <Link to="/loans/analyze" className="group mt-auto flex items-center gap-3 rounded-[var(--radius-card)] border-2 border-dashed border-indigo/25 bg-white/60 p-4 transition-colors hover:border-indigo/55 hover:bg-white">
                <IconTile tone="indigo" size="sm"><CloudUpload /></IconTile>
                <span className="min-w-0 flex-1"><span className="block font-semibold">Upload a loan document</span><span className="text-sm text-muted">PDF, up to 15 MB</span></span>
                <ArrowRight className="size-4 text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-indigo" aria-hidden />
              </Link>
            </Panel>
          </div>

          <Panel className="p-6" aria-labelledby="loan-docs-h">
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 id="loan-docs-h" className="text-[1.1rem] font-semibold">Your loan documents</h2>
                <p className="text-sm text-muted">Each document shows its real cost and the clauses worth reading.</p>
              </div>
              <LinkButton to="/loans/analyze" variant="secondary" icon={<Upload className="size-4" />}>Upload document</LinkButton>
            </div>
            {docs.isLoading ? <div className="flex flex-col gap-2"><Skeleton className="h-16" /><Skeleton className="h-16" /></div> : docs.data?.length ? (
              <ul className="flex flex-col gap-2">
                {docs.data.map((d) => (
                  <li key={d.id}>
                    <Link to={`/loans/documents/${d.id}`} className="group flex items-center gap-3 rounded-[var(--radius-card)] border border-white/80 bg-white/70 px-4 py-3.5 transition-[background-color,box-shadow] hover:bg-white hover:shadow-[var(--elev-2)]">
                      <IconTile tone="indigo" size="sm"><FileText /></IconTile>
                      <span className="min-w-0 flex-1"><span className="block truncate font-medium group-hover:text-indigo-dark">{d.display_name}</span>
                        <span className="text-sm text-muted">Uploaded {date(d.upload_time)} · {d.status === 'failed' ? "Couldn't be read" : `${d.facts_found ?? 0} terms found`}</span></span>
                      <DocStatus status={d.status} />
                      <ArrowRight className="size-4 text-muted transition-transform group-hover:translate-x-0.5" aria-hidden />
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="flex flex-col items-center gap-2 rounded-[var(--radius-card)] border-2 border-dashed border-indigo/15 px-6 py-10 text-center">
                <IconTile tone="indigo"><FileText /></IconTile>
                <p className="mt-1 font-semibold">No loan documents yet</p>
                <p className="max-w-md text-sm text-muted">Upload a sanction letter, agreement or Key Facts Statement to see the terms and the real cost.</p>
                <LinkButton to="/loans/analyze" className="mt-2" icon={<Upload className="size-4" />}>Upload your first document</LinkButton>
              </div>
            )}
          </Panel>
        </div>

        <aside className="flex flex-col gap-5" aria-label="Loan shortcuts">
          <Panel className="p-5" aria-labelledby="types-h">
            <h2 id="types-h" className="mb-2 font-semibold">Common loan types</h2>
            <ul className="-mx-2 flex flex-col">
              {TYPES.map((t) => (
                <li key={t.purpose}>
                  <Link to={`/loans/need?purpose=${t.purpose}`} className="group flex items-center gap-3 rounded-[14px] px-2 py-2 transition-colors hover:bg-ink/[0.04]">
                    <IconTile tone={t.tone} size="sm">{t.icon}</IconTile>
                    <span className="min-w-0 flex-1"><span className="block text-[0.95rem] font-medium">{t.label}</span><span className="block text-xs text-muted">{t.body}</span></span>
                    <ChevronRight className="size-4 text-muted transition-transform group-hover:translate-x-0.5" aria-hidden />
                  </Link>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel className="p-5" aria-labelledby="checks-h">
            <div className="mb-3 flex items-center gap-2.5"><IconTile tone="indigo" size="sm"><BarChart3 /></IconTile><h2 id="checks-h" className="font-semibold">Before you sign</h2></div>
            <ul className="flex flex-col gap-2.5 text-sm">
              {['Compare the total cost, not just the interest rate', 'Check processing fees, GST and other charges', 'Read prepayment and late-payment clauses'].map((t) => (
                <li key={t} className="flex items-start gap-2.5"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-positive" aria-hidden />{t}</li>
              ))}
            </ul>
          </Panel>
        </aside>
      </div>
    </>
  )
}

function DocStatus({ status }: { status: DocumentRow['status'] }) {
  const m = { queued: ['Uploaded', 'neutral'], processing: ['Processing', 'indigo'], needs_review: ['Ready for review', 'caution'], ready: ['Ready', 'positive'], failed: ['Failed', 'critical'] } as const
  const [label, tone] = m[status] ?? ['Uploaded', 'neutral']
  return <Badge tone={tone} className="hidden sm:inline-flex">{label}</Badge>
}

/* --- S11 Loan need ------------------------------------------------------- */

export function LoanNeed() {
  useSaathiPage('loan')
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const profile = useQuery({ queryKey: ['profile'], queryFn: () => get<any>('/profile') })
  const [f, setF] = useState({ purpose: params.get('purpose') ?? 'personal', amount: params.get('amount') ?? '', tenure: params.get('tenure') ?? '', collateral: 'unsure', ctype: 'property', cval: '', emi: '', prepay: false, income: '' })
  const [err, setErr] = useState<{ field: string; msg: string } | null>(null)
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value })
  const p = profile.data?.profile
  const income = p?.income_summary?.monthly_estimate
  const surplus = p?.cashflow_metrics?.monthly_surplus?.value
  const secured = ['home', 'vehicle'].includes(f.purpose)
  function setPurpose(purpose: string) {
    // Home and vehicle loans are secured by the asset being bought.
    if (purpose === 'home') setF({ ...f, purpose, collateral: 'yes', ctype: 'property' })
    else if (purpose === 'vehicle') setF({ ...f, purpose, collateral: 'yes', ctype: 'vehicle' })
    else setF({ ...f, purpose })
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    const amount = parseAmountInput(f.amount)
    if (!amount || amount <= 0) { setErr({ field: 'amount', msg: 'Enter how much you need.' }); return }
    const q = new URLSearchParams({ purpose: f.purpose, amount: String(amount) })
    if (f.tenure) q.set('tenure', String(Number(f.tenure) * 12))
    q.set('collateral', f.collateral === 'yes' ? f.ctype : f.collateral === 'no' ? 'none' : 'unsure')
    if (f.collateral === 'yes' && f.cval) q.set('cval', String(parseAmountInput(f.cval) ?? ''))
    if (f.emi) q.set('emi', String(parseAmountInput(f.emi) ?? ''))
    if (f.prepay) q.set('prepay', '1')
    if (f.income) q.set('income', String(parseAmountInput(f.income) ?? ''))
    navigate(`/loans/results?${q}`)
  }
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Loans', to: '/loans' }]} title="What do you need the loan for?" />
      <form onSubmit={submit} className="flex max-w-2xl flex-col gap-6" noValidate>
        <Panel className="grid gap-5 p-5 sm:grid-cols-2">
          <Field label="Purpose" className="sm:col-span-2"><Select value={f.purpose} onChange={(e) => setPurpose(e.target.value)}>{PURPOSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
          <Field label="Amount needed" error={err?.field === 'amount' ? err.msg : null}><Input prefix="₹" inputMode="numeric" value={f.amount} onChange={set('amount')} placeholder="3,00,000" /></Field>
          <Field label="Preferred tenure (years)" optional hint="Leave blank to see typical options."><Input inputMode="numeric" value={f.tenure} onChange={set('tenure')} /></Field>
        </Panel>
        <Panel className="flex flex-col gap-4 p-5">
          <Segmented label={secured ? `${f.purpose === 'home' ? 'Home' : 'Vehicle'} loans are secured by what you buy. Can it be pledged (girvi) to the lender?` : 'Can you pledge something as collateral (girvi)?'}
            value={f.collateral} onChange={(v) => setF({ ...f, collateral: v })}
            options={[{ value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }, { value: 'unsure', label: 'Not sure' }]} />
          {f.collateral === 'yes' && (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="What"><Select value={f.ctype} onChange={set('ctype')}><option value="property">Property</option><option value="vehicle">Vehicle</option><option value="gold">Gold</option><option value="fixed_deposit">Fixed deposit</option></Select></Field>
              <Field label="Approximate value" optional hint="Lenders finance only part of the value."><Input prefix="₹" inputMode="numeric" value={f.cval} onChange={set('cval')} /></Field>
            </div>
          )}
        </Panel>
        <Panel className="flex flex-col gap-4 p-5">
          <h2 className="font-semibold">Affordability</h2>
          {income?.value ? (
            <p className="flex flex-wrap items-center gap-2 text-[0.95rem]">Using your monthly income of <b className="num">{inr(income.value)}</b><TrustMark state={income.state} />
              {surplus != null && <>and average surplus of <b className="num">{inr(surplus)}</b></>}</p>
          ) : (
            <Field label="Monthly take-home income" optional hint="Not confirmed in your profile yet. Used only for this search."><Input prefix="₹" inputMode="numeric" value={f.income} onChange={set('income')} /></Field>
          )}
          <Field label="A comfortable EMI" optional hint="The most you'd like to pay each month."><Input prefix="₹" inputMode="numeric" value={f.emi} onChange={set('emi')} /></Field>
          <Checkbox checked={f.prepay} onChange={(e) => setF({ ...f, prepay: e.target.checked })} label="I may want to prepay or close the loan early" />
        </Panel>
        <Button type="submit" size="lg" className="w-fit">Show options</Button>
      </form>
    </>
  )
}

/* --- S12 Results --------------------------------------------------------- */

export function LoanResults() {
  useSaathiPage('loan')
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const intent = useMemo(() => intentFromParams(params), [params])
  const q = useQuery({ queryKey: ['loan-rec', params.toString()], queryFn: () => post<any>('/loans/recommend', intent), enabled: intent.amount > 0 })
  const [sel, setSel] = useState<string[]>([])
  if (!intent.amount) return <EmptyState title="Tell us what you need first" action={<LinkButton to="/loans/need">Start</LinkButton>} />
  if (q.isLoading) return <PageSkeleton />
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  const toggle = (id: string) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : s.length >= 4 ? s : [...s, id]))
  const purpose = PURPOSES.find(([v]) => v === intent.purpose)?.[1]
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Loans', to: '/loans' }]}
        title={`${inr(intent.amount)} for ${purpose?.toLowerCase()}`}
        description="Ranked by how well they may fit based on the information available — total cost, affordability, flexibility and what's still unknown. Rates are indicative."
        actions={<LinkButton to={`/loans/need?${params}`} variant="secondary">Change details</LinkButton>} />
      <div className="mb-4 flex flex-wrap items-center gap-3"><SampleBadge meta={d.results[0]?.catalogue} /><span className="text-sm text-muted">Fictional lenders, illustrative terms.</span></div>
      {d.missing_data.map((m: any) => <Callout key={m.key} tone="caution" className="mb-3">{m.message}</Callout>)}
      {d.results.length === 0 && <EmptyState title="No suitable options in the sample catalogue" body="Try a different amount, tenure or collateral answer." />}
      <ol className="flex flex-col gap-4">
        {d.results.map((r: any, i: number) => {
          const q2 = new URLSearchParams({ amount: String(intent.amount), tenure: String(r.tenure_months), purpose: intent.purpose })
          return (
            <li key={r.product_id}>
              <Panel className={clsx('p-5', i === 0 && 'border-indigo/50')}>
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      {i === 0 && <Badge tone="indigo">May fit best</Badge>}
                      <Badge>{r.secured ? 'Secured' : 'Unsecured'}</Badge>
                      <Badge>{r.interest_type === 'floating' ? 'Floating rate' : 'Fixed rate'}</Badge>
                    </div>
                    <h2 className="mt-2 text-lg font-semibold"><Link to={`/loans/p/${r.product_id}?${q2}`} className="hover:text-indigo">{r.product_name}</Link></h2>
                    <p className="text-sm text-muted">{r.lender} · {pct(r.indicative_rate)} indicative ({pct(r.rate_range[0])}–{pct(r.rate_range[1])})</p>
                    <div className="mt-3 grid gap-4 sm:grid-cols-2">
                      <div>
                        <p className="text-sm font-medium">Why this may fit</p>
                        <ul className="mt-1 flex flex-col gap-1 text-[0.95rem]">{r.why.map((w: string) => <li key={w} className="flex gap-2"><Check className="mt-1 size-4 shrink-0 text-positive" aria-hidden />{w}</li>)}</ul>
                      </div>
                      {r.cautions.length > 0 && (
                        <div>
                          <p className="text-sm font-medium">Keep in mind</p>
                          <ul className="mt-1 flex list-disc flex-col gap-1 pl-5 text-[0.95rem] text-ink/85">{r.cautions.map((w: string) => <li key={w}>{w}</li>)}</ul>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-col gap-2 border-line lg:w-60 lg:border-l lg:pl-5">
                    <p className="text-sm text-muted">EMI for {months(r.tenure_months)}</p>
                    <p className="num text-2xl font-semibold"><Money value={r.cost.monthly_emi} /></p>
                    <p className="text-sm">Total you pay <Money value={r.cost.scheduled_total_outflow} className="font-medium" /></p>
                    <p className="text-sm text-muted">incl. <Money value={r.cost.upfront_charges_total} /> fees & GST</p>
                    <div className="mt-2 flex flex-col gap-2">
                      <LinkButton to={`/loans/p/${r.product_id}?${q2}`} size="sm">Real cost & clauses</LinkButton>
                      <Checkbox checked={sel.includes(r.product_id)} onChange={() => toggle(r.product_id)} label="Compare" />
                    </div>
                  </div>
                </div>
              </Panel>
            </li>
          )
        })}
      </ol>
      {d.excluded.length > 0 && (
        <details className="mt-6">
          <summary className="font-medium">{d.excluded.length} {d.excluded.length === 1 ? "option doesn't" : "options don't"} fit what you told us</summary>
          <ul className="mt-2 flex flex-col gap-1 text-[0.95rem] text-muted">{d.excluded.map((x: any) => <li key={x.product_id}>{x.product_name} ({x.lender}) — {x.reasons.join('; ')}</li>)}</ul>
        </details>
      )}
      {sel.length > 0 && (
        <div className="sticky bottom-20 z-20 mt-6 flex items-center justify-between gap-3 rounded-[var(--radius-panel)] bg-ink px-5 py-3 text-white shadow-lg lg:bottom-4">
          <span>{sel.length} selected{sel.length < 2 && ' — pick at least 2'}</span>
          <Button variant="saathi" disabled={sel.length < 2}
            onClick={() => navigate(`/loans/compare?ids=${sel.join(',')}&${new URLSearchParams({ amount: String(intent.amount), purpose: intent.purpose, ...(intent.tenure_months ? { tenure: String(intent.tenure_months) } : {}) })}`)}>Compare side by side</Button>
        </div>
      )}
    </>
  )
}

/* --- S13 Compare --------------------------------------------------------- */

export function LoanCompare() {
  useSaathiPage('loan')
  const [params] = useSearchParams()
  const ids = (params.get('ids') ?? '').split(',').filter(Boolean)
  const intent = intentFromParams(params)
  const q = useQuery({ queryKey: ['loan-cmp', params.toString()], queryFn: () => post<any>('/loans/compare', { product_ids: ids, intent }), enabled: ids.length >= 2 })
  if (ids.length < 2) return <EmptyState title="Pick at least two loans to compare" action={<LinkButton to="/loans/need">Find loans</LinkButton>} />
  if (q.isLoading) return <PageSkeleton />
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const ps = q.data.products
  const minOut = Math.min(...ps.map((p: any) => p.price.scheduled_total_outflow))
  const rows: [string, (p: any) => any][] = [
    ['Indicative rate', (p) => `${pct(p.price.indicative_rate)} (${pct(p.price.rate_range[0])}–${pct(p.price.rate_range[1])})`],
    ['EMI', (p) => <Money value={p.price.monthly_emi} />],
    ['Tenure shown', (p) => months(p.tenure_months)],
    ['Total interest', (p) => <Money value={p.price.scheduled_interest} />],
    ['Fees & GST (known)', (p) => <Money value={p.price.upfront_charges_total} />],
    ['Total you pay', (p) => <span className={clsx('font-semibold', p.price.scheduled_total_outflow === minOut && 'text-positive')}><Money value={p.price.scheduled_total_outflow} />{p.price.scheduled_total_outflow === minOut && <span className="block text-xs font-normal">lowest</span>}</span>],
    ['Annualized cost', (p) => (p.price.annualized_cost_pct != null ? pct(p.price.annualized_cost_pct) : 'Not computable')],
    ['Not included', (p) => (p.price.missing.length ? <span className="text-caution">{p.price.missing.join('; ')}</span> : '—')],
    ['Rate type', (p) => (p.flexibility.interest_type === 'floating' ? 'Floating' : 'Fixed')],
    ['Tenure range', (p) => `${p.flexibility.tenure_range[0]}–${p.flexibility.tenure_range[1]} months`],
    ['Part-prepayment', (p) => { const r = p.flexibility.part_prepayment; return !r ? 'Not stated' : r.allowed === false ? 'Not allowed' : `Allowed${r.allowed_after_months ? ` after ${r.allowed_after_months} EMIs` : ''}${r.charge_pct != null ? `, ${r.charge_pct}% charge` : ''}` }],
    ['Foreclosure', (p) => { const r = p.flexibility.foreclosure; return !r ? 'Not stated' : `${r.charge_pct ?? '?'}% charge${r.allowed_after_months ? ` after ${r.allowed_after_months} EMIs` : ''}` }],
    ['Collateral', (p) => ({ none: 'Not needed', required: 'Required', optional: 'Optional' } as any)[p.collateral] ?? p.collateral],
    ['Eligibility', (p) => (p.eligible ? <span>Known criteria met{p.eligibility_fit.unknown.length > 0 && <span className="block text-xs text-caution">{p.eligibility_fit.unknown.length} unknown</span>}</span> : <span className="text-critical">{p.excluded_reasons.join('; ')}</span>)],
    ['Warnings', (p) => <ul className="flex flex-col gap-1">{p.warnings.map((w: any) => <li key={w.title} className="text-sm">{w.title}</li>)}</ul>],
    ['Source', (p) => <SampleBadge meta={p.catalogue} />],
  ]
  return (
    <>
      <PageHeader eyebrow={<Link to={`/loans/results?${params}`} className="hover:text-ink">Back to results</Link>} title="Compare loans" description={`For ${inr(intent.amount)}. Scheduled costs assume every EMI is paid on time.`} />
      <Panel className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-[0.95rem]">
          <thead>
            <tr className="border-b border-line">
              <th scope="col" className="sticky left-0 w-44 bg-surface p-4 text-left text-sm font-normal text-muted"><span className="sr-only">Loan detail</span></th>
              {ps.map((p: any) => (
                <th key={p.product_id} scope="col" className="p-4 text-left align-top">
                  <Link to={`/loans/p/${p.product_id}?amount=${intent.amount}&tenure=${p.tenure_months}&purpose=${intent.purpose}`} className="font-semibold hover:text-indigo">{p.product_name}</Link>
                  <span className="block text-sm font-normal text-muted">{p.lender}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map(([label, fn]) => (
              <tr key={label}>
                <th scope="row" className="sticky left-0 bg-surface p-4 text-left text-sm font-normal text-muted">{label}</th>
                {ps.map((p: any) => <td key={p.product_id} className="num p-4 align-top">{fn(p)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </>
  )
}

/* --- S14/S15 Detail + what-if ------------------------------------------- */

export function LoanDetail() {
  const { id } = useParams()
  useSaathiPage('loan', id)
  const { ask } = useSaathi()
  const [params, setParams] = useSearchParams()
  const product = useQuery({ queryKey: ['loan-product', id], queryFn: () => get<any>(`/loans/products/${id}`) })
  const p = product.data?.product
  const amount = Number(params.get('amount') ?? p?.repayment?.amount_min ?? 0)
  const tenure = Number(params.get('tenure') ?? 36)
  const [amt, setAmt] = useState(String(amount || ''))
  const [ten, setTen] = useState(String(tenure))
  const cost = useQuery({
    queryKey: ['loan-cost', id, amount, tenure],
    queryFn: () => post<any>('/loans/calculate', { kind: 'cost', product_id: id, principal: amount, tenure_months: tenure, include_schedule: true }),
    enabled: !!p && amount > 0,
  })
  if (product.isLoading) return <PageSkeleton />
  if (product.isError) return <ErrorState error={product.error} />
  const c = cost.data?.result
  const outOfRange = p && (amount < p.repayment.amount_min || amount > p.repayment.amount_max || tenure < p.repayment.tenure_min || tenure > p.repayment.tenure_max)
  return (
    <>
      <PageHeader eyebrow={<button onClick={() => history.back()} className="hover:text-ink">Back</button>} title={p.product_name}
        description={<span className="flex flex-wrap items-center gap-2">{p.lender} · {p.secured ? 'Secured' : 'Unsecured'} · {p.pricing.interest_type} rate <SampleBadge meta={p.catalogue} /></span>}
        actions={<Button variant="secondary" icon={<MessageCircle className="size-4" />} onClick={() => ask(`Explain the real cost and the clauses I should read for ${p.product_name}`)}>Ask Vitt Saathi</Button>} />
      <Panel className="mb-6 p-5">
        <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); const a = parseAmountInput(amt); if (a) setParams({ ...Object.fromEntries(params), amount: String(a), tenure: ten }) }}>
          <Field label="Amount"><Input prefix="₹" inputMode="numeric" value={amt} onChange={(e) => setAmt(e.target.value)} className="w-44" /></Field>
          <Field label="Tenure (months)"><Input inputMode="numeric" value={ten} onChange={(e) => setTen(e.target.value)} className="w-32" /></Field>
          <Button type="submit" variant="secondary">Recalculate</Button>
        </form>
        {outOfRange && <Callout tone="caution" className="mt-4">This product offers {inr(p.repayment.amount_min)}–{inr(p.repayment.amount_max)} over {p.repayment.tenure_min}–{p.repayment.tenure_max} months. The figures below are outside that range.</Callout>}
      </Panel>
      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <Panel className="p-5">
          <h2 className="mb-4 text-lg font-semibold">Real cost</h2>
          {cost.isLoading && <p className="text-sm text-muted">Calculating…</p>}
          {cost.isError && <ErrorState error={cost.error} />}
          {c && <RealCost cost={c} />}
          <p className="mt-4 text-xs text-muted">Based on the indicative rate. The lender sets your actual rate after assessing your application.</p>
        </Panel>
        <div className="flex flex-col gap-6">
          <Panel className="p-5"><h2 className="mb-3 font-semibold">Clauses to read</h2><Clauses clauses={p.clauses} /></Panel>
          <Panel className="p-5">
            <h2 className="mb-1 font-semibold">Eligibility in the sample terms</h2>
            <KeyValue items={[
              { k: 'Employment', v: p.eligibility.employment?.join(', ') },
              { k: 'Minimum monthly income', v: p.eligibility.min_monthly_income ? inr(p.eligibility.min_monthly_income) : 'Not stated' },
              { k: 'Age', v: `${p.eligibility.age_min}–${p.eligibility.age_max}` },
              { k: 'Credit score', v: p.eligibility.credit_score_min ? `${p.eligibility.credit_score_min}+ (VITRAM can't check this)` : 'Not stated' },
              { k: 'Collateral', v: p.eligibility.collateral },
            ]} />
            <h3 className="mt-4 text-sm font-medium">Documents usually needed</h3>
            <ul className="mt-1 list-disc pl-5 text-[0.95rem] text-muted">{p.documents.map((d: string) => <li key={d}>{d}</li>)}</ul>
          </Panel>
          <p className="text-sm text-muted">VITRAM doesn't process applications. Apply directly with the lender after checking their current terms.</p>
        </div>
      </div>
      {c && (
        <Panel className="mt-6 p-5">
          <h2 className="mb-1 text-lg font-semibold">What if…</h2>
          <p className="mb-4 text-sm text-muted">Calculated by VITRAM's finance engine using this product's stated rules.</p>
          <WhatIf base={{ product_id: id, principal: amount, tenure_months: tenure }} floating={p.pricing.interest_type === 'floating'} />
        </Panel>
      )}
      {c?.schedule && (
        <details className="mt-6">
          <summary className="font-medium">Repayment schedule ({c.schedule.length} months)</summary>
          <Panel className="mt-3 max-h-96 overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surface"><tr className="text-muted"><th className="p-2 text-left font-normal">Month</th><th className="p-2 text-right font-normal">EMI</th><th className="p-2 text-right font-normal">Interest</th><th className="p-2 text-right font-normal">Principal</th><th className="p-2 text-right font-normal">Balance</th></tr></thead>
              <tbody className="num divide-y divide-line">{c.schedule.map((r: any) => <tr key={r.month}><td className="p-2">{r.month}</td><td className="p-2 text-right">{inr(r.payment)}</td><td className="p-2 text-right">{inr(r.interest)}</td><td className="p-2 text-right">{inr(r.principal)}</td><td className="p-2 text-right">{inr(r.closing_balance)}</td></tr>)}</tbody>
            </table>
          </Panel>
        </details>
      )}
    </>
  )
}

/* --- S16 Loan document analyzer ------------------------------------------ */

export function LoanAnalyze() {
  useSaathiPage('loan')
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [progress, setProgress] = useState<number | null>(null)
  const vision = useVision()
  const [dup, setDup] = useState<ApiError | null>(null)
  const m = useMutation({
    mutationFn: () => { const fd = new FormData(); fd.append('file', file!); fd.append('type', 'loan_document'); return upload<DocumentRow>('/documents', fd, setProgress) },
    onSettled: () => setProgress(null),
    onSuccess: (d) => navigate(`/loans/documents/${d.id}`),
    onError: (e) => { if (isDuplicate(e)) { setDup(e as ApiError); setErr(null) } else setErr(errorMessage(e)) },
  })
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Loans', to: '/loans' }]} title="Analyse a loan document" description="Sanction letter, Key Facts Statement, loan agreement or repayment schedule — a PDF, or a clear photo of each page." />
      <div className="max-w-2xl">
        <ConsentGate purpose="financial_documents" title="Before you upload" body={DOC_CONSENT_BODY}>
          <Panel className="flex flex-col gap-4 p-5">
            {dup && <DuplicateNotice expectedType="loan_document" error={dup} onReread={(d) => navigate(`/loans/documents/${d.id}`)} />}
            <FileDrop accept={acceptFor('loan_document', vision)} file={file} onFile={(f) => { setFile(f); setDup(null) }} error={err} camera={vision?.configured} progress={progress} scanNote={vision?.configured ? (vision.on_device ? 'Photos and scans are read on this device' : 'Photos and scans are read by Gemini') : undefined}
              hint={vision?.configured ? 'PDF or photo · up to 15 MB' : 'PDF · up to 15 MB. Photos and scans need OCR, which isn’t set up on this server.'} />
            <div className="flex flex-wrap items-center gap-3">
              <Button size="lg" disabled={!file} loading={m.isPending} onClick={() => { setErr(null); m.mutate() }}>Analyse</Button>
              <a href="/api/demo/fixtures/sample_loan_kfs.pdf" className="text-sm font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">Download a sample KFS to try</a>
            </div>
          </Panel>
        </ConsentGate>
      </div>
    </>
  )
}

export function LoanDocument() {
  const { id } = useParams()
  useSaathiPage('loan', id)
  const { ask } = useSaathi()
  const poll = useDocumentPoll(id)
  const ready = poll.data && ['ready', 'needs_review'].includes(poll.data.status)
  const q = useQuery({ queryKey: ['loan-doc', id], queryFn: () => get<any>(`/loans/documents/${id}`), enabled: !!ready })
  const { user } = useAuth()
  if (poll.isLoading) return <PageSkeleton />
  if (poll.isError) return <ErrorState error={poll.error} />
  const doc = poll.data!
  if (!ready) {
    return (
      <>
        <PageHeader title={doc.display_name} description={doc.status === 'failed' ? "This document couldn't be read." : 'Reading the document…'} />
        <Panel className="max-w-xl p-5"><ProcessingSteps doc={doc} />{doc.status === 'failed' && <Callout tone="critical" className="mt-4">{doc.error_message}</Callout>}</Panel>
      </>
    )
  }
  if (q.isLoading || !q.data) return <PageSkeleton />
  const d = q.data
  const f = Object.fromEntries(d.facts.map((x: any) => [x.key, x]))
  const glance = [['lender', 'Lender'], ['product_name', 'Loan'], ['principal', 'Loan amount'], ['annual_rate_pct', 'Interest rate'], ['rate_type', 'Interest type'],
    ['tenure_months', 'Tenure'], ['stated_emi', 'EMI (as stated)'], ['first_due_date', 'First EMI'], ['collateral', 'Security']] as const
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Loans', to: '/loans' }]} title="Loan at a glance" description={<span className="flex flex-wrap items-center gap-2">{`${doc.display_name} · ${doc.page_count} page${doc.page_count === 1 ? '' : 's'} · values read automatically — check them against the document.`}{doc.read_from_scan && <Badge tone="indigo">Read from a {doc.mime?.startsWith('image/') ? 'photo' : 'scan'}{doc.ocr?.on_device ? ' on this device' : ''}</Badge>}</span>}
        actions={<Button variant="secondary" icon={<MessageCircle className="size-4" />} onClick={() => ask('What are the prepayment and late-payment terms in this document?')}>Ask about this document</Button>} />
      {doc.warnings.map((w) => <Callout key={w} tone="caution" className="mb-3">{w}</Callout>)}
      <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
        <Panel className="p-5">
          <KeyValue items={glance.filter(([k]) => f[k]).map(([k, label]) => {
            const x = f[k]
            const v = k === 'principal' || k === 'stated_emi' ? <Money value={x.value} /> : k === 'annual_rate_pct' ? pct(x.value) : k === 'tenure_months' ? months(x.value) : k === 'first_due_date' ? date(x.value) : String(x.value)
            return { k: label, v: <span className="font-medium">{v}</span>, extra: <><TrustMark state={x.state} /><SourceLink citation={x.citation} /></> }
          })} />
          {glance.some(([k]) => !f[k]) && <p className="mt-3 text-sm text-muted">Not found in this document: {glance.filter(([k]) => !f[k]).map(([, l]) => l.toLowerCase()).join(', ')}.</p>}
        </Panel>
        <Panel className="p-5">
          <h2 className="mb-4 text-lg font-semibold">Real cost from these terms</h2>
          {d.cost ? <RealCost cost={d.cost} documentId={doc.id} documentName={doc.display_name} /> : <Callout tone="caution">Add the {d.cost_missing.join(', ')} to calculate the real cost.</Callout>}
        </Panel>
      </div>
      <Panel className="mt-6 p-5"><h2 className="mb-3 font-semibold">Clauses to read before you sign</h2><Clauses clauses={d.clauses} documentId={doc.id} documentName={doc.display_name} /></Panel>
      {d.cost && d.user_loan_id && (
        <Panel className="mt-6 p-5">
          <h2 className="mb-4 text-lg font-semibold">What if…</h2>
          <WhatIf base={{ user_loan_id: d.user_loan_id, principal: d.terms.principal, tenure_months: d.terms.tenure_months }} floating={d.terms.rate_type === 'floating'} />
        </Panel>
      )}
      {user && <p className="mt-6 text-sm text-muted">Wrong value? Correct it in <Link to={`/documents?focus=${doc.id}`} className="font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">Documents & data</Link>.</p>}
    </>
  )
}
