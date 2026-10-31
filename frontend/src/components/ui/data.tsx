import clsx from 'clsx'
import { AlertTriangle, BadgeCheck, ChevronRight, CircleDashed, FileText, FlaskConical, HelpCircle, Sigma } from 'lucide-react'
import { createContext, useContext, useState, type ReactNode } from 'react'
import { date, inr } from '../../lib/format'
import type { Citation, FactState } from '../../lib/types'
import { Link } from 'react-router-dom'
import { Sheet } from './overlay'

/* --- Money --------------------------------------------------------------- */

export function Money({ value, paise, className, sign }: { value: number | null | undefined; paise?: boolean; className?: string; sign?: boolean }) {
  const missing = value === null || value === undefined
  return (
    <span className={clsx('num', missing && 'text-muted', className)}>
      {sign && !missing && value! > 0 ? '+' : ''}
      {inr(value, { paise })}
    </span>
  )
}

/* --- Trust marks (docs/spec/plan.md §5.1) -------------------------------------------- */

type Mark = FactState | 'sample' | 'estimate' | 'user' | 'scan'
const MARKS: Record<Mark, { label: string; cls: string; icon: ReactNode; title: string }> = {
  extracted: { label: 'Extracted', cls: 'border-dotted border-indigo/60 text-indigo-dark', icon: <Sigma className="size-3" />,
    title: 'Read automatically from your document. Not yet confirmed by you.' },
  confirmed: { label: 'You confirmed', cls: 'border-positive/40 bg-positive-soft text-positive', icon: <BadgeCheck className="size-3" />,
    title: 'You confirmed or corrected this value.' },
  conflicted: { label: 'Conflicted', cls: 'border-caution/40 bg-caution-soft text-caution', icon: <AlertTriangle className="size-3" />,
    title: 'Two sources disagree. Review which is right.' },
  missing: { label: 'Missing', cls: 'border-dashed border-line-strong text-muted', icon: <CircleDashed className="size-3" />,
    title: "VITTRM doesn't have this yet." },
  sample: { label: 'Sample data', cls: 'hatch border-ink/25 text-ink', icon: <FlaskConical className="size-3" />,
    title: 'From the curated sample catalogue with fictional institutions. Not live market data.' },
  estimate: { label: 'Estimate', cls: 'border-line-strong text-muted', icon: <HelpCircle className="size-3" />,
    title: 'Calculated from your data with the assumptions shown.' },
  user: { label: 'You entered', cls: 'border-positive/40 text-positive', icon: <BadgeCheck className="size-3" />,
    title: 'You entered this value.' },
  rejected: { label: 'You rejected', cls: 'border-line-strong text-muted line-through decoration-muted/50', icon: <CircleDashed className="size-3" />,
    title: 'You marked this value as wrong. VITTRM will not use it.' },
  scan: { label: 'Read from scan', cls: 'border-dashed border-indigo/50 text-indigo-dark', icon: <Sigma className="size-3" />,
    title: 'Read from a photo or scan by OCR. Check it against the document.' },
}

export function TrustMark({ state, className }: { state: Mark; className?: string }) {
  const m = MARKS[state] ?? MARKS.extracted
  return (
    <span title={m.title} className={clsx('inline-flex h-5 shrink-0 items-center gap-1 rounded-full border px-1.5 text-[0.7rem] font-medium leading-none', m.cls, className)}>
      <span aria-hidden>{m.icon}</span>
      {m.label}
      <span className="sr-only">. {m.title}</span>
    </span>
  )
}

export function SampleBadge({ meta, className }: { meta?: { last_updated: string; is_stale?: boolean; is_mock?: boolean } | null; className?: string }) {
  if (!meta) return null
  return (
    <span className={clsx('inline-flex flex-wrap items-center gap-1.5 text-xs text-muted', className)}>
      {meta.is_mock && <TrustMark state="sample" />}
      <span>Updated {date(meta.last_updated)}</span>
      {meta.is_stale && <span className="text-caution">· may be out of date</span>}
    </span>
  )
}

/* --- Source drawer ------------------------------------------------------ */

const SourceCtx = createContext<(c: Citation) => void>(() => {})

