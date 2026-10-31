import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { AlertTriangle, ArrowRight, CalendarRange, Info, Plus, Trash2, Wallet } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../../components/ui/button'
import { Badge, IconTile, Money, PageHeader, Panel, SectionHeader, TrustMark } from '../../components/ui/data'
import { Field, Input, Segmented } from '../../components/ui/field'
import { Callout, errorMessage, ErrorState, PageSkeleton, useToast } from '../../components/ui/feedback'
import { ApiError, del, get, post, put } from '../../lib/api'
import { dayMonth, parseAmountInput, relDays } from '../../lib/format'
import { useSaathiPage } from '../saathi/context'

const useForecast = (days: number) => useQuery({ queryKey: ['forecast', days], queryFn: () => get<any>(`/forecast?days=${days}`) })

/** Compact dashboard card. Shows nothing invented: without a balance or confirmed income it asks for them. */
export function ForecastCard() {
  const q = useForecast(60)
  const f = q.data
  return (
    <Panel className="p-5" aria-labelledby="fc-h">
      <div className="mb-2 flex items-center gap-3"><IconTile tone="indigo" size="sm"><CalendarRange /></IconTile>
        <h2 id="fc-h" className="font-semibold">Next 60 days</h2><TrustMark state="estimate" className="ml-auto" /></div>
      {!f ? <p className="text-sm text-muted">Loading…</p> : f.closing_balance == null ? (
        <p className="text-sm text-muted">Add your current balance and confirm your income to see an estimate.</p>
      ) : (
        <div className="flex flex-col gap-1.5">
          <p className="text-sm text-muted">Estimated balance on {dayMonth(f.to)}</p>
          <Money value={f.closing_balance} className="text-[1.35rem] font-semibold" />
          {f.pressure && <p className="flex items-start gap-1.5 text-sm text-caution"><AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />{f.pressure.message}</p>}
        </div>
      )}
      <Link to="/forecast" className="mt-3 inline-flex min-h-9 items-center gap-1 text-sm font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">See the estimate<ArrowRight className="size-4" aria-hidden /></Link>
    </Panel>
  )
}

