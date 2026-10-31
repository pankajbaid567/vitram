import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, FlaskConical, KeyRound, Lock, ShieldCheck, Sparkles } from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { Logo } from '../../app/AppShell'
import { Button } from '../../components/ui/button'
import { TrustMark } from '../../components/ui/data'
import { Checkbox, Field, Input, PasswordInput } from '../../components/ui/field'
import { Callout, errorMessage } from '../../components/ui/feedback'
import { ApiError, get, post } from '../../lib/api'
import { useAuth } from '../../lib/auth'

/* --- branded side ---------------------------------------------------------- */

function Ledger() {
  const rows: { label: string; value: string; mark: 'extracted' | 'confirmed' | 'sample' | 'estimate' }[] = [
    { label: 'Salary credit, monthly', value: '₹1,18,200', mark: 'extracted' },
    { label: 'Konkan Finance EMI', value: '₹11,240', mark: 'confirmed' },
    { label: 'Personal loan · real cost over 3 years', value: '₹5,12,387', mark: 'estimate' },
    { label: 'Health cover for your mother', value: '₹5,00,000', mark: 'extracted' },
  ]
  return (
    <div className="w-full max-w-md rounded-[var(--radius-panel)] bg-white/[0.07] p-5 shadow-[inset_0_1px_0_rgb(255_255_255/0.1)] ring-1 ring-white/12 backdrop-blur-md">
      <p className="mb-2 flex items-center gap-2 text-sm text-white/70"><FlaskConical className="size-4" aria-hidden />Example from the sample workspace (fictional data)</p>
      <ul className="divide-y divide-white/10">
        {rows.map((r) => (
          <li key={r.label} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-3">
            <span className="text-[0.95rem] text-white/85">{r.label}</span>
            <span className="flex items-center gap-2">
              <span className="num font-semibold text-white">{r.value}</span>
              <TrustMark state={r.mark} className="bg-white text-ink" />
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-sm text-white/65">Every figure says where it came from, and you can correct it.</p>
    </div>
  )
}

/** The large curved navy shape with a lit rim, an orb on the edge and glass shards (desktop). Decorative only. */
function NavyOrbit() {
  return (
    <div className="pointer-events-none absolute inset-0 hidden overflow-hidden xl:block" aria-hidden>
      <svg viewBox="0 0 1556 1011" preserveAspectRatio="xMinYMin meet" className="absolute left-0 top-0 h-auto w-full overflow-visible">
        <defs>
          <radialGradient id="auth-navy" cx="0.62" cy="0.42" r="0.62">
            <stop offset="0" stopColor="#3a48c9" />
            <stop offset="0.45" stopColor="#1d2477" />
            <stop offset="1" stopColor="#10154a" />
          </radialGradient>
          <radialGradient id="auth-rim" cx="0.5" cy="0.5" r="0.5">
            <stop offset="0.9" stopColor="#7c8cff" stopOpacity="0" />
            <stop offset="0.985" stopColor="#8f9cff" stopOpacity="0.55" />
            <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="auth-orb" cx="0.35" cy="0.3" r="0.7">
            <stop offset="0" stopColor="#ffffff" />
            <stop offset="0.35" stopColor="#c4ccff" />
            <stop offset="1" stopColor="#3443b5" />
          </radialGradient>
          <radialGradient id="auth-halo" cx="0.5" cy="0.5" r="0.5"><stop offset="0.45" stopColor="#9aa6ff" stopOpacity="0.45" /><stop offset="1" stopColor="#9aa6ff" stopOpacity="0" /></radialGradient>
          <filter id="auth-glow" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="18" /></filter>
        </defs>
        <circle cx="-100" cy="700" r="990" fill="#8f9cff" opacity="0.35" filter="url(#auth-glow)" />
        <circle cx="-100" cy="700" r="960" fill="url(#auth-navy)" />
        <circle cx="-100" cy="700" r="960" fill="url(#auth-rim)" />
        <circle cx="-100" cy="700" r="960" fill="none" stroke="#ffffff" strokeOpacity="0.55" strokeWidth="1.6" />
        <path d="M-40 520 C 300 430, 700 520, 1556 980" fill="none" stroke="#ffffff" strokeOpacity="0.16" strokeWidth="1.4" />
        <circle cx="575" cy="110" r="44" fill="url(#auth-halo)" />
        <circle cx="575" cy="110" r="21" fill="url(#auth-orb)" />
      </svg>
      {/* glass shards straddling the rim */}
      <div className="absolute left-[42%] top-[57%] h-[30%] w-[11%] -rotate-[14deg] skew-y-[18deg] rounded-[28px] border border-white/35 bg-white/[0.12] shadow-[inset_0_1px_0_rgb(255_255_255/0.4)] backdrop-blur-md" />
      <div className="absolute left-[52.5%] top-[70%] h-[20%] w-[5.5%] -rotate-[10deg] skew-y-[16deg] rounded-[22px] border border-white/35 bg-white/[0.14] backdrop-blur-md" />
      {/* dotted grids */}
      <div className="absolute left-0 top-[15%] h-32 w-16 bg-[radial-gradient(circle,rgb(255_255_255/0.28)_1.2px,transparent_1.6px)] bg-[length:18px_18px]" />
      <div className="absolute bottom-[14%] left-0 h-24 w-28 bg-[radial-gradient(circle,rgb(255_255_255/0.2)_1.2px,transparent_1.6px)] bg-[length:18px_18px]" />
      <div className="absolute right-[2%] top-[30%] h-28 w-36 bg-[radial-gradient(circle,rgb(52_67_181/0.22)_1.2px,transparent_1.6px)] bg-[length:18px_18px]" />
      <div className="absolute bottom-[12%] right-[18%] h-20 w-36 bg-[radial-gradient(circle,rgb(52_67_181/0.16)_1.2px,transparent_1.6px)] bg-[length:18px_18px]" />
    </div>
  )
}

function BrandPanel() {
  return (
    <section aria-label="About VITTRM"
      className="relative isolate flex flex-col justify-between gap-8 overflow-hidden rounded-[var(--radius-window)] px-6 py-7 text-white max-xl:sidebar-surface sm:px-10 lg:px-12 lg:py-11 xl:overflow-visible xl:rounded-none xl:px-[5.5vw] xl:py-12">
      <Logo light tagline />
      <p className="pointer-events-none -mt-2 hidden font-mono text-[0.8rem] leading-[2.1] tracking-[0.35em] text-white/30 xl:ml-[2.5vw] xl:block" aria-hidden>
        Smarter<br />Financial<br />Decisions<span className="mt-3 block h-px w-6 bg-white/30" />
      </p>
      <div className="flex flex-col gap-7 xl:ml-[4.5vw] xl:max-w-[36rem]">
        <div>
          <p className="max-w-[20ch] text-3xl font-semibold leading-[1.1] tracking-tight text-white sm:text-[2.35rem]">
            Know what your loans, cards and policies really mean for you.
          </p>
          <p className="mt-4 max-w-[52ch] text-[1rem] leading-relaxed text-white/80">
            VITTRM reads your bank statement and documents once, then helps you compare loans by their full cost,
            use the right card, stay ahead of EMIs and understand your insurance — with Vitt Saathi to explain it.
          </p>
        </div>
        <div className="hidden lg:block"><Ledger /></div>
      </div>
      <ul className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-white/80">
        <li className="flex items-center gap-2"><Lock className="size-4" aria-hidden />Encrypted documents</li>
        <li className="flex items-center gap-2"><ShieldCheck className="size-4" aria-hidden />You approve every use</li>
        <li className="flex items-center gap-2"><Sparkles className="size-4" aria-hidden />No other app account needed</li>
      </ul>
    </section>
  )
}

function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="relative isolate min-h-dvh overflow-hidden">
      <div className="auth-bg" aria-hidden />
      <NavyOrbit />
      <div className="relative grid min-h-dvh gap-3 p-3 lg:grid-cols-[1.05fr_1fr] xl:grid-cols-[1.12fr_1fr] xl:gap-0 xl:p-0">
        <BrandPanel />
        <main id="main" className="flex items-center justify-center px-2 py-8 sm:px-8 xl:justify-end xl:py-12 xl:pr-[7vw]">{children}</main>
      </div>
    </div>
  )
}

/* --- forms ------------------------------------------------------------------ */

function SampleWorkspace() {
  const { refresh } = useAuth()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  async function open() {
    setBusy(true)
    setErr(null)
    try {
      await post('/demo/workspace')
      qc.clear()
      await refresh()
      navigate('/')
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="mt-6">
      <div className="mb-5 flex items-center gap-3 text-sm text-muted"><span className="h-px flex-1 bg-ink/10" />or<span className="h-px flex-1 bg-ink/10" /></div>
      <div className="wash-amber rounded-[var(--radius-card)] p-4">
        <p className="font-semibold">Try a sample workspace</p>
        <p className="mt-1 text-sm text-ink/75">A separate account filled with generated documents from fictional institutions — a 6-month statement, three policies and a loan KFS — processed through the real pipeline.</p>
        <Button variant="secondary" className="mt-3 w-full" loading={busy} onClick={open}>Open sample workspace</Button>
        {err && <p role="alert" className="mt-2 text-sm text-critical">{err}</p>}
      </div>
    </div>
  )
}

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

function AuthCard({ title, subtitle, children }: { title: string; subtitle: ReactNode; children: ReactNode }) {
  return (
    <div className="glass-strong window-in w-full max-w-md rounded-[var(--radius-window)] p-6 sm:p-8">
      <h1 className="text-[1.9rem] font-semibold leading-tight tracking-[-0.02em]">{title}</h1>
      <p className="mt-1.5 text-[0.97rem] text-muted">{subtitle}</p>
      <div className="mt-6">{children}</div>
    </div>
  )
}

export function Login() {
  const { user, refresh } = useAuth()
  const navigate = useNavigate()
  const loc = useLocation()
  const [params] = useSearchParams()
  const [form, setForm] = useState({ email: '', password: '' })
  const [err, setErr] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)
  const from = (loc.state as any)?.from as string | undefined
  if (user) return <Navigate to={from && from !== '/login' ? from : user.onboarding_step === 'about' ? '/onboarding/about' : '/'} replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!EMAIL.test(form.email.trim())) return setErr(new ApiError(422, 'X', 'Enter the email you signed up with.', 'email'))
    if (!form.password) return setErr(new ApiError(422, 'X', 'Enter your password.', 'password'))
    setErr(null)
    setBusy(true)
    try {
      await post('/auth/login', { email: form.email, password: form.password })
      await refresh()
      navigate(from && from !== '/login' ? from : '/', { replace: true })
    } catch (e) {
      setErr(e instanceof ApiError ? e : new ApiError(0, 'X', errorMessage(e)))
    } finally {
      setBusy(false)
    }
  }
  const fe = (f: string) => (err?.field === f ? err.message : null)
  return (
    <AuthLayout>
      <div className="w-full max-w-md">
        <AuthCard title="Welcome back" subtitle="Sign in to your VITTRM workspace.">
          {params.get('expired') && <Callout tone="info" className="mb-5" title="Your session ended">Sign in again to continue. Nothing you saved was lost.</Callout>}
          <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
            <Field label="Email" error={fe('email')}>
              <Input type="email" autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </Field>
            <Field label="Password" error={fe('password')}>
              <PasswordInput autoComplete="current-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            </Field>
            <Link to="/forgot-password" className="-mt-1 w-fit text-sm font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">Forgot password?</Link>
            {err && !err.field && <p role="alert" className="text-sm text-critical">{err.message}</p>}
            <Button type="submit" loading={busy} size="lg" className="mt-1">Sign in<ArrowRight className="size-4" aria-hidden /></Button>
          </form>
          <p className="mt-5 text-center text-sm text-muted">New to VITTRM? <Link to="/signup" className="font-semibold text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">Create an account</Link></p>
        </AuthCard>
        <SampleWorkspace />
      </div>
    </AuthLayout>
  )
}

