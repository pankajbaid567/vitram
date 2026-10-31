import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Check, CircleAlert, Download, Loader2, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Logo } from '../../app/AppShell'
import { Button, LinkButton } from '../../components/ui/button'
import { Panel } from '../../components/ui/data'
import { Checkbox, Field, Input, Segmented, Select } from '../../components/ui/field'
import { Callout, errorMessage, ErrorState } from '../../components/ui/feedback'
import { FileDrop } from '../../components/ui/filedrop'
import { ApiError, del, get, patch, post, upload } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { acceptFor, useVision } from '../../lib/vision'
import { DuplicateNotice } from '../documents/DuplicateNotice'
import { isDuplicate } from '../documents/duplicates'
import { parseAmountInput } from '../../lib/format'
import type { DocumentRow } from '../../lib/types'

const STEPS = [
  { key: 'about', label: 'About you', to: '/onboarding/about' },
  { key: 'family', label: 'Family', to: '/onboarding/family' },
  { key: 'statement', label: 'Bank statement', to: '/onboarding/statement' },
  { key: 'review', label: 'Review', to: '/profile/review' },
]

export function OnboardingLayout({ step, children }: { step: string; children: ReactNode }) {
  const idx = STEPS.findIndex((s) => s.key === step)
  return (
    <div className="min-h-dvh">
      <div className="app-bg" aria-hidden />
      <div className="sticky top-0 z-30 px-3 pt-3">
        <header className="glass mx-auto flex min-h-14 max-w-3xl items-center justify-between rounded-full py-1.5 pl-4 pr-2">
          <Logo />
          <Link to="/" className="inline-flex min-h-10 items-center rounded-full px-3 text-sm font-medium text-muted transition-colors hover:bg-ink/5 hover:text-ink">Go to dashboard</Link>
        </header>
      </div>
      <main id="main" className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
        <ol className="surface-card mb-8 flex items-center gap-2 rounded-full p-2 text-sm" aria-label="Setup progress">
          {STEPS.map((s, i) => (
            <li key={s.key} className="flex flex-1 items-center gap-2" aria-current={i === idx ? 'step' : undefined}>
              <span className={clsx('flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold',
                i < idx ? 'bg-positive text-white' : i === idx ? 'bg-[image:var(--grad-indigo)] text-white shadow-[0_4px_10px_rgb(52_67_181/0.3)]' : 'border border-line-strong bg-white text-muted')}>
                {i < idx ? <Check className="size-4" aria-hidden /> : i + 1}
              </span>
              <span className={clsx('hidden sm:inline', i === idx ? 'font-semibold' : 'text-muted')}>{s.label}</span>
              {i < STEPS.length - 1 && <span className={clsx('h-0.5 flex-1 rounded-full', i < idx ? 'bg-positive/50' : 'bg-ink/10')} aria-hidden />}
            </li>
          ))}
        </ol>
        {children}
      </main>
    </div>
  )
}

/* --- S02 About you ------------------------------------------------------ */

