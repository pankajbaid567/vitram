// End-to-end smoke test: drives the core demo path in a real Chrome and fails loudly.
//
//   node scripts/e2e.mjs [--base http://localhost:5173]
//   CHROME=/path/to/chrome node scripts/e2e.mjs
//
// Needs the API and the web app running (e.g. `docker compose up`, or backend on :8000 + `npm run preview`) and a
// local Chrome/Chromium. Uses the labelled *sample workspace*, so no real data is read. Node 22 has the global
// WebSocket it needs (on Node 20 add --experimental-websocket).
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const args = process.argv.slice(2)
const BASE = args.includes('--base') ? args[args.indexOf('--base') + 1] : 'http://localhost:5173'
const CANDIDATES = [process.env.CHROME, '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser'].filter(Boolean)
const CHROME = CANDIDATES.find((p) => existsSync(p))
if (!CHROME) { console.error('No Chrome/Chromium found. Set CHROME=/path/to/chrome'); process.exit(2) }

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const port = 9300 + Math.floor(Math.random() * 500)
const chrome = spawn(CHROME, ['--headless=new', '--no-sandbox', `--remote-debugging-port=${port}`, `--user-data-dir=${mkdtempSync(join(tmpdir(), 'e2e-'))}`,
  '--no-first-run', '--no-default-browser-check', 'about:blank'], { stdio: 'ignore' })
const done = (code) => { try { chrome.kill() } catch { /* already gone */ } process.exit(code) }

let ws, opened
for (let i = 0; i < 80 && !ws; i++) {
  try {
    const page = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === 'page')
    if (page) { ws = new WebSocket(page.webSocketDebuggerUrl); opened = new Promise((r) => (ws.onopen = r)); break }
  } catch { /* still starting */ }
  await sleep(250)
}
if (!ws) { console.error('Could not connect to Chrome DevTools'); done(2) }
await opened

let id = 0
const pending = new Map()
const problems = []   // console errors, uncaught exceptions and failed requests seen during the run
ws.onmessage = (m) => {
  const msg = JSON.parse(m.data)
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); return }
  if (msg.method === 'Runtime.exceptionThrown') problems.push('exception: ' + (msg.params.exceptionDetails.exception?.description ?? msg.params.exceptionDetails.text).split('\n')[0])
  else if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') problems.push('console.error: ' + msg.params.args.map((a) => a.value ?? a.description ?? '').join(' ').slice(0, 200))
  else if (msg.method === 'Network.responseReceived') {
    const { status, url } = msg.params.response
    // 401 from /auth/me is the normal "am I signed in?" probe before sign-in
    if (status >= 400 && !(status === 401 && url.endsWith('/api/auth/me'))) problems.push(`HTTP ${status} ${url.replace(BASE, '')}`)
  }
}
const send = (method, params = {}, timeout = 30000) => new Promise((resolve) => {
  const i = ++id
  const t = setTimeout(() => { pending.delete(i); resolve({ error: { message: `timeout: ${method}` } }) }, timeout)
  pending.set(i, (m) => { clearTimeout(t); resolve(m) })
  ws.send(JSON.stringify({ id: i, method, params }))
})
const js = async (expression) => {
  const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  if (r.result?.exceptionDetails) throw new Error(r.result.exceptionDetails.exception?.description ?? 'evaluation failed')
  return r.result?.result?.value
}

