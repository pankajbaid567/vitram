import { ExplainSheet } from '../insights/Insights'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Check, ChevronRight, HelpCircle, Pencil, X } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../../components/ui/button'
import { Money, PageHeader, Panel, Stat, TrustMark } from '../../components/ui/data'
import { Field, Input, Select } from '../../components/ui/field'
import { Callout, EmptyState, errorMessage, ErrorState, PageSkeleton, useToast } from '../../components/ui/feedback'
import { Sheet } from '../../components/ui/overlay'
import { get, patch, post } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { date, dayMonth, inr, ordinal, parseAmountInput } from '../../lib/format'
import { useSaathiPage } from '../saathi/context'

export function CategoryBars({ rows, onPick }: { rows: any[]; onPick?: (cat: string) => void }) {
  const max = Math.max(...rows.map((r) => r.monthly_avg), 1)
  return (
    <ul className="flex flex-col gap-2.5">
      {rows.map((r) => (
        <li key={r.category}>
          <button type="button" disabled={!onPick} onClick={() => onPick?.(r.category)}
            className="group grid w-full grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 text-left disabled:cursor-default sm:grid-cols-[minmax(7rem,11rem)_1fr_auto]">
            <span className="truncate text-[0.95rem] group-enabled:group-hover:text-indigo">{r.label}</span>
            <span className="col-span-2 row-start-2 h-2.5 rounded-full bg-ink/[0.06] sm:col-span-1 sm:col-start-2 sm:row-start-1" aria-hidden>
              <span className="block h-full rounded-full bg-[image:var(--grad-indigo)]" style={{ width: `${Math.max((r.monthly_avg / max) * 100, 2)}%` }} />
            </span>
            <span className="num text-right text-[0.95rem] sm:w-24"><Money value={r.monthly_avg} /><span className="sr-only"> a month, {r.share_pct}% of spending</span></span>
          </button>
        </li>
      ))}
    </ul>
  )
}

