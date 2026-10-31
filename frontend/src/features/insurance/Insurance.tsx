import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { AlertTriangle, ArrowRight, BookOpen, Check, CirclePlus, FileText, HeartPulse, Lightbulb, Lock, MessageCircle, Phone, PhoneCall, Plane, ShieldAlert, ShieldCheck, Umbrella, Upload, Users } from 'lucide-react'
import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Button, LinkButton } from '../../components/ui/button'
import { Badge, FeatureTile, IconTile, KeyValue, Money, PageHeader, PageHero, Panel, SampleBadge, SourceLink, TrustMark } from '../../components/ui/data'
import { ShieldArt } from '../../components/illustrations'
import { Checkbox, Field, Input, Select, Textarea } from '../../components/ui/field'
import { Callout, EmptyState, errorMessage, ErrorState, PageSkeleton, useToast } from '../../components/ui/feedback'
import { FileDrop } from '../../components/ui/filedrop'
import { ApiError, get, patch, post, put, upload } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { acceptFor, useVision } from '../../lib/vision'
import { DuplicateNotice } from '../documents/DuplicateNotice'
import { isDuplicate } from '../documents/duplicates'
import { compactInr, date, relDays } from '../../lib/format'
import type { DocFact, DocumentRow } from '../../lib/types'
import { ConsentGate, DOC_CONSENT_BODY, ProcessingSteps, useDocumentPoll } from '../onboarding/Onboarding'
import { useSaathi, useSaathiPage } from '../saathi/context'

const TYPE_LABEL: Record<string, string> = { health: 'Health', term_life: 'Term life', traditional_life: 'Traditional life', travel: 'Travel', other: 'Other' }
const REL: Record<string, string> = { self: 'You', spouse: 'Spouse', child: 'Child', mother: 'Mother', father: 'Father', mother_in_law: 'Mother-in-law', father_in_law: 'Father-in-law', sibling: 'Sibling', other_dependant: 'Dependant' }

function useFamily() {
  return useQuery({ queryKey: ['family'], queryFn: () => get<any>('/family') })
}
function people(f: any) {
  if (!f) return []
  return [{ key: 'self', name: 'You', relation: 'self' }, ...f.members.map((m: any) => ({ key: m.id, name: m.name, relation: m.relation, age: m.age }))]
}

/* --- S40 Insurance home -------------------------------------------------- */

const TYPE_ICON: Record<string, ReactNode> = {
  health: <HeartPulse className="size-5" />, term_life: <Umbrella className="size-5" />, traditional_life: <Umbrella className="size-5" />,
  travel: <Plane className="size-5" />,
}

export function InsuranceHome() {
  useSaathiPage('insurance')
  const { ask } = useSaathi()
  const q = useQuery({ queryKey: ['ins-overview'], queryFn: () => get<any>('/insurance/overview'), refetchInterval: (q) => (q.state.data?.processing?.some((d: any) => d.status !== 'failed') ? 2000 : false) })
  if (q.isLoading) return <PageSkeleton />
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const d = q.data
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Insurance' }]} title="Insurance" description="What you're covered for, who's covered, and what to do when you need to use it."
        actions={<><LinkButton to="/insurance/emergency" variant="danger" size="lg" icon={<HeartPulse className="size-4" />}>Emergency help</LinkButton><LinkButton to="/insurance/upload" size="lg" icon={<CirclePlus className="size-4" />}>Add a policy</LinkButton></>} />
      {d.processing.map((p: DocumentRow) => (
        <Callout key={p.id} tone={p.status === 'failed' ? 'critical' : 'info'} className="mb-4" title={p.status === 'failed' ? `Couldn't read ${p.display_name}` : `Reading ${p.display_name}…`}>{p.error_message}</Callout>
      ))}
      {d.policy_count === 0 ? (
        <div className="flex flex-col gap-6">
          <PageHero pill={<><ShieldCheck />No policies yet</>} title="Add your first policy" art={<ShieldArt className="w-72" />}
            body="Upload a policy schedule or wording. VITTRM turns it into a clear summary of coverage, exclusions, waiting periods and claim steps — with page references."
            actions={<LinkButton to="/insurance/upload" size="lg" icon={<Upload className="size-4" />}>Upload a policy</LinkButton>}
            note={<><Lock />Your documents are encrypted in your workspace.</>} />
          <ul className="grid gap-5 @xl:grid-cols-2 @5xl:grid-cols-4" aria-label="What you get">
            {INSURANCE_FEATURES.map((f) => <li key={f.title}><FeatureTile icon={f.icon} tone={f.tone} title={f.title} body={f.body} /></li>)}
          </ul>
          <InsuranceHelpCards />
        </div>
      ) : (
        <div className="grid items-start gap-6 @4xl:grid-cols-[1.4fr_1fr]">
          <div className="flex flex-col gap-6">
            {d.policies_by_type.map((g: any) => (
              <section key={g.type} aria-labelledby={`t-${g.type}`}>
                <h2 id={`t-${g.type}`} className="mb-3 text-[1.05rem] font-semibold">{g.label}</h2>
                <div className="flex flex-col gap-3">
                  {g.policies.map((p: any) => (
                    <Link key={p.id} to={`/insurance/policies/${p.id}`} className="surface-card lift flex flex-wrap items-center gap-x-4 gap-y-2 rounded-[var(--radius-card)] p-4">
                      <span className="flex size-11 shrink-0 items-center justify-center rounded-[14px] bg-indigo-soft text-indigo" aria-hidden>{TYPE_ICON[g.type] ?? <ShieldCheck className="size-5" />}</span>
                      <div className="min-w-0 flex-1 basis-48">
                        <p className="flex flex-wrap items-center gap-2 font-semibold">{p.product_name ?? 'Policy'}{p.status === 'needs_review' && <Badge tone="caution">Review</Badge>}</p>
                        <p className="text-sm text-muted">{p.insurer} · covers {p.members.map((m: any) => (m.key === 'self' || !m.key ? 'you' : m.name)).join(', ') || 'not set'}</p>
                      </div>
                      <div className="ml-auto text-right text-sm">
                        <p className="num text-lg font-semibold tracking-[-0.01em]">{compactInr(p.coverage?.sum_insured)}</p>
                        <p className="text-muted">{p.end_date ? `renews ${date(p.end_date)}` : 'end date unknown'}</p>
                      </div>
                    </Link>
                  ))}
                </div>
              </section>
            ))}
          </div>
          <div className="flex flex-col gap-6">
            <Panel className="p-5">
              <h2 className="font-semibold">Family coverage</h2>
              <ul className="mt-2 divide-y divide-[var(--glass-hairline)]">
                {d.family_coverage.map((m: any) => (
                  <li key={m.key} className="flex gap-3 py-3">
                    <span className={clsx('flex size-9 shrink-0 items-center justify-center rounded-full text-sm font-semibold', m.health_cover ? 'bg-indigo-soft text-indigo-dark' : 'bg-caution-soft text-caution')} aria-hidden>{(m.key === 'self' ? 'You' : m.name ?? '?')[0]}</span>
                    <div className="min-w-0 flex-1">
                      <p className="flex justify-between gap-2 text-[0.95rem]"><span className="font-medium">{m.key === 'self' ? 'You' : m.name}</span>
                        <span className="num">{m.health_cover ? `${compactInr(m.health_cover)} health` : <span className="text-caution">No health cover</span>}</span></p>
                      <p className="text-sm text-muted">{m.policies.length ? m.policies.map((p: any) => p.name).join(', ') : 'No uploaded policy'}{m.life_cover ? ` · ${compactInr(m.life_cover)} life` : ''}</p>
                    </div>
                  </li>
                ))}
              </ul>
              <Link to="/family" className="mt-2 inline-block text-sm font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">Manage family</Link>
            </Panel>
            <Panel className="p-5">
              <h2 className="font-semibold">Premiums & renewals</h2>
              <p className="mt-1 text-[0.95rem]">About <Money value={d.annual_premium_total} className="font-semibold" /> a year{d.unknown_premiums > 0 && ` (${d.unknown_premiums} premium${d.unknown_premiums > 1 ? 's' : ''} unknown)`}</p>
              {d.upcoming_renewals.map((r: any) => <p key={r.id} className="mt-1 text-sm text-caution">{r.product_name} renews {relDays(r.end_date)}</p>)}
            </Panel>
            <Panel className="flex flex-col gap-3 p-5">
              <h2 className="font-semibold">Explore & get advice</h2>
              <LinkButton to="/insurance/explore" variant="secondary">Explore plans</LinkButton>
              <LinkButton to="/insurance/consult" variant="secondary" icon={<PhoneCall className="size-4" />}>Request a consultation call</LinkButton>
              <Button variant="quiet" icon={<MessageCircle className="size-4" />} onClick={() => ask('What documents do I need for a claim?')}>Ask Vitt Saathi</Button>
            </Panel>
          </div>
        </div>
      )}
      {d.policy_count > 0 && <div className="mt-7"><InsuranceHelpCards /></div>}
    </>
  )
}