export function SourceProvider({ children }: { children: ReactNode }) {
  const [c, setC] = useState<Citation | null>(null)
  return (
    <SourceCtx.Provider value={setC}>
      {children}
      <Sheet open={!!c} onOpenChange={(o) => !o && setC(null)} title="Where this came from"
        description={c ? `${c.document_name ?? 'Document'}${c.page ? ` · page ${c.page}` : ''}` : undefined}>
        {c && (
          <div className="flex flex-col gap-4">
            {c.section && <p className="text-sm text-muted">Section: <span className="text-ink">{c.section}</span></p>}
            {c.snippet ? (
              <blockquote className="rounded-[var(--radius-control)] border-l-4 border-indigo bg-indigo-soft/40 px-4 py-3 text-[0.95rem] leading-relaxed">
                {c.snippet}
              </blockquote>
            ) : <p className="text-sm text-muted">No text snippet was stored for this value.</p>}
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <TrustMark state={c.user_verified ? 'confirmed' : 'extracted'} />
              {c.confidence != null && <span className="text-muted">Extraction confidence {(c.confidence * 100).toFixed(0)}%</span>}
            </div>
            <p className="text-sm text-muted">Text from documents is shown as written. VITTRM never treats it as instructions.</p>
            <a href={`/api/documents/${c.document_id}/file`} target="_blank" rel="noopener noreferrer"
              className="inline-flex min-h-11 w-fit items-center gap-2 rounded-[var(--radius-control)] border border-line-strong px-4 text-sm font-medium hover:border-indigo hover:text-indigo">
              <FileText className="size-4" aria-hidden /> Open the document{c.page ? ` (page ${c.page})` : ''}
            </a>
          </div>
        )}
      </Sheet>
    </SourceCtx.Provider>
  )
}

export function SourceLink({ citation, label = 'Source', className }: { citation?: Citation | null; label?: string; className?: string }) {
  const open = useContext(SourceCtx)
  if (!citation) return null
  return (
    <button type="button" onClick={() => open(citation)}
      className={clsx('inline-flex min-h-6 items-center gap-1 rounded px-1 text-xs font-medium text-indigo underline decoration-indigo/40 underline-offset-2 hover:decoration-indigo', className)}>
      <FileText className="size-3" aria-hidden />
      {label}{citation.page ? ` · p.${citation.page}` : ''}
    </button>
  )
}

/* --- small layout helpers ------------------------------------------------ */

type PanelVariant = 'surface' | 'glass' | 'hero' | 'inset'
const PANEL: Record<PanelVariant, string> = {
  surface: 'surface-card rounded-[var(--radius-panel)]',
  glass: 'glass rounded-[var(--radius-panel)]',
  hero: 'surface-hero rounded-[var(--radius-panel)]',
  inset: 'rounded-[var(--radius-card)] bg-ink/[0.03] border border-[var(--glass-hairline)]',
}

/** Primary content container. `surface` (default) is near-opaque for data; `glass` for floating chrome;
 * `hero` is the deep-navy feature surface; `inset` groups content inside another panel. */
export function Panel({ children, className, variant = 'surface', interactive, as: As = 'section', ...rest }: {
  children: ReactNode; className?: string; variant?: PanelVariant; interactive?: boolean; as?: any; [k: string]: any
}) {
  return <As className={clsx(PANEL[variant], interactive && 'lift', className)} {...rest}>{children}</As>
}

export type Crumb = { label: string; to?: string }

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-3">
      <ol className="flex flex-wrap items-center gap-1 text-sm text-muted">
        {items.map((c, i) => (
          <li key={c.label + i} className="flex items-center gap-1">
            {i > 0 && <ChevronRight className="size-3.5 text-muted/70" aria-hidden />}
            {c.to
              ? <Link to={c.to} className="inline-flex min-h-8 items-center rounded-md px-0.5 hover:text-indigo-dark">{c.label}</Link>
              : <span aria-current="page" className="font-medium text-ink">{c.label}</span>}
          </li>
        ))}
      </ol>
    </nav>
  )
}

