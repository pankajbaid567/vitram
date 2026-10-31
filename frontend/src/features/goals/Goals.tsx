import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Flag, Plus, Target, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Button } from '../../components/ui/button'
import { Badge, IconTile, Money, PageHeader, Panel, TrustMark } from '../../components/ui/data'
import { Field, Input } from '../../components/ui/field'
import { EmptyState, errorMessage, ErrorState, PageSkeleton, useToast } from '../../components/ui/feedback'
import { ConfirmDialog, Modal } from '../../components/ui/overlay'
import { ApiError, del, get, post } from '../../lib/api'
import { date, inr, parseAmountInput } from '../../lib/format'
import { useSaathiPage } from '../saathi/context'

function GoalForm({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient()
  const [f, setF] = useState({ name: '', target: '', date: '' })
  const [err, setErr] = useState<ApiError | null>(null)
  const m = useMutation({
    mutationFn: () => post('/goals', { name: f.name, target_amount: parseAmountInput(f.target), target_date: f.date || null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['goals'] }); onDone() },
    onError: (e) => setErr(e instanceof ApiError ? e : new ApiError(0, 'X', errorMessage(e))),
  })
  const fe = (k: string) => (err?.field === k ? err.message : null)
  return (
    <form noValidate className="grid gap-4" onSubmit={(e: FormEvent) => { e.preventDefault(); if (!f.name.trim()) return setErr(new ApiError(422, 'X', 'Name the goal.', 'name')); if (!parseAmountInput(f.target)) return setErr(new ApiError(422, 'X', 'Enter the amount you want to save.', 'target_amount')); m.mutate() }}>
      <Field label="What are you saving for?" error={fe('name')}><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="e.g. Emergency fund" /></Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Target amount" error={fe('target_amount')}><Input prefix="₹" inputMode="numeric" value={f.target} onChange={(e) => setF({ ...f, target: e.target.value })} /></Field>
        <Field label="Target date" optional error={fe('target_date')}><Input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
      </div>
      {err && !err.field && <p role="alert" className="text-sm text-critical">{err.message}</p>}
      <div className="flex gap-2"><Button type="submit" loading={m.isPending}>Create goal</Button><Button variant="quiet" onClick={onDone}>Cancel</Button></div>
    </form>
  )
}

function GoalCard({ g, surplus }: { g: any; surplus: { value: number | null } }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [amt, setAmt] = useState('')
  const [note, setNote] = useState('')
  const [confirmDel, setConfirmDel] = useState(false)
  const refresh = () => qc.invalidateQueries({ queryKey: ['goals'] })
  const add = useMutation({
    mutationFn: () => post(`/goals/${g.id}/contributions`, { amount: parseAmountInput(amt), note: note || null }),
    onSuccess: () => { refresh(); setAmt(''); setNote(''); toast({ title: 'Contribution recorded', tone: 'positive' }) },
    onError: (e) => toast({ title: errorMessage(e), tone: 'critical' }),
  })
  const remove = useMutation({ mutationFn: () => del(`/goals/${g.id}`), onSuccess: refresh })
  return (
    <Panel className="flex flex-col gap-4 p-5" aria-label={g.name}>
      <div className="flex items-start gap-3">
        <IconTile tone={g.reached ? 'green' : 'indigo'}>{g.reached ? <Flag /> : <Target />}</IconTile>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[1.05rem] font-semibold">{g.name}</p>
          <p className="text-sm text-muted">{g.target_date ? `By ${date(g.target_date)}` : 'No target date'}</p>
        </div>
        {g.reached ? <Badge tone="positive">Reached</Badge> : <Badge tone="indigo">{g.pct}%</Badge>}
      </div>
      <div>
        <div role="progressbar" aria-label={`${g.name} progress`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={g.pct} className="h-2.5 overflow-hidden rounded-full bg-ink/[0.07]">
          <span className="block h-full rounded-full bg-[image:var(--grad-indigo)]" style={{ width: `${g.pct}%` }} />
        </div>
        <p className="num mt-2 text-sm"><b><Money value={g.saved} /></b> of <Money value={g.target_amount} /> · <Money value={g.remaining} /> to go</p>
      </div>
      {g.monthly_needed != null && !g.reached && (
        <p className="rounded-[var(--radius-control)] bg-ink/[0.03] px-3 py-2 text-sm">
          About <b className="num">{inr(g.monthly_needed)}</b> a month over {g.months_left} month{g.months_left === 1 ? '' : 's'} gets you there.
          {surplus.value != null && <> Your average left over each month is about {inr(surplus.value)} <TrustMark state="estimate" className="ml-1 align-middle" />.</>}
        </p>
      )}
      <form className="flex flex-wrap items-end gap-2" onSubmit={(e: FormEvent) => { e.preventDefault(); add.mutate() }}>
        <Field label="Record a contribution" className="min-w-36 flex-1"><Input prefix="₹" inputMode="numeric" value={amt} onChange={(e) => setAmt(e.target.value)} placeholder="Use − for a withdrawal" /></Field>
        <Field label="Note" optional className="min-w-36 flex-1"><Input value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        <Button type="submit" variant="secondary" loading={add.isPending} disabled={!amt.trim()}>Add</Button>
      </form>
      {g.contributions.length > 0 && (
        <ul className="flex flex-col divide-y divide-[var(--glass-hairline)] text-sm">
          {g.contributions.slice(0, 4).map((c: any) => (
            <li key={c.id} className="flex justify-between gap-2 py-1.5"><span className="text-muted">{date(c.on_date)}{c.note ? ` · ${c.note}` : ''}</span><Money value={c.amount} sign className="font-medium" /></li>
          ))}
        </ul>
      )}
      <Button size="sm" variant="quiet" className="w-fit hover:text-critical" icon={<Trash2 className="size-4" />} onClick={() => setConfirmDel(true)}>Delete goal</Button>
      <ConfirmDialog open={confirmDel} onOpenChange={setConfirmDel} title={`Delete "${g.name}"?`} description="The goal and its recorded contributions are removed. No money moves." confirmLabel="Delete goal" cancelLabel="Keep" busy={remove.isPending} onConfirm={() => remove.mutate()} />
    </Panel>
  )
}

export function Goals() {
  useSaathiPage('dashboard')
  const [adding, setAdding] = useState(false)
  const q = useQuery({ queryKey: ['goals'], queryFn: () => get<any>('/goals') })
  if (q.isLoading) return <PageSkeleton />
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Goals' }]} title="Goals" description="Save towards something specific and track it. You record contributions yourself — VITTRM never moves money or assumes returns."
        actions={<Button size="lg" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>New goal</Button>} />
      {d.goals.length === 0 ? (
        <EmptyState headingLevel={2} icon={<Target />} title="No goals yet" body="An emergency fund, a trip, a laptop — set a target and, if you like, a date. VITTRM shows what that means per month."
          action={<Button onClick={() => setAdding(true)} icon={<Plus className="size-4" />}>Create your first goal</Button>} />
      ) : (
        <div className="grid items-start gap-5 @3xl:grid-cols-2 @6xl:grid-cols-3">{d.goals.map((g: any) => <GoalCard key={g.id} g={g} surplus={d.monthly_surplus} />)}</div>
      )}
      <p className="mt-6 text-xs text-muted">{d.note}</p>
      <Modal open={adding} onOpenChange={setAdding} title="New goal"><GoalForm onDone={() => setAdding(false)} /></Modal>
    </>
  )
}