const results = []
async function step(name, fn) {
  const start = Date.now()
  try { await fn(); results.push({ name, ok: true, ms: Date.now() - start }); console.log(`  ✓ ${name}`) }
  catch (e) { results.push({ name, ok: false, error: e.message }); console.log(`  ✗ ${name}\n      ${e.message}`) }
}
const text = () => js('document.body.innerText')
async function waitFor(what, test, ms = 15000) {
  const end = Date.now() + ms
  while (Date.now() < end) { if (await js(test).catch(() => false)) return; await sleep(200) }
  throw new Error(`timed out waiting for ${what}\n      page says: ${(await text()).replace(/\s+/g, ' ').slice(0, 220)}`)
}
const hasText = (s) => `document.body.innerText.includes(${JSON.stringify(s)})`
const go = async (path) => { await send('Page.navigate', { url: BASE + path }); await sleep(600) }
const clickByText = (sel, re) => js(`(() => { const el = [...document.querySelectorAll(${JSON.stringify(sel)})].find((e) => ${re}.test(e.innerText)); if (!el) return false; el.click(); return true })()`)

await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable')
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false })
console.log(`VITRAM e2e against ${BASE}`)

await step('open the sample workspace', async () => {
  await go('/welcome')
  await waitFor('the sample-workspace button', hasText('Open sample workspace'))
  await clickByText('button', '/Open sample workspace/')
  await waitFor('the dashboard', hasText('Hello, Sample'))
  await waitFor('real figures', hasText('₹1,18,200'))
})

await step('Documents & data lists the processed documents (and does not crash)', async () => {
  await go('/documents')
  await waitFor('the page heading', `[...document.querySelectorAll('h1')].some((h) => h.innerText.includes('Documents & data'))`)
  await waitFor('the sample loan document', hasText('sample_loan_kfs.pdf'))
  if (!(await text()).includes('sample_policy_senior_care.pdf')) throw new Error('policy document missing from the list')
})

await step('a document opens with page-cited facts', async () => {
  await clickByText('button', '/Review values/')
  await waitFor('the facts sheet', hasText('Values VITRAM extracted, with where each came from.'))
  await waitFor('a cited fact', `document.querySelectorAll('[role=dialog] a, [role=dialog] button').length > 0 && /Source|p\\.\\s?\\d|page/i.test(document.body.innerText)`)
})

await step('loan options show cost, reasons and the sample-data label', async () => {
  await go('/loans/results?purpose=personal&amount=300000&tenure=36&collateral=none')
  await waitFor('the results heading', hasText('₹3,00,000 for personal need'))
  await waitFor('the EMI', hasText('₹9,857'))
  if (!(await text()).includes('Sample data')) throw new Error('catalogue is not labelled as sample data')
})

await step('real cost separates scheduled from contingent charges', async () => {
  await clickByText('a', '/Real cost & clauses/')
  await waitFor('the real-cost view', hasText('Real cost'))
  await waitFor('contingent charges', `/late|foreclosure|prepayment/i.test(document.body.innerText)`)
})

await step('the card optimiser answers for a purchase', async () => {
  await go('/cards/optimize')
  await waitFor('the page', hasText('Which card should I use?'))
})

await step('emergency mode scopes to one person and cites the policy', async () => {
  await go('/insurance/emergency?event=hospitalisation')
  await waitFor('the person picker', hasText('Who needs care?'))
  await waitFor('the family to load', hasText('Kamala'))   // the list arrives after the heading on a slow host
  if ((await text()).includes('Senior Care')) throw new Error('a policy was shown before choosing a person')
  await clickByText('button, label, [role=radio]', '/Kamala/')
  await waitFor('the policy that may apply', hasText('May apply'))
  await waitFor('the policy name', hasText('Senior Care'))
  await waitFor('page citations', `(document.body.innerText.match(/Source · p\\.\\d/g) || []).length >= 3`)
})

await step('settings offers export and account deletion', async () => {
  await go('/settings')
  await waitFor('the export button', hasText('Download my data'))
  await waitFor('delete account', hasText('Delete my account'))
})

await step('no console errors, exceptions or failed requests', async () => {
  if (problems.length) throw new Error('\n      ' + [...new Set(problems)].join('\n      '))
})

const failed = results.filter((r) => !r.ok)
console.log(`\n${results.length - failed.length}/${results.length} steps passed`)
done(failed.length ? 1 : 0)
