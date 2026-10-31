import clsx from 'clsx'
import {
  AlertCircle, ArrowRight, CalendarClock, CalendarDays, Check, CreditCard, FileSearch, FileText, FileUp, Languages, Landmark, LayoutGrid,
  Camera, Lock, MessageCircle, Mic, PiggyBank, Plus, ReceiptIndianRupee, ReceiptText, ScanLine, ShieldCheck, Sparkles, Wallet,
} from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { DocStack, PeaksArt } from '../../components/illustrations'
import { LinkButton } from '../../components/ui/button'
import { Badge, IconTile, Money, Panel, SectionHeader, Stat, TrustMark } from '../../components/ui/data'
import { ErrorState, PageSkeleton } from '../../components/ui/feedback'
import { compactInr, dayMonth, num, relDays } from '../../lib/format'
import { useVision } from '../../lib/vision'
import { CategoryBars } from '../profile/Review'
import { useSaathi, useSaathiPage } from '../saathi/context'
import { SaathiMark } from '../saathi/SaathiPanel'
import { ForecastCard } from '../forecast/Forecast'
import { CashFlowChart } from './CashFlowChart'
import { setupSteps, useDashboard } from './setup'

/* --- pieces -------------------------------------------------------------- */

function SummaryCard({ to, icon, tone, label, value, sub, mark }: {
  to: string; icon: ReactNode; tone: 'indigo' | 'green' | 'violet' | 'sky'; label: string; value: ReactNode; sub: ReactNode; mark?: ReactNode
}) {
  return (
    <Link to={to} className="surface-card lift group flex items-start gap-4 rounded-[var(--radius-card)] p-5">
      <IconTile tone={tone} size="lg">{icon}</IconTile>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2 text-sm text-muted">{label}{mark}</span>
        <span className="num mt-0.5 block truncate text-[1.35rem] font-semibold tracking-[-0.02em]">{value}</span>
        <span className="mt-1 flex items-start justify-between gap-2 text-sm text-muted">
          <span className="line-clamp-2">{sub}</span>
          <ArrowRight className="size-4 shrink-0 transition-transform duration-[var(--dur)] group-hover:translate-x-0.5 group-hover:text-indigo" aria-hidden />
        </span>
      </span>
    </Link>
  )
}

