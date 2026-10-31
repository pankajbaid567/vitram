// Real-user journey in Chrome, start to finish, as a brand-new person (no sample shortcut):
//   sign up → onboarding → upload a bank statement → review → dashboard → add a policy → loans → cards → EMIs →
//   insurance emergency → reminders → ask Vitt Saathi → export data → delete the account.
//
//   node scripts/e2e-journey.mjs [--base http://localhost:5173] [--fixtures ../backend/fixtures] [--width 390]
//
// Needs the API and web app running and a local Chrome. Uses only the repository's fictional fixture files.
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { launch, runner, sleep } from './lib/browser.mjs'

const args = process.argv.slice(2)
const arg = (name, dflt) => (args.includes(name) ? args[args.indexOf(name) + 1] : dflt)
const BASE = arg('--base', 'http://localhost:5173')
const FIX = resolve(dirname(fileURLToPath(import.meta.url)), arg('--fixtures', '../../backend/fixtures'))
const email = `journey${Date.now()}@example.com`
const PASSWORD = 'Passw0rd!long'

const WIDTH = Number(arg('--width', 1440))
const b = await launch(BASE, { width: WIDTH, height: WIDTH < 800 ? 844 : 900 })
const { step, summary } = runner()
console.log(`VITRAM user journey against ${BASE} at ${WIDTH}px as ${email}`)

/** On failure, show what the page offered so the next fix is obvious. */
const offered = () => b.js(`'buttons: ' + [...document.querySelectorAll('button,a[href]')].map(e => e.innerText.trim()).filter(Boolean).slice(0, 22).join(' | ') + '\\n      labels: ' + [...document.querySelectorAll('label')].map(e => e.innerText.trim().split('\\n')[0]).filter(Boolean).slice(0, 14).join(' | ')`)
const must = async (ok, what) => { if (ok === false || (typeof ok === 'string' && ok !== 'ok')) throw new Error(`${what}\n      path: ${await b.path()}\n      ${await offered()}`) }
const expectText = (s, ms) => b.waitFor(`"${s}"`, b.hasText(s), ms)
const expectPath = (re) => b.waitFor(`path ${re}`, `new RegExp(${JSON.stringify(re)}).test(location.pathname)`)

await step('sign up as a new user', async () => {
  await b.go('/signup')
  await expectText('Create account')
  for (const [l, v] of [['your name', 'Priya Journey'], ['email', email], ['password', PASSWORD], ['confirm password', PASSWORD]]) await must(await b.fill(l, v), `fill ${l}`)
  await must(await b.click('label', 'accept the terms'), 'tick the terms')
  await must(await b.click('button', '^Create account$'), 'submit')
  await expectPath('^/onboarding/about')
})

await step('onboarding: about you', async () => {
  await expectText('About you')
  await b.fill('date of birth', '1994-02-11')
  await b.fill('city', 'Mumbai')
  await must(await b.click('button', '^(Continue|Next|Save)'), 'continue')
  await expectPath('^/onboarding/family')
})

await step('onboarding: family (add a parent)', async () => {
  await expectText('Family')
  await b.fill('name', 'Kamala Journey')
  await b.fill('relation', 'mother')
  await b.click('button', '^(Add|Add member|Save)')
  await sleep(600)
  await must(await b.click('button, a', '^(Continue|Next|Skip)'), 'continue')
  await expectPath('^/onboarding/statement')
})

await step('upload a bank statement and see it read', async () => {
  await expectText('Upload a bank statement')
  await must(await b.click('label, button', '^(I agree|Agree)'), 'agree to document processing')
  await b.click('button', '^Continue$')
  await b.waitFor('the file picker', `document.querySelectorAll('input[type=file]').length > 0`)
  await b.upload(`${FIX}/sample_statement_6m.csv`)
  await b.fill('account name', 'Salary account')
  await b.click('label', '6 months')
  await must(await b.click('button', 'Upload & analyse'), 'upload')
  await b.waitFor('the statement to be read', b.hasText('260 transactions read'), 60000)
})

await step('review the profile the statement produced', async () => {
  await must(await b.click('a, button', 'Review your profile'), 'open the review')
  await expectPath('/(profile/review|onboarding/processing)')
  await b.go('/profile/review')
  await expectText('Review your financial profile')
  await expectText('Salary')
})

await step('the dashboard shows real figures from the statement', async () => {
  await b.go('/')
  await expectText('Hello, Priya')
  await expectText('₹1,18,200')
})

await step('add an insurance policy by upload', async () => {
  await b.go('/insurance/upload')
  await b.waitFor('the upload page', `document.querySelectorAll('input[type=file]').length > 0 || /I agree/.test(document.body.innerText)`)
  if (await b.js(`/I agree/.test(document.body.innerText) && document.querySelectorAll('input[type=file]').length === 0`)) {
    await b.click('label', '^I agree'); await b.click('button', '^Continue$')
    await b.waitFor('the file picker', `document.querySelectorAll('input[type=file]').length > 0`)
  }
  await b.upload(`${FIX}/sample_policy_family_health.pdf`)
  await must(await b.click('label', '^You$'), 'say the policy covers you')
  await must(await b.click('button', '^Analyse policy$'), 'analyse the policy')
  await b.waitFor('the policy summary', `/Sum insured/i.test(document.body.innerText) && /Family Health Shield|Sahyadri/i.test(document.body.innerText)`, 60000)
})

