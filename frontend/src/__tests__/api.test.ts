import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, get, post, setUnauthenticatedHandler } from '../lib/api'

const reply = (status: number, body: unknown) => vi.stubGlobal('fetch', vi.fn(async () => new Response(typeof body === 'string' ? body : JSON.stringify(body), { status })))
afterEach(() => { vi.unstubAllGlobals(); setUnauthenticatedHandler(() => {}) })

describe('API client', () => {
  it('returns parsed JSON and prefixes /api', async () => {
    reply(200, { ok: true })
    expect(await get('/health')).toEqual({ ok: true })
    expect((fetch as any).mock.calls[0][0]).toBe('/api/health')
  })

  it('sends JSON bodies with the right header', async () => {
    reply(200, {})
    await post('/consents', { purpose: 'terms' })
    const [, init] = (fetch as any).mock.calls[0]
    expect(init.method).toBe('POST')
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(init.body)).toEqual({ purpose: 'terms' })
  })

  it('turns the stable error shape into an ApiError with code, field and details', async () => {
    reply(409, { error: { code: 'DUPLICATE_DOCUMENT', message: 'You already uploaded this file.', field: 'file', details: { document_id: 'd1' } } })
    const err = await get('/documents').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 409, code: 'DUPLICATE_DOCUMENT', field: 'file', message: 'You already uploaded this file.' })
    expect(err.details).toEqual({ document_id: 'd1' })
  })

  it('maps FastAPI validation errors to a readable message on the right field', async () => {
    reply(422, { detail: [{ loc: ['body', 'amount'], msg: 'Value error, Enter an amount above zero.' }] })
    const err = await post('/cards/best-for-spend', { amount: 0 }).catch((e) => e)
    expect(err).toMatchObject({ status: 422, code: 'VALIDATION', field: 'amount', message: 'Enter an amount above zero.' })
  })

  it('never shows raw server text for an unexpected failure', async () => {
    reply(500, 'Traceback (most recent call last): secret')
    const err = await get('/anything').catch((e) => e)
    expect(err.message).toBe('Something went wrong. Try again.')
    expect(err.message).not.toMatch(/secret/)
  })

  it('reports an unreachable server as a network error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    const err = await get('/x').catch((e) => e)
    expect(err).toMatchObject({ status: 0, code: 'NETWORK' })
    expect(err.message).toMatch(/can't reach the server/)
  })

  it('signs the user out on 401, except for the auth endpoints themselves', async () => {
    const onSignedOut = vi.fn()
    setUnauthenticatedHandler(onSignedOut)
    reply(401, { error: { code: 'UNAUTHENTICATED', message: 'Sign in to continue.' } })
    await get('/dashboard').catch(() => {})
    expect(onSignedOut).toHaveBeenCalledTimes(1)
    await api('/auth/me').catch(() => {})
    expect(onSignedOut).toHaveBeenCalledTimes(1)   // the "am I signed in?" probe must not trigger a sign-out loop
  })
})