const INSURANCE_FEATURES: { icon: ReactNode; tone: 'indigo' | 'green' | 'amber' | 'sky'; title: string; body: string }[] = [
  { icon: <FileText />, tone: 'indigo', title: 'Coverage summary', body: "What's covered and what's not" },
  { icon: <Users />, tone: 'green', title: "Who's covered", body: 'Family members and dependants' },
  { icon: <ShieldAlert />, tone: 'amber', title: 'Claim steps', body: 'What to do when you need to claim' },
  { icon: <BookOpen />, tone: 'sky', title: 'Page references', body: 'Where each detail was found' },
]

function InsuranceHelpCards() {
  const { ask } = useSaathi()
  return (
    <div className="grid gap-5 @3xl:grid-cols-2">
      <section className="wash-amber flex items-start gap-4 rounded-[var(--radius-panel)] p-5 sm:p-6" aria-labelledby="ins-help">
        <IconTile tone="amber" size="lg"><Lightbulb /></IconTile>
        <div className="min-w-0">
          <h2 id="ins-help" className="font-semibold">Need help understanding your policy?</h2>
          <p className="mt-1 text-[0.95rem] text-ink/75">Ask Vitt Saathi to explain your coverage, exclusions or claim process in simple terms.</p>
          <button type="button" onClick={() => ask('Explain what my health policy covers and what it excludes')}
            className="mt-2 inline-flex min-h-10 items-center gap-1 font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">Ask a question<ArrowRight className="size-4" aria-hidden /></button>
        </div>
      </section>
      <section className="wash-danger flex items-start gap-4 rounded-[var(--radius-panel)] p-5 sm:p-6" aria-labelledby="ins-emg">
        <IconTile tone="red" size="lg"><ShieldAlert /></IconTile>
        <div className="min-w-0">
          <h2 id="ins-emg" className="font-semibold">In an emergency?</h2>
          <p className="mt-1 text-[0.95rem] text-ink/75">Get quick guidance on which policy applies, what to carry and who to contact.</p>
          <Link to="/insurance/emergency" className="mt-2 inline-flex min-h-10 items-center gap-1 font-medium text-critical underline decoration-critical/40 underline-offset-2 hover:decoration-critical">Get emergency help<ArrowRight className="size-4" aria-hidden /></Link>
        </div>
      </section>
    </div>
  )
}

/* --- S41 Policy upload --------------------------------------------------- */