function SetupChecklist({ d }: { d: any }) {
  const steps = setupSteps(d)
  const done = steps.filter((s) => s.done).length
  const pct = steps.length ? done / steps.length : 0
  const R = 44, C = 2 * Math.PI * R
  return (
    <Panel className="flex h-full flex-col p-6" aria-labelledby="setup-h">
      <div className="mb-4 flex items-start gap-3">
        <IconTile tone="red"><Check /></IconTile>
        <div>
          <h2 id="setup-h" className="text-[1.05rem] font-semibold">Your setup</h2>
          <p className="text-sm text-muted">The more VITRAM knows, the more precise every answer gets.</p>
        </div>
      </div>
      <div className="flex flex-1 flex-wrap items-center gap-6">
        <div className="relative mx-auto size-28 shrink-0" role="img" aria-label={`${done} of ${steps.length} setup steps done`}>
          <svg viewBox="0 0 100 100" className="size-full -rotate-90" aria-hidden>
            <circle cx="50" cy="50" r={R} fill="none" stroke="rgb(22 29 69 / 0.08)" strokeWidth="9" />
            {pct > 0 && <circle cx="50" cy="50" r={R} fill="none" stroke="url(#setup-g)" strokeWidth="9" strokeLinecap="round" strokeDasharray={`${C * pct} ${C}`} />}
            <defs><linearGradient id="setup-g" x1="0" x2="1"><stop offset="0" stopColor="#6d7cf0" /><stop offset="1" stopColor="#3443b5" /></linearGradient></defs>
          </svg>
          <span className="absolute inset-0 flex flex-col items-center justify-center" aria-hidden>
            <span className="num text-2xl font-semibold">{done}/{steps.length}</span>
            <span className="text-xs text-muted">done</span>
          </span>
        </div>
        <ul className="flex min-w-44 flex-1 flex-col gap-1">
          {steps.map((s) => (
            <li key={s.key}>
              <Link to={s.to} className="group flex min-h-10 items-center gap-2.5 rounded-[12px] px-2 text-[0.95rem] transition-colors hover:bg-ink/[0.04]">
                <span className={clsx('flex size-5 shrink-0 items-center justify-center rounded-full border-2', s.done ? 'border-positive bg-positive text-white' : 'border-line-strong bg-white')} aria-hidden>
                  {s.done && <Check className="size-3" strokeWidth={3} />}
                </span>
                <span className={clsx('flex-1', s.done && 'text-muted line-through decoration-muted/40')}>{s.label}</span>
                <span className="sr-only">{s.done ? '(done)' : '(to do)'}</span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </Panel>
  )
}

function GetStarted() {
  const benefits = [
    { icon: <PiggyBank />, tone: 'green' as const, label: 'Understand your spending' },
    { icon: <FileSearch />, tone: 'sky' as const, label: 'Find what you pay every month' },
    { icon: <CalendarClock />, tone: 'amber' as const, label: 'Detect EMIs and bills' },
    { icon: <Sparkles />, tone: 'red' as const, label: 'Get answers from your own numbers' },
  ]
  return (
    <section aria-labelledby="gs-h" className="glass relative isolate flex h-full flex-col gap-6 overflow-hidden rounded-[var(--radius-window)] p-6 sm:flex-row sm:items-center sm:p-7">
      <span className="pointer-events-none absolute -left-16 -top-20 -z-10 size-72 rounded-full bg-indigo-300/25 blur-3xl" aria-hidden />
      <DocStack className="mx-auto w-40 shrink-0 sm:w-44" />
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div>
          <Badge tone="indigo" className="mb-2">Get started</Badge>
          <h2 id="gs-h" className="text-[1.4rem] font-semibold tracking-[-0.015em]">Upload a bank statement</h2>
        </div>
        <p className="max-w-[60ch] text-[0.97rem] leading-relaxed text-ink/75">A PDF or CSV from your bank. VITRAM reads it once to build your financial profile, and every number links back to the line it came from.</p>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <LinkButton to="/onboarding/statement" size="lg" icon={<FileUp className="size-4" />}>Upload a bank statement</LinkButton>
          <span className="flex items-center gap-1.5 text-xs text-muted"><Lock className="size-3.5" aria-hidden />Encrypted in your workspace</span>
        </div>
        <ul className="mt-2 grid grid-cols-2 gap-3">
          {benefits.map((b) => (
            <li key={b.label} className="flex items-center gap-2.5 text-sm leading-snug"><IconTile tone={b.tone} size="sm">{b.icon}</IconTile>{b.label}</li>
          ))}
        </ul>
      </div>
    </section>
  )
}

function MoneyPanel({ m }: { m: any }) {
  const inc = m.monthly_income
  return (
    <section aria-labelledby="money-h" className="surface-hero relative isolate h-full overflow-hidden rounded-[var(--radius-window)] p-6 sm:p-7">
      <span className="pointer-events-none absolute -right-24 -top-32 -z-10 size-[24rem] rounded-full bg-indigo/40 blur-3xl" aria-hidden />
      <div className="mb-5 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 id="money-h" className="text-[1.2rem] font-semibold">Your month in money</h2>
          <p className="text-sm text-white/70">From your statement, {dayMonth(m.period_start)} to {dayMonth(m.period_end)}</p>
        </div>
        <Link to="/profile/review" className="inline-flex min-h-10 items-center gap-1 rounded-full bg-white/10 px-3.5 text-sm font-medium text-white shadow-[inset_0_0_0_1px_rgb(255_255_255/0.14)] hover:bg-white/15">Review numbers<ArrowRight className="size-4" aria-hidden /></Link>
      </div>
      <div className="flex flex-col gap-5">
        {(m.monthly_series ?? []).length > 0 && <CashFlowChart series={m.monthly_series} periodStart={m.period_start} periodEnd={m.period_end} />}
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: 'Left over each month', value: <Money value={m.monthly_surplus?.value} />, hint: 'average surplus' },
            { label: 'Regular commitments', value: <Money value={m.fixed_monthly?.value} />, hint: 'EMIs, rent, premiums, bills' },
          ].map((x) => (
            <div key={x.label} className="rounded-[var(--radius-card)] bg-white p-4 text-ink shadow-[var(--glass-highlight),var(--elev-2)]"><Stat label={x.label} value={x.value} hint={x.hint} /></div>
          ))}
          <p className="col-span-2 rounded-[var(--radius-card)] bg-white/[0.07] p-4 text-sm text-white/80 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]">
            Income {inc?.value != null ? <b className="num font-semibold text-white">{compactInr(inc.value)}</b> : <b className="text-white">not confirmed yet</b>}
            {inc?.state && inc.state !== 'confirmed' && inc.value != null && <> — <Link to="/profile/review" className="font-medium text-white underline decoration-marigold/70 underline-offset-2">confirm it</Link> so plans use the right number.</>}
          </p>
        </div>
      </div>
    </section>
  )
}

