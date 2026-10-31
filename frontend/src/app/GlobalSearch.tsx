import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { CornerDownLeft, FileText, Search, Sparkles } from 'lucide-react'
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { get } from '../lib/api'
import type { DocumentRow } from '../lib/types'
import { useSaathi } from '../features/saathi/context'

/** Honest search: it only finds VITTRM pages and the user's own documents; anything else goes to Vitt Saathi as a question. */
const PAGES: { label: string; to: string; hint: string; words: string }[] = [
  { label: 'Home', to: '/', hint: 'Overview', words: 'dashboard overview summary' },
  { label: 'Loans', to: '/loans', hint: 'Loans', words: 'borrow credit interest' },
  { label: 'Find a loan', to: '/loans/need', hint: 'Loans', words: 'explore compare personal home car vehicle education' },
  { label: 'Analyse a loan document', to: '/loans/analyze', hint: 'Loans', words: 'kfs sanction letter agreement upload' },
  { label: 'Insurance', to: '/insurance', hint: 'Insurance', words: 'policy cover health life' },
  { label: 'Add a policy', to: '/insurance/upload', hint: 'Insurance', words: 'upload policy schedule' },
  { label: 'Emergency help', to: '/insurance/emergency', hint: 'Insurance', words: 'hospital claim cashless urgent' },
  { label: 'Explore insurance plans', to: '/insurance/explore', hint: 'Insurance', words: 'compare plans cover' },
  { label: 'Request a consultation call', to: '/insurance/consult', hint: 'Insurance', words: 'call advisor expert' },
  { label: 'Credit cards', to: '/cards', hint: 'Cards', words: 'card rewards points dues' },
  { label: 'Which card should I use?', to: '/cards/optimize', hint: 'Cards', words: 'best card purchase rewards optimise optimize' },
  { label: 'EMIs', to: '/emis', hint: 'EMIs', words: 'instalment installment calendar due' },
  { label: 'Reminder settings', to: '/settings/reminders', hint: 'EMIs', words: 'whatsapp reminders notify alerts' },
  { label: 'Family', to: '/family', hint: 'Family', words: 'members spouse parents children' },
  { label: 'Goals', to: '/goals', hint: 'Goals', words: 'save saving target fund' },
  { label: 'Spending insights', to: '/insights', hint: 'Insights', words: 'trends subscriptions unusual spending patterns' },
  { label: 'Cash-flow estimate', to: '/forecast', hint: 'Insights', words: 'forecast balance upcoming month cash flow' },
  { label: 'Scan a receipt', to: '/documents/receipts/new', hint: 'Documents', words: 'receipt invoice bill photo camera scan' },
  { label: 'Documents & data', to: '/documents', hint: 'Documents', words: 'files uploads statements extracted' },
  { label: 'Upload a bank statement', to: '/onboarding/statement', hint: 'Documents', words: 'statement bank csv pdf upload' },
  { label: 'Review your financial profile', to: '/profile/review', hint: 'Profile', words: 'income salary confirm recurring' },
  { label: 'My profile', to: '/profile', hint: 'Account', words: 'account personal password language' },
  { label: 'Settings', to: '/settings', hint: 'Account', words: 'consents permissions delete data services' },
]

const PLACEHOLDER: [RegExp, string][] = [
  [/^\/loans/, 'Ask anything about loans, interest rates, eligibility…'],
  [/^\/insurance/, 'Ask anything about your insurance coverage, claims or policies…'],
  [/^\/cards/, 'Ask anything about cards, rewards, due dates…'],
  [/^\/emis/, 'Ask anything about EMIs, due dates or prepayment…'],
  [/^\/family/, "Search or ask about your family's cover…"],
  [/^\/documents/, 'Search documents, or ask about them…'],
  [/.*/, 'Search VITTRM or ask anything about loans, insurance, cards, EMIs…'],
]

type Item = { kind: 'ask' | 'page' | 'doc'; label: string; hint?: string; to?: string }

