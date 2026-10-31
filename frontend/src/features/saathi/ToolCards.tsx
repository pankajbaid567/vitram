import { ArrowRight, CalendarClock, CreditCard, FileSearch, HeartPulse, Landmark, PhoneCall, ShieldCheck } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Money, SampleBadge, SourceLink, TrustMark } from '../../components/ui/data'
import { dayMonth, months, num, pct } from '../../lib/format'

function Shell({ icon, title, children, footer }: { icon: ReactNode; title: ReactNode; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="mt-2 overflow-hidden rounded-[var(--radius-card)] border border-[var(--glass-hairline)] bg-white text-sm shadow-[var(--glass-highlight),var(--elev-1)]">
      <div className="flex items-center gap-2 border-b border-[var(--glass-hairline)] px-3.5 py-2.5 font-medium">
        <span className="flex size-6 items-center justify-center rounded-lg bg-indigo-soft text-indigo" aria-hidden>{icon}</span>{title}
      </div>
      <div className="px-3.5 py-2.5">{children}</div>
      {footer && <div className="border-t border-[var(--glass-hairline)] bg-ink/[0.02] px-3.5 py-2">{footer}</div>}
    </div>
  )
}

function Row({ k, v }: { k: ReactNode; v: ReactNode }) {
  return <div className="flex items-baseline justify-between gap-3 py-1"><span className="text-muted">{k}</span><span className="num text-right font-medium">{v}</span></div>
}

function GoLink({ to, children }: { to: string; children: ReactNode }) {
  return <Link to={to} className="inline-flex min-h-8 items-center gap-1 font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">{children}<ArrowRight className="size-3.5" aria-hidden /></Link>
}