export function PolicyUpload() {
  useSaathiPage('insurance')
  const navigate = useNavigate()
  const fam = useFamily()
  const vision = useVision()
  const [dup, setDup] = useState<ApiError | null>(null)
  const [progress, setProgress] = useState<number | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [who, setWho] = useState<string[]>([])
  const [later, setLater] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [docId, setDocId] = useState<string | null>(null)
  const poll = useDocumentPoll(docId ?? undefined)
  const m = useMutation({
    mutationFn: () => {
      const fd = new FormData()
      fd.append('file', file!)
      fd.append('type', 'insurance_policy')
      if (!later && who.length) fd.append('member_ids', JSON.stringify(who))
      return upload<DocumentRow>('/documents', fd, setProgress)
    },
    onSuccess: (d) => setDocId(d.id),
    onError: (e) => { if (isDuplicate(e)) { setDup(e as ApiError); setErr(null) } else setErr(errorMessage(e)) },
    onSettled: () => setProgress(null),
  })
  useEffect(() => {
    if (poll.data?.policy_id && ['ready', 'needs_review'].includes(poll.data.status)) navigate(`/insurance/policies/${poll.data.policy_id}`)
  }, [poll.data, navigate])
  const ps = people(fam.data)
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Insurance', to: '/insurance' }]} title="Add an existing policy" description="Upload the policy schedule, bond or wording — a PDF, or clear photos of the pages." />
      <div className="max-w-2xl">
        {poll.data ? (
          <Panel className="p-5">
            <ProcessingSteps doc={poll.data} />
            {poll.data.status === 'failed' && <><Callout tone="critical" className="mt-4">{poll.data.error_message}</Callout><Button className="mt-4" variant="secondary" onClick={() => { setDocId(null); setFile(null) }}>Upload a different file</Button></>}
          </Panel>
        ) : (
          <ConsentGate purpose="financial_documents" title="Before you upload" body={DOC_CONSENT_BODY}>
            <Panel className="flex flex-col gap-5 p-5">
              <fieldset>
                <legend className="mb-2 text-sm font-medium">Who does this policy cover?</legend>
                <div className="flex flex-col gap-2">
                  {ps.map((p) => (
                    <Checkbox key={p.key} disabled={later} checked={who.includes(p.key)} onChange={(e) => setWho(e.target.checked ? [...who, p.key] : who.filter((x) => x !== p.key))}
                      label={p.key === 'self' ? 'You' : `${p.name} (${REL[p.relation] ?? p.relation})`} />
                  ))}
                  <Checkbox checked={later} onChange={(e) => setLater(e.target.checked)} label="I'll confirm after VITTRM reads the policy" />
                </div>
                <Link to="/family" className="mt-2 inline-block text-sm font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">Add a family member</Link>
              </fieldset>
              {dup && <DuplicateNotice expectedType="insurance_policy" error={dup} onReread={(d) => { setDup(null); setDocId(d.id) }} />}
              <FileDrop accept={acceptFor('insurance_policy', vision)} file={file} onFile={(f) => { setFile(f); setDup(null) }} error={err} camera={vision?.configured} progress={progress} scanNote={vision?.configured ? (vision.on_device ? 'Photos and scans are read on this device' : 'Photos and scans are read by Gemini') : undefined}
                hint={vision?.configured ? 'PDF or photo · up to 15 MB' : 'PDF · up to 15 MB. Photos and scans need OCR, which isn’t set up on this server.'} />
              <div className="flex flex-wrap items-center gap-3">
                <Button size="lg" disabled={!file || (!later && !who.length)} loading={m.isPending} onClick={() => { setErr(null); m.mutate() }}>Analyse policy</Button>
                <a href="/api/demo/fixtures/sample_policy_family_health.pdf" className="text-sm font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">Download a sample policy</a>
              </div>
            </Panel>
          </ConsentGate>
        )}
      </div>
    </>
  )
}

/* --- S42 Policy summary -------------------------------------------------- */

function FactValue({ f }: { f: DocFact }) {
  if (Array.isArray(f.value)) {
    if (f.key === 'insured_members') return <span>{f.value.map((m: any) => `${m.name} (${m.relation}${m.age ? `, ${m.age}` : ''})`).join('; ')}</span>
    return <ul className="list-disc pl-5 text-left">{f.value.map((v: string, i: number) => <li key={i}>{v}</li>)}</ul>
  }
  if (f.unit === 'INR') return <Money value={f.value} className="font-medium" />
  if (f.unit === '%') return <span className="font-medium">{f.value}%</span>
  if (/date/.test(f.key) && typeof f.value === 'string') return <span className="font-medium">{date(f.value)}</span>
  if (f.key === 'policy_type') return <span className="font-medium">{TYPE_LABEL[f.value] ?? f.value}</span>
  return <span className="font-medium">{String(f.value)}</span>
}

function FactRow({ f, docId }: { f: DocFact; docId: string }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [edit, setEdit] = useState(false)
  const [val, setVal] = useState(Array.isArray(f.value) ? f.value.join('\n') : String(f.value))
  const save = useMutation({
    mutationFn: (b: any) => patch(`/documents/${docId}/facts/${f.id}`, b),
    onSuccess: () => { qc.invalidateQueries(); setEdit(false); toast({ title: 'Saved', tone: 'positive' }) },
    onError: (e) => toast({ title: errorMessage(e), tone: 'critical' }),
  })
  const list = Array.isArray(f.value)
  return (
    <div className="flex flex-col gap-1.5 py-3 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
        <dt className="text-[0.95rem] text-muted sm:w-52 sm:shrink-0">{f.label}</dt>
        <dd className="flex min-w-0 flex-1 flex-col gap-1.5 sm:items-end sm:text-right">
          {edit ? (
            <form className="flex w-full flex-col gap-2" onSubmit={(e) => { e.preventDefault(); save.mutate({ value: list ? val.split('\n').map((s) => s.trim()).filter(Boolean) : val }) }}>
              {list ? <Textarea value={val} onChange={(e) => setVal(e.target.value)} aria-label={f.label} /> : <Input value={val} onChange={(e) => setVal(e.target.value)} aria-label={f.label} />}
              <div className="flex gap-2 sm:justify-end"><Button size="sm" type="submit" loading={save.isPending}>Save</Button><Button size="sm" variant="quiet" onClick={() => setEdit(false)}>Cancel</Button></div>
            </form>
          ) : <FactValue f={f} />}
          <div className="flex flex-wrap items-center gap-1.5 sm:justify-end">
            <TrustMark state={f.state} />
            <SourceLink citation={f.citation} />
            {!edit && <button type="button" className="min-h-6 px-1 text-xs font-medium text-muted hover:text-indigo" onClick={() => setEdit(true)}>Correct</button>}
            {!edit && f.state === 'extracted' && <button type="button" className="min-h-6 px-1 text-xs font-medium text-muted hover:text-positive" onClick={() => save.mutate({ confirm_only: true })}>Looks right</button>}
          </div>
        </dd>
    </div>
  )
}

const GROUPS: [string, string][] = [['identity', 'Policy'], ['people', 'People'], ['financials', 'Cover & cost'], ['coverage', 'What\'s covered'], ['restrictions', 'Limits & exclusions'], ['claims', 'Claims']]

