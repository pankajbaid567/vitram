// Tiny Chrome DevTools helper shared by the browser scripts (no dependencies; Node 22 has the global WebSocket).
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const CANDIDATES = [process.env.CHROME, '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser'].filter(Boolean)

export async function launch(base, { width = 1440, height = 900 } = {}) {
  const exe = CANDIDATES.find((p) => existsSync(p))
  if (!exe) { console.error('No Chrome/Chromium found. Set CHROME=/path/to/chrome'); process.exit(2) }
  const port = 9300 + Math.floor(Math.random() * 500)
  const chrome = spawn(exe, ['--headless=new', '--no-sandbox', `--remote-debugging-port=${port}`, `--user-data-dir=${mkdtempSync(join(tmpdir(), 'vitram-'))}`,
    '--no-first-run', '--no-default-browser-check', 'about:blank'], { stdio: 'ignore' })
  const close = (code) => { try { chrome.kill() } catch { /* already gone */ } process.exit(code) }

  let ws, opened
  for (let i = 0; i < 80 && !ws; i++) {
    try {
      const page = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === 'page')
      if (page) { ws = new WebSocket(page.webSocketDebuggerUrl); opened = new Promise((r) => (ws.onopen = r)); break }
    } catch { /* still starting */ }
    await sleep(250)
  }
  if (!ws) { console.error('Could not connect to Chrome DevTools'); close(2) }
  await opened

  let id = 0
  const pending = new Map()
  const problems = []   // console errors, uncaught exceptions, failed requests
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data)
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); return }
    if (msg.method === 'Runtime.exceptionThrown') problems.push('exception: ' + (msg.params.exceptionDetails.exception?.description ?? msg.params.exceptionDetails.text).split('\n')[0])
    else if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') problems.push('console.error: ' + msg.params.args.map((a) => a.value ?? a.description ?? '').join(' ').slice(0, 200))
    else if (msg.method === 'Network.responseReceived') {
      const { status, url } = msg.params.response
      if (status >= 400 && !(status === 401 && url.endsWith('/api/auth/me'))) problems.push(`HTTP ${status} ${url.replace(base, '')}`)
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
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable')
  await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: width < 800 })

  const text = () => js('document.body.innerText')
  const hasText = (s) => `document.body.innerText.includes(${JSON.stringify(s)})`
  async function waitFor(what, test, ms = 15000) {
    const end = Date.now() + ms
    while (Date.now() < end) { if (await js(test).catch(() => false)) return; await sleep(200) }
    throw new Error(`timed out waiting for ${what}\n      page says: ${(await text()).replace(/\s+/g, ' ').slice(0, 260)}`)
  }
  return {
    base, problems, close, send, js, text, hasText, waitFor,
    go: async (path) => { await send('Page.navigate', { url: base + path }); await sleep(700) },
    path: () => js('location.pathname + location.search'),
    /** Click the first element matching `sel` whose visible text (or accessible label) matches the regex source `re`. */
    click: (sel, re, flags = 'i') => js(`(() => { const el = [...document.querySelectorAll(${JSON.stringify(sel)})].find((e) => new RegExp(${JSON.stringify(re)}, ${JSON.stringify(flags)}).test(e.innerText || e.value || e.getAttribute('aria-label') || '')); if (!el) return false; el.scrollIntoView({block:'center'}); el.click(); return true })()`),
    /** Fill the input/textarea/select associated with a visible label (works with React-controlled inputs). */
    fill: (label, value) => js(`(() => {
      const l = [...document.querySelectorAll('label')].find((e) => e.innerText.toLowerCase().includes(${JSON.stringify(label.toLowerCase())}))
      const el = l ? (l.control || l.querySelector('input,select,textarea')) : document.querySelector(${JSON.stringify(`[aria-label="${label}"]`)})
      if (!el) return 'no field for: ${label}'
      const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype : el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, ${JSON.stringify(String(value))})
      el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true }))
      return 'ok' })()`),
    /** Attach a local file to the first (or nth) file input on the page. */
    upload: async (filePath, nth = 0) => {
      const doc = await send('DOM.getDocument', { depth: 1 })
      const all = await send('DOM.querySelectorAll', { nodeId: doc.result.root.nodeId, selector: 'input[type=file]' })
      const nodeId = all.result?.nodeIds?.[nth]
      if (!nodeId) throw new Error('no file input on the page')
      await send('DOM.setFileInputFiles', { nodeId, files: [filePath] })
      await sleep(400)
    },
    shot: async (file) => { const r = await send('Page.captureScreenshot', { format: 'png' }); writeFileSync(file, Buffer.from(r.result.data, 'base64')) },
  }
}

/** Run named steps, print ✓/✗ with timing, and return the results. */
export function runner() {
  const results = []
  return {
    results,
    async step(name, fn) {
      const t = Date.now()
      try { await fn(); results.push({ name, ok: true }); console.log(`  ✓ ${name}  (${((Date.now() - t) / 1000).toFixed(1)}s)`) }
      catch (e) { results.push({ name, ok: false, error: e.message }); console.log(`  ✗ ${name}\n      ${e.message}`) }
    },
    summary() {
      const failed = results.filter((r) => !r.ok)
      console.log(`\n${results.length - failed.length}/${results.length} steps passed`)
      return failed.length ? 1 : 0
    },
  }
}