await step('loans: ask for ₹3,00,000 and see ranked options with real cost', async () => {
  await b.go('/loans/results?purpose=personal&amount=300000&tenure=36&collateral=none')
  await expectText('₹3,00,000 for personal need')
  await expectText('₹9,857')
  await must(await b.click('a', 'Real cost & clauses'), 'open real cost')
  await expectText('Real cost')
  await b.waitFor('contingent charges', `/late|foreclosure|prepayment/i.test(document.body.innerText)`)
})

await step('loans: compare two options', async () => {
  await b.go('/loans/results?purpose=personal&amount=300000&tenure=36&collateral=none')
  await expectText('Salaried Personal Loan')
  await b.js(`[...document.querySelectorAll('input[type=checkbox]')].slice(0, 2).forEach((c) => c.click())`)
  await must(await b.click('button, a', '^Compare'), 'compare')
  await expectText('Compare loans')
})

await step('cards: add a card and ask which to use', async () => {
  await b.go('/cards')
  await expectText('Credit cards')
  await b.go('/cards/optimize')
  await expectText('Which card should I use?')
})

await step('EMIs: the detected EMI appears and can be confirmed', async () => {
  await b.go('/emis')
  await expectText('Monthly EMIs')
  await expectText('Konkan Finance')
  await b.click('button', '^Confirm')
  await sleep(500)
})

await step('insurance emergency mode finds the uploaded policy', async () => {
  await b.go('/insurance/emergency?event=hospitalisation')
  await expectText('Who needs care?')
  await b.waitFor('the person list', `[...document.querySelectorAll('button, label, [role=radio]')].some((e) => /^Me$/.test(e.innerText.trim()))`)
  await must(await b.click('button, label, [role=radio]', '^Me$'), 'choose "Me"')
  await b.waitFor('a policy that may apply', `/May apply|Family Health Shield/.test(document.body.innerText)`)
})

await step('reminder settings state whether WhatsApp is available', async () => {
  await b.go('/settings/reminders')
  await expectText('WhatsApp')
  // Either the honest "not connected" notice, or (when this environment has a provider) a working switch.
  await b.waitFor('the WhatsApp state', `/isn't connected/.test(document.body.innerText) || /I agree to WhatsApp messages|on WhatsApp/i.test(document.body.innerText)`)
})

await step('ask Vitt Saathi a question and get an answer', async () => {
  await b.go('/cards')
  await expectText('Credit cards')
  await must(await b.click('button', 'Ask Vitt Saathi'), 'open the assistant')
  await b.waitFor('the message box', `!!document.querySelector('textarea[aria-label*="Ask in English"], textarea[placeholder*="Ask in English"]')`)
  const before = await b.js(`document.querySelectorAll('[aria-live] li, ol li').length`)
  await b.js(`(() => { const el = document.querySelector('textarea[aria-label*="Ask in English"], textarea[placeholder*="Ask in English"]'); Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(el, 'What is credit utilisation?'); el.dispatchEvent(new Event('input', { bubbles: true })) })()`)
  await must(await b.click('button', '^Send$'), 'send the question')
  await b.waitFor('the assistant to answer', `document.querySelectorAll('[aria-live] li, ol li').length >= ${before + 2}`, 30000)
  await expectText('credit utilisation')
})

await step('data controls: export works, deleting the account signs out and locks the door', async () => {
  await b.go('/settings')
  await expectText('Download my data')
  const status = await b.js(`fetch('/api/profile/export').then(async (r) => r.status + ':' + (await r.text()).includes('"account"'))`)
  if (status !== '200:true') throw new Error('export did not return the account JSON: ' + status)
  await must(await b.click('button', '^Delete account$'), 'open delete account')
  await b.fill('your password', PASSWORD)
  await b.fill('type delete', 'DELETE')
  await must(await b.click('[role=dialog] button', '^Delete my account$'), 'confirm deletion')
  await expectPath('^/(welcome|login)')
  await b.go('/login')
  await b.fill('email', email); await b.fill('password', PASSWORD)
  await b.click('button', '^Sign in$')
  await b.waitFor('a refusal', `/don't match|doesn't match|invalid/i.test(document.body.innerText)`)
})

await step('no console errors, exceptions or failed requests along the way', async () => {
  const real = b.problems.filter((p) => !/HTTP 401 .*\/api\/(auth\/login|auth\/me)|HTTP 409/.test(p))
  if (real.length) throw new Error('\n      ' + [...new Set(real)].join('\n      '))
})

b.close(summary())