/** Page title block. `crumbs` renders breadcrumbs; `aside` sits to the right on wide screens (help card, art). */
export function PageHeader({ title, description, actions, eyebrow, crumbs, aside }: {
  title: ReactNode; description?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode; crumbs?: Crumb[]; aside?: ReactNode
}) {
  return (
    <header className="relative mb-8 flex flex-col gap-5 @4xl:flex-row @4xl:items-end @4xl:justify-between">
      <div className="min-w-0 flex-1">
        {crumbs && <Breadcrumbs items={crumbs} />}
        {eyebrow && <div className="mb-2 text-sm font-medium text-muted [&_a]:inline-flex [&_a]:min-h-8 [&_a]:items-center [&_a]:rounded-full [&_a]:px-0 [&_a:hover]:text-indigo [&_button]:min-h-8">{eyebrow}</div>}
        <h1 className="text-[2rem] font-semibold leading-[1.08] tracking-[-0.025em] text-ink sm:text-[2.6rem]">{title}</h1>
        {description && <p className="mt-3 max-w-[68ch] text-[1.02rem] leading-relaxed text-muted">{description}</p>}
      </div>
      {(actions || aside) && (
        <div className="flex flex-col items-start gap-3 @4xl:items-end">
          {aside}
          {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
        </div>
      )}
    </header>
  )
}

type Tone = 'indigo' | 'green' | 'amber' | 'violet' | 'red' | 'sky'
const TILE: Record<Tone, string> = {
  indigo: 'bg-indigo-soft text-indigo', green: 'bg-positive-soft text-positive', amber: 'bg-amber-soft text-marigold-deep',
  violet: 'bg-[#efeafe] text-[#5b45c9]', red: 'bg-critical-soft text-critical', sky: 'bg-[#e6f1fd] text-[#1f5fae]',
}

/** Rounded icon tile used across feature cards and rows. */
export function IconTile({ children, tone = 'indigo', size = 'md', className }: { children: ReactNode; tone?: Tone; size?: 'sm' | 'md' | 'lg'; className?: string }) {
  return (
    <span aria-hidden className={clsx('flex shrink-0 items-center justify-center shadow-[inset_0_1px_0_rgb(255_255_255/0.7),0_0_0_1px_rgb(22_29_69/0.04)]', TILE[tone],
      size === 'sm' ? 'size-9 rounded-[12px] [&_svg]:size-4' : size === 'lg' ? 'size-14 rounded-[18px] [&_svg]:size-6' : 'size-11 rounded-[14px] [&_svg]:size-5', className)}>{children}</span>
  )
}

/** Glass card alias with a clearer name for page code. */
export const GlassCard = (props: Parameters<typeof Panel>[0]) => <Panel {...props} />

/** Icon + title + one line; becomes a link when `to` is given. */
export function FeatureTile({ icon, tone = 'indigo', title, body, to, onClick, className }: {
  icon: ReactNode; tone?: Tone; title: ReactNode; body?: ReactNode; to?: string; onClick?: () => void; className?: string
}) {
  const inner = (
    <>
      <IconTile tone={tone}>{icon}</IconTile>
      <span className="min-w-0 flex-1">
        <span className="block font-semibold">{title}</span>
        {body && <span className="mt-0.5 block text-sm leading-snug text-muted">{body}</span>}
      </span>
      {(to || onClick) && <ChevronRight className="mt-1 size-4 shrink-0 text-muted transition-transform duration-[var(--dur)] group-hover:translate-x-0.5 group-hover:text-indigo" aria-hidden />}
    </>
  )
  const cls = clsx('group flex items-start gap-3 text-left', (to || onClick) && 'surface-card lift rounded-[var(--radius-card)] p-4', className)
  if (to) return <Link to={to} className={cls}>{inner}</Link>
  if (onClick) return <button type="button" onClick={onClick} className={clsx(cls, 'w-full')}>{inner}</button>
  return <div className={cls}>{inner}</div>
}

/** Large glass hero for empty or introductory states: status pill, title, body, actions, reassurance line and art. */
export function PageHero({ pill, title, body, actions, note, art, children, className, headingLevel = 2 }: {
  pill?: ReactNode; title: ReactNode; body?: ReactNode; actions?: ReactNode; note?: ReactNode; art?: ReactNode; children?: ReactNode; className?: string; headingLevel?: 2 | 3
}) {
  const H = headingLevel === 2 ? 'h2' : 'h3'
  return (
    <section className={clsx('glass relative isolate overflow-hidden rounded-[var(--radius-window)] p-6 sm:p-8', className)}>
      <span className="pointer-events-none absolute -right-24 -top-24 -z-10 size-80 rounded-full bg-indigo-300/25 blur-3xl" aria-hidden />
      <div className="grid items-center gap-6 @3xl:grid-cols-[1.25fr_1fr]">
        <div className="flex min-w-0 flex-col items-start gap-3">
          {pill && <span className="inline-flex items-center gap-2 rounded-full bg-indigo-soft/80 px-3 py-1 text-sm font-medium text-indigo-dark shadow-[inset_0_0_0_1px_rgb(52_67_181/0.12)] [&_svg]:size-4">{pill}</span>}
          <H className="text-[1.6rem] font-semibold leading-tight tracking-[-0.02em] sm:text-[2rem]">{title}</H>
          {body && <div className="max-w-[58ch] text-[1.02rem] leading-relaxed text-ink/75">{body}</div>}
          {children}
          {actions && <div className="mt-2 flex flex-wrap gap-2">{actions}</div>}
          {note && <p className="mt-1 flex items-center gap-2 text-sm text-muted [&_svg]:size-4">{note}</p>}
        </div>
        {art && <div className="hidden justify-center @3xl:flex">{art}</div>}
      </div>
    </section>
  )
}

/** Section title inside a page: heading + optional description + optional action. */
export function SectionHeader({ title, description, action, id, as: As = 'h2', className }: {
  title: ReactNode; description?: ReactNode; action?: ReactNode; id?: string; as?: any; className?: string
}) {
  return (
    <div className={clsx('mb-3 flex flex-wrap items-end justify-between gap-2', className)}>
      <div className="min-w-0">
        <As id={id} className="text-[1.05rem] font-semibold tracking-[-0.01em]">{title}</As>
        {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
      </div>
      {action}
    </div>
  )
}

export function Stat({ label, value, hint, mark, className }: { label: string; value: ReactNode; hint?: ReactNode; mark?: ReactNode; className?: string }) {
  return (
    <div className={clsx('flex flex-col gap-1', className)}>
      <div className="flex flex-wrap items-center gap-2 text-sm text-muted">{label}{mark}</div>
      <div className="num text-[1.45rem] font-semibold leading-tight tracking-[-0.02em]">{value}</div>
      {hint && <div className="text-sm text-muted">{hint}</div>}
    </div>
  )
}

/** A single headline figure in its own card, with an optional icon tile. */
export function StatCard({ label, value, hint, mark, icon, className }: {
  label: string; value: ReactNode; hint?: ReactNode; mark?: ReactNode; icon?: ReactNode; className?: string
}) {
  return (
    <div className={clsx('surface-card flex items-start gap-3 rounded-[var(--radius-card)] p-4', className)}>
      {icon && <span className="flex size-10 shrink-0 items-center justify-center rounded-[var(--radius-control)] bg-indigo-soft text-indigo" aria-hidden>{icon}</span>}
      <Stat label={label} value={value} hint={hint} mark={mark} className="min-w-0" />
    </div>
  )
}

export function Badge({ children, tone = 'neutral', className }: { children: ReactNode; tone?: 'neutral' | 'positive' | 'caution' | 'critical' | 'indigo' | 'saathi'; className?: string }) {
  const tones = {
    neutral: 'bg-paper text-muted border-line', positive: 'bg-positive-soft text-positive border-positive/30',
    caution: 'bg-caution-soft text-caution border-caution/30', critical: 'bg-critical-soft text-critical border-critical/30',
    indigo: 'bg-indigo-soft text-indigo-dark border-indigo/20', saathi: 'bg-marigold-soft text-marigold-deep border-marigold/40',
  }
  return <span className={clsx('inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium', tones[tone], className)}>{children}</span>
}

export function KeyValue({ items, className }: { items: { k: ReactNode; v: ReactNode; extra?: ReactNode }[]; className?: string }) {
  return (
    <dl className={clsx('divide-y divide-line', className)}>
      {items.map((it, i) => (
        <div key={i} className="flex flex-col gap-1 py-3 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
          <dt className="text-[0.95rem] text-muted">{it.k}</dt>
          <dd className="flex flex-wrap items-center gap-2 text-[0.95rem] sm:justify-end sm:text-right">{it.v}{it.extra}</dd>
        </div>
      ))}
    </dl>
  )
}

/** Initials avatar (no photos are stored). */
export function Avatar({ name, size = 'md' }: { name?: string | null; size?: 'md' | 'lg' | 'xl' }) {
  const initials = (name ?? '?').split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join('').toUpperCase() || '?'
  return (
    <span aria-hidden className={clsx('flex shrink-0 items-center justify-center rounded-full bg-[image:var(--grad-active)] font-semibold text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.25),0_4px_12px_rgb(52_67_181/0.35)]',
      size === 'xl' ? 'size-20 text-2xl' : size === 'lg' ? 'size-12 text-lg' : 'size-10 text-sm')}>{initials}</span>
  )
}