export function GlobalSearch({ className }: { className?: string }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const { ask } = useSaathi()
  const listId = useId()
  const placeholder = PLACEHOLDER.find(([re]) => re.test(pathname))![1]
  const docs = useQuery({ queryKey: ['documents'], queryFn: () => get<DocumentRow[]>('/documents'), enabled: open, staleTime: 30_000 })

  const items = useMemo<Item[]>(() => {
    const t = q.trim().toLowerCase()
    if (!t) return PAGES.slice(0, 6).map((p) => ({ kind: 'page', label: p.label, hint: p.hint, to: p.to }))
    const words = t.split(/\s+/)
    const pages = PAGES.filter((p) => words.every((w) => `${p.label} ${p.words}`.toLowerCase().includes(w))).slice(0, 5)
      .map<Item>((p) => ({ kind: 'page', label: p.label, hint: p.hint, to: p.to }))
    const ds = (docs.data ?? []).filter((d) => d.display_name.toLowerCase().includes(t)).slice(0, 4)
      .map<Item>((d) => ({ kind: 'doc', label: d.display_name, hint: d.type_label, to: `/documents?focus=${d.id}` }))
    return [{ kind: 'ask', label: q.trim() }, ...pages, ...ds]
  }, [q, docs.data])

  useEffect(() => {
    function onKey(e: globalThis.KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); input.current?.focus(); setOpen(true) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  function choose(it: Item | undefined) {
    if (!it) return
    setOpen(false)
    setQ('')
    input.current?.blur()
    if (it.kind === 'ask') ask(it.label)
    else if (it.to) navigate(it.to)
  }
  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setActive((a) => Math.min(a + 1, items.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); choose(items[active]) }
    else if (e.key === 'Escape') { setOpen(false); input.current?.blur() }
  }
  const mac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

  return (
    <div className={clsx('relative', className)}>
      <div className="glass relative flex min-h-12 items-center rounded-full">
        <Search className="pointer-events-none absolute left-4 size-[1.1rem] text-muted" aria-hidden />
        <input ref={input} value={q} placeholder={placeholder}
          role="combobox" aria-expanded={open} aria-controls={listId} aria-autocomplete="list" aria-label="Search VITTRM or ask Vitt Saathi"
          aria-activedescendant={open && items[active] ? `${listId}-${active}` : undefined}
          onChange={(e) => { setQ(e.target.value); setActive(0); setOpen(true) }}
          onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 120)} onKeyDown={onKeyDown}
          className="min-h-12 w-full min-w-0 rounded-full bg-transparent pl-11 pr-16 text-[0.95rem] text-ink placeholder:text-muted focus:outline-none focus-visible:shadow-[var(--ring)]" />
        <kbd className="pointer-events-none absolute right-2.5 hidden rounded-[8px] bg-ink/[0.06] px-2 py-0.5 font-sans text-xs text-muted sm:inline" aria-hidden>{mac ? '⌘' : 'Ctrl'} K</kbd>
      </div>
      {open && (
        <ul id={listId} role="listbox" aria-label="Suggestions"
          className="window-in absolute inset-x-0 top-[calc(100%+0.5rem)] z-50 max-h-[26rem] overflow-y-auto rounded-[var(--radius-card)] border border-[var(--glass-hairline)] bg-white p-1.5 shadow-[var(--elev-4)]">
          {!q.trim() && <li role="presentation" className="px-3 pb-1 pt-2 text-xs font-medium text-muted">Go to</li>}
          {items.map((it, i) => (
            <li key={it.kind + it.label + i} id={`${listId}-${i}`} role="option" aria-selected={i === active}
              onMouseDown={(e) => { e.preventDefault(); choose(it) }} onMouseEnter={() => setActive(i)}
              className={clsx('flex min-h-11 cursor-pointer items-center gap-3 rounded-[12px] px-3 text-[0.95rem]', i === active ? 'bg-indigo-soft/80' : '')}>
              {it.kind === 'ask' ? <span className="flex size-7 items-center justify-center rounded-full bg-[image:var(--grad-saathi)] text-ink" aria-hidden><Sparkles className="size-4" /></span>
                : it.kind === 'doc' ? <FileText className="size-4 shrink-0 text-muted" aria-hidden /> : <Search className="size-4 shrink-0 text-muted" aria-hidden />}
              <span className="min-w-0 flex-1 truncate">{it.kind === 'ask' ? <>Ask Vitt Saathi: <b className="font-semibold">“{it.label}”</b></> : it.label}</span>
              {it.hint && <span className="shrink-0 text-xs text-muted">{it.hint}</span>}
              {i === active && <CornerDownLeft className="size-3.5 shrink-0 text-muted" aria-hidden />}
            </li>
          ))}
          {q.trim() && items.length === 1 && <li role="presentation" className="px-3 py-2 text-sm text-muted">No pages or documents match. Press Enter to ask Vitt Saathi.</li>}
        </ul>
      )}
    </div>
  )
}