export function TransactionsSheet({ category, onClose, options }: { category: string | null; onClose: () => void; options: { key: string; label: string }[] }) {
  const qc = useQueryClient()
  const toast = useToast()
  const q = useQuery({ queryKey: ['txns', category], queryFn: () => get<any>(`/transactions?category=${category}&limit=200`), enabled: !!category })
  const fix = useMutation({
    mutationFn: ({ id, cat }: { id: string; cat: string }) => patch(`/transactions/${id}`, { category: cat }),
    onSuccess: () => { qc.invalidateQueries(); toast({ title: 'Category updated', tone: 'positive' }) },
    onError: (e) => toast({ title: errorMessage(e), tone: 'critical' }),
  })
  const label = options.find((o) => o.key === category)?.label
  const [explain, setExplain] = useState<string | null>(null)
  return (
    <>
    <Sheet open={!!category} onOpenChange={(o) => !o && onClose()} title={label ?? 'Transactions'} description="Change a category if VITTRM got it wrong. Your correction is kept." wide>
      {q.isLoading && <p className="text-sm text-muted">Loading…</p>}
      {q.data && (
        <ul className="divide-y divide-line">
          {q.data.items.map((t: any) => (
            <li key={t.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center">
              <div className="min-w-0 flex-1">
                <p className="truncate text-[0.95rem] font-medium">{t.merchant ?? t.description}</p>
                <p className="text-xs text-muted">{date(t.date)} · {t.source.document_name} · {t.source.ref} {t.category_source === 'user' && '· you set this'}</p>
              </div>
              <Money value={t.direction === 'debit' ? -t.amount : t.amount} className="w-28 text-right font-medium" />
              <label className="sr-only" htmlFor={`cat-${t.id}`}>Category</label>
              <Select id={`cat-${t.id}`} className="sm:w-44" value={t.category} onChange={(e) => fix.mutate({ id: t.id, cat: e.target.value })}>
                {options.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
              </Select>
              <button type="button" onClick={() => setExplain(t.id)} aria-label={`Explain ${t.merchant ?? 'this transaction'} on ${date(t.date)}`}
                className="inline-flex min-h-10 items-center gap-1 self-start rounded-full px-3 text-sm font-medium text-indigo hover:bg-indigo-soft sm:self-center"><HelpCircle className="size-4" aria-hidden />Explain</button>
            </li>
          ))}
        </ul>
      )}
    </Sheet>
    <ExplainSheet id={explain} onClose={() => setExplain(null)} />
    </>
  )
}

function IncomeBlock({ data }: { data: any }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const est = data.income.monthly_estimate
  const act = useMutation({
    mutationFn: ({ id, action, kind }: any) => post(`/profile/recurring/${id}`, { action, kind }),
    onSuccess: () => { qc.invalidateQueries(); toast({ title: 'Saved', tone: 'positive' }) },
  })
  const override = useMutation({
    mutationFn: (v: number) => patch('/profile/overrides', { path: 'income/monthly_estimate', value: v }),
    onSuccess: () => { qc.invalidateQueries(); setEditing(false); toast({ title: 'Income updated', tone: 'positive' }) },
    onError: (e) => setErr(errorMessage(e)),
  })
  return (
    <Panel className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="font-semibold">Monthly income</h2>
          <p className="mt-0.5 text-sm text-muted">{est.source}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="num text-2xl font-semibold">{est.value != null ? inr(est.value) : '—'}</span>
          <TrustMark state={est.state} />
        </div>
      </div>
      {est.state === 'conflicted' && (
        <Callout tone="caution" className="mt-4" title="Two values disagree">
          You entered {inr(est.value)}, but your latest statement suggests {inr(est.statement_value)}. Keep yours or update it.
        </Callout>
      )}
      {data.income.salary_candidates.length > 0 && (
        <ul className="mt-4 divide-y divide-line border-t border-line">
          {data.income.salary_candidates.map((c: any) => (
            <li key={c.group_id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{c.label}</p>
                <p className="text-sm text-muted">{c.occurrences} credits, usually around the {ordinal(c.day_of_month)} · <Money value={c.typical_amount} /></p>
              </div>
              {c.state === 'confirmed' ? <TrustMark state="confirmed" /> : (
                <div className="flex gap-2">
                  <Button size="sm" icon={<Check className="size-4" />} loading={act.isPending} onClick={() => act.mutate({ id: c.group_id, action: 'set_kind', kind: 'salary' })}>This is my salary</Button>
                  <Button size="sm" variant="secondary" onClick={() => act.mutate({ id: c.group_id, action: 'set_kind', kind: 'income_other' })}>Not salary</Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3">
        {editing ? (
          <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); const v = parseAmountInput(val); if (v === null) { setErr('Enter an amount.'); return } override.mutate(v) }}>
            <Field label="Your monthly take-home" error={err}><Input prefix="₹" inputMode="numeric" value={val} onChange={(e) => setVal(e.target.value)} className="w-48" /></Field>
            <Button type="submit" loading={override.isPending}>Save</Button>
            <Button variant="quiet" onClick={() => setEditing(false)}>Cancel</Button>
          </form>
        ) : <Button variant="ghost" size="sm" icon={<Pencil className="size-4" />} onClick={() => { setVal(est.value ? String(est.value) : ''); setEditing(true) }}>Enter a different amount</Button>}
      </div>
    </Panel>
  )
}

function RecurringRow({ g, kinds }: { g: any; kinds: { key: string; label: string }[] }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const act = useMutation({
    mutationFn: (b: any) => post(`/profile/recurring/${g.id}`, b),
    onSuccess: (_, b: any) => { qc.invalidateQueries(); toast({ title: b.action === 'reject' ? 'Marked as not recurring' : 'Confirmed', tone: 'positive' }) },
  })
  return (
    <li className="py-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <button type="button" onClick={() => setOpen(!open)} className="flex min-w-0 flex-1 items-start gap-2 text-left" aria-expanded={open}>
          <ChevronRight className={clsx('mt-1 size-4 shrink-0 text-muted transition-transform', open && 'rotate-90')} aria-hidden />
          <span className="min-w-0">
            <span className="flex flex-wrap items-center gap-2 font-medium">{g.label}<TrustMark state={g.state === 'confirmed' ? 'confirmed' : 'extracted'} /></span>
            <span className="block text-sm text-muted">{g.kind_label} · {g.direction === 'credit' ? 'received' : 'paid'} {g.occurrences} times, usually on the {ordinal(g.day_of_month)}</span>
          </span>
        </button>
        <Money value={g.typical_amount} className="text-right font-semibold sm:w-28" />
        {g.state !== 'confirmed' ? (
          <div className="flex flex-wrap gap-2">
            <label className="sr-only" htmlFor={`kind-${g.id}`}>Type</label>
            <Select id={`kind-${g.id}`} className="min-h-9 w-40 text-sm" value={g.kind} onChange={(e) => act.mutate({ action: 'set_kind', kind: e.target.value })}>
              {kinds.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
            </Select>
            <Button size="sm" icon={<Check className="size-4" />} onClick={() => act.mutate({ action: 'confirm' })}>Confirm</Button>
            <Button size="sm" variant="quiet" icon={<X className="size-4" />} onClick={() => act.mutate({ action: 'reject' })}>Not recurring</Button>
          </div>
        ) : <Button size="sm" variant="quiet" onClick={() => act.mutate({ action: 'reject' })}>Undo</Button>}
      </div>
      {open && (
        <ul className="ml-6 mt-2 flex flex-col gap-1 text-sm text-muted">
          {g.transactions.map((t: any) => (
            <li key={t.id} className="flex flex-wrap justify-between gap-2">
              <span>{date(t.date)} · {t.description.slice(0, 60)}</span>
              <span>{t.source.document_name} · {t.source.ref} · <Money value={t.amount} /></span>
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}

export function Review() {
  useSaathiPage('dashboard')
  const { user } = useAuth()
  const navigate = useNavigate()
  const [cat, setCat] = useState<string | null>(null)
  const q = useQuery({ queryKey: ['review'], queryFn: () => get<any>('/profile/review') })
  const qc = useQueryClient()
  if (q.isLoading) return <PageSkeleton />
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  if (!d.cashflow || d.cashflow.months_covered === 0) {
    return (
      <>
        <PageHeader title="Your financial profile" />
        <EmptyState title="No bank statement yet" body="Upload a 3, 6 or 12-month statement and VITTRM will show what it found here for you to confirm." action={<Button onClick={() => navigate('/onboarding/statement')}>Upload a statement</Button>} />
      </>
    )
  }
  const cf = d.cashflow
  const pending = d.recurring.filter((g: any) => g.needs_confirmation && g.kind !== 'salary')
  const others = d.recurring.filter((g: any) => !g.needs_confirmation && g.kind !== 'salary')
  async function finish() {
    if (user?.onboarding_step !== 'done') await post('/onboarding/step', { step: 'done' })
    qc.invalidateQueries({ queryKey: ['me'] })
    navigate('/')
  }
  return (
    <>
      <PageHeader title="Review your financial profile"
        description={`From ${date(cf.period_start)} to ${date(cf.period_end)} (${cf.months_covered} months). Confirm what's right and fix what isn't — your corrections are used everywhere in VITTRM.`}
        actions={<Button onClick={finish}>{d.review_state.items_needing_review ? 'Continue to dashboard' : 'Looks right — continue'}</Button>} />

      <Panel className="mb-6 grid gap-5 p-5 sm:grid-cols-4">
        <Stat label="Average money in" value={<Money value={cf.avg_monthly_inflow.value} />} mark={<TrustMark state="estimate" />} hint="a month" />
        <Stat label="Average money out" value={<Money value={cf.avg_monthly_outflow.value} />} mark={<TrustMark state="estimate" />} hint="a month" />
        <Stat label="Fixed commitments" value={<Money value={cf.fixed_monthly.value} />} hint="EMIs, rent, premiums, bills" />
        <Stat label="Left over" value={<Money value={cf.monthly_surplus.value} />} hint="average surplus a month" />
      </Panel>

      {d.review_state.items_needing_review > 0 && (
        <Callout tone="saathi" className="mb-6" title={`${d.review_state.items_needing_review} items to confirm`}>
          VITTRM treats unconfirmed items as estimates. Confirming them makes loan and EMI numbers more reliable.
        </Callout>
      )}

      <div className="flex flex-col gap-6">
        <IncomeBlock data={d} />

        <Panel className="p-5">
          <h2 className="font-semibold">Regular payments to confirm</h2>
          <p className="mt-0.5 text-sm text-muted">Detected from repeating debits. Confirmed EMIs go to your EMI calendar.</p>
          {pending.length === 0 ? <p className="mt-3 text-sm text-muted">Nothing left to confirm.</p> : (
            <ul className="mt-2 divide-y divide-line">{pending.map((g: any) => <RecurringRow key={g.id} g={g} kinds={d.kind_options} />)}</ul>
          )}
        </Panel>

        {others.length > 0 && (
          <Panel className="p-5">
            <h2 className="font-semibold">Other regular payments</h2>
            <ul className="mt-2 divide-y divide-line">{others.map((g: any) => <RecurringRow key={g.id} g={g} kinds={d.kind_options} />)}</ul>
          </Panel>
        )}

        <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
          <Panel className="p-5">
            <h2 className="font-semibold">Where your money goes</h2>
            <p className="mb-4 mt-0.5 text-sm text-muted">Average a month. Select a category to see and fix its transactions.</p>
            <CategoryBars rows={d.categories} onPick={setCat} />
          </Panel>
          <Panel className="p-5">
            <h2 className="font-semibold">Frequent merchants</h2>
            <ul className="mt-3 divide-y divide-line">
              {d.merchants.slice(0, 8).map((m: any) => (
                <li key={m.merchant} className="flex justify-between gap-2 py-2 text-[0.95rem]">
                  <span>{m.merchant}<span className="block text-xs text-muted">{m.per_month} times a month</span></span>
                  <Money value={m.monthly_spend} className="font-medium" />
                </li>
              ))}
            </ul>
          </Panel>
        </div>

        {d.high_value_events.length > 0 && (
          <Panel className="p-5">
            <h2 className="font-semibold">Large one-off transactions</h2>
            <ul className="mt-2 divide-y divide-line">
              {d.high_value_events.map((h: any) => (
                <li key={h.transaction_id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-[0.95rem]">
                  <span>{h.description}<span className="block text-xs text-muted">{dayMonth(h.date)} · {h.source.document_name} · {h.source.ref}</span></span>
                  <Money value={h.direction === 'debit' ? -h.amount : h.amount} className={clsx('font-medium', h.direction === 'credit' && 'text-positive')} />
                </li>
              ))}
            </ul>
          </Panel>
        )}

        {d.uncertain_transactions.length > 0 && (
          <Panel className="p-5">
            <h2 className="font-semibold">Transactions VITTRM wasn't sure about</h2>
            <p className="mt-0.5 text-sm text-muted">The PDF didn't make clear whether these were money in or out.</p>
            <UncertainList items={d.uncertain_transactions} />
          </Panel>
        )}
      </div>
      <TransactionsSheet category={cat} onClose={() => setCat(null)} options={d.category_options} />
    </>
  )
}

function UncertainList({ items }: { items: any[] }) {
  const qc = useQueryClient()
  const fix = useMutation({ mutationFn: ({ id, direction }: any) => patch(`/transactions/${id}`, { direction }), onSuccess: () => qc.invalidateQueries() })
  return (
    <ul className="mt-2 divide-y divide-line">
      {items.map((t) => (
        <li key={t.id} className="flex flex-wrap items-center gap-3 py-2.5">
          <span className="min-w-0 flex-1 text-[0.95rem]">{t.description}<span className="block text-xs text-muted">{date(t.date)} · {t.source.ref}</span></span>
          <Money value={t.amount} />
          <Button size="sm" variant="secondary" onClick={() => fix.mutate({ id: t.id, direction: 'credit' })}>Money in</Button>
          <Button size="sm" variant="secondary" onClick={() => fix.mutate({ id: t.id, direction: 'debit' })}>Money out</Button>
        </li>
      ))}
    </ul>
  )
}