export function VerifyEmail() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const [state, setState] = useState<'idle' | 'busy' | 'done' | 'error'>('idle')
  const [error, setError] = useState('')
  return <AuthLayout><AuthCard title="Verify your email" subtitle="Confirm that this address belongs to you.">
    {state === 'done' ? <p role="status">Email verified. <Link className="text-indigo underline" to="/profile">Return to your profile.</Link></p> : <>
      {state === 'error' && <p role="alert" className="mb-3 text-sm text-critical">{error}</p>}
      <Button disabled={!token} loading={state === 'busy'} onClick={async () => {
        setState('busy')
        try { await post('/auth/email-verification/confirm', { token }); window.history.replaceState({}, '', '/verify-email'); setState('done') }
        catch (err) { setError(errorMessage(err)); setState('error') }
      }}>Verify email</Button>
    </>}
  </AuthCard></AuthLayout>
}

export function Signup() {
  const { user, refresh } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', email: '', password: '', confirm: '', accept: false })
  const [err, setErr] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)
  if (user) return <Navigate to={user.onboarding_step === 'about' ? '/onboarding/about' : '/'} replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    const bad = (field: string, msg: string) => setErr(new ApiError(422, 'X', msg, field))
    if (!form.name.trim()) return bad('name', 'Enter your name.')
    if (!EMAIL.test(form.email.trim())) return bad('email', 'Enter a valid email address.')
    if (form.password.length < 8) return bad('password', 'Use at least 8 characters.')
    if (form.confirm !== form.password) return bad('confirm', "The passwords don't match.")
    if (!form.accept) return bad('accept_terms', 'Accept the terms and privacy notice to create an account.')
    setErr(null)
    setBusy(true)
    try {
      await post('/auth/signup', { name: form.name, email: form.email, password: form.password, accept_terms: form.accept })
      await refresh()
      navigate('/onboarding/about', { replace: true })
    } catch (e) {
      setErr(e instanceof ApiError ? e : new ApiError(0, 'X', errorMessage(e)))
    } finally {
      setBusy(false)
    }
  }
  const fe = (f: string) => (err?.field === f ? err.message : null)
  return (
    <AuthLayout>
      <div className="w-full max-w-md">
        <AuthCard title="Create your account" subtitle="Two minutes to set up. You choose what VITTRM may read.">
          <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
            <Field label="Your name" error={fe('name')}>
              <Input autoComplete="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Field>
            <Field label="Email" error={fe('email')}>
              <Input type="email" autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </Field>
            <Field label="Password" hint="At least 8 characters." error={fe('password')}>
              <PasswordInput autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            </Field>
            <Field label="Confirm password" error={fe('confirm')}>
              <PasswordInput autoComplete="new-password" value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} />
            </Field>
            <Checkbox checked={form.accept} onChange={(e) => setForm({ ...form, accept: e.target.checked })}
              label="I accept the terms and privacy notice"
              description="VITTRM asks separately before processing any financial document, sending WhatsApp messages or calling you." />
            {fe('accept_terms') && <p role="alert" className="-mt-2 text-sm text-critical">{fe('accept_terms')}</p>}
            {err && !err.field && <p role="alert" className="text-sm text-critical">{err.message}</p>}
            <Button type="submit" loading={busy} size="lg" className="mt-1">Create account<ArrowRight className="size-4" aria-hidden /></Button>
          </form>
          <p className="mt-5 text-center text-sm text-muted">Already have an account? <Link to="/login" className="font-semibold text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">Sign in</Link></p>
        </AuthCard>
        <SampleWorkspace />
      </div>
    </AuthLayout>
  )
}

