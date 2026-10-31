import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Bell, Calculator, ChevronLeft, ChevronRight, Lightbulb, ListChecks, PieChart, Plus, Trash2, Wallet, X } from 'lucide-react'
import { Tabs } from 'radix-ui'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Button, LinkButton } from '../../components/ui/button'
import { Badge, IconTile, KeyValue, Money, PageHeader, Panel, StatCard, TrustMark } from '../../components/ui/data'
import { ListTileArt } from '../../components/illustrations'
import { Checkbox, Field, Input, Select } from '../../components/ui/field'
import { Callout, EmptyState, errorMessage, ErrorState, PageSkeleton, useToast } from '../../components/ui/feedback'
import { Sheet } from '../../components/ui/overlay'
import { ApiError, del, get, patch, post, put } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { date, dayMonth, inr, ordinal, parseAmountInput, pct, relDays } from '../../lib/format'
import { useSaathiPage } from '../saathi/context'

const EMI_TYPES = [['home_loan', 'Home loan'], ['personal_loan', 'Personal loan'], ['vehicle_loan', 'Vehicle loan'], ['education_loan', 'Education loan'],
  ['card_emi', 'Credit card EMI'], ['consumer_emi', 'Consumer / device EMI'], ['gold_loan', 'Gold loan'], ['loan', 'Loan'], ['other', 'Other']] as const

const SOURCE_LABEL: Record<string, string> = { manual: 'You added', bank_detection: 'Found in bank statement', document: 'From loan document' }

function EmiForm({ initial, onDone }: { initial?: any; onDone: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [f, setF] = useState({
    title: initial?.title ?? '', emi_type: initial?.emi_type ?? 'personal_loan', lender: initial?.lender ?? '', amount: initial?.amount ?? '', due_day: initial?.due_day ?? '',
    remaining_count: initial?.remaining_count ?? '', rate: initial?.rate ?? '', rate_type: initial?.rate_type ?? '', principal: initial?.principal ?? '',
    late_fee: initial?.late_rule?.flat_fee ?? '', penal: initial?.late_rule?.penal_rate_pa ?? '', late_gst: initial?.late_rule?.gst_applicable ?? true,
    pp_allowed: initial?.prepayment_rule?.allowed ?? true, pp_charge: initial?.prepayment_rule?.charge_pct ?? '',
  })
  const [err, setErr] = useState<ApiError | null>(null)
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value })
  const n = (v: any) => (v === '' || v === null || v === undefined ? null : Number(String(v).replace(/[,₹\s]/g, '')))
  const m = useMutation({
    mutationFn: () => {
      const body = {
        title: f.title, emi_type: f.emi_type, lender: f.lender || null, amount: n(f.amount), due_day: n(f.due_day), remaining_count: n(f.remaining_count),
        rate: n(f.rate), rate_type: f.rate_type || null, principal: n(f.principal),
        late_rule: f.late_fee !== '' || f.penal !== '' ? { flat_fee: n(f.late_fee), penal_rate_pa: n(f.penal), gst_applicable: f.late_gst } : null,
        prepayment_rule: f.pp_charge !== '' || !f.pp_allowed ? { allowed: f.pp_allowed, charge_pct: n(f.pp_charge), gst_applicable: true } : null,
      }
      return initial ? patch(`/emis/${initial.id}`, body) : post('/emis', body)
    },
    onSuccess: () => { qc.invalidateQueries(); toast({ title: initial ? 'EMI saved' : 'EMI added', tone: 'positive' }); onDone() },
    onError: (e) => setErr(e instanceof ApiError ? e : null),
  })
  const fe = (k: string) => (err?.field === k ? err.message : null)
  return (
    <form onSubmit={(e: FormEvent) => { e.preventDefault(); if (!f.title.trim()) { setErr(new ApiError(422, 'X', 'Name this EMI.', 'title')); return } m.mutate() }} className="grid gap-4 sm:grid-cols-2" noValidate>
      <Field label="Name" error={fe('title')}><Input value={f.title} onChange={set('title')} placeholder="e.g. Car loan" /></Field>
      <Field label="Type"><Select value={f.emi_type} onChange={set('emi_type')}>{EMI_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
      <Field label="EMI amount" error={fe('amount')}><Input prefix="₹" inputMode="numeric" value={f.amount} onChange={set('amount')} /></Field>
      <Field label="Due day of month" error={fe('due_day')}><Input inputMode="numeric" value={f.due_day} onChange={set('due_day')} placeholder="1–31" /></Field>
      <Field label="Lender" optional><Input value={f.lender} onChange={set('lender')} /></Field>
      <Field label="EMIs remaining" optional error={fe('remaining_count')}><Input inputMode="numeric" value={f.remaining_count} onChange={set('remaining_count')} /></Field>
      <Field label="Interest rate % p.a." optional error={fe('rate')}><Input inputMode="decimal" value={f.rate} onChange={set('rate')} /></Field>
      <Field label="Rate type" optional><Select value={f.rate_type} onChange={set('rate_type')}><option value="">Not sure</option><option value="fixed">Fixed</option><option value="floating">Floating</option></Select></Field>
      <fieldset className="grid gap-4 rounded-[var(--radius-card)] border border-[var(--glass-hairline)] bg-ink/[0.02] p-4 sm:col-span-2 sm:grid-cols-2">
        <legend className="px-1 text-sm font-medium">Late-payment terms (from your loan agreement)</legend>
        <Field label="Late fee per instance" optional><Input prefix="₹" inputMode="numeric" value={f.late_fee} onChange={set('late_fee')} /></Field>
        <Field label="Penal interest % p.a." optional><Input inputMode="decimal" value={f.penal} onChange={set('penal')} /></Field>
        <Checkbox checked={f.late_gst} onChange={(e) => setF({ ...f, late_gst: e.target.checked })} label="GST applies to these charges" className="sm:col-span-2" />
      </fieldset>
      <fieldset className="grid gap-4 rounded-[var(--radius-card)] border border-[var(--glass-hairline)] bg-ink/[0.02] p-4 sm:col-span-2 sm:grid-cols-2">
        <legend className="px-1 text-sm font-medium">Prepayment terms</legend>
        <Checkbox checked={f.pp_allowed} onChange={(e) => setF({ ...f, pp_allowed: e.target.checked })} label="Part-prepayment allowed" />
        <Field label="Prepayment charge %" optional><Input inputMode="decimal" value={f.pp_charge} onChange={set('pp_charge')} /></Field>
      </fieldset>
      {err && !['title', 'amount', 'due_day', 'remaining_count', 'rate'].includes(err.field ?? '') && <p role="alert" className="text-sm text-critical sm:col-span-2">{err.message}</p>}
      <div className="flex gap-2 sm:col-span-2"><Button type="submit" loading={m.isPending}>{initial ? 'Save' : 'Add EMI'}</Button><Button variant="quiet" onClick={onDone}>Cancel</Button></div>
    </form>
  )
}

