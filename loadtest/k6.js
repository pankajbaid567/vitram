// k6 load test for VITRAM.
//   BASE=http://127.0.0.1:18000 VUS=25 DURATION=60s k6 run loadtest/k6.js
// setup() opens USERS sample workspaces (their cost is reported separately), then every virtual user replays a realistic
// read-heavy mix as one of those users, so read latency is not polluted by workspace creation.
import http from 'k6/http'
import { check, sleep } from 'k6'
import { Trend } from 'k6/metrics'

const BASE = __ENV.BASE || 'http://127.0.0.1:18000'
const VUS = Number(__ENV.VUS || 20)
const USERS = Number(__ENV.USERS || 10)
const THINK = Number(__ENV.THINK ?? 0.5) // seconds between requests per user; 0 = saturation test
const DURATION = __ENV.DURATION || '60s'
const workspace = new Trend('workspace_create_ms', true)

export const options = {
  scenarios: { mix: { executor: 'constant-vus', vus: VUS, duration: DURATION } },
  thresholds: {
    'http_req_failed{kind:read}': ['rate<0.01'],
    'http_req_duration{kind:read}': ['p(95)<300'],
    // per-endpoint rows in the summary (limits are deliberately loose; the aim is to see the numbers)
    ...Object.fromEntries(['dashboard', 'documents', 'emis', 'insurance', 'loan_recommend', 'cards'].map((n) => [`http_req_duration{name:${n}}`, ['p(95)<5000']])),
  },
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
}

const JSONH = { headers: { 'Content-Type': 'application/json', Origin: BASE } }
const read = (name) => ({ tags: { kind: 'read', name } })

export function setup() {
  const sessions = []
  for (let i = 0; i < USERS; i++) {
    const r = http.post(`${BASE}/api/demo/workspace`, null, { headers: { Origin: BASE } })
    workspace.add(r.timings.duration)
    if (r.status === 200) sessions.push(r.cookies.vitram_session[0].value)
  }
  return { sessions }
}

export default function (data) {
  const jar = http.cookieJar()
  jar.set(BASE, 'vitram_session', data.sessions[(__VU - 1) % data.sessions.length])
  const pick = Math.random()
  let r
  if (pick < 0.35) r = http.get(`${BASE}/api/dashboard`, read('dashboard'))
  else if (pick < 0.50) r = http.get(`${BASE}/api/documents`, read('documents'))
  else if (pick < 0.62) r = http.get(`${BASE}/api/emis`, read('emis'))
  else if (pick < 0.74) r = http.get(`${BASE}/api/insurance/overview`, read('insurance'))
  else if (pick < 0.86)
    r = http.post(`${BASE}/api/loans/recommend`, JSON.stringify({ purpose: 'personal', amount: 300000 }), { ...JSONH, ...read('loan_recommend') })
  else r = http.get(`${BASE}/api/cards`, read('cards'))
  if (r.status !== 200 && __ENV.DEBUG) console.log(r.request.url, r.status, r.body.slice(0, 100))
  check(r, { ok: (x) => x.status === 200 })
  if (THINK > 0) sleep(THINK * (0.4 + Math.random() * 1.2))
}
