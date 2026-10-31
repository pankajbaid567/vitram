import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Money, TrustMark } from '../components/ui/data'
import { Field, Input } from '../components/ui/field'
import { compactInr, inr, ordinal, parseAmountInput, pct } from '../lib/format'

describe('Indian money formatting', () => {
  it('uses lakh/crore digit grouping', () => {
    expect(inr(1234567)).toBe('₹12,34,567')
    expect(inr(300000)).toBe('₹3,00,000')
    expect(compactInr(1500000)).toBe('₹15 L')
    expect(compactInr(10000000)).toBe('₹1 Cr')
  })
  it('never shows a missing value as zero', () => {
    expect(inr(null)).toBe('Not available')
    render(<Money value={undefined} />)
    expect(screen.getByText('Not available')).toBeInTheDocument()
  })
  it('parses user amounts and formats helpers', () => {
    expect(parseAmountInput('₹3,00,000')).toBe(300000)
    expect(parseAmountInput('abc')).toBeNull()
    expect(ordinal(1)).toBe('1st')
    expect(ordinal(3)).toBe('3rd')
    expect(ordinal(11)).toBe('11th')
    expect(ordinal(22)).toBe('22nd')
    expect(pct(17.6167)).toBe('17.62%')
  })
})

describe('TrustMark', () => {
  it('states provenance in text, not colour alone', () => {
    render(<TrustMark state="extracted" />)
    expect(screen.getByText('Extracted')).toBeInTheDocument()
    expect(screen.getByText(/Not yet confirmed by you/)).toBeInTheDocument()
  })
  it('labels sample data', () => {
    render(<TrustMark state="sample" />)
    expect(screen.getByText('Sample data')).toBeInTheDocument()
  })
})

describe('Field', () => {
  it('connects label, hint and error to the control', () => {
    render(<Field label="Amount" hint="In rupees" error="Enter an amount."><Input /></Field>)
    const input = screen.getByLabelText('Amount')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(input.getAttribute('aria-describedby')).toBeTruthy()
    expect(screen.getByRole('alert')).toHaveTextContent('Enter an amount.')
  })
})
