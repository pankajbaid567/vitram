/**
 * VITRAM edge worker (Cloudflare, free plan).
 *
 *  - serves the built web app (static assets, with single-page-app fallback; configured in wrangler.jsonc);
 *  - forwards /api/* to the API so the browser stays on one origin (cookies and the CSRF origin check keep working);
 *  - a cron trigger pings the API every 10 minutes so a free host that sleeps when idle stays awake and its
 *    in-process reminder scheduler keeps running.
 */
export interface Env {
  ASSETS: Fetcher
  /** Base URL of the API, e.g. https://vitram-api.onrender.com (no trailing slash). */
  API_ORIGIN: string
  /** Optional: other free services to keep awake, comma-separated base URLs (e.g. the OpenWA gateway). */
  KEEPALIVE_URLS?: string
}

const HOP_BY_HOP = ['connection', 'keep-alive', 'transfer-encoding', 'upgrade', 'proxy-authenticate', 'proxy-authorization', 'te', 'trailer']

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url)
    if (!url.pathname.startsWith('/api/')) return env.ASSETS.fetch(request)

    const upstream = new URL(url.pathname + url.search, env.API_ORIGIN)
    const headers = new Headers(request.headers)
    for (const h of HOP_BY_HOP) headers.delete(h)
    headers.set('x-forwarded-host', url.host)
    headers.set('x-forwarded-proto', 'https')
    try {
      const res = await fetch(upstream, {
        method: request.method, headers, body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body, redirect: 'manual',
      })
      return new Response(res.body, res)   // status, Set-Cookie and the rest pass through unchanged
    } catch {
      return Response.json({ error: { code: 'UPSTREAM_UNAVAILABLE', message: 'The server is starting up. Try again in a few seconds.' } }, { status: 502 })
    }
  },

  /** Cron: keep the API awake and let it report readiness. */
  async scheduled(_event: ScheduledController, env: Env): Promise<void> {
    const targets = [new URL('/api/ready', env.API_ORIGIN).toString(), ...(env.KEEPALIVE_URLS ?? '').split(',').map((u) => u.trim()).filter(Boolean)]
    await Promise.all(targets.map((u) => fetch(u).catch(() => undefined)))
  },
}
