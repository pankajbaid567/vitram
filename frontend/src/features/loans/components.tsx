import { useMutation } from '@tanstack/react-query'
import clsx from 'clsx'
import { Tabs } from 'radix-ui'
import { useState, type FormEvent } from 'react'
import { Button } from '../../components/ui/button'
import { Badge, Money, SourceLink, TrustMark } from '../../components/ui/data'
import { Field, Input, Select } from '../../components/ui/field'
import { Callout, errorMessage } from '../../components/ui/feedback'
import { post } from '../../lib/api'
import { months, parseAmountInput, pct } from '../../lib/format'

export const PURPOSES = [
  ['personal', 'Personal need'], ['home', 'Buying a home'], ['home_renovation', 'Home renovation'], ['vehicle', 'Vehicle'],
  ['education', 'Education'], ['medical', 'Medical expenses'], ['wedding', 'Wedding'], ['travel', 'Travel'],
  ['debt_consolidation', 'Consolidating debt'], ['other', 'Something else'],
] as const

export const SEVERITY: Record<string, { label: string; tone: 'caution' | 'critical' | 'indigo' | 'neutral' }> = {
  important: { label: 'Important', tone: 'critical' },
  cost_impact: { label: 'Cost impact', tone: 'caution' },
  flexibility_impact: { label: 'Flexibility impact', tone: 'indigo' },
  eligibility_condition: { label: 'Eligibility / condition', tone: 'neutral' },
}

function docCitation(documentId: string | undefined, documentName: string | undefined, src: any) {
  if (!documentId || !src) return null
  return { document_id: documentId, document_type: 'loan_document', document_name: documentName, page: src.page, snippet: src.snippet }
}