export function PolicySummary() {
  const { id } = useParams()
  useSaathiPage('insurance', id)
  const { ask } = useSaathi()
  const qc = useQueryClient()
  const toast = useToast()
  const q = useQuery({ queryKey: ['policy', id], queryFn: () => get<any>(`/insurance/policies/${id}`) })
  const [members, setMembers] = useState<string[] | null>(null)
  const setM = useMutation({ mutationFn: (keys: string[]) => put(`/insurance/policies/${id}/members`, { member_keys: keys }), onSuccess: () => { qc.invalidateQueries(); setMembers(null); toast({ title: 'Covered people saved', tone: 'positive' }) } })
  const confirm = useMutation({ mutationFn: () => post(`/insurance/policies/${id}/confirm`), onSuccess: () => { qc.invalidateQueries(); toast({ title: 'Policy summary confirmed', tone: 'positive' }) }, onError: (e) => toast({ title: errorMessage(e), tone: 'critical' }) })
  if (q.isLoading) return <PageSkeleton />
  if (q.isError) return <ErrorState error={q.error} />
  const d = q.data
  const p = d.policy
  const current = members ?? p.members.map((m: any) => m.key ?? 'self')
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Insurance', to: '/insurance' }]} title={p.product_name ?? 'Policy summary'}
        description={<span>{p.insurer}{p.policy_ref_masked && ` · ${p.policy_ref_masked}`} · read from {d.document?.display_name}</span>}
        actions={<>
          <Button variant="secondary" icon={<MessageCircle className="size-4" />} onClick={() => ask('What is not covered in this policy?')}>Ask about this policy</Button>
          <LinkButton to={`/insurance/consult?policy=${p.id}`} variant="secondary" icon={<Phone className="size-4" />}>Consult</LinkButton>
        </>} />
      {p.status === 'needs_review' && (
        <Callout tone="saathi" className="mb-6" title="Check this summary"
          action={<Button size="sm" onClick={() => confirm.mutate()} loading={confirm.isPending} disabled={!p.members_confirmed}>{p.members_confirmed ? 'Confirm summary' : 'Confirm who is covered first'}</Button>}>
          VITTRM read these values automatically. Correct anything that doesn't match the document, then confirm.
        </Callout>
      )}
      {d.document?.warnings?.map((w: string) => <Callout key={w} tone="caution" className="mb-4">{w}</Callout>)}
      {d.conflicts.length > 0 && <Callout tone="caution" className="mb-6" title="Another version of this policy disagrees">{d.conflicts.map((c: any) => c.label).join(', ')} differ between uploaded versions. Check which document is current.</Callout>}
      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <div className="flex flex-col gap-6">
          {GROUPS.filter(([g]) => d.facts[g]?.length).map(([g, label]) => (
            <Panel key={g} className="px-5 pt-4">
              <h2 className="font-semibold">{label}</h2>
              <dl className="divide-y divide-line">{d.facts[g].map((f: DocFact) => <FactRow key={f.id} f={f} docId={p.document_id} />)}</dl>
            </Panel>
          ))}
        </div>
        <div className="flex flex-col gap-6">
          <Panel className="p-5">
            <h2 className="font-semibold">Who's covered</h2>
            <p className="mb-3 mt-0.5 text-sm text-muted">{p.members_confirmed ? 'Confirmed by you.' : 'Matched from the policy — please confirm.'}</p>
            <div className="flex flex-col gap-2">
              {d.family_options.map((m: any) => (
                <Checkbox key={m.key} checked={current.includes(m.key)} onChange={(e) => setMembers(e.target.checked ? [...current, m.key] : current.filter((x: string) => x !== m.key))}
                  label={m.key === 'self' ? 'You' : `${m.name} (${REL[m.relation] ?? m.relation})`} />
              ))}
            </div>
            {(members || !p.members_confirmed) && <Button size="sm" className="mt-3" disabled={!current.length} loading={setM.isPending} onClick={() => setM.mutate(current)}>Save covered people</Button>}
          </Panel>
          {d.waiting_status.length > 0 && (
            <Panel className="p-5">
              <h2 className="font-semibold">Waiting periods</h2>
              <ul className="mt-2 flex flex-col gap-2 text-[0.95rem]">
                {d.waiting_status.map((w: any) => (
                  <li key={w.label}>{w.label}: {w.running ? <span className="text-caution">running until {date(w.ends_on)}</span> : <span className="text-positive">completed {date(w.ends_on)}</span>} <SourceLink citation={w.citation} /></li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-muted">Calculated from the policy start date in the document. Earlier continuous cover may shorten these — confirm with the insurer.</p>
            </Panel>
          )}
          <Panel className="p-5">
            <h2 className="font-semibold">In an emergency</h2>
            <p className="mb-3 mt-0.5 text-sm text-muted">See claim steps, documents and contacts for the person who needs care.</p>
            <LinkButton to="/insurance/emergency" variant="danger" size="sm" icon={<HeartPulse className="size-4" />}>Emergency help</LinkButton>
          </Panel>
          <p className="text-xs text-muted">{d.disclaimer}</p>
        </div>
      </div>
    </>
  )
}

/* --- S43/S44 Explore ---------------------------------------------------- */

export function InsuranceExplore() {
  useSaathiPage('insurance')
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const fam = useFamily()
  const [type, setType] = useState(params.get('type') ?? 'health')
  const [who, setWho] = useState<string[]>(['self'])
  const [si, setSi] = useState('')
  const [budget, setBudget] = useState('')
  const [sel, setSel] = useState<string[]>([])
  const m = useMutation({ mutationFn: (b: any) => post<any>('/insurance/recommend', b) })
  const ps = people(fam.data)
  function run(e?: FormEvent) {
    e?.preventDefault()
    setSel([])
    m.mutate({ type, member_keys: who, sum_insured: si ? Number(si) : null, budget_annual: budget ? Number(budget.replace(/\D/g, '')) : null })
  }
  const r = m.data
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Insurance', to: '/insurance' }]} title="Explore insurance" description="Plans are matched to the people you choose and the cover they already have. Premiums are indicative from a sample catalogue." />
      <Panel className="mb-6 p-5">
        <form onSubmit={run} className="grid gap-4 md:grid-cols-4" noValidate>
          <Field label="Type of cover"><Select value={type} onChange={(e) => setType(e.target.value)}><option value="health">Health</option><option value="term_life">Term life</option><option value="traditional_life">Traditional life (endowment, LIC-style)</option><option value="travel">Travel</option></Select></Field>
          <fieldset className="md:col-span-2">
            <legend className="mb-1.5 text-sm font-medium">For</legend>
            <div className="flex flex-wrap gap-x-4 gap-y-2">{ps.map((p) => <Checkbox key={p.key} checked={who.includes(p.key)} onChange={(e) => setWho(e.target.checked ? [...who, p.key] : who.filter((x) => x !== p.key))} label={p.key === 'self' ? 'You' : p.name} />)}</div>
          </fieldset>
          <Field label="Cover amount" optional><Select value={si} onChange={(e) => setSi(e.target.value)}><option value="">Any</option>{[300000, 500000, 1000000, 2500000, 5000000, 10000000, 20000000].map((v) => <option key={v} value={v}>{compactInr(v)}</option>)}</Select></Field>
          <Field label="Yearly budget" optional><Input prefix="₹" inputMode="numeric" value={budget} onChange={(e) => setBudget(e.target.value)} /></Field>
          <div className="flex items-end md:col-span-3"><Button type="submit" loading={m.isPending} disabled={!who.length}>Find plans</Button></div>
        </form>
      </Panel>
      {m.isError && <ErrorState error={m.error} onRetry={() => run()} />}
      {r && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-3"><SampleBadge meta={r.results[0]?.catalogue} /><span className="text-sm text-muted">Fictional insurers. Not a quote or advice to buy.</span></div>
          {r.missing_data.map((x: any) => <Callout key={x.key} tone="caution" className="mb-3">{x.message}</Callout>)}
          {r.results.length === 0 && <EmptyState title="No plans fit these people" body={r.excluded.map((e: any) => `${e.product_name}: ${e.reasons.join('; ')}`).join(' · ')} />}
          <ul className="flex flex-col gap-4">
            {r.results.map((x: any, i: number) => (
              <li key={x.product_id}>
                <Panel className="flex flex-col gap-4 p-5 lg:flex-row">
                  <div className="min-w-0 flex-1">
                    {i === 0 && <Badge tone="indigo" className="mb-2">May fit best</Badge>}
                    <h2 className="text-lg font-semibold">{x.product_name}</h2>
                    <p className="text-sm text-muted">{x.insurer} · {x.variant?.replaceAll('_', ' ')}</p>
                    <ul className="mt-3 flex flex-col gap-1 text-[0.95rem]">{x.why.map((w: string) => <li key={w} className="flex gap-2"><Check className="mt-1 size-4 shrink-0 text-positive" aria-hidden />{w}</li>)}</ul>
                    {x.cautions.length > 0 && <ul className="mt-2 list-disc pl-5 text-[0.95rem] text-ink/80">{x.cautions.map((w: string) => <li key={w}>{w}</li>)}</ul>}
                    {x.coverage?.benefits && <p className="mt-2 text-sm text-muted">Includes: {x.coverage.benefits.slice(0, 5).join(', ')}</p>}
                  </div>
                  <div className="flex shrink-0 flex-col gap-2 lg:w-56 lg:border-l lg:border-line lg:pl-5">
                    <p className="text-sm text-muted">Indicative premium</p>
                    {x.indicative_premium.amount ? <p className="num text-2xl font-semibold"><Money value={x.indicative_premium.amount} /><span className="text-sm font-normal text-muted"> /{x.indicative_premium.frequency === 'annual' ? 'year' : 'trip'}</span></p>
                      : <p className="text-sm text-caution">{x.indicative_premium.reason}</p>}
                    {x.indicative_premium.sum_insured && <p className="text-sm">for {compactInr(x.indicative_premium.sum_insured)} cover</p>}
                    <Checkbox checked={sel.includes(x.product_id)} onChange={() => setSel((s) => (s.includes(x.product_id) ? s.filter((y) => y !== x.product_id) : [...s, x.product_id].slice(0, 4)))} label="Compare" />
                    <LinkButton to={`/insurance/consult?product=${x.product_id}&topic=${encodeURIComponent('Is ' + x.product_name + ' right for us?')}`} variant="ghost" size="sm">Talk to a consultant</LinkButton>
                  </div>
                </Panel>
              </li>
            ))}
          </ul>
          {r.excluded.length > 0 && r.results.length > 0 && (
            <details className="mt-4"><summary className="font-medium">{r.excluded.length} plans don't fit</summary>
              <ul className="mt-2 text-[0.95rem] text-muted">{r.excluded.map((e: any) => <li key={e.product_id}>{e.product_name}: {e.reasons.join('; ')}</li>)}</ul></details>
          )}
          {sel.length > 0 && (
            <div className="sticky bottom-20 z-20 mt-6 flex items-center justify-between gap-3 rounded-[var(--radius-panel)] bg-ink px-5 py-3 text-white shadow-lg lg:bottom-4">
              <span>{sel.length} selected</span>
              <Button variant="saathi" onClick={() => navigate(`/insurance/compare?products=${sel.join(',')}&members=${who.join(',')}`)}>Compare{sel.length === 1 ? ' with my policies' : ''}</Button>
            </div>
          )}
        </>
      )}
    </>
  )
}

