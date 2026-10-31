import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowRight, Bell, BriefcaseBusiness, KeyRound, Languages, LogOut, MessageCircle, Phone, ShieldCheck, UserRound, Wallet } from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../../components/ui/button'
import { Avatar, Badge, IconTile, Money, PageHeader, Panel, TrustMark } from '../../components/ui/data'
import { Field, Input, PasswordInput, Segmented, Select } from '../../components/ui/field'
import { Callout, errorMessage, PageSkeleton, useToast } from '../../components/ui/feedback'
import { ConfirmDialog } from '../../components/ui/overlay'
import { ApiError, get, patch, post } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { date, parseAmountInput } from '../../lib/format'
import type { User } from '../../lib/types'
import { useSaathiPage } from '../saathi/context'

function Section({ id, icon, title, description, children, tone = 'indigo' }: { id: string; icon: ReactNode; title: string; description?: string; children: ReactNode; tone?: 'indigo' | 'green' | 'amber' | 'violet' }) {
  return (
    <Panel className="p-5 sm:p-6" aria-labelledby={id}>
      <div className="mb-5 flex items-start gap-3">
        <IconTile tone={tone}>{icon}</IconTile>
        <div><h2 id={id} className="text-[1.1rem] font-semibold">{title}</h2>{description && <p className="text-sm text-muted">{description}</p>}</div>
      </div>
      {children}
    </Panel>
  )
}

function PersonalForm({ user }: { user: User }) {
  const { refresh } = useAuth()
  const toast = useToast()
  const init = {
    name: user.name ?? '', phone: '', dob: user.dob ?? '', city: user.city ?? '',
    employment_type: user.employment_type ?? 'salaried', employer: user.employer ?? '', designation: user.designation ?? '',
  }
  const [f, setF] = useState(init)
  const [err, setErr] = useState<ApiError | null>(null)
  const set = (k: keyof typeof init) => (e: any) => setF({ ...f, [k]: e.target.value })
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {}
      for (const k of ['name', 'city', 'employer', 'designation', 'employment_type'] as const) if (f[k] !== init[k]) body[k] = f[k] || null
      if (f.dob !== init.dob) body.dob = f.dob || null
      if (f.phone.trim()) body.phone = f.phone.trim()
      return patch<User>('/onboarding/about', body)
    },
    onSuccess: () => { refresh(); setF((x) => ({ ...x, phone: '' })); setErr(null); toast({ title: 'Profile saved', tone: 'positive' }) },
    onError: (e) => setErr(e instanceof ApiError ? e : new ApiError(0, 'X', errorMessage(e))),
  })
  const removePhone = useMutation({ mutationFn: () => patch('/onboarding/about', { phone: null }), onSuccess: () => { refresh(); toast({ title: 'Mobile number removed', tone: 'positive' }) } })
  const fe = (k: string) => (err?.field === k ? err.message : null)
  const changed = JSON.stringify({ ...f, phone: '' }) !== JSON.stringify({ ...init, phone: '' }) || !!f.phone.trim()
  return (
    <form onSubmit={(e: FormEvent) => { e.preventDefault(); if (!f.name.trim()) { setErr(new ApiError(422, 'X', 'Enter your name.', 'name')); return } save.mutate() }} className="grid gap-4 @2xl:grid-cols-2" noValidate>
      <Field label="Name" error={fe('name')}><Input autoComplete="name" value={f.name} onChange={set('name')} /></Field>
      <Field label="Email" hint="Your sign-in email can't be changed here yet."><Input value={user.email} readOnly aria-readonly className="bg-ink/[0.03] text-muted" /></Field>
      <Field label="Mobile number" optional error={fe('phone')}
        hint={user.phone_masked ? <>Saved as <span className="num font-medium text-ink">{user.phone_masked}</span>. Enter a new number to replace it.</> : 'Needed for WhatsApp reminders and consultation calls. Stored encrypted.'}>
        <Input inputMode="tel" autoComplete="tel-national" placeholder="10-digit mobile" value={f.phone} onChange={set('phone')} />
      </Field>
      <Field label="Date of birth" optional error={fe('dob')}><Input type="date" value={f.dob} onChange={set('dob')} /></Field>
      <Field label="City" optional><Input autoComplete="address-level2" value={f.city} onChange={set('city')} /></Field>
      <Field label="Work"><Select value={f.employment_type} onChange={set('employment_type')}><option value="salaried">Salaried</option><option value="other">Other</option></Select></Field>
      <Field label="Employer" optional><Input autoComplete="organization" value={f.employer} onChange={set('employer')} /></Field>
      <Field label="Designation" optional><Input autoComplete="organization-title" value={f.designation} onChange={set('designation')} /></Field>
      {err && !err.field && <p role="alert" className="text-sm text-critical @2xl:col-span-2">{err.message}</p>}
      <div className="flex flex-wrap items-center gap-2 @2xl:col-span-2">
        <Button type="submit" loading={save.isPending} disabled={!changed}>Save changes</Button>
        {changed && <Button variant="quiet" onClick={() => { setF(init); setErr(null) }}>Discard</Button>}
        {user.phone_masked && <Button variant="quiet" className="ml-auto" loading={removePhone.isPending} onClick={() => removePhone.mutate()}>Remove mobile number</Button>}
      </div>
    </form>
  )
}

