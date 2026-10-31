import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Bell, CalendarClock, Camera, ChevronRight, Info, ScanLine, CreditCard, FileStack, Home, Landmark, LogOut, Menu, PanelLeftClose, PanelLeftOpen, Settings, ShieldCheck, Target, UserRound, Users, X } from 'lucide-react'
import { DropdownMenu, Popover, Tooltip } from 'radix-ui'
import { useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Avatar, Badge } from '../components/ui/data'
import { SidebarWave } from '../components/illustrations'
import { ConfirmDialog, Sheet, SheetClose } from '../components/ui/overlay'
import { setupSteps, useDashboard } from '../features/dashboard/setup'
import { GlobalSearch } from './GlobalSearch'
import { useVision } from '../lib/vision'
import { get, post } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useSaathi } from '../features/saathi/context'
import { SaathiMark, SaathiPanel } from '../features/saathi/SaathiPanel'

const PRIMARY = [
  { to: '/', label: 'Home', icon: Home, end: true },
  { to: '/loans', label: 'Loans', icon: Landmark },
  { to: '/insurance', label: 'Insurance', icon: ShieldCheck },
  { to: '/cards', label: 'Cards', icon: CreditCard },
  { to: '/emis', label: 'EMIs', icon: CalendarClock },
]
const SECONDARY = [
  { to: '/family', label: 'Family', icon: Users },
  { to: '/goals', label: 'Goals', icon: Target },
  { to: '/documents', label: 'Documents & data', icon: FileStack },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function Logo({ light, tagline, compact }: { light?: boolean; tagline?: boolean; compact?: boolean }) {
  return (
    <span className={clsx('inline-flex items-center gap-2.5 text-lg font-semibold tracking-[0.08em]', light ? 'text-white' : 'text-ink')}>
      <svg viewBox="0 0 32 32" className={tagline ? 'size-10 drop-shadow-[0_4px_10px_rgb(0_0_0/0.25)]' : 'size-7'} aria-hidden>
        <rect width="32" height="32" rx="7" fill={light ? '#ffffff' : '#161D45'} />
        <path d="M8 9l8 15 8-15" fill="none" stroke={light ? '#161D45' : '#fff'} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="24" cy="9" r="3" fill="#E7A02F" />
      </svg>
      {!compact && (tagline ? (
        <span className="flex flex-col leading-tight">VITRAM<span className="text-[0.7rem] font-normal tracking-normal text-white/65">Your Money, A Brighter You</span></span>
      ) : 'VITRAM')}
    </span>
  )
}

function Notifications() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['notifications'], queryFn: () => get<any>('/notifications'), refetchInterval: 30_000 })
  const readAll = useMutation({ mutationFn: () => post('/notifications/read-all'), onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }) })
  const navigate = useNavigate()
  const unread = q.data?.unread ?? 0
  return (
    <Popover.Root>
      <Popover.Trigger className="glass relative inline-flex size-12 items-center justify-center rounded-full text-ink/80 transition-[color,box-shadow] hover:text-ink data-[state=open]:text-indigo-dark" aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`}>
        <Bell className="size-5" aria-hidden />
        {unread > 0 && <span className="absolute right-2 top-2 flex size-4 items-center justify-center rounded-full bg-critical text-[0.6rem] font-semibold text-white ring-2 ring-white">{unread > 9 ? '9+' : unread}</span>}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content align="end" sideOffset={8} className="window-in glass-strong z-50 w-[min(24rem,calc(100vw-2rem))] overflow-hidden rounded-[var(--radius-panel)]">
          <div className="flex items-center justify-between border-b border-[var(--glass-hairline)] px-4 py-3">
            <p className="font-semibold">Notifications</p>
            {unread > 0 && <button className="-my-1 min-h-9 rounded-full px-3 text-sm font-medium text-indigo hover:bg-indigo-soft" onClick={() => readAll.mutate()}>Mark all read</button>}
          </div>
          <ul className="max-h-96 overflow-y-auto">
            {(q.data?.items ?? []).length === 0 && <li className="px-4 py-6 text-sm text-muted">Nothing yet. Reminders and document updates appear here.</li>}
            {(q.data?.items ?? []).map((n: any) => (
              <li key={n.id}>
                <Popover.Close asChild>
                  <button type="button" onClick={() => { post(`/notifications/${n.id}/read`).then(() => qc.invalidateQueries({ queryKey: ['notifications'] })); if (n.link) navigate(n.link) }}
                    className={clsx('relative flex w-full flex-col items-start gap-0.5 border-b border-[var(--glass-hairline)] px-4 py-3 text-left transition-colors hover:bg-ink/[0.04]', !n.read && 'bg-indigo-soft/50 before:absolute before:left-1.5 before:top-4 before:size-1.5 before:rounded-full before:bg-indigo')}>
                    <span className="text-sm font-medium">{n.title}</span>
                    {n.body && <span className="text-sm text-muted">{n.body}</span>}
                    <span className="text-xs text-muted">{new Date(n.created_at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })}</span>
                  </button>
                </Popover.Close>
              </li>
            ))}
          </ul>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

export function Disclaimer() {
  return (
    <footer className="mt-14 flex items-start gap-3 rounded-[var(--radius-card)] border border-white/70 bg-white/55 px-5 py-4 text-xs leading-relaxed text-muted shadow-[var(--glass-highlight)]">
      <Info className="mt-0.5 size-4 shrink-0 text-ink/60" aria-hidden />
      <p>VITRAM is a decision-support prototype, not a lender, insurer, broker or adviser. Loan, card and insurance products shown are
        sample data with fictional institutions. Calculations use the inputs and assumptions shown; confirm terms with the provider before acting.</p>
    </footer>
  )
}


const ALL_NAV = [...PRIMARY, ...SECONDARY]

function readCollapsed() {
  try { return localStorage.getItem('vitram.sidebar') === 'collapsed' } catch { return false }
}

function NavItem({ to, label, icon: Icon, end, collapsed, onNavigate }: { to: string; label: string; icon: any; end?: boolean; collapsed?: boolean; onNavigate?: () => void }) {
  const link = (
    <NavLink to={to} end={end} onClick={onNavigate} aria-label={collapsed ? label : undefined}
      className={({ isActive }) => clsx('group relative flex min-h-12 items-center gap-3 rounded-[16px] text-[0.95rem] transition-[background-color,color,box-shadow] duration-[var(--dur)]',
        collapsed ? 'justify-center px-0' : 'px-3.5',
        isActive ? 'bg-[image:var(--grad-active)] font-semibold text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.22),inset_0_0_0_1px_rgb(154_164_240/0.45),0_8px_22px_rgb(52_67_181/0.45)]'
          : 'text-white/78 hover:bg-white/[0.08] hover:text-white')}>
      {({ isActive }) => (<>
        <Icon className={clsx('size-5 shrink-0', isActive ? 'text-white' : 'text-white/70 group-hover:text-white')} aria-hidden />
        {!collapsed && <span className="truncate">{label}</span>}
      </>)}
    </NavLink>
  )
  if (!collapsed) return link
  return (
    <Tooltip.Root delayDuration={150}>
      <Tooltip.Trigger asChild>{link}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content side="right" sideOffset={10} className="z-50 rounded-[10px] bg-navy-900 px-2.5 py-1.5 text-sm font-medium text-white shadow-[var(--elev-3)]">{label}</Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  )
}

/** Real setup progress (links home); hidden once everything is done. */
function SetupCard({ collapsed }: { collapsed?: boolean }) {
  const q = useDashboard()
  const steps = setupSteps(q.data)
  if (!steps.length || collapsed) return null
  const done = steps.filter((s) => s.done).length
  if (done === steps.length) return null
  const next = steps.find((s) => !s.done)!
  return (
    <Link to={next.to} className="group relative block overflow-hidden rounded-[18px] bg-white/[0.07] p-4 shadow-[inset_0_1px_0_rgb(255_255_255/0.08),inset_0_0_0_1px_rgb(255_255_255/0.08)] backdrop-blur-sm transition-colors hover:bg-white/[0.11]">
      <p className="text-xs font-medium text-white/65">Set up VITRAM · {done} of {steps.length}</p>
      <p className="mt-1 text-sm font-semibold text-white">Next: {next.label}</p>
      <span className="mt-3 block h-1.5 overflow-hidden rounded-full bg-white/10" aria-hidden>
        <span className="block h-full rounded-full bg-marigold" style={{ width: `${(done / steps.length) * 100}%` }} />
      </span>
      <ChevronRight className="absolute right-3 top-4 size-4 text-white/60 transition-transform group-hover:translate-x-0.5" aria-hidden />
    </Link>
  )
}

function ProfileCard({ collapsed, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const { user } = useAuth()
  return (
    <Link to="/profile" onClick={onNavigate} aria-label={collapsed ? `${user?.name ?? 'Your'} profile` : undefined}
      className={clsx('group flex items-center gap-3 rounded-[18px] bg-white/[0.06] p-2.5 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)] transition-colors hover:bg-white/[0.1]', collapsed && 'justify-center')}>
      <Avatar name={user?.name} />
      {!collapsed && (
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold text-white">{user?.name}</span>
          <span className="block text-xs text-white/65">View profile</span>
        </span>
      )}
      {!collapsed && <ChevronRight className="size-4 text-white/60 transition-transform group-hover:translate-x-0.5" aria-hidden />}
    </Link>
  )
}


function SidebarBody({ collapsed, onNavigate, onToggle }: { collapsed?: boolean; onNavigate?: () => void; onToggle?: () => void }) {
  return (
    <>
      <div className={clsx('mb-7 flex items-center gap-2', collapsed ? 'flex-col' : 'justify-between pr-1')}>
        <Link to="/" onClick={onNavigate} className="rounded-[12px] px-1.5 py-1" aria-label="VITRAM home"><Logo light tagline compact={collapsed} /></Link>
        {onToggle && (
          <button type="button" onClick={onToggle} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-expanded={!collapsed}
            className="inline-flex size-9 items-center justify-center rounded-full text-white/60 transition-colors hover:bg-white/10 hover:text-white">
            {collapsed ? <PanelLeftOpen className="size-[1.1rem]" aria-hidden /> : <PanelLeftClose className="size-[1.1rem]" aria-hidden />}
          </button>
        )}
      </div>
      <nav aria-label="Journeys" className="flex flex-col gap-1.5">{PRIMARY.map((n) => <NavItem key={n.to} {...n} collapsed={collapsed} onNavigate={onNavigate} />)}</nav>
      <div className="mx-3 my-5 border-t border-white/10" />
      <nav aria-label="Family, documents and settings" className="flex flex-col gap-1.5">{SECONDARY.map((n) => <NavItem key={n.to} {...n} collapsed={collapsed} onNavigate={onNavigate} />)}</nav>
      <div className="relative mt-auto flex flex-col gap-3 pt-6">
        <SidebarWave className="absolute -left-3 bottom-16 w-[115%] opacity-80" />
        <div className="relative"><SetupCard collapsed={collapsed} /></div>
        <div className="relative"><ProfileCard collapsed={collapsed} onNavigate={onNavigate} /></div>
      </div>
    </>
  )
}

/** Camera shortcut to every scan flow — shown only when this server can read photos and scans. */
function ScanMenu() {
  const vision = useVision()
  if (!vision?.configured) return null
  const item = 'flex min-h-11 cursor-pointer items-center gap-3 rounded-[var(--radius-control)] px-3 text-[0.95rem] outline-none data-[highlighted]:bg-indigo-soft/70'
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger aria-label="Scan a document" title="Scan a document"
        className="glass inline-flex size-12 items-center justify-center rounded-full text-ink/80 transition-colors hover:text-indigo-dark data-[state=open]:text-indigo-dark">
        <ScanLine className="size-5" aria-hidden />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={10} className="window-in z-50 w-72 rounded-[var(--radius-card)] border border-[var(--glass-hairline)] bg-white p-1.5 shadow-[var(--elev-4)]">
          <p className="px-3 pb-2 pt-2 text-xs text-muted">{vision.on_device ? 'Photos and scans are read on this device.' : 'Photos and scans are read by Gemini.'}</p>
          <DropdownMenu.Item asChild><Link to="/documents/receipts/new" className={item}><Camera className="size-4 text-muted" aria-hidden />Receipt or invoice</Link></DropdownMenu.Item>
          <DropdownMenu.Item asChild><Link to="/insurance/upload" className={item}><ShieldCheck className="size-4 text-muted" aria-hidden />Insurance policy</Link></DropdownMenu.Item>
          <DropdownMenu.Item asChild><Link to="/loans/analyze" className={item}><Landmark className="size-4 text-muted" aria-hidden />Loan document</Link></DropdownMenu.Item>
          <DropdownMenu.Item asChild><Link to="/onboarding/statement" className={item}><FileStack className="size-4 text-muted" aria-hidden />Bank statement</Link></DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}

function AccountMenu() {
  const { user, logout } = useAuth()
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const item = 'flex min-h-11 cursor-pointer items-center gap-3 rounded-[var(--radius-control)] px-3 text-[0.95rem] outline-none data-[highlighted]:bg-indigo-soft/70'
  return (
    <>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger aria-label="Account menu" className="inline-flex rounded-full transition-transform active:scale-95">
          <Avatar name={user?.name} size="lg" />
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content align="end" sideOffset={10} className="window-in glass-strong z-50 w-64 rounded-[var(--radius-card)] p-1.5">
            <div className="flex items-center gap-3 px-3 pb-3 pt-2">
              <Avatar name={user?.name} />
              <div className="min-w-0"><p className="truncate font-semibold">{user?.name}</p><p className="truncate text-xs text-muted">{user?.is_sample ? 'Sample workspace' : user?.email}</p></div>
            </div>
            <DropdownMenu.Separator className="mx-2 mb-1 h-px bg-[var(--glass-hairline)]" />
            <DropdownMenu.Item asChild><Link to="/profile" className={item}><UserRound className="size-4 text-muted" aria-hidden />My profile</Link></DropdownMenu.Item>
            <DropdownMenu.Item asChild><Link to="/settings" className={item}><Settings className="size-4 text-muted" aria-hidden />Settings</Link></DropdownMenu.Item>
            <DropdownMenu.Item asChild><Link to="/documents" className={item}><FileStack className="size-4 text-muted" aria-hidden />Documents & data</Link></DropdownMenu.Item>
            <DropdownMenu.Separator className="mx-2 my-1 h-px bg-[var(--glass-hairline)]" />
            <DropdownMenu.Item onSelect={() => setConfirm(true)} className={item}><LogOut className="size-4 text-muted" aria-hidden />Sign out</DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
      <ConfirmDialog open={confirm} onOpenChange={setConfirm} title="Sign out of VITRAM?" danger={false} confirmLabel="Sign out" busy={busy}
        description={user?.is_sample ? "This is a sample workspace with a generated password, so you can't sign back into it. You can open a new sample workspace any time." : 'Your data stays in your workspace. Sign in again with your email and password.'}
        onConfirm={async () => { setBusy(true); try { await logout() } finally { setBusy(false); setConfirm(false) } }} />
    </>
  )
}

export function AppShell({ children }: { children?: ReactNode }) {
  const { user } = useAuth()
  const { open, setOpen } = useSaathi()
  const { pathname } = useLocation()
  const [collapsed, setCollapsed] = useState(readCollapsed)
  const [drawer, setDrawer] = useState(false)
  const toggle = () => setCollapsed((c) => { try { localStorage.setItem('vitram.sidebar', c ? 'open' : 'collapsed') } catch { /* private mode */ } return !c })
  const current = ALL_NAV.find((n) => (n.to === '/' ? pathname === '/' : pathname.startsWith(n.to)))
  return (
    <Tooltip.Provider>
      <div className="app-bg" aria-hidden />
      <div className="flex min-h-dvh">
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[70] focus:rounded-full focus:bg-surface focus:px-4 focus:py-2 focus:shadow-[var(--elev-3)]">Skip to content</a>

        {/* Floating navy sidebar (desktop), collapsible to an icon rail with tooltips. */}
        <div className={clsx('sticky top-0 hidden h-dvh shrink-0 p-3 pr-0 transition-[width] duration-[var(--dur-slow)] ease-[var(--ease-out-soft)] lg:block', collapsed ? 'w-[var(--sidebar-w-collapsed)]' : 'w-[var(--sidebar-w)]')}>
          <aside className="sidebar-surface relative flex h-full flex-col overflow-hidden rounded-[var(--radius-window)] px-3 py-5" aria-label="Sidebar">
            <SidebarBody collapsed={collapsed} onToggle={toggle} />
          </aside>
        </div>

        <div className="relative flex min-w-0 flex-1 flex-col">
          {/* Floating topbar: search · notifications · Ask Vitt Saathi · account */}
          <div className="sticky top-0 z-30 px-3 pt-3 lg:px-[var(--page-gutter)]">
            <header className="mx-auto flex max-w-[var(--page-max)] items-center gap-2 sm:gap-3">
              <button type="button" onClick={() => setDrawer(true)} aria-label="Open menu"
                className="glass inline-flex size-12 shrink-0 items-center justify-center rounded-full text-ink/80 lg:hidden"><Menu className="size-5" aria-hidden /></button>
              <Link to="/" className="rounded-[12px] sm:hidden" aria-label="VITRAM home"><Logo /></Link>
              <GlobalSearch className="hidden min-w-0 max-w-2xl flex-1 sm:block" />
              <div className="ml-auto flex items-center gap-2 sm:gap-3">
                {user?.is_sample && <span className="hidden xl:block"><Badge tone="saathi">Sample workspace</Badge></span>}
                <ScanMenu />
                <Notifications />
                {!open && (
                  <button type="button" onClick={() => setOpen(true)} data-saathi-opener
                    className="hidden min-h-12 items-center gap-2 rounded-full bg-[image:var(--grad-saathi)] py-1.5 pl-1.5 pr-5 text-[0.95rem] font-semibold text-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.4),0_6px_18px_rgb(231_160_47/0.35)] transition-[filter,box-shadow] duration-[var(--dur)] hover:brightness-105 hover:shadow-[inset_0_1px_0_rgb(255_255_255/0.4),var(--glow-saathi)] md:inline-flex">
                    <SaathiMark className="size-9 bg-white/40" />Ask Vitt Saathi
                  </button>
                )}
                <AccountMenu />
              </div>
            </header>
          </div>
          <main id="main" className="@container mx-auto w-full max-w-[var(--page-max)] flex-1 px-4 pb-32 pt-8 sm:px-6 lg:px-[var(--page-gutter)] lg:pb-12 lg:pt-10">
            {children ?? <Outlet />}
            <Disclaimer />
          </main>
        </div>

        <SaathiPanel />

        {/* Mobile / tablet drawer with the full navigation. */}
        <Sheet open={drawer} onOpenChange={setDrawer} side="left" bare title="Menu" description={current ? `Current page: ${current.label}` : undefined}>
          <div className="sidebar-surface flex min-h-dvh flex-col px-4 py-5">
            <SheetClose className="absolute right-3 top-3 z-10 inline-flex size-11 items-center justify-center rounded-full text-white/75 hover:bg-white/10 hover:text-white" aria-label="Close menu"><X className="size-5" aria-hidden /></SheetClose>
            <SidebarBody onNavigate={() => setDrawer(false)} />
          </div>
        </Sheet>

        {!open && (
          <button type="button" onClick={() => setOpen(true)} aria-label="Ask Vitt Saathi" data-saathi-opener
            className="fixed bottom-[calc(5.75rem+env(safe-area-inset-bottom))] right-4 z-40 inline-flex size-14 items-center justify-center rounded-full bg-[image:var(--grad-saathi)] shadow-[inset_0_1px_0_rgb(255_255_255/0.35),var(--glow-saathi)] transition-transform active:scale-95 md:hidden">
            <SaathiMark className="size-9 bg-transparent" />
          </button>
        )}
        {/* Floating glass tab bar (phones and tablets). */}
        <div className="fixed inset-x-0 bottom-0 z-30 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] lg:hidden">
          <nav aria-label="Journeys" className="glass mx-auto grid max-w-lg grid-cols-5 rounded-[var(--radius-window)] p-1.5">
            {PRIMARY.map(({ to, label, icon: Icon, end }) => (
              <NavLink key={to} to={to} end={end}
                className={({ isActive }) => clsx('flex min-h-13 flex-col items-center justify-center gap-0.5 rounded-[20px] text-[0.72rem] transition-colors duration-[var(--dur)]',
                  isActive ? 'bg-indigo-soft font-semibold text-indigo-dark' : 'text-muted hover:text-ink')}>
                <Icon className="size-5" aria-hidden />{label}
              </NavLink>
            ))}
          </nav>
        </div>
      </div>
    </Tooltip.Provider>
  )
}
