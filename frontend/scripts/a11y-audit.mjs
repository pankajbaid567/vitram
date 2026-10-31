// VITTRM accessibility audit: axe-core (WCAG 2.1 A/AA) on every route at desktop and mobile widths,
// plus scripted keyboard checks (skip link, visible focus, dialog focus trap / Escape / focus return).
//
// Needs the app running (API on :8000, web on :5173) and a local Chrome. Uses a fresh browser profile and
// opens the labelled *sample workspace*, so no real user data is read.
//
//   node scripts/a11y-audit.mjs [--base http://127.0.0.1:5173] [--json report.json]
//   CHROME=/path/to/chrome node scripts/a11y-audit.mjs
import { spawn } from 'node:child_process'
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const args = process.argv.slice(2)
const BASE = args[args.indexOf('--base') + 1] && args.includes('--base') ? args[args.indexOf('--base') + 1] : 'http://127.0.0.1:5173'
const JSON_OUT = args.includes('--json') ? args[args.indexOf('--json') + 1] : null
const CHROME = process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const AXE = readFileSync(new URL('../node_modules/axe-core/axe.min.js', import.meta.url), 'utf8')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const port = 9400 + Math.floor(Math.random() * 400)
const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${mkdtempSync(join(tmpdir(), 'a11y-'))}`,
  '--no-first-run', '--no-default-browser-check', 'about:blank'], { stdio: 'ignore' })
let ws, opened
for (let i = 0; i < 60 && !ws; i++) {
  try {
    const page = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === 'page')
    if (page) {
      ws = new WebSocket(page.webSocketDebuggerUrl)
      opened = new Promise((r) => (ws.onopen = r)) // attach before yielding, or the open event can be missed
      break
    }
  } catch { /* chrome still starting */ }
  await sleep(200)
}
if (!ws) throw new Error('Could not connect to Chrome DevTools')
await opened
let id = 0
const pending = new Map()
ws.onmessage = (m) => { const msg = JSON.parse(m.data); if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id) } }
const send = (method, params = {}, timeout = 20000) => new Promise((r) => {
  const i = ++id
  const t = setTimeout(() => { pending.delete(i); r({ error: { message: `timeout: ${method}` } }) }, timeout)
  pending.set(i, (m) => { clearTimeout(t); r(m) })
  ws.send(JSON.stringify({ id: i, method, params }))
})
const VERBOSE = args.includes('--verbose')
const js = async (expression, timeout = 20000) => {
  const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }, timeout)
  if (r.error) throw new Error(r.error.message)
  if (r.result?.exceptionDetails) throw new Error(r.result.exceptionDetails.exception?.description ?? r.result.exceptionDetails.text)
  return r.result?.result?.value
}
const viewport = (w, h) => send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: w < 800 })
const go = async (path) => { if (VERBOSE) console.error('→', path); await send('Page.navigate', { url: BASE + path }); await waitIdle() }
async function waitIdle() {
  for (let i = 0; i < 60; i++) {
    const busy = await js("document.readyState !== 'complete' || !document.querySelector('main') || !!document.querySelector('.skeleton, [aria-busy=\"true\"]')").catch(() => true)
    if (!busy) break
    await sleep(150)
  }
  await sleep(400)
}
const key = async (k, shift = false) => {
  const codes = { Tab: 9, Escape: 27, Enter: 13 }
  const text = k === 'Enter' ? '\r' : undefined // Enter must carry text to activate buttons
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: k, code: k, windowsVirtualKeyCode: codes[k], modifiers: shift ? 8 : 0, text })
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: k, code: k, windowsVirtualKeyCode: codes[k], modifiers: shift ? 8 : 0 })
  await sleep(80)
}

await send('Page.enable')
await send('Runtime.enable')
await viewport(1440, 900)

// 1. Sample workspace (fictional data)
await go('/welcome')
await js("[...document.querySelectorAll('button')].find(b => b.textContent.includes('Open sample workspace')).click()")
for (let i = 0; i < 80; i++) { if (await js("location.pathname === '/' && document.body.innerText.includes('Hello')")) break; await sleep(250) }
const ids = await js(`(async () => {
  const j = (p) => fetch('/api' + p).then(r => r.json())
  const [pol, emis, cards, docs, fam] = await Promise.all([j('/insurance/policies'), j('/emis'), j('/cards'), j('/documents'), j('/family')])
  return { policy: pol[0]?.id, emi: emis.emis[0]?.id, card: cards.cards[0]?.id, loanDoc: docs.find(d => d.type === 'loan_document')?.id,
           mother: fam.members.find(m => m.relation === 'mother')?.id }
})()`)

// A receipt photo drawn in the browser and read by the server's OCR, so the review screen is audited with real data.
const receiptId = await js(`(async () => {
  const c = document.createElement('canvas'); c.width = 700; c.height = 520
  const g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, 700, 520); g.fillStyle = '#111'; g.font = '30px Arial'
  ;['CITY MEDICAL STORES', 'Date: 12/08/2026', 'Paracetamol 650  2  60.00', 'Cough Syrup  1  145.00', 'Subtotal  205.00', 'GST 12%  24.60', 'Grand Total  229.60', 'Paid by UPI']
    .forEach((t, i) => g.fillText(t, 30, 50 + i * 58))
  const blob = await new Promise((r) => c.toBlob(r, 'image/png'))
  const fd = new FormData(); fd.append('file', blob, 'audit-receipt.png'); fd.append('type', 'receipt')
  const d = await fetch('/api/documents', { method: 'POST', body: fd }).then((r) => r.json())
  for (let i = 0; i < 60; i++) {
    const s = await fetch('/api/documents/' + d.id).then((r) => r.json())
    if (!['queued', 'processing'].includes(s.status)) return s.status === 'failed' ? null : d.id
    await new Promise((r) => setTimeout(r, 500))
  }
  return null
})()`, 90000)

const routes = [...(receiptId ? [`/documents/receipts/${receiptId}`] : []), '/', '/profile/review', '/loans', '/loans/need', '/loans/results?purpose=personal&amount=300000&tenure=36&collateral=none',
  '/loans/p/aravali-personal-flex?amount=300000&tenure=36', '/loans/compare?ids=aravali-personal-flex,nilgiri-salaried-personal&amount=300000&purpose=personal',
  `/loans/documents/${ids.loanDoc}`, '/loans/analyze', '/cards', '/cards/explore', '/cards/upload', `/cards/${ids.card}`, '/cards/optimize', '/emis', `/emis/${ids.emi}`, '/settings/reminders',
  '/insurance', '/insurance/upload', `/insurance/policies/${ids.policy}`, '/insurance/explore', '/insurance/consult',
  `/insurance/emergency?member=${ids.mother}&event=hospitalisation`, '/documents', '/family', '/settings', '/profile', '/insights', '/forecast', '/goals', '/documents/receipts/new', '/onboarding/about', '/onboarding/statement']

const results = []
async function axe(path, label) {
  await js(AXE)
  const r = await js(`axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','best-practice'] } })
    .then(r => r.violations.map(v => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.slice(0, 4).map(n => n.target.join(' ') + ' :: ' + (n.failureSummary || '').split('\\n')[1]) , count: v.nodes.length })))`, 90000)
  results.push({ path, label, violations: r })
}
for (const [w, h, label] of [[1440, 900, 'desktop'], [390, 844, 'mobile']]) {
  await viewport(w, h)
  for (const r of routes) { await go(r); await axe(r, label) }
}
await viewport(390, 844)
await go('/')
await js("document.querySelector('button[aria-label=\"Ask Vitt Saathi\"]').click()")
await sleep(900)
await axe('/ (Vitt Saathi sheet)', 'mobile')

// 2. Keyboard checks
await viewport(1440, 900)
const kb = []
await go('/')
await js('document.activeElement.blur(); window.scrollTo(0,0)')
await key('Tab')
kb.push({ check: 'First Tab reaches skip link', pass: await js("document.activeElement?.getAttribute('href') === '#main'") })
const focusVisible = []
for (let i = 0; i < 25; i++) {
  await key('Tab')
  focusVisible.push(await js(`(() => { const e = document.activeElement; if (!e || e === document.body) return null;
    const s = getComputedStyle(e); const visible = (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none';
    return { el: (e.getAttribute('aria-label') || e.textContent || e.tagName).trim().slice(0, 40), visible } })()`))
}
const hidden = focusVisible.filter((f) => f && !f.visible)
kb.push({ check: 'Visible focus on first 25 tab stops', pass: hidden.length === 0, detail: hidden.map((f) => f.el) })

await go('/cards')
await js("[...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Add a card').focus()")
await key('Enter')
await sleep(500)
const inDialog = await js("!!document.activeElement.closest('[role=dialog]')")
let trapped = true
for (let i = 0; i < 20; i++) { await key('Tab'); if (!(await js("!!document.activeElement.closest('[role=dialog]')"))) trapped = false }
await key('Escape')
await sleep(400)
kb.push({ check: 'Dialog: focus moves in, Tab is trapped, Escape closes, focus returns to trigger',
  pass: inDialog && trapped && (await js("!document.querySelector('[role=dialog]') && document.activeElement.textContent.trim() === 'Add a card'")) })

await go('/')
await js("[...document.querySelectorAll('button')].find(b => b.textContent.includes('Ask Vitt Saathi')).focus()")
await key('Enter')
await sleep(600)
kb.push({ check: 'Saathi panel: message box reachable and labelled', pass: await js("!!document.querySelector('#saathi-input') && !!document.querySelector('label[for=saathi-input]')") })
await js("document.querySelector('button[aria-label=\\'Close Vitt Saathi\\']').focus()")
await key('Enter')
await sleep(500)
kb.push({ check: 'Saathi panel: closing returns focus to the opener', pass: await js("document.activeElement?.hasAttribute('data-saathi-opener')") })
kb.push({ check: 'Saathi transcript is a live region', pass: await js("!!document.querySelector('[aria-live=polite] ol, [aria-live=polite]')") })

await viewport(390, 844)
await go('/')
const smallTargets = await js(`[...document.querySelectorAll('a[href], button, input, select, textarea, [role=button]')]
  .filter(e => { const r = e.getBoundingClientRect(); return r.width > 1 && r.height > 1 && getComputedStyle(e).visibility !== 'hidden' && !e.classList.contains('sr-only') })
  .filter(e => { const r = e.getBoundingClientRect(); return (r.width < 24 || r.height < 24) && !e.closest('p, li span') })
  .map(e => (e.getAttribute('aria-label') || e.textContent || e.tagName).trim().slice(0, 30) + ' ' + Math.round(e.getBoundingClientRect().width) + 'x' + Math.round(e.getBoundingClientRect().height))`)
kb.push({ check: 'Mobile dashboard: no interactive target under 24×24 px (WCAG 2.5.8 minimum)', pass: smallTargets.length === 0, detail: smallTargets })
kb.push({ check: 'Mobile: no horizontal page scroll', pass: await js('document.documentElement.scrollWidth <= window.innerWidth') })

// 4. Signed-out pages (login, sign-up) after signing out of the sample workspace
await js("fetch('/api/auth/logout', { method: 'POST' }).then(r => r.status)")
for (const [w, h, label] of [[1440, 900, 'desktop'], [390, 844, 'mobile']]) {
  await viewport(w, h)
  for (const r of ['/login', '/login?expired=1', '/signup', '/forgot-password', '/reset-password?token=example-token-for-audit', '/verify-email']) { await go(r); await axe(r, label) }
}

ws.close()
chrome.kill()

// 3. Report
const byRule = {}
for (const r of results) for (const v of r.violations) {
  const k = v.id
  byRule[k] ??= { id: k, impact: v.impact, help: v.help, pages: [], examples: new Set() }
  byRule[k].pages.push(`${r.label}:${r.path}`)
  v.nodes.forEach((n) => byRule[k].examples.add(n))
}
const rules = Object.values(byRule).sort((a, b) => ['critical', 'serious', 'moderate', 'minor'].indexOf(a.impact) - ['critical', 'serious', 'moderate', 'minor'].indexOf(b.impact))
console.log(`\naxe: ${results.length} page scans, ${rules.length} distinct rule violations`)
for (const r of rules) {
  console.log(`\n[${r.impact}] ${r.id} — ${r.help}  (${r.pages.length} pages)`)
  console.log('  pages: ' + [...new Set(r.pages)].slice(0, 6).join(', ') + (r.pages.length > 6 ? ' …' : ''))
  ;[...r.examples].slice(0, 3).forEach((e) => console.log('  e.g. ' + e))
}
console.log('\nkeyboard & touch:')
for (const k of kb) console.log(`  ${k.pass ? 'PASS' : 'FAIL'}  ${k.check}${k.detail?.length ? '  → ' + JSON.stringify(k.detail).slice(0, 300) : ''}`)
if (JSON_OUT) writeFileSync(JSON_OUT, JSON.stringify({ results, keyboard: kb }, null, 2))
const failed = rules.filter((r) => ['critical', 'serious'].includes(r.impact)).length + kb.filter((k) => !k.pass).length
process.exit(failed ? 1 : 0)