export function ForgotPassword() {
  const status = useQuery({ queryKey: ['reset-status'], queryFn: () => get<{ email_configured: boolean }>('/auth/password-reset/status') })
  const [email, setEmail] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!EMAIL.test(email.trim())) return setErr('Enter the email you signed up with.')
    setErr(null)
    setBusy(true)
    try {
      const r = await post<{ message: string }>('/auth/password-reset/request', { email })
      setDone(r.message)
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  const configured = status.data?.email_configured
  return (
    <AuthLayout>
      <div className="w-full max-w-md">
        <AuthCard title="Reset your password" subtitle="We'll email you a link to choose a new one.">
          {status.isLoading ? <p className="text-sm text-muted">Checking…</p> : configured === false ? (
            <div className="flex items-start gap-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-indigo-soft text-indigo" aria-hidden><KeyRound className="size-5" /></span>
              <div className="text-[0.95rem] text-ink/80">
                <p>This VITTRM server can't send email yet, so it can't send a reset link.</p>
                <p className="mt-2">If you're signed in on another device, change your password in <b>Profile → Security</b>. Otherwise, ask the person running this server to set up email (see the README).</p>
              </div>
            </div>
          ) : done ? (
            <Callout tone="positive" title="Check your email">{done}</Callout>
          ) : (
            <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
              <Field label="Email" error={err}><Input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
              <Button type="submit" size="lg" loading={busy}>Send reset link</Button>
            </form>
          )}
          <p className="mt-5 text-center text-sm text-muted"><Link to="/login" className="font-semibold text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo">Back to sign in</Link></p>
        </AuthCard>
      </div>
    </AuthLayout>
  )
}