function Journey({ to, icon, tone, art, title, summary, cta, children }: {
  to: string; icon: ReactNode; tone: 'indigo' | 'green' | 'violet' | 'amber'; art: 'indigo' | 'green' | 'violet' | 'amber'; title: string; summary: ReactNode; cta: string; children?: ReactNode
}) {
  return (
    <li>
      <Link to={to} className="surface-card lift group relative flex h-full flex-col gap-3 overflow-hidden rounded-[var(--radius-card)] p-5">
        <PeaksArt hue={art} className="pointer-events-none absolute -right-2 top-2 w-32 opacity-80 transition-transform duration-[var(--dur-slow)] group-hover:-translate-y-0.5" />
        <IconTile tone={tone} className="relative">{icon}</IconTile>
        <span className="relative mt-6 flex flex-1 flex-col gap-1">
          <span className="text-[1.15rem] font-semibold">{title}</span>
          <span className="text-[0.95rem] leading-snug text-muted">{summary}</span>
          {children}
        </span>
        <span className="relative inline-flex items-center gap-1 text-sm font-medium text-indigo underline decoration-indigo/40 underline-offset-2 group-hover:decoration-indigo">{cta}<ArrowRight className="size-4" aria-hidden /></span>
      </Link>
    </li>
  )
}

function MeetSaathi({ chatMode, voice }: { chatMode: 'gemini' | 'tool'; voice: boolean }) {
  const { ask, setOpen } = useSaathi()
  const [t, setT] = useState('')
  function submit(e: FormEvent) {
    e.preventDefault()
    if (t.trim()) { ask(t.trim()); setT('') } else setOpen(true)
  }
  const chips = [
    { icon: <Sparkles />, label: chatMode === 'gemini' ? 'Gemini configured' : 'Tool mode · answers from calculators' },
    { icon: <Mic />, label: voice ? 'Voice configured' : 'Voice needs setup' },
    { icon: <Languages />, label: 'English, Hindi & Hinglish' },
    { icon: <LayoutGrid />, label: 'Works across all journeys' },
  ]
  return (
    <section aria-labelledby="saathi-h" className="wash-amber relative overflow-hidden rounded-[var(--radius-window)] p-5 sm:p-6">
      <div className="flex flex-col gap-4 @4xl:flex-row @4xl:items-center">
        <div className="flex min-w-0 flex-1 items-center gap-4">
          <SaathiMark className="size-14 shadow-[var(--glow-saathi)]" />
          <div className="min-w-0">
            <h2 id="saathi-h" className="flex flex-wrap items-center gap-2 text-[1.15rem] font-semibold">Meet Vitt Saathi <Badge tone="saathi">Beta</Badge></h2>
            <p className="text-[0.95rem] text-ink/75">Your financial assistant. It answers from your own documents and VITRAM's calculators, and shows where each number comes from.</p>
          </div>
        </div>
        <form onSubmit={submit} className="flex min-w-0 flex-1 items-center gap-2 rounded-full border border-white/80 bg-white/90 p-1.5 shadow-[var(--glass-highlight),var(--elev-1)] focus-within:shadow-[var(--glass-highlight),var(--elev-1),var(--ring)] @4xl:max-w-md">
          <label htmlFor="dash-ask" className="sr-only">Ask Vitt Saathi</label>
          <input id="dash-ask" value={t} onChange={(e) => setT(e.target.value)} placeholder="e.g. What would a ₹5 lakh car loan really cost?"
            className="min-h-11 min-w-0 flex-1 rounded-full bg-transparent px-3 text-[0.95rem] placeholder:text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-marigold/70" />
          <button type="submit" className="inline-flex min-h-11 shrink-0 items-center gap-2 rounded-full bg-[image:var(--grad-saathi)] px-5 font-semibold text-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.35),var(--glow-saathi)] transition-[filter] hover:brightness-105">
            <MessageCircle className="size-4" aria-hidden />Ask
          </button>
        </form>
      </div>
      <ul className="mt-4 flex flex-wrap gap-2" aria-label="Vitt Saathi status">
        {chips.map((c) => (
          <li key={c.label} className="inline-flex items-center gap-1.5 rounded-full border border-white/80 bg-white/75 px-3 py-1 text-xs font-medium text-ink/80 [&_svg]:size-3.5 [&_svg]:text-marigold-deep">{c.icon}{c.label}</li>
        ))}
      </ul>
    </section>
  )
}