function PhoneVerification({ user }: { user: User }) {
  const { refresh } = useAuth()
  const toast = useToast()
  const [code, setCode] = useState('')
  const [pending, setPending] = useState(false)
  const start = useMutation({
    mutationFn: () => post('/onboarding/phone/verification', {}),
    onSuccess: () => { setPending(true); toast({ title: 'Verification code sent', tone: 'positive' }) },
    onError: (e) => toast({ title: errorMessage(e), tone: 'critical' }),
  })
  const check = useMutation({
    mutationFn: () => post('/onboarding/phone/verification/check', { code }),
    onSuccess: () => { setPending(false); setCode(''); refresh(); toast({ title: 'Mobile number verified', tone: 'positive' }) },
    onError: (e) => toast({ title: errorMessage(e), tone: 'critical' }),
  })
  if (!user.phone_masked) return null
  return <div className="mt-4 rounded-[14px] bg-white/70 p-4">
    <p className="text-sm font-medium">Mobile verification: {user.phone_verified ? 'Verified' : 'Not verified'}</p>
    {!user.phone_verified && <>
      <p className="mt-1 text-sm text-muted">Verify {user.phone_masked} before WhatsApp reminders or live consultation calls can be sent.</p>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <Button type="button" variant="secondary" loading={start.isPending} onClick={() => start.mutate()}>{pending ? 'Resend code' : 'Send code'}</Button>
        {pending && <><Field label="SMS code"><Input inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} /></Field>
          <Button type="button" loading={check.isPending} disabled={!/^\d{4,10}$/.test(code)} onClick={() => check.mutate()}>Verify</Button></>}
      </div>
    </>}
  </div>
}

function EmailVerification({ user }: { user: User }) {
  const toast = useToast()
  const request = useMutation({
    mutationFn: () => post('/auth/email-verification/request', {}),
    onSuccess: () => toast({ title: 'Verification link sent', tone: 'positive' }),
    onError: (e) => toast({ title: errorMessage(e), tone: 'critical' }),
  })
  if (user.is_sample) return null
  return <div className="mt-4 rounded-[14px] bg-white/70 p-4">
    <p className="text-sm font-medium">Email: {user.email_verified ? 'Verified' : 'Not verified'}</p>
    {!user.email_verified && <><p className="mt-1 text-sm text-muted">Verify your sign-in email for account recovery.</p>
      <Button className="mt-3" variant="secondary" loading={request.isPending} onClick={() => request.mutate()}>Send verification link</Button></>}
  </div>
}