export function AboutStep() {
  const { user, refresh } = useAuth()
  const navigate = useNavigate()
  const [f, setF] = useState({
    name: user?.name ?? '', dob: user?.dob ?? '', city: user?.city ?? '', employment_type: user?.employment_type ?? 'salaried',
    employer: user?.employer ?? '', designation: user?.designation ?? '', salary: user?.salary_manual ? String(user.salary_manual) : '',
    phone: '', preferred_language: user?.preferred_language ?? 'en',
  })
  const [err, setErr] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value })

  async function submit(e: FormEvent) {
    e.preventDefault()
    setErr(null)
    if (!f.dob) { setErr(new ApiError(422, 'X', 'Enter your date of birth.', 'dob')); return }
    const salary = f.salary ? parseAmountInput(f.salary) : null
    if (f.salary && salary === null) { setErr(new ApiError(422, 'X', 'Enter the salary as a number, or leave it blank.', 'salary_manual')); return }
    setBusy(true)
    try {
      const body: any = { name: f.name, dob: f.dob, city: f.city || null, employment_type: f.employment_type, employer: f.employer || null,
        designation: f.designation || null, salary_manual: salary, preferred_language: f.preferred_language }
      if (f.phone) body.phone = f.phone
      await patch('/onboarding/about', body)
      await refresh()
      navigate('/onboarding/family')
    } catch (e) {
      setErr(e instanceof ApiError ? e : null)
    } finally {
      setBusy(false)
    }
  }
  const fe = (k: string) => (err?.field === k ? err.message : null)
  return (
    <OnboardingLayout step="about">
      <h1 className="text-2xl font-semibold">About you</h1>
      <p className="mt-2 max-w-prose text-muted">A few basics so recommendations can check age and employment limits. Only date of birth is needed now.</p>
      <form onSubmit={submit} className="mt-6 grid gap-5 sm:grid-cols-2" noValidate>
        <Field label="Name" error={fe('name')}><Input value={f.name} onChange={set('name')} autoComplete="name" /></Field>
        <Field label="Date of birth" error={fe('dob')}><Input type="date" value={f.dob} onChange={set('dob')} max={new Date().toISOString().slice(0, 10)} /></Field>
        <Field label="Employment" hint={f.employment_type === 'other' ? 'VITTRM is designed for salaried people; some features may not fit other situations.' : undefined}>
          <Select value={f.employment_type} onChange={set('employment_type')}>
            <option value="salaried">Salaried (formal sector)</option>
            <option value="other">Other</option>
          </Select>
        </Field>
        <Field label="City" optional><Input value={f.city} onChange={set('city')} autoComplete="address-level2" /></Field>
        <Field label="Employer" optional><Input value={f.employer} onChange={set('employer')} autoComplete="organization" /></Field>
        <Field label="Designation" optional><Input value={f.designation} onChange={set('designation')} autoComplete="organization-title" /></Field>
        <Field label="Monthly take-home salary" optional error={fe('salary_manual')}
          hint="Skip this if you prefer — VITTRM can estimate it from your bank statement and ask you to confirm.">
          <Input prefix="₹" inputMode="numeric" value={f.salary} onChange={set('salary')} />
        </Field>
        <Field label="Mobile number" optional error={fe('phone')} hint={user?.phone_masked ? `On file: ${user.phone_masked}` : 'Needed only for WhatsApp reminders or consultation calls.'}>
          <Input type="tel" inputMode="tel" autoComplete="tel-national" placeholder="10-digit mobile" value={f.phone} onChange={set('phone')} />
        </Field>
        <Field label="Preferred language for Vitt Saathi">
          <Select value={f.preferred_language} onChange={set('preferred_language')}>
            <option value="en">English</option><option value="hi">हिन्दी (Hindi)</option><option value="hinglish">Hinglish</option>
          </Select>
        </Field>
        {err && !err.field && <p role="alert" className="text-sm text-critical sm:col-span-2">{err.message}</p>}
        <div className="flex gap-3 sm:col-span-2"><Button type="submit" size="lg" loading={busy}>Continue</Button></div>
      </form>
    </OnboardingLayout>
  )
}

/* --- S03 Family --------------------------------------------------------- */

export const RELATIONS = [
  ['spouse', 'Spouse'], ['child', 'Child'], ['mother', 'Mother'], ['father', 'Father'], ['mother_in_law', 'Mother-in-law'],
  ['father_in_law', 'Father-in-law'], ['sibling', 'Sibling'], ['other_dependant', 'Other dependant'],
] as const

