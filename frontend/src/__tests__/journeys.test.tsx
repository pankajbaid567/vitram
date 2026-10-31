import { cleanup, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { baseRoutes, fx, fxIds, mockApi, renderAt, resetApp } from './helpers'

beforeEach(resetApp)
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('Loan options', () => {
  it('ranks catalogue options with their cost, reasons and a sample-data label', async () => {
    mockApi({ ...baseRoutes(), '/loans/recommend': fx.loan_recommend })
    renderAt('/loans/results?purpose=personal&amount=300000&tenure=36&collateral=none')
    expect(await screen.findByRole('heading', { name: '₹3,00,000 for personal need' })).toBeInTheDocument()
    expect(await screen.findByText('Salaried Personal Loan')).toBeInTheDocument()
    expect(screen.getByText('₹9,857')).toBeInTheDocument()                       // the independently verified EMI
    expect(screen.getAllByText(/Total you pay/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Sample data/).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('link', { name: 'Real cost & clauses' }).length).toBeGreaterThan(1)
    expect(screen.getByText(/Fictional lenders, illustrative terms/)).toBeInTheDocument()
  })

  it('shows an honest error with a retry when the server fails', async () => {
    mockApi({ ...baseRoutes(), '/loans/recommend': { error: { code: 'INTERNAL_ERROR', message: 'Something went wrong on our side.' } } }, { '/loans/recommend': 500 })
    renderAt('/loans/results?purpose=personal&amount=300000&tenure=36&collateral=none')
    expect(await screen.findByRole('alert')).toHaveTextContent(/went wrong/i)
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })
})

describe('Emergency mode', () => {
  it('names the person, the policy that may apply, what to do now and cites the pages', async () => {
    mockApi({ ...baseRoutes(), '/family': fx.family, '/insurance/events': fx.insurance_events, '/insurance/emergency': fx.emergency })
    renderAt(`/insurance/emergency?member=${fxIds.mother}&event=hospitalisation`)
    expect(await screen.findByRole('heading', { name: 'Emergency help' })).toBeInTheDocument()
    expect(await screen.findByText('Senior Care')).toBeInTheDocument()
    expect(screen.getByText('May apply')).toBeInTheDocument()
    expect(screen.getByText(/Inform the insurer within/)).toBeInTheDocument()
    expect(screen.getAllByText(/Source · p\.\d/).length).toBeGreaterThanOrEqual(3)           // every material figure opens its source
    expect(screen.getByRole('link', { name: /Call 1800-000-1111/ }) ?? screen.getByText(/Call 1800-000-1111/)).toBeTruthy()
    expect(screen.getByText(/waiting period is still running/i)).toBeInTheDocument()
  })

  it('asks who needs care before showing any policy', async () => {
    mockApi({ ...baseRoutes(), '/family': fx.family, '/insurance/events': fx.insurance_events })
    renderAt('/insurance/emergency?event=hospitalisation')
    expect(await screen.findByText(/Choose the person first/)).toBeInTheDocument()
    expect(screen.queryByText('Senior Care')).toBeNull()
  })
})

describe('Reminder settings', () => {
  const prefs = (over: object) => ({ ...fx.reminders, preferences: { ...fx.reminders.preferences, ...over } })

  it('explains why WhatsApp is not active', async () => {
    mockApi({ ...baseRoutes(), '/reminders': prefs({ whatsapp_enabled: true, whatsapp_consent: true, phone_verified: false, whatsapp_configured: true,
      whatsapp_blocked_reason: "Your mobile number isn't verified yet." }) })
    renderAt('/settings/reminders')
    const callout = await screen.findByText('WhatsApp is on, but not active yet')
    expect(callout.closest('div')).toHaveTextContent("Your mobile number isn't verified yet.")
    expect(screen.getByRole('link', { name: 'My profile' })).toBeInTheDocument()
  })

  it('stays quiet when WhatsApp is active', async () => {
    mockApi({ ...baseRoutes(), '/reminders': prefs({ whatsapp_enabled: true, whatsapp_consent: true, phone_verified: true, whatsapp_configured: true, whatsapp_blocked_reason: null }) })
    renderAt('/settings/reminders')
    expect(await screen.findByRole('heading', { name: 'WhatsApp' })).toBeInTheDocument()
    expect(screen.queryByText('WhatsApp is on, but not active yet')).toBeNull()
  })

  it('says plainly when no WhatsApp provider is connected', async () => {
    mockApi({ ...baseRoutes(), '/reminders': prefs({ whatsapp_configured: false, whatsapp_consent: false }) })
    renderAt('/settings/reminders')
    expect(await screen.findByText("WhatsApp isn't connected in this environment")).toBeInTheDocument()
  })
})

describe('Settings: your data', () => {
  it('offers a download and requires typing DELETE before deleting the account', async () => {
    mockApi({ ...baseRoutes(), '/consents': { purposes: [] }, '/auth/password-reset/status': { email_configured: false } })
    renderAt('/settings')
    expect(await screen.findByRole('button', { name: 'Download my data' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Delete account' }))
    const dialog = await screen.findByRole('dialog', { name: /Delete your account/ })
    const confirm = within(dialog).getByRole('button', { name: 'Delete my account' })
    expect(confirm).toBeDisabled()
    await userEvent.type(within(dialog).getByLabelText('Type DELETE to confirm'), 'DELETE')
    expect(confirm).toBeEnabled()        // the sample workspace has no password to ask for
  })
})