/** RD §12.5 / §22.2 — scheduled cost kept separate from contingent charges. */
export function RealCost({ cost, documentId, documentName }: { cost: any; documentId?: string; documentName?: string }) {
  const rows: { k: string; v: number | null; note?: string; cite?: any; missing?: boolean }[] = [
    { k: 'Amount borrowed', v: cost.principal },
    { k: `Interest over ${months(cost.tenure_months)} at ${pct(cost.annual_rate_pct)}`, v: cost.scheduled_interest },
  ]
  for (const c of cost.documented_mandatory_charges) {
    rows.push({ k: c.label + (c.basis === 'percent_of_principal' && c.rate_value != null ? ` (${c.rate_value}%)` : ''), v: c.amount, note: c.note, cite: docCitation(documentId, documentName, c.source), missing: c.status === 'not_available' })
    if (c.gst) rows.push({ k: `GST on ${c.label.toLowerCase()}`, v: c.gst })
  }
  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-[var(--radius-panel)] bg-ink p-4 text-white">
          <p className="text-sm text-white/70">Monthly EMI</p>
          <p className="num text-2xl font-semibold"><Money value={cost.monthly_emi} /></p>
        </div>
        <div className="rounded-[var(--radius-card)] border border-[var(--glass-hairline)] bg-ink/[0.02] p-4">
          <p className="text-sm text-muted">Total you pay if on time</p>
          <p className="num text-2xl font-semibold"><Money value={cost.scheduled_total_outflow} /></p>
        </div>
        <div className="rounded-[var(--radius-card)] border border-[var(--glass-hairline)] bg-ink/[0.02] p-4">
          <p className="flex items-center gap-2 text-sm text-muted">Annualized cost <TrustMark state="estimate" /></p>
          {cost.annualized_cost_pct != null ? <p className="num text-2xl font-semibold">{pct(cost.annualized_cost_pct)}</p>
            : <p className="mt-1 text-[0.95rem] text-muted">Not computable — some mandatory charges aren't stated</p>}
          {cost.stated_apr_pct != null && <p className="text-xs text-muted">Lender states APR {pct(cost.stated_apr_pct)}</p>}
        </div>
      </div>

      <div>
        <h3 className="mb-2 font-semibold">Scheduled cost — paid on time</h3>
        <table className="w-full text-[0.95rem]">
          <tbody className="divide-y divide-line">
            {rows.map((r, i) => (
              <tr key={i}>
                <td className="py-2.5 pr-3">{r.k}{r.note && <span className="block text-xs text-muted">{r.note}</span>}{r.cite && <SourceLink citation={r.cite} />}</td>
                <td className="py-2.5 text-right">{r.missing ? <span className="text-sm text-caution">Not available</span> : <Money value={r.v} />}</td>
              </tr>
            ))}
            <tr className="font-semibold"><td className="py-3">Total scheduled outflow</td><td className="py-3 text-right"><Money value={cost.scheduled_total_outflow} /></td></tr>
            <tr className="text-muted"><td className="py-1 text-sm">Cost of credit (everything above the amount borrowed)</td><td className="py-1 text-right text-sm"><Money value={cost.total_cost_of_credit} /></td></tr>
          </tbody>
        </table>
        {cost.missing?.length > 0 && <Callout tone="caution" className="mt-3" title="Not included because it isn't stated">{cost.missing.join('; ')}.</Callout>}
        {cost.emi_check && (
          <p className={clsx('mt-2 text-sm', cost.emi_check.matches ? 'text-positive' : 'text-caution')}>
            {cost.emi_check.matches ? 'The EMI in the document matches VITRAM\'s calculation.' : `The document states an EMI of ₹${cost.emi_check.stated}, but the stated terms give ${Math.round(cost.emi_check.calculated)}. Check the document.`}
          </p>
        )}
      </div>

      {cost.optional_charges?.length > 0 && (
        <div>
          <h3 className="mb-1 font-semibold">Optional add-ons (not in the total)</h3>
          <ul className="text-[0.95rem]">{cost.optional_charges.map((c: any) => <li key={c.key} className="flex justify-between py-1.5"><span>{c.label}</span><Money value={c.amount} /></li>)}</ul>
        </div>
      )}

      <div>
        <h3 className="mb-1 font-semibold">Only if something happens</h3>
        <p className="mb-2 text-sm text-muted">These charges apply only in specific situations, so they aren't added to the total.</p>
        <ul className="divide-y divide-line text-[0.95rem]">
          {cost.contingent_charges.map((c: any) => (
            <li key={c.key} className="flex flex-col gap-0.5 py-2.5 sm:flex-row sm:justify-between sm:gap-6">
              <span className="font-medium">{c.label}</span>
              <span className={clsx('sm:text-right', c.status === 'not_available' && 'text-caution')}>{c.description}{c.source && <SourceLink citation={docCitation(documentId, documentName, c.source)} className="ml-1" />}</span>
            </li>
          ))}
        </ul>
      </div>
      <details className="text-sm text-muted">
        <summary className="font-medium text-ink">Assumptions and formula</summary>
        <ul className="mt-2 list-disc pl-5">{cost.assumptions.map((a: string) => <li key={a}>{a}</li>)}</ul>
        <p className="mt-2">EMI = P × r × (1 + r)ⁿ ÷ ((1 + r)ⁿ − 1), r = monthly rate. Formula version {cost.formula_version}.</p>
      </details>
    </div>
  )
}

export function Clauses({ clauses, documentId, documentName }: { clauses: any[]; documentId?: string; documentName?: string }) {
  if (!clauses?.length) return <p className="text-sm text-muted">No material clauses were found in the available terms.</p>
  return (
    <ul className="flex flex-col gap-3">
      {clauses.map((c, i) => {
        const s = SEVERITY[c.severity] ?? SEVERITY.important
        return (
          <li key={i} className="rounded-[var(--radius-control)] border border-line p-3">
            <div className="flex flex-wrap items-center gap-2"><Badge tone={s.tone}>{s.label}</Badge><span className="font-medium">{c.title}</span></div>
            <p className="mt-1 text-[0.95rem] text-ink/85">{c.text}</p>
            {c.source && documentId && <SourceLink citation={docCitation(documentId, documentName, c.source)} label="View clause" />}
          </li>
        )
      })}
    </ul>
  )
}