export function MemberForm({ onDone, initial, defaultRelation }: { onDone: () => void; initial?: any; defaultRelation?: string }) {
  const qc = useQueryClient()
  const [f, setF] = useState({ name: initial?.name ?? '', relation: initial?.relation ?? defaultRelation ?? 'spouse', dob: initial?.dob ?? '', age: initial?.age && !initial?.dob ? String(initial.age) : '', is_dependant: initial?.is_dependant ?? false })
  const [err, setErr] = useState<ApiError | null>(null)
  const m = useMutation({
    mutationFn: () => {
      const body = { name: f.name, relation: f.relation, dob: f.dob || null, age: f.dob ? null : f.age ? Number(f.age) : null, is_dependant: f.is_dependant }
      return initial ? patch(`/family/${initial.id}`, body) : post('/family', body)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['family'] }); onDone() },
    onError: (e) => setErr(e instanceof ApiError ? e : null),
  })
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (!f.name.trim()) { setErr(new ApiError(422, 'X', 'Enter a name or nickname.', 'name')); return } m.mutate() }}
      className="grid gap-4 sm:grid-cols-2" noValidate>
      <Field label="Name or nickname" error={err?.field === 'name' ? err.message : null}><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
      <Field label="Relation"><Select value={f.relation} onChange={(e) => setF({ ...f, relation: e.target.value })}>{RELATIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
      <Field label="Date of birth" optional hint="Or give an age below. Needed for insurance age limits."><Input type="date" value={f.dob} onChange={(e) => setF({ ...f, dob: e.target.value })} /></Field>
      <Field label="Age" optional error={err?.field === 'age' ? err.message : null}><Input inputMode="numeric" value={f.age} disabled={!!f.dob} onChange={(e) => setF({ ...f, age: e.target.value.replace(/\D/g, '') })} /></Field>
      <Checkbox className="sm:col-span-2" checked={f.is_dependant} onChange={(e) => setF({ ...f, is_dependant: e.target.checked })} label="Financially dependent on me" />
      {err && !err.field && <p role="alert" className="text-sm text-critical sm:col-span-2">{err.message}</p>}
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" loading={m.isPending}>{initial ? 'Save changes' : 'Add member'}</Button>
        <Button variant="quiet" onClick={onDone}>Cancel</Button>
      </div>
    </form>
  )
}

