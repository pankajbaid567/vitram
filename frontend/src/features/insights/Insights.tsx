import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, FileText, HelpCircle, Lightbulb, MessageCircle, Repeat, Search, TrendingDown, TrendingUp, X } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, LinkButton } from '../../components/ui/button'
import { Badge, IconTile, Money, PageHeader, Panel, SectionHeader } from '../../components/ui/data'
import { EmptyState, errorMessage, ErrorState, PageSkeleton, Skeleton, useToast } from '../../components/ui/feedback'
import { Sheet } from '../../components/ui/overlay'
import { get, post } from '../../lib/api'
import { date, inr } from '../../lib/format'
import { useSaathi, useSaathiPage } from '../saathi/context'

const monthLabel = (k: string) => new Date(`${k}-01T00:00:00`).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })

export function Insights() {
  useSaathiPage('dashboard')
  const qc = useQueryClient()
  const toast = useToast()
  const [explainId, setExplainId] = useState<string | null>(null)
  const q = useQuery({ queryKey: ['insights'], queryFn: () => get<any>('/insights/spending') })
  const decideSub = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: string }) => post(`/insights/subscriptions/${id}`, { decision }),
    onSuccess: (_d, v) => { qc.invalidateQueries({ queryKey: ['insights'] }); toast({ title: v.decision === 'confirm' ? 'Marked as a subscription' : 'Removed from subscriptions', tone: 'positive' }) },
    onError: (e) => toast({ title: errorMessage(e), tone: 'critical' }),
  })
  const expected = useMutation({
    mutationFn: (id: string) => post(`/insights/unusual/${id}`, { decision: 'expected' }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['insights'] }); toast({ title: "Noted — it won't be flagged again", tone: 'positive' }) },
  })
  if (q.isLoading) return <PageSkeleton />
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  const months: string[] = d.months_covered
  const crumbs = [{ label: 'Home', to: '/' }, { label: 'Spending insights' }]
  if (!months.length) {
    return (
      <>
        <PageHeader crumbs={crumbs} title="Spending insights" description="Patterns in your own bank statement — trends, subscriptions and payments worth a second look." />
        <EmptyState headingLevel={2} icon={<Search />} title="No statement yet" body="Upload a bank statement of 3, 6 or 12 months. VITTRM compares full calendar months, so three or more give the clearest picture."
          action={<LinkButton to="/onboarding/statement">Upload a bank statement</LinkButton>} />
      </>
    )
  }
  return (
    <>
      <PageHeader crumbs={crumbs} title="Spending insights"
        description={<>From your statement, {monthLabel(months[0])} to {monthLabel(months[months.length - 1])} ({months.length} full months). These are patterns, not judgements — you decide what matters.</>} />

      {d.opportunities.length > 0 && (
        <section className="mb-8 grid gap-4 @3xl:grid-cols-2" aria-label="Worth a look">
          {d.opportunities.map((o: any) => (
            <div key={o.kind} className="wash-amber flex items-start gap-3 rounded-[var(--radius-panel)] p-5">
              <IconTile tone="amber"><Lightbulb /></IconTile>
              <div><p className="font-semibold">{o.title}</p><p className="mt-1 text-[0.95rem] text-ink/80">{o.body}</p></div>
            </div>
          ))}
        </section>
      )}

      <div className="grid items-start gap-6 @5xl:grid-cols-2">
        <Panel className="p-5 sm:p-6" aria-labelledby="trend-h">
          <SectionHeader id="trend-h" title="How your month compared" description={d.latest_full_month ? `${monthLabel(d.latest_full_month)} against your average for the months before` : 'Needs at least three full months'} />
          {d.trends.length === 0 ? <p className="text-sm text-muted">No category moved by more than 20% (and ₹1,000) from your usual month.</p> : (
            <ul className="flex flex-col gap-2">
              {d.trends.map((t: any) => {
                const up = t.change > 0
                const max = Math.max(t.amount, t.average, 1)
                return (
                  <li key={t.category} className="rounded-[var(--radius-card)] border border-white/80 bg-white/75 p-3.5">
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-medium">{t.label}</p>
                      <Badge tone="indigo">{up ? <TrendingUp className="size-3.5" aria-hidden /> : <TrendingDown className="size-3.5" aria-hidden />}{up ? '+' : '−'}{Math.abs(t.change_pct)}%</Badge>
                    </div>
                    <div className="mt-2 grid grid-cols-[4.5rem_1fr_auto] items-center gap-x-3 gap-y-1 text-sm">
                      <span className="text-muted">This month</span><span className="h-2 overflow-hidden rounded-full bg-ink/[0.06]"><span className="block h-full rounded-full bg-[image:var(--grad-indigo)]" style={{ width: `${(t.amount / max) * 100}%` }} /></span><Money value={t.amount} className="text-right font-medium" />
                      <span className="text-muted">Average</span><span className="h-2 overflow-hidden rounded-full bg-ink/[0.06]"><span className="block h-full rounded-full bg-indigo-300" style={{ width: `${(t.average / max) * 100}%` }} /></span><Money value={t.average} className="text-right" />
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </Panel>

        <Panel className="p-5 sm:p-6" aria-labelledby="subs-h">
          <SectionHeader id="subs-h" title="Possible subscriptions" description="Monthly payments that look like subscriptions. Confirm the ones that are." />
          {d.subscriptions.length === 0 ? <p className="text-sm text-muted">No monthly subscription-like payments found.</p> : (
            <ul className="flex flex-col gap-2">
              {d.subscriptions.map((s: any) => (
                <li key={s.group_id} className="rounded-[var(--radius-card)] border border-white/80 bg-white/75 p-3.5">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="flex min-w-0 items-start gap-3">
                      <IconTile tone="violet" size="sm"><Repeat /></IconTile>
                      <div className="min-w-0">
                        <p className="truncate font-medium">{s.label}</p>
                        <p className="num text-sm text-muted"><Money value={s.typical_amount} /> a month · about {inr(s.yearly_estimate)} a year · last {date(s.last_date)}</p>
                        <p className="text-xs text-muted">{s.why}</p>
                      </div>
                    </div>
                    <Badge tone={s.status === 'confirmed' ? 'positive' : 'neutral'}>{s.status === 'confirmed' ? 'You confirmed' : 'Possible'}</Badge>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {s.status !== 'confirmed' && <Button size="sm" variant="secondary" icon={<Check className="size-4" />} onClick={() => decideSub.mutate({ id: s.group_id, decision: 'confirm' })}>Yes, a subscription</Button>}
                    <Button size="sm" variant="quiet" icon={<X className="size-4" />} onClick={() => decideSub.mutate({ id: s.group_id, decision: 'dismiss' })}>Not a subscription</Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel className="p-5 sm:p-6 @5xl:col-span-2" aria-labelledby="odd-h">
          <SectionHeader id="odd-h" title="Payments worth a second look" description="Different from your usual pattern in the last 90 days. Unusual doesn't mean wrong — if you don't recognise one, contact your bank." />
          {d.unusual.length === 0 ? <p className="text-sm text-muted">Nothing stands out from your usual pattern.</p> : (
            <ul className="grid gap-2 @4xl:grid-cols-2">
              {d.unusual.map((u: any) => (
                <li key={u.id} className="rounded-[var(--radius-card)] border border-white/80 bg-white/75 p-3.5">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0"><p className="truncate font-medium">{u.merchant ?? u.description}</p><p className="num text-sm text-muted">{date(u.date)} · {u.category}</p></div>
                    <Money value={u.amount} className="font-semibold" />
                  </div>
                  <ul className="mt-1.5 text-sm text-ink/80">{u.reasons.map((r: string) => <li key={r}>{r}</li>)}</ul>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <Button size="sm" variant="secondary" icon={<HelpCircle className="size-4" />} onClick={() => setExplainId(u.id)}>Explain</Button>
                    <Button size="sm" variant="quiet" icon={<Check className="size-4" />} loading={expected.isPending && expected.variables === u.id} onClick={() => expected.mutate(u.id)}>I expected this</Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
      <ul className="mt-6 flex flex-col gap-1 text-xs text-muted">{d.notes.map((n: string) => <li key={n}>{n}</li>)}</ul>
      <ExplainSheet id={explainId} onClose={() => setExplainId(null)} />
    </>
  )
}

/** "Explain this transaction": category, pattern, history and the statement line it came from. */
export function ExplainSheet({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { ask } = useSaathi()
  const q = useQuery({ queryKey: ['explain', id], queryFn: () => get<any>(`/transactions/${id}/explain`), enabled: !!id })
  const t = q.data?.transaction
  return (
    <Sheet open={!!id} onOpenChange={(o) => !o && onClose()} title="About this transaction" description={t ? `${date(t.date)} · ${inr(t.amount)}` : undefined}>
      {q.isLoading || !q.data ? <div className="flex flex-col gap-2"><Skeleton className="h-6" /><Skeleton className="h-20" /></div> : (
        <div className="flex flex-col gap-4 text-[0.95rem]">
          <div className="rounded-[var(--radius-card)] border border-white/80 bg-white/80 p-4">
            <p className="font-semibold">{t.merchant ?? 'Payment'}</p>
            <p className="mt-0.5 break-words text-sm text-muted">{t.description}</p>
            <div className="mt-2 flex flex-wrap gap-1.5"><Badge tone="indigo">{t.category}</Badge>{t.channel && <Badge>{t.channel}</Badge>}<Badge>{t.direction === 'debit' ? 'Money out' : 'Money in'}</Badge></div>
          </div>
          <ul className="flex flex-col gap-2">{q.data.explanation.map((l: string) => <li key={l} className="flex gap-2"><span className="mt-2 size-1.5 shrink-0 rounded-full bg-indigo" aria-hidden />{l}</li>)}</ul>
          {q.data.unusual.length > 0 && <div className="rounded-[var(--radius-control)] bg-caution-soft/60 p-3 text-sm"><p className="font-medium">Why it was flagged</p><ul>{q.data.unusual.map((r: string) => <li key={r}>{r}</li>)}</ul></div>}
          {q.data.receipts.length > 0 && (
            <div><p className="mb-1 text-sm font-medium">Matched receipt</p>
              {q.data.receipts.map((r: any) => <Link key={r.document_id} to={`/documents/receipts/${r.document_id}`} className="block text-indigo underline decoration-indigo/40 underline-offset-2">{r.merchant ?? r.name}</Link>)}</div>
          )}
          <p className="flex items-center gap-2 text-sm text-muted"><FileText className="size-4" aria-hidden />From {q.data.source.document_name ?? 'your statement'} · {q.data.source.ref}</p>
          <Button variant="secondary" icon={<MessageCircle className="size-4" />} onClick={() => ask(`Explain my ${t.merchant ?? 'payment'} of ${inr(t.amount)} on ${date(t.date)}`)}>Ask Vitt Saathi</Button>
        </div>
      )}
    </Sheet>
  )
}