function LanguagePref({ user }: { user: User }) {
  const { refresh } = useAuth()
  const toast = useToast()
  const m = useMutation({ mutationFn: (l: string) => patch('/onboarding/about', { preferred_language: l }), onSuccess: () => { refresh(); toast({ title: 'Language saved', tone: 'positive' }) }, onError: (e) => toast({ title: errorMessage(e), tone: 'critical' }) })
  return (
    <div>
      <Segmented label="Vitt Saathi replies in" name="lang" value={user.preferred_language ?? 'en'} onChange={(v) => m.mutate(v)}
        options={[{ value: 'en', label: 'English' }, { value: 'hi', label: 'हिन्दी' }, { value: 'hinglish', label: 'Hinglish' }]} />
      <p className="mt-2 text-sm text-muted">Used when a message doesn't make the language clear. Writing in Hindi or Hinglish always gets a reply in that language.</p>
    </div>
  )
}

function PasswordForm({ sample }: { sample: boolean }) {
  const toast = useToast()
  const [f, setF] = useState({ current: '', next: '', confirm: '' })
  const [err, setErr] = useState<ApiError | null>(null)
  const m = useMutation({
    mutationFn: () => post<any>('/auth/password', { current_password: f.current, new_password: f.next }),
    onSuccess: (r) => { setF({ current: '', next: '', confirm: '' }); setErr(null); toast({ title: r.other_sessions_ended ? `Password changed. Signed out ${r.other_sessions_ended} other session${r.other_sessions_ended > 1 ? 's' : ''}.` : 'Password changed', tone: 'positive' }) },
    onError: (e) => setErr(e instanceof ApiError ? e : new ApiError(0, 'X', errorMessage(e))),
  })
  if (sample) return <Callout tone="info" title="Sample workspaces have no password">This workspace was created with a generated password, so there's nothing to change. Create your own account to set one.</Callout>
  function submit(e: FormEvent) {
    e.preventDefault()
    if (!f.current) return setErr(new ApiError(422, 'X', 'Enter your current password.', 'current_password'))
    if (f.next.length < 8) return setErr(new ApiError(422, 'X', 'Use at least 8 characters.', 'new_password'))
    if (f.confirm !== f.next) return setErr(new ApiError(422, 'X', "The new passwords don't match.", 'confirm'))
    m.mutate()
  }
  const fe = (k: string) => (err?.field === k ? err.message : null)
  return (
    <form onSubmit={submit} className="grid gap-4 @2xl:grid-cols-3" noValidate>
      <Field label="Current password" error={fe('current_password')}><PasswordInput autoComplete="current-password" value={f.current} onChange={(e) => setF({ ...f, current: e.target.value })} /></Field>
      <Field label="New password" hint="At least 8 characters." error={fe('new_password')}><PasswordInput autoComplete="new-password" value={f.next} onChange={(e) => setF({ ...f, next: e.target.value })} /></Field>
      <Field label="Confirm new password" error={fe('confirm')}><PasswordInput autoComplete="new-password" value={f.confirm} onChange={(e) => setF({ ...f, confirm: e.target.value })} /></Field>
      {err && !err.field && <p role="alert" className="text-sm text-critical @2xl:col-span-3">{err.message}</p>}
      <div className="@2xl:col-span-3"><Button type="submit" loading={m.isPending}>Change password</Button><p className="mt-2 text-sm text-muted">Changing it signs out every other device. This one stays signed in.</p></div>
    </form>
  )
}