export function FamilyStep() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['family'], queryFn: () => get<any>('/family') })
  const [adding, setAdding] = useState(false)
  const remove = useMutation({ mutationFn: (id: string) => del(`/family/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ['family'] }) })
  async function next() {
    await post('/onboarding/step', { step: 'statement' })
    navigate('/onboarding/statement')
  }
  const members = q.data?.members ?? []
  return (
    <OnboardingLayout step="family">
      <h1 className="text-2xl font-semibold">Family</h1>
      <p className="mt-2 max-w-prose text-muted">Add people whose insurance or obligations you manage — spouse, parents, children. You can skip this and add them later. VITTRM always shows whose data it's using.</p>
      <div className="mt-6 flex flex-col gap-3">
        {members.map((m: any) => (
          <Panel key={m.id} className="flex items-center justify-between gap-3 p-4">
            <div><p className="font-medium">{m.name}</p><p className="text-sm text-muted">{RELATIONS.find((r) => r[0] === m.relation)?.[1]}{m.age != null ? ` · ${m.age} years` : ' · age not added'}</p></div>
            <Button variant="quiet" size="sm" icon={<Trash2 className="size-4" />} onClick={() => remove.mutate(m.id)} aria-label={`Remove ${m.name}`}>Remove</Button>
          </Panel>
        ))}
        {adding ? <Panel className="p-5"><MemberForm onDone={() => setAdding(false)} /></Panel>
          : <Button variant="secondary" className="w-fit" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>Add a family member</Button>}
      </div>
      <div className="mt-8 flex gap-3">
        <Button size="lg" onClick={next}>{members.length ? 'Continue' : 'Skip for now'}</Button>
      </div>
    </OnboardingLayout>
  )
}

/* --- S04 Bank statement upload ----------------------------------------- */

export function ConsentGate({ purpose, children, title, body }: { purpose: string; children: ReactNode; title: string; body: ReactNode }) {
  const { user, refresh } = useAuth()
  const [checked, setChecked] = useState(false)
  const [busy, setBusy] = useState(false)
  if (user?.consents.includes(purpose)) return <>{children}</>
  return (
    <Panel className="flex flex-col gap-4 p-5">
      <h2 className="font-semibold">{title}</h2>
      <div className="text-[0.95rem] text-muted">{body}</div>
      <Checkbox checked={checked} onChange={(e) => setChecked(e.target.checked)} label="I agree" />
      <Button className="w-fit" disabled={!checked} loading={busy} onClick={async () => {
        setBusy(true)
        try { await post('/consents', { purpose }); await refresh() } finally { setBusy(false) }
      }}>Continue</Button>
    </Panel>
  )
}

export const DOC_CONSENT_BODY = (
  <ul className="list-disc space-y-1 pl-5">
    <li>VITTRM reads your statement and documents to build your financial profile, then stores the extracted facts.</li>
    <li>Files are encrypted and only you can open them. You can delete any document and its data at any time.</li>
    <li>Only the facts needed for a page are shared with Vitt Saathi. Card numbers, PINs and passwords are never needed.</li>
  </ul>
)

export function StatementUpload({ onUploaded, compact }: { onUploaded: (d: DocumentRow) => void; compact?: boolean }) {
  const vision = useVision()
  const [progress, setProgress] = useState<number | null>(null)
  const accounts = useQuery({ queryKey: ['accounts'], queryFn: () => get<any[]>('/accounts') })
  const [months, setMonths] = useState<3 | 6 | 12 | null>(6)
  const [account, setAccount] = useState<string>('new')
  const [label, setLabel] = useState('Salary account')
  const [bank, setBank] = useState('')
  const [last4, setLast4] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [err, setErr] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (accounts.data?.length && account === 'new') setAccount(accounts.data.find((a) => a.is_primary)?.id ?? accounts.data[0].id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accounts.data])

  async function submit(e: FormEvent) {
    e.preventDefault()
    setErr(null)
    if (!file) { setErr(new ApiError(422, 'X', 'Choose your statement file.', 'file')); return }
    if (!months) { setErr(new ApiError(422, 'X', 'Choose the statement period.', 'period_months')); return }
    const fd = new FormData()
    fd.append('file', file)
    fd.append('type', 'bank_statement')
    fd.append('period_months', String(months))
    if (account !== 'new') fd.append('bank_account_id', account)
    else {
      fd.append('account_label', label)
      if (bank) fd.append('bank_name', bank)
      if (last4) fd.append('account_last4', last4)
    }
    setBusy(true)
    try {
      onUploaded(await upload<DocumentRow>('/documents', fd, setProgress))
    } catch (e) {
      setErr(e instanceof ApiError ? e : new ApiError(0, 'X', errorMessage(e)))
    } finally {
      setBusy(false)
      setProgress(null)
    }
  }
  return (
    <form onSubmit={submit} className="flex flex-col gap-5" noValidate>
      <Segmented label="Statement period" value={months} onChange={(v) => setMonths(v)}
        options={[{ value: 3, label: '3 months' }, { value: 6, label: '6 months' }, { value: 12, label: '12 months' }]} />
      {err?.field === 'period_months' && <p className="-mt-3 text-sm text-critical">{err.message}</p>}
      <Field label="Bank account">
        <Select value={account} onChange={(e) => setAccount(e.target.value)}>
          {(accounts.data ?? []).map((a) => <option key={a.id} value={a.id}>{a.label}{a.masked_ref ? ` (${a.masked_ref})` : ''}</option>)}
          <option value="new">Add a new account…</option>
        </Select>
      </Field>
      {account === 'new' && (
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Account name" error={err?.field === 'account_label' ? err.message : null}><Input value={label} onChange={(e) => setLabel(e.target.value)} /></Field>
          <Field label="Bank" optional><Input value={bank} onChange={(e) => setBank(e.target.value)} /></Field>
          <Field label="Last 4 digits" optional hint="Only the last 4."><Input inputMode="numeric" maxLength={4} value={last4} onChange={(e) => setLast4(e.target.value.replace(/\D/g, ''))} /></Field>
        </div>
      )}
      {err && isDuplicate(err) && <DuplicateNotice expectedType="bank_statement" error={err as ApiError} onReread={(d) => { setErr(null); onUploaded(d) }} />}
      <FileDrop accept={acceptFor('bank_statement', vision)} file={file} onFile={(f) => { setFile(f); setErr(null) }} camera={vision?.configured} progress={progress} scanNote={vision?.configured ? (vision.on_device ? 'Photos and scans are read on this device' : 'Photos and scans are read by Gemini') : undefined}
        hint={vision?.configured ? 'PDF or CSV from net banking, or a clear photo · up to 15 MB' : 'PDF from net banking or CSV export · up to 15 MB'} error={err?.field === 'file' && !isDuplicate(err) ? err.message : null} />
      {err && !['file', 'period_months', 'account_label'].includes(err.field ?? '') && (
        <Callout tone={err.code === 'DUPLICATE_DOCUMENT' ? 'caution' : 'critical'}>{err.message}</Callout>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" size="lg" loading={busy}>Upload & analyse</Button>
        {!compact && (
          <a href="/api/demo/fixtures/sample_statement_6m.csv" className="inline-flex min-h-11 items-center gap-2 text-sm font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">
            <Download className="size-4" aria-hidden />Download a sample statement to try
          </a>
        )}
      </div>
    </form>
  )
}

export function StatementStep() {
  const navigate = useNavigate()
  return (
    <OnboardingLayout step="statement">
      <h1 className="text-2xl font-semibold">Upload a bank statement</h1>
      <p className="mt-2 max-w-prose text-muted">Use your salary account for 3, 6 or 12 months. VITTRM finds your income, spending categories, frequent merchants, EMIs and other regular payments, and asks you to confirm them.</p>
      <div className="mt-6">
        <ConsentGate purpose="financial_documents" title="Before you upload" body={DOC_CONSENT_BODY}>
          <Panel className="p-5"><StatementUpload onUploaded={(d) => navigate(`/onboarding/processing/${d.id}`)} /></Panel>
        </ConsentGate>
      </div>
      <p className="mt-6 text-sm text-muted">Password-protected PDFs can't be read — download an unlocked copy first. <Link to="/" className="font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">Skip for now</Link></p>
    </OnboardingLayout>
  )
}

/* --- S05 Processing ------------------------------------------------------ */

const STAGES: Record<string, { key: string; label: string }[]> = {
  bank_statement: [
    { key: 'uploaded', label: 'Uploaded securely' }, { key: 'reading', label: 'Reading transactions' },
    { key: 'categorising', label: 'Categorising spending' }, { key: 'building_profile', label: 'Building your profile' },
  ],
  insurance_policy: [
    { key: 'uploaded', label: 'Uploaded securely' }, { key: 'reading', label: 'Reading the policy' },
    { key: 'extracting', label: 'Finding coverage, exclusions and claim steps' }, { key: 'linking', label: 'Linking to your family' },
  ],
  loan_document: [
    { key: 'uploaded', label: 'Uploaded securely' }, { key: 'reading', label: 'Reading the document' },
    { key: 'extracting', label: 'Finding terms, fees and clauses' }, { key: 'linking', label: 'Calculating the real cost' },
  ],
  receipt: [
    { key: 'uploaded', label: 'Uploaded securely' }, { key: 'reading', label: 'Opening the receipt' },
    { key: 'extracting', label: 'Finding merchant, date, total and GST' },
  ],
}

export function ProcessingSteps({ doc }: { doc: DocumentRow }) {
  const base = STAGES[doc.type] ?? STAGES.loan_document
  // Photos and scans get an extra, visible OCR step (on this device or with Gemini).
  const scan = doc.stage === 'reading_scan' || doc.read_from_scan || doc.mime?.startsWith('image/')
  const stages = scan
    ? [...base.slice(0, 2), { key: 'reading_scan', label: doc.ocr?.provider === 'gemini' ? 'Reading the scan with Gemini' : 'Reading the scan on this device' }, ...base.slice(2)]
    : base
  const done = doc.status === 'ready' || doc.status === 'needs_review'
  const current = done ? stages.length : Math.max(stages.findIndex((s) => s.key === doc.stage), 0)
  return (
    <ol className="flex flex-col gap-3" aria-live="polite">
      {stages.map((s, i) => {
        const state = doc.status === 'failed' && i === current ? 'failed' : i < current ? 'done' : i === current ? 'active' : 'todo'
        return (
          <li key={s.key} className="flex items-center gap-3">
            <span className={clsx('flex size-7 items-center justify-center rounded-full',
              state === 'done' ? 'bg-positive text-white' : state === 'active' ? 'bg-indigo-soft text-indigo' : state === 'failed' ? 'bg-critical-soft text-critical' : 'border border-line-strong text-muted')}>
              {state === 'done' ? <Check className="size-4" aria-hidden /> : state === 'active' ? <Loader2 className="size-4 animate-spin" aria-hidden /> : state === 'failed' ? <CircleAlert className="size-4" aria-hidden /> : null}
            </span>
            <span className={clsx(state === 'todo' && 'text-muted', state === 'active' && 'font-medium')}>{s.label}</span>
            <span className="sr-only">{state === 'done' ? 'done' : state === 'active' ? 'in progress' : state === 'failed' ? 'failed' : 'waiting'}</span>
          </li>
        )
      })}
    </ol>
  )
}

export function useDocumentPoll(id: string | undefined) {
  return useQuery({
    queryKey: ['doc', id],
    queryFn: () => get<DocumentRow>(`/documents/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data && ['queued', 'processing'].includes(q.state.data.status) ? 1000 : false),
  })
}