/* --- S45 Compare --------------------------------------------------------- */

export function InsuranceCompare() {
  useSaathiPage('insurance')
  const [params] = useSearchParams()
  const pols = useQuery({ queryKey: ['policies'], queryFn: () => get<any[]>('/insurance/policies') })
  const products = (params.get('products') ?? '').split(',').filter(Boolean)
  const memberKeys = (params.get('members') ?? 'self').split(',').filter(Boolean)
  const [policyIds, setPolicyIds] = useState<string[]>([])
  const enabled = products.length + policyIds.length >= 2
  const q = useQuery({ queryKey: ['ins-cmp', products, policyIds, memberKeys], queryFn: () => post<any>('/insurance/compare', { product_ids: products, policy_ids: policyIds, member_keys: memberKeys }), enabled })
  const rows: [string, (c: any) => any][] = useMemo(() => [
    ['Source', (c) => (c.kind === 'existing' ? <Badge tone="positive">Your policy</Badge> : <SampleBadge meta={c.catalogue} />)],
    ['Cover', (c) => (c.coverage.sum_insured ? <Money value={c.coverage.sum_insured} /> : c.coverage.sum_insured_options ? c.coverage.sum_insured_options.map((v: number) => compactInr(v)).join(' / ') : '—')],
    ['Cost', (c) => (c.cost.amount ? <span><Money value={c.cost.amount} /> <span className="block text-xs text-muted">{c.cost.label}</span></span> : <span className="text-sm text-muted">{c.cost.reason ?? 'Not available'}</span>)],
    ['Room rent', (c) => c.coverage.room_rent ?? '—'],
    ['Co-payment', (c) => (c.restrictions.copay_pct != null ? `${c.restrictions.copay_pct}%` : '—')],
    ['Deductible', (c) => (c.restrictions.deductible ? <Money value={c.restrictions.deductible} /> : 'None stated')],
    ['Pre-existing waiting', (c) => (c.restrictions.ped_waiting_months ? `${c.restrictions.ped_waiting_months} months` : c.restrictions.ped_waiting ?? '—')],
    ['Specific illness waiting', (c) => (c.restrictions.specific_disease_waiting_months ? `${c.restrictions.specific_disease_waiting_months} months` : c.restrictions.specific_disease_waiting ?? '—')],
    ['Sub-limits', (c) => (c.coverage.sub_limits?.length ? <ul className="text-sm">{c.coverage.sub_limits.slice(0, 4).map((s: string) => <li key={s}>{s}</li>)}</ul> : 'None listed')],
    ['Key exclusions', (c) => <ul className="text-sm">{(c.restrictions.exclusions ?? []).slice(0, 4).map((s: string) => <li key={s}>{s}</li>)}</ul>],
    ['Family fit', (c) => <ul className="text-sm">{c.family_fit.map((f: any) => <li key={f.name} className={f.eligible ? '' : 'text-critical'}>{f.name}: {f.eligible ? 'covered' : 'not eligible'}{!f.age_known && ' (age unknown)'}</li>)}</ul>],
    ['Claims', (c) => (c.claims?.cashless !== undefined ? `${c.claims.cashless ? 'Cashless' : ''}${c.claims.reimbursement ? ' · Reimbursement' : ''}` : c.claims?.intimation ?? '—')],
  ], [])
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Explore', to: '/insurance/explore' }]} title="Compare insurance" description="Catalogue premiums are indicative and not binding quotes." />
      {pols.data && pols.data.length > 0 && (
        <Panel className="mb-4 p-4">
          <p className="mb-2 text-sm font-medium">Include your existing policies</p>
          <div className="flex flex-wrap gap-x-4 gap-y-2">{pols.data.map((p: any) => <Checkbox key={p.id} checked={policyIds.includes(p.id)} onChange={(e) => setPolicyIds(e.target.checked ? [...policyIds, p.id] : policyIds.filter((x) => x !== p.id))} label={p.product_name ?? 'Policy'} />)}</div>
        </Panel>
      )}
      {!enabled && <EmptyState title="Pick at least two plans or policies" action={<LinkButton to="/insurance/explore">Explore plans</LinkButton>} />}
      {q.isLoading && enabled && <PageSkeleton />}
      {q.isError && <ErrorState error={q.error} />}
      {q.data && (
        <Panel className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-[0.95rem]">
            <thead><tr className="border-b border-line"><th scope="col" className="sticky left-0 w-44 bg-surface p-4"><span className="sr-only">Plan detail</span></th>
              {q.data.columns.map((c: any) => <th key={c.id} className="p-4 text-left align-top"><span className="font-semibold">{c.product_name}</span><span className="block text-sm font-normal text-muted">{c.insurer}</span></th>)}</tr></thead>
            <tbody className="divide-y divide-line">
              {rows.map(([label, fn]) => <tr key={label}><th scope="row" className="sticky left-0 bg-surface p-4 text-left text-sm font-normal text-muted">{label}</th>{q.data.columns.map((c: any) => <td key={c.id} className="p-4 align-top">{fn(c)}</td>)}</tr>)}
            </tbody>
          </table>
        </Panel>
      )}
    </>
  )
}

