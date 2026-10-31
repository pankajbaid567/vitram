import { usePreference } from '../../lib/preferences'
import clsx from 'clsx'
import { BarChart3, Table2 } from 'lucide-react'
import { useState } from 'react'
import { inr } from '../../lib/format'

/** Money in vs out per calendar month, from the processed statement (profile cashflow_metrics.monthly_series).
 * Designed for the navy hero surface; palette validated against #1B2352 (dataviz validator, CVD ΔE 20). */
type Point = { month: string; inflow: number; outflow: number }

const monthName = (k: string, style: 'short' | 'long' = 'short') =>
  new Date(`${k}-01T00:00:00`).toLocaleDateString('en-IN', style === 'long' ? { month: 'long', year: 'numeric' } : { month: 'short' })

function niceMax(v: number) {
  if (v <= 0) return 1
  const p = 10 ** Math.floor(Math.log10(v))
  const n = v / p
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p
}
const axis = (v: number) => (v >= 1e7 ? `₹${+(v / 1e7).toFixed(1)}Cr` : v >= 1e5 ? `₹${+(v / 1e5).toFixed(1)}L` : v >= 1e3 ? `₹${+(v / 1e3).toFixed(0)}k` : `₹${v}`)

function isPartial(k: string, start?: string, end?: string) {
  if (start && start.slice(0, 7) === k && start.slice(8, 10) !== '01') return true
  if (end && end.slice(0, 7) === k) {
    const d = new Date(`${end}T00:00:00`)
    const last = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate()
    if (d.getDate() !== last) return true
  }
  return false
}

export function CashFlowChart({ series, periodStart, periodEnd }: { series: Point[]; periodStart?: string; periodEnd?: string }) {
  const [table, setTable] = usePreference('cashflow-table', false)
  const [hover, setHover] = useState<number | null>(null)
  const data = series.slice(-6).map((p) => ({ ...p, partial: isPartial(p.month, periodStart, periodEnd) }))
  const max = niceMax(Math.max(...data.map((d) => Math.max(d.inflow, d.outflow)), 0))
  const ticks = [max, max / 2, 0]
  const anyPartial = data.some((d) => d.partial)

  return (
    <figure className="flex flex-col gap-3" aria-labelledby="cf-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <figcaption id="cf-title" className="text-sm font-medium text-white/85">Money in and out, by month</figcaption>
        <div className="flex items-center gap-3">
          <ul className="flex items-center gap-3 text-xs text-white/80" aria-label="Legend">
            <li className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm bg-viz-in" aria-hidden />Money in</li>
            <li className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm bg-viz-out" aria-hidden />Money out</li>
          </ul>
          <button type="button" onClick={() => setTable(!table)} aria-pressed={table}
            className="inline-flex min-h-8 items-center gap-1.5 rounded-full bg-white/10 px-2.5 text-xs font-medium text-white/85 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.12)] transition-colors hover:bg-white/15 hover:text-white">
            {table ? <BarChart3 className="size-3.5" aria-hidden /> : <Table2 className="size-3.5" aria-hidden />}{table ? 'Chart' : 'Table'}
          </button>
        </div>
      </div>

      {table ? (
        <div className="overflow-x-auto rounded-[var(--radius-control)] bg-white/[0.06] shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]">
          <table className="num w-full text-left text-sm text-white">
            <thead className="text-xs text-white/70"><tr><th className="px-3 py-2 font-medium">Month</th><th className="px-3 py-2 text-right font-medium">Money in</th><th className="px-3 py-2 text-right font-medium">Money out</th><th className="px-3 py-2 text-right font-medium">Net</th></tr></thead>
            <tbody className="divide-y divide-white/10">
              {data.map((d) => (
                <tr key={d.month}>
                  <td className="px-3 py-2">{monthName(d.month, 'long')}{d.partial && <span className="text-white/65"> (partial)</span>}</td>
                  <td className="px-3 py-2 text-right">{inr(d.inflow)}</td>
                  <td className="px-3 py-2 text-right">{inr(d.outflow)}</td>
                  <td className="px-3 py-2 text-right">{d.inflow - d.outflow >= 0 ? '+' : '−'}{inr(Math.abs(d.inflow - d.outflow))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="relative" aria-hidden>
          {/* recessive grid */}
          <div className="pointer-events-none absolute inset-0 bottom-6 flex flex-col justify-between">
            {ticks.map((t) => (
              <div key={t} className="flex items-center gap-2">
                <span className="num w-10 shrink-0 text-right text-[0.68rem] text-white/60">{axis(t)}</span>
                <span className={clsx('h-px flex-1', t === 0 ? 'bg-white/25' : 'bg-white/[0.08]')} />
              </div>
            ))}
          </div>
          <div className="relative ml-12 flex h-44 gap-1 sm:h-48">
            {data.map((d, i) => {
              const net = d.inflow - d.outflow
              return (
                <div key={d.month} className="relative flex flex-1 flex-col" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                  <div className={clsx('flex flex-1 items-end justify-center gap-[2px] rounded-t-lg pb-px transition-colors', hover === i && 'bg-white/[0.06]')}>
                    {(['inflow', 'outflow'] as const).map((k) => (
                      <span key={k} className={clsx('relative w-[34%] max-w-6 overflow-hidden rounded-t-[4px]', k === 'inflow' ? 'bg-viz-in' : 'bg-viz-out', d.partial && 'opacity-60')}
                        style={{ height: `${Math.max((d[k] / max) * 100, d[k] > 0 ? 1.5 : 0)}%` }}>
                        {d.partial && <span className="absolute inset-0 bg-[repeating-linear-gradient(-45deg,transparent_0_3px,rgb(15_21_56/0.45)_3px_5px)]" />}
                      </span>
                    ))}
                  </div>
                  <span className="mt-1.5 h-4 text-center text-[0.72rem] leading-4 text-white/75">{monthName(d.month)}</span>
                  {hover === i && (
                    <div className={clsx('pointer-events-none absolute bottom-[calc(100%-1.5rem)] z-10 w-44 rounded-[var(--radius-control)] bg-white p-2.5 text-xs text-ink shadow-[var(--elev-3)]',
                      i < data.length / 2 ? 'left-0' : 'right-0')}>
                      <p className="mb-1 font-semibold">{monthName(d.month, 'long')}{d.partial && <span className="font-normal text-muted"> · partial</span>}</p>
                      <p className="num flex justify-between"><span className="flex items-center gap-1.5"><span className="size-2 rounded-sm bg-viz-in" />In</span>{inr(d.inflow)}</p>
                      <p className="num flex justify-between"><span className="flex items-center gap-1.5"><span className="size-2 rounded-sm bg-viz-out" />Out</span>{inr(d.outflow)}</p>
                      <p className="num mt-1 flex justify-between border-t border-line pt-1 font-medium"><span>Net</span>{net >= 0 ? '+' : '−'}{inr(Math.abs(net))}</p>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
      {/* Screen readers always get the table, whichever view is showing. */}
      {!table && (
        <table className="sr-only">
          <caption>Money in and out by month</caption>
          <thead><tr><th>Month</th><th>Money in</th><th>Money out</th></tr></thead>
          <tbody>{data.map((d) => <tr key={d.month}><td>{monthName(d.month, 'long')}{d.partial ? ' (partial month)' : ''}</td><td>{inr(d.inflow)}</td><td>{inr(d.outflow)}</td></tr>)}</tbody>
        </table>
      )}
      {anyPartial && !table && <p className="text-xs text-white/65">Striped bars are partial months at the edges of your statement.</p>}
    </figure>
  )
}
