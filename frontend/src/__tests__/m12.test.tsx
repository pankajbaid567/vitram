import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Breadcrumbs } from '../components/ui/data'
import { PasswordInput } from '../components/ui/field'
import { ConfirmDialog } from '../components/ui/overlay'
import { Signup } from '../features/auth/Welcome'
import { setupSteps } from '../features/dashboard/setup'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const dash = (o: any = {}) => ({
  data_quality: { statements_processed: 0, ...o.dq },
  journeys: { insurance: { active_policies: 0 }, cards: { count: 0 }, emis: { count: 0, confirmed: 0 }, ...o.j },
})

describe('Setup steps (sidebar card + home checklist)', () => {
  it('are all to-do for a new account', () => {
    expect(setupSteps(dash()).map((s) => s.done)).toEqual([false, false, false, false])
  })
  it('only counts EMIs as done when every EMI is confirmed', () => {
    const d = dash({ dq: { statements_processed: 1 }, j: { insurance: { active_policies: 2 }, cards: { count: 1 }, emis: { count: 2, confirmed: 1 } } })
    expect(setupSteps(d).map((s) => [s.key, s.done])).toEqual([['statement', true], ['policy', true], ['cards', true], ['emis', false]])
  })
  it('returns nothing before the dashboard has loaded', () => {
    expect(setupSteps(undefined)).toEqual([])
  })
})

function renderSignup() {
  return render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><Signup /></MemoryRouter></QueryClientProvider>)
}

describe('Sign-up validation', () => {
  it('checks fields in order without calling the server, and keeps what was typed', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    renderSignup()
    const submit = screen.getByRole('button', { name: /create account/i })
    fireEvent.click(submit)
    expect(screen.getByText('Enter your name.')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Your name'), { target: { value: 'Asha' } })
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'asha@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'long-enough-1' } })
    fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'different-1' } })
    fireEvent.click(submit)
    expect(screen.getByText("The passwords don't match.")).toBeTruthy()
    expect((screen.getByLabelText('Your name') as HTMLInputElement).value).toBe('Asha')
    fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'long-enough-1' } })
    fireEvent.click(submit)
    expect(screen.getByText(/Accept the terms/)).toBeTruthy()
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})

describe('Shared controls', () => {
  it('PasswordInput shows and hides the value', () => {
    render(<PasswordInput aria-label="Password" defaultValue="secret-1" />)
    const input = screen.getByLabelText('Password') as HTMLInputElement
    expect(input.type).toBe('password')
    fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(input.type).toBe('text')
    expect(screen.getByRole('button', { name: 'Hide password' })).toHaveAttribute('aria-pressed', 'true')
  })
  it('ConfirmDialog does nothing until the confirm button is pressed, and respects confirmDisabled', () => {
    const onConfirm = vi.fn()
    const { rerender } = render(<ConfirmDialog open onOpenChange={() => {}} title="Delete?" confirmLabel="Delete" onConfirm={onConfirm} confirmDisabled />)
    expect(onConfirm).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(onConfirm).not.toHaveBeenCalled()
    rerender(<ConfirmDialog open onOpenChange={() => {}} title="Delete?" confirmLabel="Delete" onConfirm={onConfirm} />)
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })
  it('Breadcrumbs link parents and mark the current page', () => {
    render(<MemoryRouter><Breadcrumbs items={[{ label: 'Home', to: '/' }, { label: 'Loans' }]} /></MemoryRouter>)
    expect(screen.getByRole('link', { name: 'Home' })).toHaveAttribute('href', '/')
    expect(screen.getByText('Loans')).toHaveAttribute('aria-current', 'page')
  })
})