/** Makes the document-vision features easy to find, with the server's real OCR status. */
function ScanBand() {
  const vision = useVision()
  const on = vision?.configured
  const items = [
    { to: '/documents/receipts/new', label: 'Scan a receipt', icon: <ReceiptText className="size-4" />, primary: true },
    { to: '/insurance/upload', label: 'Photo of a policy', icon: <ShieldCheck className="size-4" /> },
    { to: '/loans/analyze', label: 'Photo of a loan document', icon: <FileText className="size-4" /> },
    { to: '/onboarding/statement', label: 'Photo of a statement', icon: <Landmark className="size-4" /> },
  ]
  return (
    <section aria-labelledby="scan-h" className="glass relative isolate overflow-hidden rounded-[var(--radius-window)] p-5 sm:p-6">
      <span className="pointer-events-none absolute -right-16 -top-20 -z-10 size-64 rounded-full bg-indigo-300/30 blur-3xl" aria-hidden />
      <div className="flex flex-col gap-4 @4xl:flex-row @4xl:items-center">
        <div className="flex min-w-0 flex-1 items-start gap-4">
          <span className="flex size-14 shrink-0 items-center justify-center rounded-[18px] bg-[image:var(--grad-indigo)] text-white shadow-[0_8px_20px_rgb(52_67_181/0.3)]" aria-hidden><ScanLine className="size-7" /></span>
          <div className="min-w-0">
            <h2 id="scan-h" className="flex flex-wrap items-center gap-2 text-[1.15rem] font-semibold">Scan documents with your camera
              {vision && <Badge tone={on ? 'positive' : 'neutral'}>{on ? (vision.on_device ? 'Read on this device' : 'Read by Gemini') : 'Not set up on this server'}</Badge>}
            </h2>
            <p className="mt-1 max-w-[62ch] text-[0.95rem] text-ink/75">
              {on ? 'Photograph a receipt, a policy page or a loan letter. VITRAM reads the text, finds the key values and shows each one with the line it came from for you to check.'
                : 'Reading photos and scanned PDFs needs OCR on the server. Digital PDFs and CSV statements work already.'}
            </p>
          </div>
        </div>
        {on && (
          <ul className="flex flex-wrap gap-2 @4xl:max-w-md @4xl:justify-end">
            {items.map((it) => (
              <li key={it.to}><LinkButton to={it.to} size="sm" variant={it.primary ? 'primary' : 'secondary'} icon={it.primary ? <Camera className="size-4" /> : it.icon}>{it.label}</LinkButton></li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}

/* --- page ---------------------------------------------------------------- */

export function Dashboard() {
  useSaathiPage('dashboard')
  const q = useDashboard()
  const visionStatus = useVision()
  if (q.isLoading) return <PageSkeleton />
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  const m = d.money
  const j = d.journeys
  const inc = m.monthly_income
  const hasStatement = d.data_quality.statements_processed > 0
  const today = new Date()
  const next = d.upcoming[0]
  const vision = visionStatus
  return (
    <div className="flex flex-col gap-[var(--section-gap)]">
      <header className="flex flex-col gap-5 @4xl:flex-row @4xl:items-end @4xl:justify-between">
        <div className="min-w-0">
          <h1 className="text-[2.1rem] font-semibold leading-tight tracking-[-0.025em] sm:text-[2.75rem]">Hello, {d.user.name.split(' ')[0]}</h1>
          <p className="mt-2 text-[1.05rem] text-ink/80">Take control of your financial life with VITRAM.</p>
          <p className="mt-1 max-w-[64ch] text-[0.97rem] text-muted">
            {hasStatement ? <>Everything here comes from your statement ({dayMonth(m.period_start)} – {dayMonth(m.period_end)}) and the documents you've added.</> : 'VITRAM uses only the documents you add and the numbers you confirm. Nothing is guessed.'}
            {d.data_quality.items_needing_review > 0 && <> <Link to="/profile/review" className="font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">{d.data_quality.items_needing_review} items need review</Link>.</>}
            {d.data_quality.documents_processing > 0 && <> {d.data_quality.documents_processing} document{d.data_quality.documents_processing > 1 ? 's are' : ' is'} still processing…</>}
          </p>
        </div>
        <div className="glass flex items-center gap-4 rounded-[var(--radius-card)] px-5 py-4 @4xl:min-w-72">
          <IconTile tone="indigo"><CalendarDays /></IconTile>
          <div className="min-w-0">
            <p className="text-sm text-muted">{today.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })}</p>
            {next ? <p className="font-semibold leading-snug">Next due: {next.title} <span className="font-normal text-muted">{relDays(next.date)}</span></p>
              : <p className="font-semibold leading-snug">Nothing due that VITRAM knows of</p>}
          </div>
        </div>
      </header>

      <section aria-label="Summary" className="grid gap-4 @xl:grid-cols-2 @5xl:grid-cols-4">
        <SummaryCard to={hasStatement ? '/profile/review' : '/onboarding/statement'} icon={<Wallet />} tone="indigo" label="Monthly income"
          value={inc?.value != null ? <Money value={inc.value} /> : 'Not available'} mark={inc?.value != null ? <TrustMark state={inc.state ?? 'extracted'} /> : undefined}
          sub={inc?.value != null ? (inc.state === 'confirmed' ? 'Confirmed by you' : 'Review to confirm') : 'Add a statement'} />
        <SummaryCard to={hasStatement ? '/profile/review' : '/onboarding/statement'} icon={<ReceiptIndianRupee />} tone="green" label="Average spending"
          value={hasStatement ? <Money value={m.avg_monthly_outflow?.value} /> : 'Not available'} mark={hasStatement ? <TrustMark state="estimate" /> : undefined}
          sub={hasStatement ? `a month, over ${m.months_covered} months` : 'Add a statement'} />
        <SummaryCard to="/emis" icon={<CalendarClock />} tone="sky" label="Active EMIs" value={num(j.emis.count)}
          sub={j.emis.count ? <><Money value={j.emis.monthly_total} /> a month{j.emis.confirmed < j.emis.count ? ` · ${j.emis.count - j.emis.confirmed} to confirm` : ''}</> : 'Add or detect EMIs'} />
        <SummaryCard to="/insurance" icon={<ShieldCheck />} tone="violet" label="Insurance policies" value={num(j.insurance.active_policies)}
          sub={j.insurance.active_policies ? `covering ${j.insurance.covered_people} ${j.insurance.covered_people === 1 ? 'person' : 'people'}` : 'Add a policy'} />
      </section>

      <ScanBand />

      <div className="grid gap-5 @5xl:grid-cols-[1.75fr_1fr]">
        {hasStatement ? <MoneyPanel m={m} /> : <GetStarted />}
        <SetupChecklist d={d} />
      </div>

      {d.attention.length > 0 && (
        <section aria-labelledby="attn">
          <SectionHeader id="attn" title="Needs your attention" />
          <ul className="grid gap-3 @3xl:grid-cols-2 @6xl:grid-cols-3">
            {d.attention.map((a: any) => (
              <li key={a.kind + a.title}>
                <Link to={a.link} className="lift flex h-full items-start gap-3 rounded-[var(--radius-card)] border border-caution/25 bg-caution-soft/90 p-4 shadow-[var(--elev-1)] hover:border-caution/60">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-white/80 text-caution" aria-hidden><AlertCircle className="size-5" /></span>
                  <span><span className="block font-medium">{a.title}</span><span className="text-sm text-ink/80">{a.body}</span></span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="grid gap-[var(--section-gap)] @5xl:grid-cols-[1.75fr_1fr] @5xl:gap-5">
        <section aria-labelledby="journeys">
          <SectionHeader id="journeys" title="Your journeys" description="Tools and answers for each part of your money, worked out from your data." />
          <ul className="grid gap-4 @xl:grid-cols-2 @6xl:grid-cols-4">
            <Journey to="/loans" icon={<Landmark />} tone="indigo" art="indigo" title="Loans" cta="Find a loan"
              summary={j.loans.documents ? `${j.loans.documents} loan document${j.loans.documents > 1 ? 's' : ''} analysed. Compare options by their full cost.` : 'Compare loans by their full cost — interest, fees, GST and clauses.'} />
            <Journey to="/insurance" icon={<ShieldCheck />} tone="green" art="green" title="Insurance" cta="Open insurance"
              summary={j.insurance.active_policies ? `${j.insurance.active_policies} policies covering ${j.insurance.covered_people} ${j.insurance.covered_people === 1 ? 'person' : 'people'}.` : 'Upload a policy to see coverage, exclusions and claim steps.'}>
              {j.insurance.upcoming_renewals.length > 0 && <span className="text-sm text-caution">{j.insurance.upcoming_renewals[0].name} renews {relDays(j.insurance.upcoming_renewals[0].date)}</span>}
            </Journey>
            <Journey to="/cards" icon={<CreditCard />} tone="violet" art="violet" title="Credit cards" cta="Which card to use"
              summary={j.cards.count ? `${j.cards.count} cards${j.cards.next_due ? ` · next bill ${relDays(j.cards.next_due)}` : ''}.` : 'Add your cards to see which one earns most for each purchase.'}>
              {j.cards.reward_balances.length > 0 && <span className="text-sm text-muted">{j.cards.reward_balances.map((r: any) => `${num(r.balance)} ${r.unit}`).join(' · ')}</span>}
            </Journey>
            <Journey to="/emis" icon={<CalendarClock />} tone="amber" art="amber" title="EMIs" cta="Open calendar"
              summary={j.emis.count ? <>{j.emis.count} EMIs · <Money value={j.emis.monthly_total} /> a month.</> : 'Add EMIs, or confirm the ones found in your statement.'} />
          </ul>
        </section>

        <div className="flex flex-col gap-5 @5xl:pt-[3.6rem]">
          <ForecastCard />
          <Panel className="p-5" aria-labelledby="upcoming">
            <div className="mb-2 flex items-center gap-3"><IconTile tone="indigo" size="sm"><CalendarDays /></IconTile><h2 id="upcoming" className="font-semibold">Upcoming in 30 days</h2></div>
            {d.upcoming.length === 0 ? (
              <div className="flex flex-col items-start gap-3 py-2">
                <p className="text-sm text-muted">Nothing due that VITRAM knows of.</p>
                <LinkButton to="/emis" variant="secondary" size="sm" icon={<Plus className="size-4" />}>Add an EMI or bill</LinkButton>
              </div>
            ) : (
              <ul className="-mx-2 flex flex-col">
                {d.upcoming.map((u: any) => {
                  const dt = new Date(u.date + 'T00:00:00')
                  return (
                    <li key={u.kind + u.object_id + u.date}>
                      <Link to={u.link} className="group flex items-center gap-3 rounded-[14px] px-2 py-2 transition-colors hover:bg-ink/[0.04]">
                        <span className="flex w-11 shrink-0 flex-col items-center rounded-[12px] bg-indigo-soft py-1 text-indigo-dark" aria-hidden>
                          <span className="num text-[1.05rem] font-semibold leading-tight">{dt.getDate()}</span>
                          <span className="text-[0.65rem] font-medium leading-tight">{dt.toLocaleDateString('en-IN', { month: 'short' })}</span>
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[0.95rem] font-medium group-hover:text-indigo-dark">{u.title}</span>
                          <span className="flex flex-wrap items-center gap-1.5 text-sm text-muted"><span className="sr-only">{dayMonth(u.date)}, </span>{relDays(u.date)}{!u.confirmed && <Badge tone="caution" className="py-0">Unconfirmed</Badge>}</span>
                        </span>
                        <Money value={u.amount} className="shrink-0 font-semibold" />
                      </Link>
                    </li>
                  )
                })}
              </ul>
            )}
          </Panel>
          <Panel className="p-5" aria-labelledby="add-doc">
            <div className="mb-3 flex items-start gap-3">
              <IconTile tone="indigo" size="sm"><FileText /></IconTile>
              <div><h2 id="add-doc" className="font-semibold">Add a document</h2><p className="text-sm text-muted">PDF{vision?.configured ? ', photo' : ''} or CSV. More documents mean sharper answers.</p></div>
            </div>
            <div className="flex flex-wrap gap-2">
              <LinkButton to="/onboarding/statement" variant="secondary" size="sm">Bank statement</LinkButton>
              <LinkButton to="/insurance/upload" variant="secondary" size="sm">Insurance policy</LinkButton>
              <LinkButton to="/loans/analyze" variant="secondary" size="sm">Loan document</LinkButton>
              <LinkButton to="/documents/receipts/new" variant="secondary" size="sm">Receipt</LinkButton>
            </div>
          </Panel>
        </div>
      </div>

      {hasStatement && m.top_categories?.length > 0 && (
        <section aria-labelledby="spend">
          <SectionHeader id="spend" title="Where the money goes" description={`Average a month over ${m.months_covered} months · ${compactInr(m.avg_monthly_outflow?.value)} in total`}
            action={<span className="flex flex-wrap gap-4">
              <Link to="/insights" className="inline-flex min-h-10 items-center gap-1 text-sm font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">Spending insights<ArrowRight className="size-4" aria-hidden /></Link>
              <Link to="/profile/review" className="inline-flex min-h-10 items-center gap-1 text-sm font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">Review categories<ArrowRight className="size-4" aria-hidden /></Link>
            </span>} />
          <Panel className="p-5 sm:p-6"><CategoryBars rows={m.top_categories} /></Panel>
        </section>
      )}

      <MeetSaathi chatMode={d.assistant.chat_mode} voice={d.assistant.voice_available} />
    </div>
  )
}