export function ToolCard({ card, onQuick }: { card: any; onQuick?: (t: string) => void }) {
  switch (card.type) {
    case 'loan_options': {
      const q = new URLSearchParams({ purpose: card.intent.purpose, amount: String(card.intent.amount), ...(card.intent.tenure_months ? { tenure: String(card.intent.tenure_months) } : {}) })
      return (
        <Shell icon={<Landmark className="size-4" />} title="Loan options" footer={<GoLink to={`/loans/results?${q}`}>See all options and compare</GoLink>}>
          <ul className="divide-y divide-line">
            {card.results.slice(0, 3).map((r: any) => (
              <li key={r.product_id} className="py-2">
                <div className="flex items-start justify-between gap-2">
                  <Link to={`/loans/p/${r.product_id}?${q}`} className="font-medium hover:text-indigo">{r.product_name}<span className="block text-xs font-normal text-muted">{r.lender}</span></Link>
                  <div className="text-right"><Money value={r.cost.monthly_emi} className="font-semibold" /><span className="block text-xs text-muted">a month · {months(r.tenure_months)}</span></div>
                </div>
                <p className="mt-1 text-xs text-muted">Total cost of credit <Money value={r.cost.total_cost_of_credit} /> incl. fees</p>
              </li>
            ))}
          </ul>
          <SampleBadge meta={card.results[0]?.catalogue} className="mt-1" />
        </Shell>
      )
    }
    case 'loan_cost': {
      const r = card.result
      return (
        <Shell icon={<Landmark className="size-4" />} title="Real cost if paid on time"
          footer={card.product_id ? <GoLink to={`/loans/p/${card.product_id}?amount=${r.principal}&tenure=${r.tenure_months}`}>Full breakdown</GoLink> : undefined}>
          <Row k="Borrowed" v={<Money value={r.principal} />} />
          <Row k="EMI" v={<Money value={r.monthly_emi} />} />
          <Row k="Interest" v={<Money value={r.scheduled_interest} />} />
          <Row k="Fees & GST" v={<Money value={r.upfront_charges_total} />} />
          <Row k={<b className="text-ink">Total you pay</b>} v={<Money value={r.scheduled_total_outflow} className="font-semibold" />} />
          {r.annualized_cost_pct != null && <Row k="Annualized cost (estimate)" v={pct(r.annualized_cost_pct)} />}
          {r.missing?.length > 0 && <p className="mt-1 text-xs text-caution">Not included: {r.missing.join('; ')}</p>}
        </Shell>
      )
    }
    case 'what_if':
    case 'emi_what_if': {
      const r = card.result
      if (!r.computable) {
        return (
          <Shell icon={<CalendarClock className="size-4" />} title="Scenario can't be calculated precisely">
            <ul className="list-disc pl-4 text-caution">{[...(r.missing ?? []), ...(r.notes ?? [])].map((m: string) => <li key={m}>{m}</li>)}</ul>
            {card.emi && <div className="mt-2"><GoLink to={`/emis/${card.emi.id}`}>Add the missing terms</GoLink></div>}
          </Shell>
        )
      }
      const b = r.baseline || {}, s = r.scenario || {}
      const keys: [string, string][] = r.kind.includes('payment')
        ? [['amount_due', 'Amount due'], ['extra_cost', 'Extra cost']]
        : [['monthly_emi', 'EMI'], ['total_interest', 'Total interest'], ['total_repayment', 'Total repayment']]
      return (
        <Shell icon={<CalendarClock className="size-4" />} title="What-if">
          <table className="w-full text-left">
            <thead><tr className="text-xs text-muted"><th className="py-1 font-normal"></th><th className="py-1 text-right font-normal">Now</th><th className="py-1 text-right font-normal">Scenario</th></tr></thead>
            <tbody>
              {keys.filter(([k]) => b[k] !== undefined || s[k] !== undefined).map(([k, label]) => (
                <tr key={k}><td className="py-1 text-muted">{label}</td><td className="py-1 text-right"><Money value={b[k]} /></td><td className="py-1 text-right font-medium"><Money value={s[k]} /></td></tr>
              ))}
              {s.interest_saved != null && <tr><td className="py-1 text-muted">Interest saved</td><td /><td className="py-1 text-right font-medium text-positive"><Money value={s.interest_saved} /></td></tr>}
              {s.prepayment_charge !== undefined && <tr><td className="py-1 text-muted">Prepayment charge</td><td /><td className="py-1 text-right"><Money value={s.prepayment_charge} /></td></tr>}
            </tbody>
          </table>
          {r.assumptions?.length > 0 && <p className="mt-1 text-xs text-muted">Assumes: {r.assumptions.join(' ')}</p>}
        </Shell>
      )
    }
    case 'loan_comparison':
      return (
        <Shell icon={<Landmark className="size-4" />} title="Comparison"
          footer={<GoLink to={`/loans/compare?ids=${card.result.products.map((p: any) => p.product_id).join(',')}&amount=${card.result.intent.amount}&purpose=${card.result.intent.purpose}${card.result.intent.tenure_months ? `&tenure=${card.result.intent.tenure_months}` : ''}`}>Open side-by-side</GoLink>}>
          {card.result.products.map((p: any) => (
            <Row key={p.product_id} k={p.product_name} v={<span><Money value={p.price.monthly_emi} />/mo · <Money value={p.price.scheduled_total_outflow} /></span>} />
          ))}
        </Shell>
      )
    case 'card_ranking': {
      const r = card.result
      return (
        <Shell icon={<CreditCard className="size-4" />} title={`Best card for ${num(r.purchase.amount) !== '—' ? '₹' + num(r.purchase.amount) : 'this purchase'}`}
          footer={<GoLink to={`/cards/optimize?amount=${r.purchase.amount}${r.purchase.category ? `&category=${r.purchase.category}` : ''}`}>Open optimizer</GoLink>}>
          <ol className="flex flex-col gap-1.5">
            {r.ranked.map((x: any, i: number) => (
              <li key={x.card_id} className="flex items-baseline justify-between gap-2">
                <span><span className="mr-1.5 text-muted">{i + 1}.</span>{x.card_name}</span>
                <span className="num text-right">{num(x.reward_units)} {x.unit_name} · <Money value={x.value_inr} className="font-medium" /></span>
              </li>
            ))}
            {r.unranked.map((x: any) => (
              <li key={x.card_id} className="flex items-baseline justify-between gap-2 text-muted">
                <span>{x.card_name}</span><span className="num">{x.reward_units != null ? `${num(x.reward_units)} ${x.unit_name}` : '—'} · value unknown</span>
              </li>
            ))}
          </ol>
          {r.ranked[0]?.caveats?.[0] && <p className="mt-1.5 text-xs text-caution">{r.ranked[0].caveats[0]}</p>}
        </Shell>
      )
    }
    case 'card_list':
      return (
        <Shell icon={<CreditCard className="size-4" />} title="Your cards" footer={<GoLink to="/cards">Open cards</GoLink>}>
          {card.cards.map((c: any) => <Row key={c.id} k={c.nickname} v={c.points?.balance != null ? `${num(c.points.balance)} ${c.reward_unit ?? 'points'}` : '—'} />)}
        </Shell>
      )
    case 'emi_list':
      return (
        <Shell icon={<CalendarClock className="size-4" />} title="Your EMIs" footer={<GoLink to="/emis">Open EMI calendar</GoLink>}>
          {card.emis.map((e: any) => (
            <div key={e.id} className="flex items-baseline justify-between gap-2 py-1">
              <span className="flex items-center gap-1.5">{e.title}{!e.confirmed && <TrustMark state="extracted" />}</span>
              <span className="num text-right"><Money value={e.amount} /> · {dayMonth(e.next_due)}</span>
            </div>
          ))}
        </Shell>
      )
    case 'insurance_options':
      return (
        <Shell icon={<ShieldCheck className="size-4" />} title="Plans that may fit" footer={<GoLink to={`/insurance/explore?type=${card.result.intent.type}`}>Explore and compare</GoLink>}>
          {card.result.results.slice(0, 3).map((r: any) => (
            <Row key={r.product_id} k={<span>{r.product_name}<span className="block text-xs text-muted">{r.insurer}</span></span>}
              v={r.indicative_premium?.amount ? <span><Money value={r.indicative_premium.amount} />/yr</span> : <span className="text-muted">Premium n/a</span>} />
          ))}
          <SampleBadge meta={card.result.results[0]?.catalogue} className="mt-1" />
        </Shell>
      )
    case 'insurance_comparison':
      return (
        <Shell icon={<ShieldCheck className="size-4" />} title="Comparison" footer={<GoLink to="/insurance/compare">Open comparison</GoLink>}>
          {card.result.columns.map((c: any) => <Row key={c.id} k={c.product_name} v={c.cost?.amount ? <Money value={c.cost.amount} /> : '—'} />)}
        </Shell>
      )
    case 'emergency': {
      const r = card.result
      const first = r.policies.find((p: any) => p.status === 'may_apply')
      return (
        <Shell icon={<HeartPulse className="size-4" />} title={`${r.event.label} · ${r.person.name}`}
          footer={<GoLink to={`/insurance/emergency?member=${r.person.key}&event=${r.event.key}`}>Open emergency checklist</GoLink>}>
          {r.policies.length === 0 && <p className="text-muted">No uploaded policy covers {r.person.name}.</p>}
          {r.policies.map((p: any) => (
            <div key={p.policy.id} className="flex items-baseline justify-between gap-2 py-1">
              <span>{p.policy.product_name}</span>
              <span className={p.status === 'may_apply' ? 'font-medium text-positive' : 'text-muted'}>{p.status === 'may_apply' ? 'May apply' : p.status === 'not_applicable' ? 'Not for this' : 'Check'}</span>
            </div>
          ))}
          {first?.claim?.intimation && (
            <p className="mt-1">Inform insurer within <b>{first.claim.intimation.value}</b> <SourceLink citation={first.claim.intimation.citation} /></p>
          )}
          <p className="mt-1.5 text-xs text-muted">{r.disclaimer}</p>
        </Shell>
      )
    }
    case 'policy_summary':
      return (
        <Shell icon={<ShieldCheck className="size-4" />} title={card.policy.product_name ?? 'Policy'} footer={<GoLink to={`/insurance/policies/${card.policy.id}`}>Open policy summary</GoLink>}>
          <Row k="Sum insured" v={<Money value={card.policy.coverage?.sum_insured} />} />
          <Row k="Premium" v={<Money value={card.policy.premium?.amount} />} />
        </Shell>
      )
    case 'document_summary': {
      const doc = card.document
      const to = doc.type === 'receipt' ? `/documents/receipts/${doc.id}` : doc.type === 'loan_document' ? `/loans/documents/${doc.id}` : `/documents?focus=${doc.id}`
      const show = (f: any) => Array.isArray(f.value) ? `${f.value.length} lines` : f.unit === 'INR' && typeof f.value === 'number' ? <Money value={f.value} paise={!Number.isInteger(f.value)} /> : String(f.value)
      return (
        <Shell icon={<FileSearch className="size-4" />} title={doc.name} footer={<GoLink to={to}>Check and correct these values</GoLink>}>
          {doc.read_from_scan && <p className="mb-1 text-xs text-muted">Read from a scan or photo — check each value.</p>}
          {card.facts.length === 0 ? <p className="text-muted">No values found.</p> : card.facts.slice(0, 8).map((f: any) => (
            <div key={f.id} className="flex items-baseline justify-between gap-3 py-1">
              <span className="text-muted">{f.label}</span>
              <span className="flex items-center gap-1.5 text-right font-medium"><span className="num">{show(f)}</span><TrustMark state={f.state === 'extracted' && doc.read_from_scan ? 'scan' : f.state} /></span>
            </div>
          ))}
          {card.warnings?.length > 0 && <p className="mt-1 text-xs text-caution">{card.warnings[0]}</p>}
        </Shell>
      )
    }
    case 'doc_search':
      return (
        <Shell icon={<FileSearch className="size-4" />} title={card.found ? 'From your document' : 'Not found in your documents'}>
          {!card.found && <p className="text-muted">VITTRM didn't find this, so it won't guess.</p>}
          {card.results.slice(0, 2).map((r: any, i: number) => (
            <div key={i} className="py-1">
              <p className="line-clamp-3 border-l-2 border-indigo/50 pl-2 text-ink/90">{r.citation.snippet}</p>
              <SourceLink citation={r.citation} label={r.citation.document_name ?? 'Source'} />
            </div>
          ))}
        </Shell>
      )
    case 'consultation_draft': {
      const q = new URLSearchParams({ topic: card.topic ?? '', ...(card.policy_id ? { policy: card.policy_id } : {}), ...(card.member_key ? { member: card.member_key } : {}), ...(card.product_id ? { product: card.product_id } : {}) })
      return (
        <Shell icon={<PhoneCall className="size-4" />} title="Consultation request (not sent)" footer={<GoLink to={`/insurance/consult?${q}`}>Review and confirm the call</GoLink>}>
          <pre className="whitespace-pre-wrap font-sans text-xs text-muted">{card.summary}</pre>
        </Shell>
      )
    }
    case 'navigation':
      return (
        <div className="mt-2">
          <Link to={card.route} className="inline-flex min-h-10 items-center gap-1.5 rounded-[var(--radius-control)] border border-line-strong bg-surface px-3 text-sm font-medium hover:border-indigo hover:text-indigo">
            {card.label}<ArrowRight className="size-4" aria-hidden />
          </Link>
          {card.note && <p className="mt-1 text-xs text-muted">{card.note}</p>}
        </div>
      )
    case 'quick_replies':
    case 'choose': {
      const opts: { label: string }[] = (card.options ?? []).map((o: any) => (typeof o === 'string' ? { label: o } : o))
      return (
        <div className="mt-2 flex flex-wrap gap-2">
          {opts.map((o) => (
            <button key={o.label} type="button" onClick={() => onQuick?.(o.label)}
              className="min-h-9 rounded-full border border-line-strong bg-surface px-3 text-sm hover:border-indigo hover:text-indigo">{o.label}</button>
          ))}
        </div>
      )
    }
    case 'profile_summary':
      return null
    default:
      return null
  }
}
