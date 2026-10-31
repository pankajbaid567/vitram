import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import { EmptyState } from '../components/ui/feedback'
import { Panel, StatCard } from '../components/ui/data'
import { CardFace } from '../features/cards/Cards'
import { CashFlowChart } from '../features/dashboard/CashFlowChart'

afterEach(cleanup)

const series = [
  { month: '2026-03', inflow: 118200, outflow: 90000 },
  { month: '2026-04', inflow: 118200, outflow: 150000 },
  { month: '2026-05', inflow: 60000, outflow: 40000 },
]

describe('Cash-flow chart (dashboard hero)', () => {
  it('always exposes the data as a table to screen readers, with Indian grouping', () => {
    render(<CashFlowChart series={series} periodStart="2026-03-01" periodEnd="2026-05-31" />)
    const table = screen.getByRole('table')
    expect(within(table).getAllByText('₹1,18,200')).toHaveLength(2)
    expect(within(table).getByText('₹1,50,000')).toBeTruthy()
    expect(screen.queryByText(/partial/)).toBeNull()
  })
  it('marks months at the edges of the statement as partial', () => {
    render(<CashFlowChart series={series} periodStart="2026-03-12" periodEnd="2026-05-20" />)
    expect(screen.getByText(/March 2026 \(partial month\)/)).toBeTruthy()
    expect(screen.getByText(/May 2026 \(partial month\)/)).toBeTruthy()
    expect(screen.queryByText(/April 2026 \(partial month\)/)).toBeNull()
  })
  it('toggles to a visible table with net per month', () => {
    render(<CashFlowChart series={series} periodStart="2026-03-01" periodEnd="2026-05-31" />)
    fireEvent.click(screen.getByRole('button', { name: /table/i }))
    expect(screen.getByRole('button', { name: /chart/i })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('−₹31,800')).toBeTruthy() // April: out exceeds in
  })
  it('shows only the last six months', () => {
    const long = Array.from({ length: 9 }, (_, i) => ({ month: `2026-0${i + 1}`, inflow: 1, outflow: 1 }))
    render(<CashFlowChart series={long} />)
    expect(screen.getAllByRole('row')).toHaveLength(7) // header + 6
  })
})

describe('Card face', () => {
  it('shows only the last four digits, read as "ending"', () => {
    render(<CardFace card={{ id: 'c1', nickname: 'Travel', last4: '4821', issuer: 'Horizon Bank (sample)', network: 'Visa' }} />)
    expect(screen.getByText('ending')).toHaveClass('sr-only')
    expect(document.body.textContent).toContain('4821')
    expect(document.body.textContent).not.toMatch(/\d{5,}/)
  })
  it('says when the last four are missing instead of inventing them', () => {
    render(<CardFace card={{ id: 'c2', nickname: 'Other card' }} />)
    expect(screen.getByText('Last 4 not added')).toBeTruthy()
  })
})

describe('Glass primitives', () => {
  it('Panel variants map to surface classes and pass through attributes', () => {
    render(<><Panel data-testid="a">x</Panel><Panel variant="hero" data-testid="b">y</Panel><Panel variant="glass" interactive data-testid="c">z</Panel></>)
    expect(screen.getByTestId('a')).toHaveClass('surface-card')
    expect(screen.getByTestId('b')).toHaveClass('surface-hero')
    expect(screen.getByTestId('c')).toHaveClass('glass', 'lift')
  })
  it('StatCard and EmptyState render their content', () => {
    render(<MemoryRouter><StatCard label="Monthly EMIs" value="₹24,960" /><EmptyState title="No cards yet" body="Add one." /></MemoryRouter>)
    expect(screen.getByText('Monthly EMIs')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'No cards yet' })).toBeTruthy()
  })
})