function FinancialSummary({ user }: { user: User }) {
  const { refresh } = useAuth()
  const toast = useToast()
  const q = useQuery({ queryKey: ['profile'], queryFn: () => get<any>('/profile') })
  const [salary, setSalary] = useState(user.salary_manual != null ? String(user.salary_manual) : '')
  const save = useMutation({
    mutationFn: () => patch('/onboarding/about', { salary_manual: salary.trim() ? parseAmountInput(salary) : null }),
    onSuccess: () => { refresh(); q.refetch(); toast({ title: 'Salary saved', tone: 'positive' }) },
    onError: (e) => toast({ title: errorMessage(e), tone: 'critical' }),
  })
  const p = q.data?.profile
  const inc = p?.income_summary?.monthly_estimate
  const cf = p?.cashflow_metrics
  const rows: { label: string; value: ReactNode; mark?: ReactNode }[] = [
    { label: 'Monthly income', value: inc?.value != null ? <Money value={inc.value} /> : 'Not available', mark: inc?.value != null ? <TrustMark state={inc.state ?? 'extracted'} /> : undefined },
    { label: 'Average monthly spending', value: cf?.avg_monthly_outflow?.value != null ? <Money value={cf.avg_monthly_outflow.value} /> : 'Not available', mark: cf?.avg_monthly_outflow?.value != null ? <TrustMark state="estimate" /> : undefined },
    { label: 'Regular commitments', value: cf?.fixed_monthly?.value != null ? <Money value={cf.fixed_monthly.value} /> : 'Not available' },
    { label: 'Statement months covered', value: cf?.months_covered ? String(cf.months_covered) : 'None yet' },
  ]
  return (
    <div className="flex flex-col gap-5">
      {q.isLoading ? <p className="text-sm text-muted">Loading…</p> : (
        <dl className="grid gap-3 @2xl:grid-cols-2">
          {rows.map((r) => (
            <div key={r.label} className="rounded-[var(--radius-card)] border border-white/80 bg-white/70 p-4">
              <dt className="flex flex-wrap items-center gap-2 text-sm text-muted">{r.label}{r.mark}</dt>
              <dd className="num mt-0.5 text-[1.2rem] font-semibold">{r.value}</dd>
            </div>
          ))}
        </dl>
      )}
      <form onSubmit={(e) => { e.preventDefault(); save.mutate() }} className="flex flex-wrap items-end gap-3">
        <Field label="Monthly take-home salary (you enter)" optional hint="Used when there's no statement, or to check the detected salary." className="min-w-56 flex-1">
          <Input prefix="₹" inputMode="numeric" value={salary} onChange={(e) => setSalary(e.target.value)} />
        </Field>
        <Button type="submit" variant="secondary" loading={save.isPending}>Save salary</Button>
      </form>
      <Link to="/profile/review" className="inline-flex min-h-10 w-fit items-center gap-1 font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">Review and correct everything VITTRM found<ArrowRight className="size-4" aria-hidden /></Link>
    </div>
  )
}

