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
    await userEvent.click(await screen.findByRole('button', { name: /view|review|open/i }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
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