/* --- S46 Consultation ---------------------------------------------------- */

export function Consult() {
  useSaathiPage('insurance')
  const [params] = useSearchParams()
  const { user } = useAuth()
  const fam = useFamily()
  const pols = useQuery({ queryKey: ['policies'], queryFn: () => get<any[]>('/insurance/policies') })
  const history = useQuery({ queryKey: ['consults'], queryFn: () => get<any>('/consultations'), refetchInterval: (q) => (q.state.data?.items?.some((c: any) => ['calling', 'ringing', 'in_progress'].includes(c.status)) ? 3000 : false) })
  const [f, setF] = useState({ topic: params.get('topic') ?? '', policy: params.get('policy') ?? '', member: params.get('member') ?? '', product: params.get('product') ?? '', phone: '', useFile: true })
  const [consent, setConsent] = useState(false)
  const [preview, setPreview] = useState<any>(null)
  const [err, setErr] = useState<ApiError | null>(null)
  const qc = useQueryClient()
  const prev = useMutation({ mutationFn: () => post<any>('/consultations/preview', { topic: f.topic, policy_id: f.policy || null, member_key: f.member || null, product_id: f.product || null }), onSuccess: setPreview, onError: (e) => setErr(e instanceof ApiError ? e : null) })
  const req = useMutation({
    mutationFn: () => post<any>('/consultations', { topic: f.topic, policy_id: f.policy || null, member_key: f.member || null, product_id: f.product || null, consent, phone: f.useFile && user?.phone_masked ? null : f.phone, use_phone_on_file: f.useFile && !!user?.phone_masked }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['consults'] }); setPreview(null); setConsent(false) },
    onError: (e) => setErr(e instanceof ApiError ? e : null),
  })
  const retry = useMutation({ mutationFn: (id: string) => post(`/consultations/${id}/retry`), onSuccess: () => qc.invalidateQueries({ queryKey: ['consults'] }) })
  const ps = people(fam.data)
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Insurance', to: '/insurance' }]} title="Talk to a consultant" description="Request a call about a policy or plan. You see exactly what will be shared before anything is sent." />
      {history.data && !history.data.calling_configured && (
        <Callout tone="caution" className="mb-6" title="Calling isn't set up in this environment">You can prepare and save a request, but no call will be placed until Twilio is configured. VITTRM will say so clearly.</Callout>
      )}
      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <Panel className="p-5">
          <form onSubmit={(e) => { e.preventDefault(); setErr(null); if (f.topic.trim().length < 3) { setErr(new ApiError(422, 'X', 'Tell us what you want to discuss.', 'topic')); return } prev.mutate() }} className="flex flex-col gap-4" noValidate>
            <Field label="What would you like to discuss?" error={err?.field === 'topic' ? err.message : null}><Textarea value={f.topic} onChange={(e) => setF({ ...f, topic: e.target.value })} placeholder="e.g. Is my mother's cover enough for a knee surgery?" /></Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="About whom" optional><Select value={f.member} onChange={(e) => setF({ ...f, member: e.target.value })}><option value="">Not specific</option>{ps.map((p) => <option key={p.key} value={p.key}>{p.key === 'self' ? 'You' : p.name}</option>)}</Select></Field>
              <Field label="Related policy" optional><Select value={f.policy} onChange={(e) => setF({ ...f, policy: e.target.value })}><option value="">None</option>{pols.data?.map((p: any) => <option key={p.id} value={p.id}>{p.product_name}</option>)}</Select></Field>
            </div>
            <Button type="submit" variant="secondary" className="w-fit" loading={prev.isPending}>Preview what will be shared</Button>
          </form>
          {preview && (
            <div className="mt-6 flex flex-col gap-4 border-t border-line pt-5">
              <div>
                <p className="text-sm font-medium">Summary the consultant will see</p>
                <pre className="mt-2 whitespace-pre-wrap rounded-[var(--radius-control)] bg-ink/[0.04] p-4 font-sans text-[0.95rem]">{preview.context_summary}</pre>
                <p className="mt-1 text-xs text-muted">No bank transactions, income or account numbers are shared.</p>
              </div>
              {user?.phone_masked ? (
                <Checkbox checked={f.useFile} onChange={(e) => setF({ ...f, useFile: e.target.checked })} label={`Call me on ${user.phone_masked}`} />
              ) : null}
              {(!user?.phone_masked || !f.useFile) && <Field label="Number to call" error={err?.field === 'phone' ? err.message : null}><Input type="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} className="w-56" /></Field>}
              <Checkbox checked={consent} onChange={(e) => setConsent(e.target.checked)} label="I agree to receive this call and to share the summary above with the consultant" description="Calls aren't recorded." />
              {err && err.field !== 'topic' && err.field !== 'phone' && <p role="alert" className="text-sm text-critical">{err.message}</p>}
              <Button className="w-fit" disabled={!consent} loading={req.isPending} icon={<PhoneCall className="size-4" />} onClick={() => { setErr(null); req.mutate() }}>{preview.calling_configured ? 'Request the call' : 'Save the request'}</Button>
            </div>
          )}
        </Panel>
        <Panel className="p-5">
          <h2 className="font-semibold">Your requests</h2>
          {history.data?.items?.length ? (
            <ul className="mt-2 divide-y divide-line">
              {history.data.items.map((c: any) => (
                <li key={c.id} className="py-3">
                  <p className="font-medium">{c.topic}</p>
                  <p className="text-sm text-muted">{new Date(c.created_at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })} · {c.phone_masked}</p>
                  <Badge className="mt-1" tone={c.status === 'completed' ? 'positive' : c.status === 'failed' || c.status === 'no_answer' ? 'critical' : c.status === 'not_configured' ? 'caution' : 'indigo'}>{c.status_text}</Badge>
                  {c.error && c.status === 'failed' && <p className="mt-1 text-sm text-critical">{c.error}</p>}
                  {['failed', 'no_answer', 'not_configured'].includes(c.status) && <Button size="sm" variant="ghost" className="mt-1" loading={retry.isPending} onClick={() => retry.mutate(c.id)}>Try again</Button>}
                </li>
              ))}
            </ul>
          ) : <p className="mt-2 text-sm text-muted">No requests yet.</p>}
        </Panel>
      </div>
    </>
  )
}

