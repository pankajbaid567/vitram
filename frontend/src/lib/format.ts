/** Indian number formatting (₹12,34,567) and dates. */

const inrFmt = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const inrFmt2 = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2, maximumFractionDigits: 2 })
const numFmt = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })

export function inr(v: number | null | undefined, opts: { paise?: boolean } = {}): string {
  if (v === null || v === undefined || Number.isNaN(v)) return 'Not available'
  return (opts.paise ? inrFmt2 : inrFmt).format(v)
}

export function num(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined) return '—'
  return digits ? v.toLocaleString('en-IN', { maximumFractionDigits: digits }) : numFmt.format(v)
}

export function pct(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return 'Not available'
  return `${v.toFixed(digits).replace(/\.?0+$/, '')}%`
}

export function compactInr(v: number | null | undefined): string {
  if (v === null || v === undefined) return 'Not available'
  if (Math.abs(v) >= 1e7) return `₹${(v / 1e7).toFixed(2).replace(/\.?0+$/, '')} Cr`
  if (Math.abs(v) >= 1e5) return `₹${(v / 1e5).toFixed(2).replace(/\.?0+$/, '')} L`
  return inr(v)
}

export function date(iso: string | null | undefined, style: 'short' | 'long' = 'short'): string {
  if (!iso) return 'Not available'
  const d = new Date(iso.length === 10 ? iso + 'T00:00:00' : iso)
  return d.toLocaleDateString('en-IN', style === 'long' ? { day: 'numeric', month: 'long', year: 'numeric' } : { day: 'numeric', month: 'short', year: 'numeric' })
}

export function dayMonth(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

export function daysFromToday(iso: string): number {
  const d = new Date(iso + 'T00:00:00')
  const t = new Date()
  t.setHours(0, 0, 0, 0)
  return Math.round((d.getTime() - t.getTime()) / 86400000)
}

export function relDays(iso: string): string {
  const n = daysFromToday(iso)
  if (n === 0) return 'today'
  if (n === 1) return 'tomorrow'
  if (n === -1) return 'yesterday'
  return n > 0 ? `in ${n} days` : `${-n} days ago`
}

export function months(n: number | null | undefined): string {
  if (!n) return 'Not available'
  if (n % 12 === 0) return `${n / 12} year${n === 12 ? '' : 's'}`
  return `${n} months`
}

export function parseAmountInput(s: string): number | null {
  const clean = s.replace(/[₹,\s]/g, '')
  if (!clean) return null
  const v = Number(clean)
  return Number.isFinite(v) ? v : null
}

export function ordinal(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  const s = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th'
  return `${n}${s}`
}
