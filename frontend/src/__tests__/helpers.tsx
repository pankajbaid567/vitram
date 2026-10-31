import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import { App } from '../app/App'
import { queryClient } from '../lib/queryClient'
import api from './fixtures/api.json'
import ids from './fixtures/ids.json'

/** Real API responses, captured from the running backend (see fixtures/): tests break if the contract drifts. */
export const fx = api as Record<string, any>
export const fxIds = ids as { mother: string; emi: string }

/** Answer the app's API calls from a table keyed by path (query string ignored). Unlisted paths return `{}`. */
export function mockApi(routes: Record<string, unknown>, status: Record<string, number> = {}) {
  const fetchMock = vi.fn(async (url: string) => {
    const path = String(url).replace(/^\/api/, '').split('?')[0]
    return new Response(JSON.stringify(path in routes ? routes[path] : {}), { status: status[path] ?? 200, headers: { 'content-type': 'application/json' } })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** The routes every signed-in screen needs: the session, the dashboard (setup checklist) and AI status. */
export const baseRoutes = () => ({ '/auth/me': fx.me, '/dashboard': fx.dashboard, '/ai/status': { chat_mode: 'tool', vision: { provider: 'macos', configured: true, on_device: true, note: '' } } })

/** Fresh cache per test, and no retry back-off, so an error state shows up immediately. */
export const resetApp = () => {
  queryClient.clear()
  queryClient.setDefaultOptions({ queries: { retry: false, refetchOnWindowFocus: false } })
}

export const renderAt = (path: string) => render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>)