/* --- S47 Emergency mode --------------------------------------------------- */

function Cite({ item }: { item: any }) {
  return item?.citation ? <SourceLink citation={item.citation} /> : null
}

export function Emergency() {
  const [params, setParams] = useSearchParams()
  const member = params.get('member')
  const event = params.get('event') ?? 'hospitalisation'
  useSaathiPage('emergency', null, member)
  const { ask } = useSaathi()
  const fam = useFamily()
  const events = useQuery({ queryKey: ['events'], queryFn: () => get<any[]>('/insurance/events') })
  const q = useQuery({ queryKey: ['emergency', member, event], queryFn: () => post<any>('/insurance/emergency', { member_key: member, event }), enabled: !!member })
  const ps = people(fam.data)
  const set = (k: string, v: string) => { const n = new URLSearchParams(params); n.set(k, v); setParams(n) }
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'Insurance', to: '/insurance' }]} title="Emergency help"
        description="Find which of your policies may apply, what to do now, and which documents to collect." />
      <Panel className="mb-6 border-critical/30 p-5">
        <fieldset>
          <legend className="mb-2 font-semibold">Who needs care?</legend>
          <div className="flex flex-wrap gap-2" role="radiogroup">
            {ps.map((p) => (
              <label key={p.key} className={clsx('flex min-h-12 items-center rounded-[var(--radius-control)] border px-4 text-[0.95rem]', member === p.key ? 'border-critical bg-critical-soft font-semibold' : 'border-line-strong bg-surface hover:border-critical')}>
                <input type="radio" name="who" className="sr-only" checked={member === p.key} onChange={() => set('member', p.key)} />
                {p.key === 'self' ? 'Me' : `${p.name} (${REL[p.relation] ?? p.relation})`}
              </label>
            ))}
          </div>
        </fieldset>
        <Field label="What happened" className="mt-4 max-w-sm">
          <Select value={event} onChange={(e) => set('event', e.target.value)}>{events.data?.map((e: any) => <option key={e.key} value={e.key}>{e.label}</option>)}</Select>
        </Field>
      </Panel>
      {!member && <p className="text-muted">Choose the person first so VITTRM only looks at their policies.</p>}
      {q.isLoading && member && <PageSkeleton />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data && (
        <div className="flex flex-col gap-6" aria-live="polite">
          {q.data.policies.length === 0 && (
            <EmptyState title={`No uploaded policy covers ${q.data.person.name}`} body="If they have a policy, upload it now. You can also call the insurer from the policy card or request a consultation."
              action={<div className="flex flex-wrap gap-2"><LinkButton to="/insurance/upload">Upload a policy</LinkButton><LinkButton to={`/insurance/consult?member=${member}&topic=${encodeURIComponent('Emergency: ' + q.data.event.label)}`} variant="secondary">Request a consultation</LinkButton></div>} />
          )}
          {q.data.policies.map((p: any) => (
            <Panel key={p.policy.id} className={clsx('p-5', p.status === 'may_apply' ? 'border-positive/40' : 'opacity-90')}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <Badge tone={p.status === 'may_apply' ? 'positive' : p.status === 'not_applicable' ? 'neutral' : 'caution'}>
                    {p.status === 'may_apply' ? 'May apply' : p.status === 'not_applicable' ? 'Not for this event' : p.status === 'lapsed_or_expired' ? 'Check if renewed' : 'Not started yet'}
                  </Badge>
                  <h2 className="mt-2 text-lg font-semibold"><Link to={`/insurance/policies/${p.policy.id}`} className="hover:text-indigo">{p.policy.product_name}</Link></h2>
                  <p className="text-sm text-muted">{p.policy.insurer}{p.policy.policy_ref_masked && ` · ${p.policy.policy_ref_masked}`}</p>
                </div>
                {p.contacts.helpline && <a href={`tel:${String(p.contacts.helpline.value).replace(/[^\d+]/g, '')}`} className="inline-flex min-h-11 items-center gap-2 rounded-[var(--radius-control)] bg-critical px-4 font-medium text-white"><Phone className="size-4" aria-hidden />Call {p.contacts.helpline.value}</a>}
              </div>
              <ul className="mt-2 text-[0.95rem]">{p.reasons.map((r: string) => <li key={r}>{r}</li>)}</ul>
              {p.status === 'may_apply' && (
                <div className="mt-4 grid gap-6 lg:grid-cols-2">
                  <div className="flex flex-col gap-4">
                    <section>
                      <h3 className="font-semibold">Can I use this?</h3>
                      <KeyValue items={[
                        p.coverage.sum_insured && { k: 'Sum insured', v: <Money value={p.coverage.sum_insured.value} />, extra: <Cite item={p.coverage.sum_insured} /> },
                        p.coverage.copay && { k: 'You pay (co-payment)', v: `${p.coverage.copay.value}% of each claim`, extra: <Cite item={p.coverage.copay} /> },
                        p.coverage.room_rent && { k: 'Room rent', v: p.coverage.room_rent.value, extra: <Cite item={p.coverage.room_rent} /> },
                        p.coverage.deductible && { k: 'Deductible', v: <Money value={p.coverage.deductible.value} />, extra: <Cite item={p.coverage.deductible} /> },
                      ].filter(Boolean) as any} />
                      {p.waiting_periods.map((w: any) => (
                        <p key={w.label} className={clsx('mt-2 flex items-start gap-1.5 text-[0.95rem]', w.status?.running && 'text-caution')}>
                          {w.status?.running && <AlertTriangle className="mt-1 size-4 shrink-0" aria-hidden />}
                          <span>{w.label}: {w.value}{w.status && (w.status.running ? ` — running until ${date(w.status.ends_on)}` : ' — completed')} <SourceLink citation={w.citation} /></span>
                        </p>
                      ))}
                    </section>
                    {p.exclusions && (
                      <section>
                        <h3 className="font-semibold">Not covered <Cite item={p.exclusions} /></h3>
                        <ul className="mt-1 list-disc pl-5 text-[0.95rem]">{p.exclusions.value.slice(0, 8).map((x: string) => <li key={x}>{x}</li>)}</ul>
                      </section>
                    )}
                  </div>
                  <div className="flex flex-col gap-4">
                    <section>
                      <h3 className="font-semibold">What to do now</h3>
                      {p.claim.intimation && <Callout tone="caution" className="mt-2">Inform the insurer within <b>{p.claim.intimation.value}</b>. <Cite item={p.claim.intimation} /></Callout>}
                      {p.claim.cashless && <><p className="mt-3 text-sm font-medium">Cashless at a network hospital <Cite item={p.claim.cashless} /></p><ol className="mt-1 list-decimal pl-5 text-[0.95rem]">{p.claim.cashless.value.map((s: string) => <li key={s}>{s.replace(/^\d+\.\s*/, '')}</li>)}</ol></>}
                      {p.claim.reimbursement && <><p className="mt-3 text-sm font-medium">Reimbursement <Cite item={p.claim.reimbursement} /></p><ol className="mt-1 list-decimal pl-5 text-[0.95rem]">{p.claim.reimbursement.value.map((s: string) => <li key={s}>{s.replace(/^\d+\.\s*/, '')}</li>)}</ol></>}
                      {p.claim.general_steps && <><p className="mt-3 text-sm font-medium">General steps <Badge>not from your policy</Badge></p><ol className="mt-1 list-decimal pl-5 text-[0.95rem]">{p.claim.general_steps.map((s: string) => <li key={s}>{s}</li>)}</ol></>}
                    </section>
                    <section>
                      <h3 className="font-semibold">Documents to collect {p.claim.documents && <Cite item={p.claim.documents} />}</h3>
                      {p.claim.documents ? <ul className="mt-1 flex flex-col gap-1 text-[0.95rem]">{p.claim.documents.value.map((x: string) => <li key={x}><Checkbox label={x} /></li>)}</ul>
                        : <p className="text-sm text-muted">The policy document doesn't list them. Ask the insurer or TPA.</p>}
                    </section>
                    {(p.contacts.tpa || p.contacts.email) && (
                      <section>
                        <h3 className="font-semibold">Contacts</h3>
                        <KeyValue items={[
                          p.contacts.tpa && { k: 'TPA', v: p.contacts.tpa.value, extra: <Cite item={p.contacts.tpa} /> },
                          p.contacts.email && { k: 'Claims email', v: <a className="text-indigo underline" href={`mailto:${p.contacts.email.value}`}>{p.contacts.email.value}</a> },
                        ].filter(Boolean) as any} />
                      </section>
                    )}
                  </div>
                </div>
              )}
            </Panel>
          ))}
          <Callout tone="info" title="The insurer decides the claim">{q.data.disclaimer}</Callout>
          <div className="flex flex-wrap gap-2">
            <Button variant="saathi" icon={<MessageCircle className="size-4" />} onClick={() => ask('Which policy covers this and what should I do first?')}>Ask Vitt Saathi</Button>
            <LinkButton to={`/insurance/consult?member=${member}&topic=${encodeURIComponent('Emergency: ' + q.data.event.label + ' for ' + q.data.person.name)}`} variant="secondary" icon={<PhoneCall className="size-4" />}>Request a consultation call</LinkButton>
            <Link to="/insurance" className="inline-flex min-h-11 items-center gap-1 px-2 text-sm font-medium text-indigo">All policies<ArrowRight className="size-4" aria-hidden /></Link>
          </div>
        </div>
      )}
    </>
  )
}