export function Forecast() {
  useSaathiPage('dashboard')
  const qc = useQueryClient()
  const toast = useToast()
  const [days, setDays] = useState(60)
  const q = useForecast(days)
  const refresh = () => qc.invalidateQueries({ queryKey: ['forecast'] })
  const [bal, setBal] = useState('')
  const opening = useMutation({ mutationFn: (amount: number | null) => put('/forecast/opening-balance', { amount }), onSuccess: () => { refresh(); setBal(''); toast({ title: 'Balance saved', tone: 'positive' }) } })
  const exclude = useMutation({ mutationFn: (b: { key: string; excluded: boolean }) => post('/forecast/exclusions', b), onSuccess: refresh })
  const [x, setX] = useState({ label: '', amount: '', direction: 'debit' as 'debit' | 'credit', on_date: '' })
  const [xErr, setXErr] = useState<ApiError | null>(null)
  const addX = useMutation({
    mutationFn: () => post('/forecast/expected', { ...x, amount: parseAmountInput(x.amount) }),
    onSuccess: () => { refresh(); setX({ label: '', amount: '', direction: 'debit', on_date: '' }); setXErr(null) },
    onError: (e) => setXErr(e instanceof ApiError ? e : new ApiError(0, 'X', errorMessage(e))),
  })
  const delX = useMutation({ mutationFn: (id: string) => del(`/forecast/expected/${id}`), onSuccess: refresh })
  if (q.isLoading) return <PageSkeleton />
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const f = q.data
  const o = f.opening_balance
  const byDate = new Map<string, any[]>()
  for (const e of f.events) byDate.set(e.date, [...(byDate.get(e.date) ?? []), e])
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Cash-flow estimate' }]} title="Cash-flow estimate"
        description="What's likely to come in and go out, using only numbers you've confirmed or entered. An estimate, not a guarantee."
        actions={<Segmented label="Period" value={days} onChange={setDays} options={[{ value: 30, label: '30 days' }, { value: 60, label: '60 days' }, { value: 90, label: '90 days' }]} />} />

      {f.pressure && <Callout tone="caution" className="mb-6" title={f.pressure.level === 'shortfall' ? 'Money could run short' : 'Things could get tight'}>{f.pressure.message} Moving a payment date or adding income you expect changes this.</Callout>}

      <section className="mb-6 grid gap-4 @xl:grid-cols-2 @5xl:grid-cols-4" aria-label="Summary">
        <div className="surface-card rounded-[var(--radius-card)] p-4">
          <p className="flex items-center justify-between text-sm text-muted">Starting balance{o.source && <Badge tone={o.source === 'you entered' ? 'positive' : 'neutral'}>{o.source}</Badge>}</p>
          <p className="num mt-1 text-[1.3rem] font-semibold">{o.amount != null ? <Money value={o.amount} /> : 'Not added'}</p>
          {o.as_of && <p className="text-xs text-muted">as of {dayMonth(o.as_of)}</p>}
          <form className="mt-2 flex gap-2" onSubmit={(e: FormEvent) => { e.preventDefault(); const v = parseAmountInput(bal); if (v != null) opening.mutate(v) }}>
            <Input aria-label="Current balance" prefix="₹" inputMode="numeric" placeholder="Current balance" value={bal} onChange={(e) => setBal(e.target.value)} className="min-h-10" />
            <Button type="submit" size="sm" variant="secondary" loading={opening.isPending}>Save</Button>
          </form>
        </div>
        {[['Money in', f.totals.in], ['Money out', f.totals.out]].map(([l, v]) => (
          <div key={l as string} className="surface-card rounded-[var(--radius-card)] p-4"><p className="text-sm text-muted">{l} · next {days} days</p><p className="num mt-1 text-[1.3rem] font-semibold"><Money value={v as number} /></p></div>
        ))}
        <div className="surface-card rounded-[var(--radius-card)] p-4">
          <p className="flex items-center justify-between text-sm text-muted">Estimated balance on {dayMonth(f.to)}<TrustMark state="estimate" /></p>
          <p className="num mt-1 text-[1.3rem] font-semibold">{f.closing_balance != null ? <Money value={f.closing_balance} /> : '—'}</p>
          {f.lowest && <p className="text-xs text-muted">Lowest: <Money value={f.lowest.amount} /> around {dayMonth(f.lowest.date)}</p>}
        </div>
      </section>

      <div className="grid items-start gap-6 @5xl:grid-cols-[1.5fr_1fr]">
        <Panel className="p-5 sm:p-6" aria-labelledby="tl-h">
          <SectionHeader id="tl-h" title="Timeline" description="Switch off anything that won't happen. Excluded items stay listed but don't count." />
          {f.events.length === 0 ? <p className="text-sm text-muted">Nothing confirmed falls in this period yet.</p> : (
            <ol className="flex flex-col gap-4">
              {[...byDate.entries()].map(([d, evs]) => (
                <li key={d}>
                  <p className="mb-1.5 text-sm font-semibold">{dayMonth(d)} <span className="font-normal text-muted">· {relDays(d)}</span></p>
                  <ul className="flex flex-col gap-1.5">
                    {evs.map((e: any) => {
                      const k = e.key.split('@')[0]
                      return (
                        <li key={e.key} className={clsx('flex flex-wrap items-center gap-3 rounded-[14px] border px-3 py-2.5', e.excluded ? 'border-dashed border-line-strong bg-white/40 text-muted' : 'border-white/80 bg-white/75')}>
                          <span className="min-w-0 flex-1"><span className={clsx('block truncate font-medium', e.excluded && 'line-through')}>{e.label}</span><span className="text-xs text-muted">{e.source}</span></span>
                          <span className={clsx('num font-semibold', e.direction === 'credit' ? 'text-positive' : '')}>{e.direction === 'credit' ? '+' : '−'}<Money value={e.amount} /></span>
                          {!e.excluded && <span className="num hidden w-28 text-right text-xs text-muted @3xl:block">then <Money value={e.balance_after} /></span>}
                          <label className="flex min-h-9 items-center gap-1.5 text-xs">
                            <input type="checkbox" checked={!e.excluded} onChange={(ev) => exclude.mutate({ key: k, excluded: !ev.target.checked })} className="size-4 accent-[var(--color-indigo)]" />
                            Include
                          </label>
                        </li>
                      )
                    })}
                  </ul>
                </li>
              ))}
            </ol>
          )}
        </Panel>

        <div className="flex flex-col gap-6">
          <Panel className="p-5" aria-labelledby="ex-h">
            <SectionHeader id="ex-h" title="Expected payments" description="One-off amounts you know are coming, in or out." />
            <form className="grid gap-3" noValidate onSubmit={(e: FormEvent) => { e.preventDefault(); addX.mutate() }}>
              <Field label="What is it" error={xErr?.field === 'label' ? xErr.message : null}><Input value={x.label} onChange={(e) => setX({ ...x, label: e.target.value })} placeholder="e.g. School fees" /></Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Amount" error={xErr?.field === 'amount' ? xErr.message : null}><Input prefix="₹" inputMode="numeric" value={x.amount} onChange={(e) => setX({ ...x, amount: e.target.value })} /></Field>
                <Field label="Date" error={xErr?.field === 'on_date' ? xErr.message : null}><Input type="date" value={x.on_date} onChange={(e) => setX({ ...x, on_date: e.target.value })} /></Field>
              </div>
              <Segmented label="Direction" value={x.direction} onChange={(v) => setX({ ...x, direction: v })} options={[{ value: 'debit', label: 'Money out' }, { value: 'credit', label: 'Money in' }]} />
              {xErr && !xErr.field && <p role="alert" className="text-sm text-critical">{xErr.message}</p>}
              <Button type="submit" variant="secondary" icon={<Plus className="size-4" />} loading={addX.isPending} className="w-fit">Add</Button>
            </form>
            {f.expected_payments.length > 0 && (
              <ul className="mt-4 flex flex-col divide-y divide-[var(--glass-hairline)]">
                {f.expected_payments.map((p: any) => (
                  <li key={p.id} className="flex items-center gap-2 py-2 text-sm">
                    <span className="min-w-0 flex-1 truncate">{p.label} · {dayMonth(p.on_date)}</span>
                    <span className="num font-medium">{p.direction === 'credit' ? '+' : '−'}<Money value={p.amount} /></span>
                    <Button size="sm" variant="quiet" aria-label={`Remove ${p.label}`} onClick={() => delX.mutate(p.id)}><Trash2 className="size-4" /></Button>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          <Panel className="p-5" aria-labelledby="as-h">
            <h2 id="as-h" className="mb-2 flex items-center gap-2 font-semibold"><Info className="size-4 text-indigo" aria-hidden />How this is worked out</h2>
            <ul className="flex flex-col gap-1.5 text-sm text-ink/80">{f.assumptions.map((a: string) => <li key={a}>{a}</li>)}</ul>
            {f.missing.length > 0 && <>
              <h3 className="mb-1 mt-4 flex items-center gap-2 text-sm font-semibold"><Wallet className="size-4 text-caution" aria-hidden />Not included yet</h3>
              <ul className="flex flex-col gap-1.5 text-sm text-ink/80">{f.missing.map((m: string) => <li key={m}>{m}</li>)}</ul>
              <p className="mt-3 flex flex-wrap gap-3 text-sm"><Link to="/profile/review" className="font-medium text-indigo underline decoration-indigo/40 underline-offset-2">Review your profile</Link><Link to="/emis" className="font-medium text-indigo underline decoration-indigo/40 underline-offset-2">Confirm EMIs</Link></p>
            </>}
            <p className="mt-4 text-xs text-muted">{f.note}</p>
          </Panel>
        </div>
      </div>
    </>
  )
}