const KIND_LABEL: Record<string, string> = { emi: 'EMI', card: 'Card bill', policy: 'Policy renewal' }

function Calendar() {
  const now = new Date()
  const [ym, setYm] = useState({ y: now.getFullYear(), m: now.getMonth() + 1 })
  const [view, setView] = useState<'month' | 'week'>('month')
  const [weekAnchor, setWeekAnchor] = useState(now)
  const [sel, setSel] = useState<string | null>(null)
  const dateKey = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  const key = `${ym.y}-${String(ym.m).padStart(2, '0')}`
  const weekStart = new Date(weekAnchor.getFullYear(), weekAnchor.getMonth(), weekAnchor.getDate() - (weekAnchor.getDay() + 6) % 7)
  const q = useQuery({ queryKey: ['emi-cal', view, key, dateKey(weekStart)], queryFn: () => get<any>(view === 'week' ? `/emis/calendar?view=week&day=${dateKey(weekStart)}` : `/emis/calendar?month=${key}`) })
  const first = new Date(ym.y, ym.m - 1, 1)
  const days = new Date(ym.y, ym.m, 0).getDate()
  const lead = (first.getDay() + 6) % 7
  const shownDays = view === 'week'
    ? Array.from({ length: 7 }, (_, i) => new Date(weekStart.getFullYear(), weekStart.getMonth(), weekStart.getDate() + i))
    : Array.from({ length: days }, (_, i) => new Date(ym.y, ym.m - 1, i + 1))
  const byDay: Record<string, any[]> = {}
  for (const i of q.data?.items ?? []) {
    ;(byDay[i.date] ??= []).push(i)
  }
  const shift = (n: number) => {
    setSel(null)
    if (view === 'week') setWeekAnchor((d) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + 7 * n))
    else setYm((s) => { const d = new Date(s.y, s.m - 1 + n, 1); return { y: d.getFullYear(), m: d.getMonth() + 1 } })
  }
  const today = dateKey(now)
  const heading = view === 'week'
    ? `${shownDays[0].toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })} – ${shownDays[6].toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}`
    : first.toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })
  const kindStyle: Record<string, string> = { emi: 'bg-indigo-soft text-indigo-dark', card: 'bg-marigold-soft text-marigold-deep', policy: 'bg-positive-soft text-positive' }
  return (
    <Panel className="p-5">
      <div className="mb-4 flex items-start justify-between gap-2">
        <div>
          <h2 className="text-[1.05rem] font-semibold" aria-live="polite">{heading}</h2>
          <p className="mt-0.5 text-sm text-muted">Total due <Money value={q.data?.total} className="font-semibold text-ink" />{q.data?.unknown_amounts > 0 && ` · ${q.data.unknown_amounts} with unknown amount`}</p>
        </div>
        <div className="flex items-center rounded-full border border-[var(--glass-hairline)] bg-white/80 p-0.5 shadow-[var(--elev-1)]">
          <button type="button" className="inline-flex size-10 items-center justify-center rounded-full text-muted hover:bg-ink/5 hover:text-ink" aria-label={`Previous ${view}`} onClick={() => shift(-1)}><ChevronLeft className="size-4" aria-hidden /></button>
          <button type="button" className="inline-flex size-10 items-center justify-center rounded-full text-muted hover:bg-ink/5 hover:text-ink" aria-label={`Next ${view}`} onClick={() => shift(1)}><ChevronRight className="size-4" aria-hidden /></button>
        </div>
      </div>
      <div className="mb-4 flex gap-2" role="group" aria-label="Calendar view">
        <Button size="sm" variant={view === 'month' ? 'primary' : 'quiet'} aria-pressed={view === 'month'} onClick={() => { setView('month'); setSel(null) }}>Month</Button>
        <Button size="sm" variant={view === 'week' ? 'primary' : 'quiet'} aria-pressed={view === 'week'} onClick={() => { setView('week'); setSel(null) }}>Week</Button>
      </div>
      <div className="hidden grid-cols-7 gap-1.5 text-center text-xs font-medium text-muted sm:grid" aria-hidden>{['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => <div key={d} className="pb-1">{d}</div>)}</div>
      <div className="hidden grid-cols-7 gap-1.5 sm:grid">
        {view === 'month' && Array.from({ length: lead }).map((_, i) => <div key={'x' + i} />)}
        {shownDays.map((shown) => {
          const d = shown.getDate()
          const shownKey = dateKey(shown)
          const items = byDay[shownKey] ?? []
          const weekend = shown.getDay() === 0 || shown.getDay() === 6
          const monthName = shown.toLocaleDateString('en-IN', { month: 'long' })
          return (
            <button type="button" key={shownKey} onClick={() => setSel(sel === shownKey ? null : shownKey)} aria-pressed={sel === shownKey}
              aria-label={`${d} ${monthName}${items.length ? `, ${items.length} due: ${items.map((it) => it.title).join(', ')}` : ', nothing due'}${shownKey === today ? ', today' : ''}`}
              className={clsx('flex min-h-[5.25rem] flex-col items-stretch rounded-[12px] p-1.5 text-left transition-[background-color,box-shadow] duration-[var(--dur)]',
                sel === shownKey ? 'bg-[image:var(--grad-active)] text-white shadow-[0_8px_18px_rgb(52_67_181/0.35)]'
                  : shownKey === today ? 'bg-indigo-soft/70 shadow-[inset_0_0_0_1.5px_var(--color-indigo)] hover:bg-indigo-soft'
                  : items.length ? 'bg-white shadow-[inset_0_0_0_1px_var(--glass-hairline),var(--elev-1)] hover:shadow-[inset_0_0_0_1px_rgb(52_67_181/0.3),var(--elev-2)]'
                  : weekend ? 'bg-white/35 hover:bg-white/70' : 'bg-white/55 hover:bg-white/80')}>
              <span className={clsx('mb-1 flex size-6 items-center justify-center rounded-full text-xs',
                sel === shownKey ? 'font-semibold text-white' : shownKey === today ? 'bg-indigo font-semibold text-white' : items.length ? 'font-semibold text-ink' : 'text-muted')} aria-hidden>{d}</span>
              {items.slice(0, 2).map((it) => (
                <span key={it.kind + it.object_id} aria-hidden className={clsx('mt-0.5 flex items-center gap-1 truncate rounded-[6px] px-1.5 py-0.5 text-[0.7rem] font-medium', sel === shownKey ? 'bg-white/20 text-white' : kindStyle[it.kind])}>
                  <span className="truncate">{it.title}</span>
                </span>
              ))}
              {items.length > 2 && <span aria-hidden className={clsx('mt-0.5 px-1.5 text-[0.7rem]', sel === shownKey ? 'text-white/80' : 'text-muted')}>+{items.length - 2} more</span>}
            </button>
          )
        })}
      </div>
      {sel != null && (
        <div className="mt-4 hidden rounded-[var(--radius-card)] border border-white/80 bg-white/80 p-4 shadow-[var(--elev-1)] sm:block" aria-live="polite">
          <p className="mb-2 text-sm font-semibold">{new Date(`${sel}T12:00:00`).toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' })}</p>
          {(byDay[sel] ?? []).length === 0 ? <p className="text-sm text-muted">Nothing due on this day that VITTRM knows of.</p> : (
            <ul className="flex flex-col divide-y divide-[var(--glass-hairline)]">
              {byDay[sel].map((it: any) => (
                <li key={it.kind + it.object_id}>
                  <Link to={it.link} className="group flex items-center gap-3 py-2">
                    <span className={clsx('size-2.5 shrink-0 rounded-full', { emi: 'bg-indigo', card: 'bg-marigold', policy: 'bg-positive' }[it.kind as 'emi' | 'card' | 'policy'])} aria-hidden />
                    <span className="min-w-0 flex-1"><span className="block truncate font-medium group-hover:text-indigo-dark">{it.title}</span>
                      <span className="text-xs text-muted">{KIND_LABEL[it.kind] ?? it.kind}{!it.confirmed && ' · unconfirmed'}</span></span>
                    <Money value={it.amount} className="font-semibold" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <ul className="divide-y divide-[var(--glass-hairline)] sm:hidden">
        {(q.data?.items ?? []).length === 0 && <li className="py-3 text-sm text-muted">Nothing due this {view}.</li>}
        {(q.data?.items ?? []).map((it: any) => (
          <li key={it.kind + it.object_id + it.date}><Link to={it.link} className="flex items-center justify-between gap-3 py-3">
            <span><span className="block font-medium">{it.title}</span><span className="text-sm text-muted">{dayMonth(it.date)}{!it.confirmed && ' · unconfirmed'}</span></span>
            <Money value={it.amount} className="font-medium" /></Link></li>
        ))}
      </ul>
      <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted">
        <span className="flex items-center gap-1"><span className="size-3 rounded bg-indigo-soft ring-1 ring-inset ring-indigo/40" />EMI</span>
        <span className="flex items-center gap-1"><span className="size-3 rounded bg-marigold-soft ring-1 ring-inset ring-marigold-deep/40" />Card bill</span>
        <span className="flex items-center gap-1"><span className="size-3 rounded bg-positive-soft ring-1 ring-inset ring-positive/40" />Policy renewal</span>
      </div>
    </Panel>
  )
}

function ExploreNewEmi() {
  const [opts, setOpts] = useState([{ label: 'Option A', amount: '', rate: '', tenure: '', fee: '' }, { label: 'Option B', amount: '', rate: '', tenure: '', fee: '' }])
  const [err, setErr] = useState<string | null>(null)
  const m = useMutation({ mutationFn: (b: any) => post<any>('/emis/explore', b), onError: (e) => setErr(errorMessage(e)) })
  const upd = (i: number, k: string, v: string) => setOpts((s) => s.map((o, j) => (j === i ? { ...o, [k]: v } : o)))
  function run(e: FormEvent) {
    e.preventDefault()
    const options = opts.filter((o) => o.amount).map((o) => ({ label: o.label, amount: parseAmountInput(o.amount), rate: Number(o.rate || 0), tenure_months: Number(o.tenure), processing_fee: o.fee === '' ? null : parseAmountInput(o.fee) }))
    if (!options.length || options.some((o) => !o.amount || !o.tenure_months)) { setErr('Enter amount and tenure for each option.'); return }
    setErr(null)
    m.mutate({ options })
  }
  return (
    <Panel className="p-5 sm:p-6">
      <div className="mb-5 flex items-start gap-3">
        <IconTile tone="indigo"><Calculator /></IconTile>
        <div>
          <h2 className="text-[1.1rem] font-semibold">Thinking about a new EMI?</h2>
          <p className="text-sm text-muted">Compare EMI offers side by side — including "no-cost" EMIs — and see how each changes your monthly commitments.</p>
        </div>
      </div>
      <div className="grid gap-5 @6xl:grid-cols-[1fr_15rem]">
      <form onSubmit={run} className="flex flex-col gap-4" noValidate>
        {opts.map((o, i) => (
          <div key={i} className="grid gap-3 sm:grid-cols-5">
            <Field label="Label"><Input value={o.label} onChange={(e) => upd(i, 'label', e.target.value)} /></Field>
            <Field label="Amount"><Input prefix="₹" inputMode="numeric" value={o.amount} onChange={(e) => upd(i, 'amount', e.target.value)} /></Field>
            <Field label="Rate % p.a."><Input inputMode="decimal" value={o.rate} onChange={(e) => upd(i, 'rate', e.target.value)} placeholder="0 for no-cost" /></Field>
            <Field label="Months"><Input inputMode="numeric" value={o.tenure} onChange={(e) => upd(i, 'tenure', e.target.value)} /></Field>
            <Field label="Processing fee" optional><Input prefix="₹" inputMode="numeric" value={o.fee} onChange={(e) => upd(i, 'fee', e.target.value)} /></Field>
          </div>
        ))}
        {err && <p role="alert" className="text-sm text-critical">{err}</p>}
        <div className="flex gap-2">
          <Button type="submit" loading={m.isPending}>Compare</Button>
          {opts.length < 3 && <Button variant="quiet" onClick={() => setOpts([...opts, { label: 'Option C', amount: '', rate: '', tenure: '', fee: '' }])}>Add option</Button>}
        </div>
      </form>
      <aside className="wash-amber h-fit rounded-[var(--radius-card)] p-4 text-sm">
        <p className="mb-1 flex items-center gap-2 font-semibold"><Lightbulb className="size-4 text-marigold-deep" aria-hidden />Tip</p>
        <p className="text-ink/80">A "no-cost" EMI can still carry a processing fee and GST. Enter the fee to see the true total, and compare tenures to see what fits your budget.</p>
      </aside>
      </div>
      {m.data && (
        <div className="mt-5 overflow-x-auto">
          <table className="w-full min-w-[520px] text-[0.95rem]">
            <thead><tr className="text-sm text-muted"><th className="py-2 text-left font-normal"></th>{m.data.options.map((o: any) => <th key={o.label} className="py-2 text-right font-semibold text-ink">{o.label}</th>)}</tr></thead>
            <tbody className="num divide-y divide-line">
              <tr><td className="py-2">EMI</td>{m.data.options.map((o: any) => <td key={o.label} className="py-2 text-right"><Money value={o.monthly_emi} /></td>)}</tr>
              <tr><td className="py-2">Interest</td>{m.data.options.map((o: any) => <td key={o.label} className="py-2 text-right"><Money value={o.total_interest} /></td>)}</tr>
              <tr><td className="py-2">Fee with GST</td>{m.data.options.map((o: any) => <td key={o.label} className="py-2 text-right">{o.fee_known ? <Money value={o.processing_fee_with_gst} /> : <span className="text-caution">Not entered</span>}</td>)}</tr>
              <tr className="font-semibold"><td className="py-2">Total cost</td>{m.data.options.map((o: any) => <td key={o.label} className="py-2 text-right"><Money value={o.total_cost} /></td>)}</tr>
              <tr><td className="py-2">Share of income on EMIs</td>{m.data.options.map((o: any) => <td key={o.label} className="py-2 text-right">{o.affordability.computable ? `${pct(o.affordability.baseline.obligation_share_pct, 1)} → ${pct(o.affordability.scenario.obligation_share_pct, 1)}` : 'Confirm income'}</td>)}</tr>
            </tbody>
          </table>
          {m.data.notes.map((n: string) => <p key={n} className="mt-2 text-sm text-muted">{n}</p>)}
        </div>
      )}
    </Panel>
  )
}

export function EmisHome() {
  useSaathiPage('emi')
  const qc = useQueryClient()
  const toast = useToast()
  const [adding, setAdding] = useState(false)
  const q = useQuery({ queryKey: ['emis'], queryFn: () => get<any>('/emis') })
  const confirm = useMutation({ mutationFn: (id: string) => post(`/emis/${id}/confirm`), onSuccess: () => { qc.invalidateQueries(); toast({ title: 'EMI confirmed and added to reminders', tone: 'positive' }) } })
  const reject = useMutation({ mutationFn: (id: string) => del(`/emis/${id}`), onSuccess: () => { qc.invalidateQueries(); toast({ title: 'Removed — it won\'t be detected again', tone: 'positive' }) } })
  if (q.isLoading) return <PageSkeleton />
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  const pending = d.emis.filter((e: any) => !e.confirmed)
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'EMIs' }]} title="EMIs" description="Every instalment, when it's due, and what happens if things change."
        actions={<><LinkButton to="/settings/reminders" variant="secondary" icon={<Bell className="size-4" />}>Reminders</LinkButton><Button icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>Add an EMI</Button></>} />
      <div className="mb-7 grid gap-3 sm:grid-cols-3">
        <StatCard icon={<Wallet className="size-5" />} label="Monthly EMIs" value={<Money value={d.monthly_total} />} hint={!d.emis.length ? 'No EMIs added yet' : pending.length ? `incl. ${inr(d.monthly_total - d.monthly_total_confirmed)} not yet confirmed` : 'all confirmed'} />
        <StatCard icon={<PieChart className="size-5" />} label="Share of monthly income" value={d.obligation_share_pct != null ? pct(d.obligation_share_pct, 1) : 'Income not known'} mark={d.income.state && <TrustMark state={d.income.state} />} />
        <StatCard icon={<ListChecks className="size-5" />} label="Number of EMIs" value={d.emis.length} />
      </div>
      {pending.length > 0 && (
        <Panel className="mb-7 p-5 ring-1 ring-caution/35">
          <h2 className="font-semibold">Confirm {pending.length === 1 ? 'this EMI' : 'these EMIs'}</h2>
          <ul className="mt-2 divide-y divide-line">
            {pending.map((e: any) => (
              <li key={e.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center">
                <div className="min-w-0 flex-1">
                  <Link to={`/emis/${e.id}`} className="font-medium hover:text-indigo">{e.title}</Link>
                  <p className="text-sm text-muted">{SOURCE_LABEL[e.source_type]}{e.source_ref && ` · ${e.source_ref}`} · due on the {ordinal(e.due_day)}</p>
                </div>
                <Money value={e.amount} className="font-semibold" />
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => confirm.mutate(e.id)}>Confirm</Button>
                  <Button size="sm" variant="quiet" onClick={() => reject.mutate(e.id)}>Not an EMI</Button>
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      <div className="grid items-start gap-6 @4xl:grid-cols-[1fr_1.3fr]">
        <Panel className="p-5">
          <h2 className="mb-2 font-semibold">All EMIs</h2>
          {d.emis.length === 0 ? (
            <div className="flex flex-col items-center gap-2 px-4 py-6 text-center">
              <ListTileArt className="w-44" />
              <p className="text-[1.05rem] font-semibold">No EMIs yet</p>
              <p className="max-w-sm text-sm text-muted">Add one, or upload a bank statement so VITTRM can find them.</p>
              <Button className="mt-2" size="lg" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>Add an EMI</Button>
            </div>
          ) : (
            <ul className="divide-y divide-line">
              {d.emis.map((e: any) => (
                <li key={e.id}>
                  <Link to={`/emis/${e.id}`} className="flex items-center justify-between gap-3 py-3 hover:text-indigo">
                    <span className="min-w-0"><span className="flex flex-wrap items-center gap-2 font-medium">{e.title}{!e.confirmed && <TrustMark state="extracted" />}</span>
                      <span className="text-sm text-muted">Next {dayMonth(e.next_due)} ({relDays(e.next_due)}){e.remaining_count ? ` · ${e.remaining_count} left` : ''}</span></span>
                    <Money value={e.amount} className="shrink-0 font-semibold" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Calendar />
      </div>
      <div className="mt-6"><ExploreNewEmi /></div>
      <Sheet open={adding} onOpenChange={setAdding} wide title="Add an EMI" description="The instalment amount and due day are enough to start. Add loan terms for precise what-ifs."><EmiForm onDone={() => setAdding(false)} /></Sheet>
    </>
  )
}

function EmiScenarios({ emi }: { emi: any }) {
  const [tab, setTab] = useState('missed_payment')
  const [v, setV] = useState({ days: '15', prepay: '50000', mode: 'reduce_tenure', rate: emi.rate ? String(emi.rate + 1) : '', hold: 'emi' })
  const [err, setErr] = useState<string | null>(null)
  const m = useMutation({ mutationFn: (b: any) => post<any>(`/emis/${emi.id}/what-if`, b), onError: (e) => setErr(errorMessage(e)) })
  const set = (k: string) => (e: any) => setV({ ...v, [k]: e.target.value })
  function run(e: FormEvent) {
    e.preventDefault()
    setErr(null)
    const b: any = { kind: tab }
    if (tab === 'late_payment') b.days_late = Number(v.days)
    if (tab === 'prepayment') Object.assign(b, { prepay_amount: parseAmountInput(v.prepay), mode: v.mode })
    if (tab === 'rate_change') Object.assign(b, { new_rate_pct: Number(v.rate), hold: v.hold })
    m.mutate(b)
  }
  const r = m.data?.result
  const tabs = [['missed_payment', 'Miss next EMI'], ['late_payment', 'Pay late'], ['prepayment', 'Prepay'], ...(emi.rate_type !== 'fixed' ? [['rate_change', 'Rate change']] : [])]
  return (
    <Tabs.Root value={tab} onValueChange={(t) => { setTab(t); m.reset() }}>
      <Tabs.List className="mb-4 flex w-fit max-w-full flex-wrap gap-1 rounded-[16px] bg-ink/[0.05] p-1" aria-label="Scenarios">
        {tabs.map(([k, l]) => <Tabs.Trigger key={k} value={k} className="min-h-10 rounded-[12px] px-3.5 text-sm font-medium text-muted transition-[background-color,color,box-shadow] duration-[var(--dur)] hover:text-ink data-[state=active]:bg-white data-[state=active]:text-ink data-[state=active]:shadow-[var(--elev-1)]">{l}</Tabs.Trigger>)}
      </Tabs.List>
      <form onSubmit={run} className="flex flex-col gap-4">
        <Tabs.Content value="missed_payment"><p className="text-sm text-muted">Uses the late-payment terms saved for this EMI.</p></Tabs.Content>
        <Tabs.Content value="late_payment" className="grid gap-4 sm:grid-cols-2"><Field label="Days late"><Input inputMode="numeric" value={v.days} onChange={set('days')} /></Field></Tabs.Content>
        <Tabs.Content value="prepayment" className="grid gap-4 sm:grid-cols-2">
          <Field label="Prepay amount"><Input prefix="₹" inputMode="numeric" value={v.prepay} onChange={set('prepay')} /></Field>
          <Field label="Use it to"><Select value={v.mode} onChange={set('mode')}><option value="reduce_tenure">Finish sooner</option><option value="reduce_emi">Lower the EMI</option></Select></Field>
        </Tabs.Content>
        <Tabs.Content value="rate_change" className="grid gap-4 sm:grid-cols-2">
          <Field label="New rate % p.a."><Input inputMode="decimal" value={v.rate} onChange={set('rate')} /></Field>
          <Field label="Keep constant"><Select value={v.hold} onChange={set('hold')}><option value="emi">EMI</option><option value="tenure">Tenure</option></Select></Field>
        </Tabs.Content>
        {err && <p role="alert" className="text-sm text-critical">{err}</p>}
        <Button type="submit" className="w-fit" loading={m.isPending}>Calculate</Button>
      </form>
      {r && (
        <div className="mt-5" aria-live="polite">
          {!r.computable ? (
            <Callout tone="caution" title="Can't calculate this precisely">
              <ul className="list-disc pl-5">{[...r.missing, ...r.notes].map((x: string) => <li key={x}>{x}</li>)}</ul>
              <p className="mt-2">Add the terms from your loan agreement using Edit, and VITTRM will calculate it. It won't guess a penalty.</p>
            </Callout>
          ) : (
            <div className="flex flex-col gap-2 text-[0.95rem]">
              {r.kind.includes('payment') ? (
                <KeyValue items={[
                  { k: 'Late fee', v: <Money value={r.scenario.late_fee} /> }, { k: 'Penal interest', v: <Money value={r.scenario.penal_interest} /> },
                  { k: 'GST', v: <Money value={r.scenario.gst} /> }, { k: <b className="text-ink">Extra cost</b>, v: <Money value={r.scenario.extra_cost} className="font-semibold" /> },
                ]} />
              ) : r.kind === 'prepayment' ? (
                <KeyValue items={[
                  { k: 'Estimated outstanding', v: <Money value={r.scenario.outstanding_before_prepayment} /> },
                  { k: 'EMI', v: <span><Money value={r.baseline.monthly_emi} /> → <Money value={r.scenario.monthly_emi} /></span> },
                  { k: 'EMIs left', v: `${r.baseline.tenure_months} → ${r.scenario.total_tenure_months}` },
                  { k: 'Interest saved', v: <Money value={r.scenario.interest_saved} className="text-positive" /> },
                  { k: 'Prepayment charge', v: r.scenario.prepayment_charge != null ? <Money value={r.scenario.prepayment_charge} /> : <span className="text-caution">Not known</span> },
                ]} />
              ) : (
                <KeyValue items={[
                  { k: 'EMI', v: <span><Money value={r.baseline.monthly_emi} /> → <Money value={r.scenario.monthly_emi} /></span> },
                  { k: 'EMIs left', v: `${r.baseline.tenure_months} → ${r.scenario.tenure_months}` },
                  { k: 'Total interest', v: <span><Money value={r.baseline.total_interest} /> → <Money value={r.scenario.total_interest} /></span> },
                ]} />
              )}
              {r.notes.map((n: string) => <p key={n} className="text-sm text-muted">{n}</p>)}
              <details className="text-sm text-muted"><summary className="font-medium text-ink">Assumptions</summary><ul className="mt-1 list-disc pl-5">{r.assumptions.map((a: string) => <li key={a}>{a}</li>)}</ul></details>
            </div>
          )}
        </div>
      )}
    </Tabs.Root>
  )
}

export function EmiDetail() {
  const { id } = useParams()
  useSaathiPage('emi', id)
  const qc = useQueryClient()
  const toast = useToast()
  const navigate = useNavigate()
  const [editing, setEditing] = useState(false)
  const q = useQuery({ queryKey: ['emis'], queryFn: () => get<any>('/emis') })
  const remind = useMutation({ mutationFn: () => post<any>('/reminders/send-now', { object_type: 'emi', object_id: id }), onSuccess: (r) => { qc.invalidateQueries({ queryKey: ['notifications'] }); toast({ title: r.explanation, tone: r.status === 'failed' ? 'critical' : 'info' }) } })
  const confirm = useMutation({ mutationFn: () => post(`/emis/${id}/confirm`), onSuccess: () => qc.invalidateQueries() })
  const remove = useMutation({ mutationFn: () => del(`/emis/${id}`), onSuccess: () => { qc.invalidateQueries(); navigate('/emis') } })
  if (q.isLoading) return <PageSkeleton />
  if (q.isError) return <ErrorState error={q.error} />
  const e = q.data.emis.find((x: any) => x.id === id)
  if (!e) return <EmptyState title="EMI not found" action={<LinkButton to="/emis">Back to EMIs</LinkButton>} />
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'EMIs', to: '/emis' }]} title={e.title}
        description={<span className="flex flex-wrap items-center gap-2">{SOURCE_LABEL[e.source_type]}{e.source_ref && ` · ${e.source_ref}`}<TrustMark state={e.confirmed ? 'confirmed' : 'extracted'} /></span>}
        actions={<>
          {!e.confirmed && <Button onClick={() => confirm.mutate()} loading={confirm.isPending}>Confirm</Button>}
          <Button variant="secondary" onClick={() => setEditing(true)}>Edit terms</Button>
          <Button variant="quiet" icon={<Trash2 className="size-4" />} onClick={() => remove.mutate()}>Remove</Button>
        </>} />
      <div className="grid items-start gap-6 @4xl:grid-cols-[1fr_1.3fr]">
        <Panel className="p-5">
          <KeyValue items={[
            { k: 'EMI', v: <Money value={e.amount} className="font-semibold" /> },
            { k: 'Next due', v: `${date(e.next_due)} (${relDays(e.next_due)})` },
            { k: 'EMIs remaining', v: e.remaining_count ?? 'Not added' },
            { k: 'Interest rate', v: e.rate != null ? `${pct(e.rate)} ${e.rate_type ?? ''}` : 'Not added' },
            { k: 'Lender', v: e.lender ?? 'Not added' },
            { k: 'Estimated outstanding', v: e.estimated_outstanding != null ? <Money value={e.estimated_outstanding} /> : 'Needs rate and EMIs left', extra: e.estimated_outstanding != null && <TrustMark state="estimate" /> },
            { k: 'Late-payment terms', v: e.late_rule ? [e.late_rule.flat_fee != null && inr(e.late_rule.flat_fee), e.late_rule.penal_rate_pa != null && `${e.late_rule.penal_rate_pa}% p.a.`, e.late_rule.gst_applicable && '+ GST'].filter(Boolean).join(', ') : <span className="text-caution">Not added</span> },
          ]} />
          {e.missing_terms.length > 0 && <Callout tone="info" className="mt-4">Add {e.missing_terms.join(', ').toLowerCase()} from your loan agreement for precise scenarios.</Callout>}
          {e.source_document_id && <Link to={`/loans/documents/${e.source_document_id}`} className="mt-3 inline-block text-sm font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">Open the loan document</Link>}
          <div className="mt-4 flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" icon={<Bell className="size-4" />} loading={remind.isPending} onClick={() => remind.mutate()}>Send a reminder now</Button>
            <LinkButton to={`/loans/need?purpose=debt_consolidation&amount=${Math.round(e.estimated_outstanding ?? 0) || ''}`} variant="quiet" size="sm">Explore refinancing</LinkButton>
          </div>
        </Panel>
        <Panel className="p-5">
          <h2 className="mb-1 font-semibold">What if…</h2>
          <p className="mb-4 text-sm text-muted">Only uses this EMI's stated terms. Missing terms are asked for, never assumed.</p>
          <EmiScenarios emi={e} />
        </Panel>
      </div>
      <Sheet open={editing} onOpenChange={setEditing} wide title="Edit EMI"><EmiForm initial={e} onDone={() => setEditing(false)} /></Sheet>
    </>
  )
}

export function ReminderSettings() {
  useSaathiPage('emi')
  const { user, refresh } = useAuth()
  const qc = useQueryClient()
  const toast = useToast()
  const q = useQuery({ queryKey: ['reminders'], queryFn: () => get<any>('/reminders') })
  const [local, setLocal] = useState<any>(null)
  const [phone, setPhone] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const p = local ?? q.data?.preferences
  const save = useMutation({
    mutationFn: (b: any) => put('/reminders/preferences', b),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['reminders'] }); setLocal(null); toast({ title: 'Reminder settings saved', tone: 'positive' }) },
    onError: (e) => setErr(errorMessage(e)),
  })
  if (q.isLoading || !p) return <PageSkeleton />
  async function enableWhatsApp() {
    setErr(null)
    try {
      if (!user?.phone_masked) {
        if (!phone) { setErr('Enter your mobile number.'); return }
        await patch('/onboarding/about', { phone })
      }
      await post('/consents', { purpose: 'whatsapp_reminders' })
      await refresh()
      await qc.invalidateQueries({ queryKey: ['reminders'] })
      setLocal({ ...p, whatsapp_enabled: true, whatsapp_consent: true })
    } catch (e) { setErr(errorMessage(e)) }
  }
  const toggleDay = (d: number) => setLocal({ ...p, days_before: p.days_before.includes(d) ? p.days_before.filter((x: number) => x !== d) : [...p.days_before, d].sort() })
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'EMIs', to: '/emis' }]} title="Reminders" description="When and where VITTRM reminds you about EMIs, card bills and policy renewals. Reminders always appear in VITTRM; WhatsApp is optional." />
      <div className="grid max-w-3xl gap-6">
        <Panel className="flex flex-col gap-5 p-5">
          <fieldset>
            <legend className="mb-2 text-sm font-medium">Remind me before the due date</legend>
            <div className="flex flex-wrap gap-2">{[1, 2, 3, 5, 7].map((d) => (
              <label key={d} className={clsx('flex min-h-11 items-center gap-2 rounded-[var(--radius-control)] border px-4', p.days_before.includes(d) ? 'border-indigo bg-indigo-soft font-medium' : 'border-line-strong')}>
                <input type="checkbox" className="sr-only" checked={p.days_before.includes(d)} onChange={() => toggleDay(d)} />{d} day{d > 1 ? 's' : ''}
              </label>
            ))}</div>
          </fieldset>
          <Checkbox checked={p.on_due_date} onChange={(e) => setLocal({ ...p, on_due_date: e.target.checked })} label="Also on the due date" />
          <Field label="Time of day (IST)"><Select value={p.send_hour} onChange={(e) => setLocal({ ...p, send_hour: Number(e.target.value) })} className="w-40">{Array.from({ length: 16 }, (_, i) => i + 6).map((h) => <option key={h} value={h}>{h}:00</option>)}</Select></Field>
          <p className="text-sm text-muted">Policy renewals are reminded {p.policy_lead_days.join(' and ')} days before.</p>
        </Panel>
        <ReminderItems data={q.data} />
        <Panel className="flex flex-col gap-4 p-5">
          <h2 className="font-semibold">WhatsApp</h2>
          {!p.whatsapp_configured && <Callout tone="caution" title="WhatsApp isn't connected in this environment">You can turn it on, but messages won't be sent until a WhatsApp provider is connected. You'll still get every reminder in VITTRM.</Callout>}
          {p.whatsapp_enabled && p.whatsapp_blocked_reason && <Callout tone="caution" title="WhatsApp is on, but not active yet">{p.whatsapp_blocked_reason}{!p.phone_verified && p.whatsapp_consent && <> Finish the SMS check in <Link to="/profile" className="text-indigo underline">My profile</Link>.</>} Reminders still appear in VITTRM.</Callout>}
          {p.whatsapp_consent ? (
            <Checkbox checked={p.whatsapp_enabled} onChange={(e) => setLocal({ ...p, whatsapp_enabled: e.target.checked })}
              label={`Send reminders to ${user?.phone_masked ?? 'my number'} on WhatsApp`} description="Messages show the item, due date and amount only — no account numbers. Reply STOP any time." />
          ) : (
            <div className="flex flex-col gap-3">
              <p className="text-[0.95rem] text-muted">Get reminders and emergency insurance help on WhatsApp. VITTRM only messages you after you agree.</p>
              {!user?.phone_masked && <Field label="Mobile number"><Input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} className="w-56" /></Field>}
              <Button variant="secondary" className="w-fit" onClick={enableWhatsApp}>I agree to WhatsApp messages</Button>
            </div>
          )}
        </Panel>
        {err && <p role="alert" className="text-sm text-critical">{err}</p>}
        <Button className="w-fit" loading={save.isPending} onClick={() => save.mutate({ days_before: p.days_before, on_due_date: p.on_due_date, send_hour: p.send_hour, whatsapp_enabled: p.whatsapp_enabled, include: p.include })}>Save settings</Button>
        <Panel className="p-5">
          <h2 className="mb-2 font-semibold">Upcoming reminders</h2>
          {q.data.upcoming.length === 0 ? <p className="text-sm text-muted">None scheduled. Confirmed EMIs, card due dates and policy renewals get reminders automatically.</p> : (
            <ul className="divide-y divide-line text-[0.95rem]">{q.data.upcoming.slice(0, 10).map((r: any) => (
              <li key={r.id} className="flex justify-between gap-3 py-2"><span>{KIND_ICON[r.object_type] ?? r.object_type} due {date(r.due_date)}</span><span className="text-muted">{new Date(r.schedule_at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit', timeZone: 'Asia/Kolkata' })} IST · {r.channel === 'whatsapp' ? 'WhatsApp' : 'In VITTRM'}</span></li>
            ))}</ul>
          )}
          {q.data.history.length > 0 && <>
            <h3 className="mb-1 mt-4 text-sm font-medium">Sent</h3>
            <ul className="divide-y divide-line text-sm">{q.data.history.slice(0, 10).map((r: any) => (
              <li key={r.id} className="flex flex-wrap justify-between gap-2 py-2"><span>{KIND_ICON[r.object_type] ?? r.object_type} due {date(r.due_date)}</span>
                <Badge tone={r.status === 'failed' ? 'critical' : r.status === 'not_configured' ? 'caution' : 'positive'}>{r.status_text}</Badge></li>
            ))}</ul>
          </>}
        </Panel>
      </div>
    </>
  )
}


const KIND_ICON: Record<string, string> = { emi: 'EMI', card: 'Card bill', policy: 'Policy renewal' }

/** Per-item control: switch reminders off for one EMI, card or policy, or cancel one upcoming reminder. */
function ReminderItems({ data }: { data: any }) {
  const qc = useQueryClient()
  const toast = useToast()
  const mute = useMutation({
    mutationFn: ({ kind, id, muted }: { kind: string; id: string; muted: boolean }) => put(`/reminders/items/${kind}/${id}`, { muted }),
    onSuccess: (_d, v) => { qc.invalidateQueries({ queryKey: ['reminders'] }); toast({ title: v.muted ? 'Reminders off for this item' : 'Reminders back on', tone: 'positive' }) },
    onError: (e) => toast({ title: errorMessage(e), tone: 'critical' }),
  })
  const cancel = useMutation({ mutationFn: (id: string) => del(`/reminders/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ['reminders'] }) })
  const items: any[] = data?.items ?? []
  const upcoming: any[] = data?.upcoming ?? []
  return (
    <Panel className="flex flex-col gap-4 p-5" aria-labelledby="ri-h">
      <div><h2 id="ri-h" className="font-semibold">Reminders for each item</h2><p className="text-sm text-muted">Due dates come from EMIs you confirmed, card due dates you entered and policy dates you checked.</p></div>
      {items.length === 0 ? <p className="text-sm text-muted">Nothing due in the next 60 days that VITTRM knows of.</p> : (
        <ul className="flex flex-col divide-y divide-[var(--glass-hairline)]">
          {items.map((it) => {
            const next = upcoming.filter((r) => r.object_type === it.kind && r.object_id === it.object_id)
            return (
              <li key={it.key} className="flex flex-col gap-2 py-3">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="min-w-0 flex-1"><span className="block font-medium">{it.title}</span>
                    <span className="text-sm text-muted">{KIND_ICON[it.kind]} · next {dayMonth(it.next_date)}{!it.confirmed && ' · not confirmed yet'}{!it.included && ' · type switched off above'}</span></span>
                  <label className="flex min-h-10 items-center gap-2 text-sm">
                    <input type="checkbox" role="switch" checked={!it.muted} onChange={(e) => mute.mutate({ kind: it.kind, id: it.object_id, muted: !e.target.checked })} className="size-4 accent-[var(--color-indigo)]" />
                    Remind me
                  </label>
                </div>
                {!it.muted && next.length > 0 && (
                  <ul className="flex flex-wrap gap-1.5">
                    {next.map((r) => (
                      <li key={r.id} className="inline-flex items-center gap-1 rounded-full bg-ink/[0.05] py-0.5 pl-3 pr-1 text-xs">
                        {new Date(r.schedule_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', timeZone: 'Asia/Kolkata' })} · {r.channel === 'whatsapp' ? 'WhatsApp' : 'In VITTRM'}
                        <button type="button" onClick={() => cancel.mutate(r.id)} aria-label={`Cancel the reminder on ${new Date(r.schedule_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'long' })}`}
                          className="inline-flex size-6 items-center justify-center rounded-full text-muted hover:bg-ink/10 hover:text-critical"><X className="size-3.5" aria-hidden /></button>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </Panel>
  )
}