function ScenarioTable({ r }: { r: any }) {
  if (!r) return null
  if (!r.computable) {
    return (
      <Callout tone="caution" title="Can't calculate this precisely">
        <ul className="list-disc pl-5">{[...(r.missing ?? []), ...(r.notes ?? [])].map((m: string) => <li key={m}>{m}</li>)}</ul>
      </Callout>
    )
  }
  const b = r.baseline ?? {}, s = r.scenario ?? {}
  const pay = r.kind.includes('payment')
  const lines: [string, any, any][] = pay
    ? [['Amount due', b.amount_due, s.amount_due], ['Late fee', null, s.late_fee], ['Penal interest', null, s.penal_interest], ['GST', null, s.gst], ['Extra cost', b.extra_cost, s.extra_cost]]
    : r.kind === 'prepayment'
      ? [['EMI', b.monthly_emi, s.monthly_emi], ['Tenure', b.tenure_months, s.total_tenure_months], ['Total repayment', b.total_repayment, s.total_repayment], ['Interest saved', null, s.interest_saved], ['Prepayment charge', null, s.prepayment_charge], ['Net saving', null, s.net_saving]]
      : [['EMI', b.monthly_emi, s.monthly_emi], ['Tenure', b.tenure_months, s.tenure_months], ['Total interest', b.total_interest, s.total_interest], ['Total repayment', b.total_repayment, s.total_repayment]]
  return (
    <div className="flex flex-col gap-3">
      <table className="w-full text-[0.95rem]">
        <thead><tr className="text-sm text-muted"><th className="py-2 text-left font-normal">&nbsp;</th><th className="py-2 text-right font-normal">Now</th><th className="py-2 text-right font-normal">Scenario</th></tr></thead>
        <tbody className="divide-y divide-line">
          {lines.map(([k, a, c]) => (
            <tr key={k}>
              <td className="py-2">{k}</td>
              <td className="py-2 text-right text-muted">{k === 'Tenure' ? (a ? `${a} months` : '') : a != null ? <Money value={a} /> : ''}</td>
              <td className="py-2 text-right font-medium">{k === 'Tenure' ? (c ? `${c} months` : '') : c === null && (k === 'Net saving' || k === 'Prepayment charge') ? <span className="text-caution">Not known</span> : c != null ? <Money value={c} /> : ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {r.notes?.length > 0 && <ul className="list-disc pl-5 text-sm text-muted">{r.notes.map((n: string) => <li key={n}>{n}</li>)}</ul>}
      {r.missing?.length > 0 && <p className="text-sm text-caution">Missing: {r.missing.join('; ')}</p>}
      <details className="text-sm text-muted"><summary className="font-medium text-ink">Assumptions</summary><ul className="mt-1 list-disc pl-5">{r.assumptions.map((a: string) => <li key={a}>{a}</li>)}</ul></details>
    </div>
  )
}

/** S15 — deterministic what-if scenarios with baseline vs scenario (RD §12.8, §22.3). */
export function WhatIf({ base, floating }: { base: { product_id?: string; user_loan_id?: string; principal: number; tenure_months: number }; floating?: boolean }) {
  const [tab, setTab] = useState('tenure')
  const [v, setV] = useState({ tenure: String(base.tenure_months + 12), amount: String(Math.round(base.principal * 0.8)), prepay: '50000', after: '12', mode: 'reduce_tenure', days: '30', rate: '', hold: 'emi', lateFee: '', penal: '' })
  const [err, setErr] = useState<string | null>(null)
  const m = useMutation({ mutationFn: (body: any) => post<any>('/loans/calculate', body), onError: (e) => setErr(errorMessage(e)) })
  const set = (k: string) => (e: any) => setV({ ...v, [k]: e.target.value })

  function run(e: FormEvent) {
    e.preventDefault()
    setErr(null)
    const b: any = { ...base }
    if (tab === 'tenure') Object.assign(b, { kind: 'tenure_change', new_tenure_months: Number(v.tenure) })
    if (tab === 'amount') Object.assign(b, { kind: 'amount_change', new_principal: parseAmountInput(v.amount) })
    if (tab === 'prepay') Object.assign(b, { kind: 'prepayment', prepay_amount: parseAmountInput(v.prepay), after_month: Number(v.after), mode: v.mode })
    if (tab === 'missed') {
      Object.assign(b, { kind: 'missed_payment', days_late: Number(v.days) })
      if (v.lateFee || v.penal) b.late_rule_override = { flat_fee: v.lateFee ? parseAmountInput(v.lateFee) : null, penal_rate_pa: v.penal ? Number(v.penal) : null, gst_applicable: true }
    }
    if (tab === 'rate') {
      if (!v.rate) { setErr('Enter the new rate.'); return }
      Object.assign(b, { kind: 'rate_change', new_rate_pct: Number(v.rate), hold: v.hold })
    }
    m.mutate(b)
  }
  const tabs = [['tenure', 'Tenure'], ['amount', 'Amount'], ['prepay', 'Prepay'], ['missed', 'Miss / delay an EMI'], ...(floating ? [['rate', 'Rate change']] : [])]
  return (
    <Tabs.Root value={tab} onValueChange={(t) => { setTab(t); m.reset() }}>
      <Tabs.List className="mb-4 flex w-fit max-w-full flex-wrap gap-1 rounded-[16px] bg-ink/[0.05] p-1" aria-label="What-if scenarios">
        {tabs.map(([k, l]) => (
          <Tabs.Trigger key={k} value={k} className="min-h-10 rounded-[12px] px-3.5 text-sm font-medium text-muted transition-[background-color,color,box-shadow] duration-[var(--dur)] hover:text-ink data-[state=active]:bg-white data-[state=active]:text-ink data-[state=active]:shadow-[var(--elev-1)]">{l}</Tabs.Trigger>
        ))}
      </Tabs.List>
      <form onSubmit={run} className="flex flex-col gap-4">
        <Tabs.Content value="tenure" className="grid gap-4 sm:grid-cols-2"><Field label="New tenure (months)"><Input inputMode="numeric" value={v.tenure} onChange={set('tenure')} /></Field></Tabs.Content>
        <Tabs.Content value="amount" className="grid gap-4 sm:grid-cols-2"><Field label="New amount"><Input prefix="₹" inputMode="numeric" value={v.amount} onChange={set('amount')} /></Field></Tabs.Content>
        <Tabs.Content value="prepay" className="grid gap-4 sm:grid-cols-3">
          <Field label="Prepay"><Input prefix="₹" inputMode="numeric" value={v.prepay} onChange={set('prepay')} /></Field>
          <Field label="After how many EMIs"><Input inputMode="numeric" value={v.after} onChange={set('after')} /></Field>
          <Field label="Use it to"><Select value={v.mode} onChange={set('mode')}><option value="reduce_tenure">Finish sooner (same EMI)</option><option value="reduce_emi">Lower the EMI</option></Select></Field>
        </Tabs.Content>
        <Tabs.Content value="missed" className="grid gap-4 sm:grid-cols-3">
          <Field label="Days late"><Input inputMode="numeric" value={v.days} onChange={set('days')} /></Field>
          <Field label="Late fee" optional hint="Only if the terms don't state it"><Input prefix="₹" inputMode="numeric" value={v.lateFee} onChange={set('lateFee')} /></Field>
          <Field label="Penal interest % p.a." optional><Input inputMode="decimal" value={v.penal} onChange={set('penal')} /></Field>
        </Tabs.Content>
        <Tabs.Content value="rate" className="grid gap-4 sm:grid-cols-2">
          <Field label="New rate % p.a."><Input inputMode="decimal" value={v.rate} onChange={set('rate')} /></Field>
          <Field label="Keep constant"><Select value={v.hold} onChange={set('hold')}><option value="emi">EMI (tenure changes)</option><option value="tenure">Tenure (EMI changes)</option></Select></Field>
        </Tabs.Content>
        {err && <p role="alert" className="text-sm text-critical">{err}</p>}
        <Button type="submit" className="w-fit" loading={m.isPending}>Run scenario</Button>
      </form>
      {m.data && <div className="mt-5"><ScenarioTable r={m.data.result} /></div>}
    </Tabs.Root>
  )
}
