import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App, queryClient } from '../app/App'
import { ErrorBoundary } from '../app/ErrorBoundary'

const user = {
  id: 'u1', name: 'Sample User', email: 's@x.test', onboarding_step: 'done', is_sample: true, consents: ['terms'],
  preferred_language: 'en', phone_masked: null, phone_verified: false, email_verified: false,
}
const dashboard = {
  data_quality: { statements_processed: 1, documents_processing: 0 },
  journeys: { insurance: { active_policies: 1 }, cards: { count: 1 }, emis: { count: 1, confirmed: 1 } },
}
const documents = [{
  id: 'd1', type: 'loan_document', type_label: 'Loan document', display_name: 'sample_loan_kfs.pdf', mime: 'application/pdf',
  size_bytes: 3147, upload_time: '2026-10-31T10:00:00', status: 'needs_review', stage: 'done', page_count: 2, warnings: [],
}]

/** Answer the app's API calls from a table; anything unlisted is an empty object. */
function mockApi(routes: Record<string, unknown>) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = String(url).replace(/^\/api/, '').split('?')[0]
    const body = path in routes ? routes[path] : {}
    return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } })
  }))
}

const at = (path: string) => render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>)

beforeEach(() => queryClient.clear())
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('Documents & data page', () => {
  // Regression: the page crashed to a blank screen because the facts sheet dereferenced a null document on mount.
  it('renders the document list instead of crashing when no document is open', async () => {
    mockApi({ '/auth/me': user, '/documents': documents, '/ai/status': {}, '/dashboard': dashboard })
    at('/documents')
    expect(await screen.findByRole('heading', { name: 'Documents & data' })).toBeInTheDocument()
    expect(await screen.findByText('sample_loan_kfs.pdf')).toBeInTheDocument()
  })

  it('opens the facts sheet for a document', async () => {
    mockApi({ '/auth/me': user, '/documents': documents, '/documents/d1/facts': { document: documents[0], facts: [] }, '/ai/status': {}, '/dashboard': dashboard })
    at('/documents')
    await userEvent.click(await screen.findByRole('button', { name: 'Review values' }))
    expect(await screen.findByText('Values VITTRM extracted, with where each came from.')).toBeInTheDocument()
  })
})

describe('Card statement spend reconciliation', () => {
  const cardDoc = { ...documents[0], id: 'd2', type: 'card_document', type_label: 'Card document', display_name: 'card_statement.pdf' }
  const fact = (key: string, value: unknown, extra = {}) => ({ id: `f-${key}`, fact_type: 'card', key, label: key, value, unit: null, state: 'extracted', confidence: 0.7, user_verified: false,
    citation: { document_id: 'd2', document_name: 'card_statement.pdf', page: 1, section: 'Card statement', snippet: key, fact_key: key, confidence: 0.7, user_verified: false }, ...extra })
  const preview = { currency: 'INR', counted_rows: [{ fact_id: 'f-p1', date: '2026-09-20', merchant: 'SWIGGY', amount: 1000, category: 'food_delivery', category_label: 'Food & delivery', page: 1 }],
    by_category: { food_delivery: 1000 }, total: 1000, unconfirmed_rows: 2, rejected_rows: 0 }

  it('previews the confirmed purchases and offers to count them', async () => {
    mockApi({
      '/auth/me': user, '/dashboard': dashboard, '/ai/status': {}, '/documents': [cardDoc],
      '/documents/d2/facts': { document: cardDoc, facts: [fact('last4', '4821', { user_verified: true })] },
      '/cards': { cards: [{ id: 'c1', nickname: 'Voyager', last4: '4821', imported_spend: null }] },
      '/cards/c1/spend-reconciliation': preview,
    })
    at('/documents')
    await userEvent.click(await screen.findByRole('button', { name: 'Review values' }))
    expect(await screen.findByText('Count confirmed purchases toward rewards')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getAllByLabelText('Saved card').pop()!, 'c1')
    expect(await screen.findByText(/SWIGGY/)).toBeInTheDocument()
    expect(screen.getByText(/2 unconfirmed row\(s\) are not counted/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Count these purchases' })).toBeEnabled()
  })

  it('says so when nothing is confirmed yet', async () => {
    mockApi({
      '/auth/me': user, '/dashboard': dashboard, '/ai/status': {}, '/documents': [cardDoc],
      '/documents/d2/facts': { document: cardDoc, facts: [fact('last4', '4821', { user_verified: true })] },
      '/cards': { cards: [{ id: 'c1', nickname: 'Voyager', last4: '4821', imported_spend: null }] },
      '/cards/c1/spend-reconciliation': { ...preview, counted_rows: [], by_category: {}, total: 0 },
    })
    at('/documents')
    await userEvent.click(await screen.findByRole('button', { name: 'Review values' }))
    await userEvent.selectOptions((await screen.findAllByLabelText('Saved card')).pop()!, 'c1')
    expect(await screen.findByText(/No purchase rows are confirmed yet/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Count these purchases' })).toBeDisabled()
  })
})

describe('ErrorBoundary', () => {
  const Boom = ({ explode }: { explode: boolean }) => {
    if (explode) throw new Error('boom')
    return <p>all good</p>
  }

  it('shows a recoverable message instead of unmounting the app', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<ErrorBoundary><Boom explode /></ErrorBoundary>)
    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong on this screen')
  })

  it('gives the screen another chance when the route changes', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const { rerender } = render(<ErrorBoundary resetKey="/documents"><Boom explode /></ErrorBoundary>)
    expect(screen.getByRole('alert')).toBeInTheDocument()
    rerender(<ErrorBoundary resetKey="/loans"><Boom explode={false} /></ErrorBoundary>)
    expect(screen.getByText('all good')).toBeInTheDocument()
  })
})