export function Profile() {
  useSaathiPage('dashboard')
  const { user, logout } = useAuth()
  const [signout, setSignout] = useState(false)
  const [busy, setBusy] = useState(false)
  if (!user) return <PageSkeleton />
  const whatsapp = user.consents.includes('whatsapp_reminders')
  const calls = user.consents.includes('consultation_calls')
  return (
    <>
      <PageHeader crumbs={[{ label: 'Home', to: '/' }, { label: 'My profile' }]} title="My profile" description="Your details, preferences and account security." />
      <section className="glass relative isolate mb-7 flex flex-col gap-4 overflow-hidden rounded-[var(--radius-window)] p-6 @xl:flex-row @xl:items-center" aria-label="Your account summary">
        <span className="pointer-events-none absolute -right-20 -top-24 -z-10 size-72 rounded-full bg-indigo-300/25 blur-3xl" aria-hidden />
        <Avatar name={user.name} size="xl" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[1.5rem] font-semibold tracking-[-0.015em]">{user.name}</p>
          <p className="truncate text-muted">{user.is_sample ? 'Sample workspace — fictional data' : user.email}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {user.is_sample && <Badge tone="saathi">Sample workspace</Badge>}
            {user.phone_masked ? <Badge tone="indigo"><Phone className="size-3" aria-hidden />{user.phone_masked}</Badge> : <Badge>No mobile number</Badge>}
            {user.city && <Badge>{user.city}</Badge>}
          </div>
        </div>
        <Button variant="secondary" icon={<LogOut className="size-4" />} onClick={() => setSignout(true)}>Sign out</Button>
      </section>

      <div className="grid gap-6 @5xl:grid-cols-[1.5fr_1fr]">
        <div className="flex min-w-0 flex-col gap-6">
          <Section id="personal-h" icon={<UserRound />} title="Personal information" description="Used to personalise plans and to check insurance age limits.">
            <PersonalForm user={user} />
            <PhoneVerification user={user} />
            <EmailVerification user={user} />
          </Section>
          <Section id="fin-h" icon={<Wallet />} tone="green" title="Financial profile" description="Built from your statement and what you confirmed. Only you can see it.">
            <FinancialSummary user={user} />
          </Section>
          <Section id="sec-h" icon={<KeyRound />} tone="violet" title="Security" description="Your password and signed-in devices.">
            <PasswordForm sample={user.is_sample} />
          </Section>
        </div>
        <div className="flex flex-col gap-6">
          <Section id="pref-h" icon={<Languages />} tone="amber" title="Preferences">
            <LanguagePref user={user} />
          </Section>
          <Section id="comm-h" icon={<Bell />} title="Notifications & contact">
            <ul className="flex flex-col gap-2 text-[0.95rem]">
              <li className="flex items-center justify-between gap-2 rounded-[14px] bg-white/70 px-3 py-2.5"><span className="flex items-center gap-2"><MessageCircle className="size-4 text-positive" aria-hidden />WhatsApp messages</span><Badge tone={whatsapp && user.phone_verified ? 'positive' : 'neutral'}>{whatsapp ? user.phone_verified ? 'Allowed' : 'Verify phone first' : 'Not allowed'}</Badge></li>
              <li className="flex items-center justify-between gap-2 rounded-[14px] bg-white/70 px-3 py-2.5"><span className="flex items-center gap-2"><Phone className="size-4 text-marigold-deep" aria-hidden />Consultation calls</span><Badge tone={calls && user.phone_verified ? 'positive' : 'neutral'}>{calls ? user.phone_verified ? 'Allowed' : 'Verify phone first' : 'Not allowed'}</Badge></li>
              <li className="flex items-center justify-between gap-2 rounded-[14px] bg-white/70 px-3 py-2.5"><span className="flex items-center gap-2"><Bell className="size-4 text-indigo" aria-hidden />In-app reminders</span><Badge tone="positive">Always on</Badge></li>
            </ul>
            <div className="mt-4 flex flex-col gap-1">
              <Link to="/settings/reminders" className="inline-flex min-h-10 items-center gap-1 text-sm font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">When and how reminders arrive<ArrowRight className="size-4" aria-hidden /></Link>
              <Link to="/settings" className="inline-flex min-h-10 items-center gap-1 text-sm font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">Change permissions in Settings<ArrowRight className="size-4" aria-hidden /></Link>
            </div>
          </Section>
          <Section id="acct-h" icon={<ShieldCheck />} tone="green" title="Account">
            <dl className="flex flex-col gap-2 text-sm">
              <div className="flex justify-between gap-2"><dt className="text-muted">Sign-in</dt><dd>{user.is_sample ? 'Sample workspace' : 'Email and password'}</dd></div>
              <div className="flex justify-between gap-2"><dt className="text-muted">Date of birth</dt><dd>{user.dob ? date(user.dob) : 'Not added'}</dd></div>
              <div className="flex justify-between gap-2"><dt className="text-muted">Work</dt><dd className="flex items-center gap-1.5"><BriefcaseBusiness className="size-3.5 text-muted" aria-hidden />{user.employment_type === 'salaried' ? 'Salaried' : user.employment_type ? 'Other' : 'Not added'}</dd></div>
            </dl>
            <p className="mt-3 text-sm text-muted">To remove everything VITTRM holds, use <Link to="/settings" className="font-medium text-critical underline decoration-critical/40 underline-offset-2">Delete all my data</Link> in Settings.</p>
          </Section>
        </div>
      </div>

      <ConfirmDialog open={signout} onOpenChange={setSignout} title="Sign out of VITTRM?" danger={false} confirmLabel="Sign out" busy={busy}
        description={user.is_sample ? "This is a sample workspace with a generated password, so you can't sign back into it." : 'Your data stays in your workspace. Sign in again with your email and password.'}
        onConfirm={async () => { setBusy(true); try { await logout() } finally { setBusy(false); setSignout(false) } }} />
    </>
  )
}