export function ResetPassword() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const [f, setF] = useState({ next: '', confirm: '' })
  const [err, setErr] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)
  const [ok, setOk] = useState(false)
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (f.next.length < 8) return setErr(new ApiError(422, 'X', 'Use at least 8 characters.', 'new_password'))
    if (f.confirm !== f.next) return setErr(new ApiError(422, 'X', "The passwords don't match.", 'confirm'))
    setErr(null)
    setBusy(true)
    try {
      await post('/auth/password-reset/confirm', { token, new_password: f.next })
      setOk(true)
    } catch (e) {
      setErr(e instanceof ApiError ? e : new ApiError(0, 'X', errorMessage(e)))
    } finally {
      setBusy(false)
    }
  }
  const fe = (k: string) => (err?.field === k ? err.message : null)
  return (
    <AuthLayout>
      <div className="w-full max-w-md">
        <AuthCard title="Choose a new password" subtitle="This signs you out on every device.">
          {!token ? <Callout tone="critical" title="This link is incomplete">Open the link from the email again, or ask for a new one.</Callout> : ok ? (
            <div className="flex flex-col gap-4"><Callout tone="positive" title="Password changed">Sign in with your new password.</Callout><Link to="/login" className="font-semibold text-indigo underline decoration-indigo/40 underline-offset-2">Go to sign in</Link></div>
          ) : (
            <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
              <Field label="New password" hint="At least 8 characters." error={fe('new_password')}><PasswordInput autoComplete="new-password" value={f.next} onChange={(e) => setF({ ...f, next: e.target.value })} /></Field>
              <Field label="Confirm new password" error={fe('confirm')}><PasswordInput autoComplete="new-password" value={f.confirm} onChange={(e) => setF({ ...f, confirm: e.target.value })} /></Field>
              {err && !err.field && <p role="alert" className="text-sm text-critical">{err.message}</p>}
              {err?.code === 'RESET_LINK_INVALID' && <Link to="/forgot-password" className="text-sm font-medium text-indigo underline underline-offset-2">Ask for a new link</Link>}
              <Button type="submit" size="lg" loading={busy}>Save new password</Button>
            </form>
          )}
        </AuthCard>
      </div>
    </AuthLayout>
  )
}

/** Kept for existing links: /welcome shows the sign-up page. */
export const Welcome = Signup