export function ProcessingStep() {
  const { id } = useParams()
  const qc = useQueryClient()
  const q = useDocumentPoll(id)
  const doc = q.data
  const done = doc && (doc.status === 'ready' || doc.status === 'needs_review')
  useEffect(() => {
    if (done) { qc.invalidateQueries({ queryKey: ['me'] }); qc.invalidateQueries({ queryKey: ['dashboard'] }) }
  }, [done, qc])
  return (
    <OnboardingLayout step="statement">
      <h1 className="text-2xl font-semibold">{done ? 'Your statement is ready' : doc?.status === 'failed' ? "We couldn't read this statement" : 'Analysing your statement'}</h1>
      <p className="mt-2 text-muted">{done ? `${doc?.transactions_found ?? 0} transactions read. Next, check what VITTRM found.` : doc?.status === 'failed' ? '' : 'This usually takes a few seconds. You can leave this page — it keeps going.'}</p>
      <Panel className="mt-6 p-5">
        {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
        {doc && <ProcessingSteps doc={doc} />}
        {doc?.status === 'failed' && (
          <Callout tone="critical" className="mt-5" title="What went wrong">
            {doc.error_message}
          </Callout>
        )}
        {doc?.warnings?.map((w) => <Callout key={w} tone="caution" className="mt-4">{w}</Callout>)}
      </Panel>
      <div className="mt-6 flex flex-wrap gap-3">
        {done && <LinkButton to="/profile/review" size="lg">Review your profile</LinkButton>}
        {doc?.status === 'failed' && (
          <>
            <LinkButton to="/onboarding/statement" size="lg">Upload a different file</LinkButton>
            {doc.error_code === 'PROCESSING_ERROR' && <Button variant="secondary" size="lg" onClick={async () => { await post(`/documents/${doc.id}/reprocess`); q.refetch() }}>Try again</Button>}
          </>
        )}
        {!done && doc?.status !== 'failed' && <LinkButton to="/" variant="secondary">Continue in the background</LinkButton>}
      </div>
    </OnboardingLayout>
  )
}
