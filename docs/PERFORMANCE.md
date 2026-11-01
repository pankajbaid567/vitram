# Performance

Measured, not guessed. Reproduce with `loadtest/k6.js` ([k6](https://k6.io)).

```bash
# one API process against local PostgreSQL 16 (see "Setup")
BASE=http://127.0.0.1:18000 VUS=50 USERS=10 DURATION=30s k6 run loadtest/k6.js         # realistic users (think time)
THINK=0 BASE=http://127.0.0.1:18000 VUS=30 USERS=10 DURATION=25s k6 run loadtest/k6.js  # saturation (no think time)
```

`setup()` opens `USERS` sample workspaces (so their cost is reported separately), then every virtual user replays a read-heavy mix as one
of them: dashboard 35%, documents 15%, EMIs 12%, insurance overview 12%, loan recommendation 12%, cards 14%. Thresholds in the script:
reads fail < 1% and p95 < 300 ms.

## Setup

Apple M3 laptop (8 cores), Docker PostgreSQL 16 on the same machine, **one** uvicorn process (the same shape as the free Render instance, but with
far more CPU), `RATE_LIMIT_BACKEND=database`, no reverse proxy. Numbers on the free cloud tier will be higher: add the network round trip
(browser to Cloudflare to Render in Ohio) and a fraction of a CPU.

## Results

| Scenario | Users | Throughput | Read p50 | Read p95 | Read p99 | Errors |
|---|---|---|---|---|---|---|
| Realistic (0.5 s think time) | 10 | 18 req/s | 17 ms | 86 ms | 207 ms | 0 / 627 |
| Realistic | 25 | 46 req/s | 13 ms | 108 ms | 211 ms | 0 / 1,594 |
| Realistic | 50 | 90 req/s | 12 ms | 151 ms | 260 ms | 0 / 3,129 |
| **Saturation** (no think time), after the IRR fix | 30 | **~213 req/s** | 109 ms | 239 ms | 343 ms | 0 / 12,546 |
| Saturation, before the IRR fix | 30 | ~187 req/s | 124 ms | 267 ms | 411 ms | 0 / 11,036 |

A single process saturates at about 200 requests per second of this mix with no errors; 50 simultaneous realistic users use less than half of that.
Opening a sample workspace (five documents parsed inline) takes about 0.4 to 0.5 s on this machine.

## Optimisation 1: loan IRR (before / after)

Profiling the handlers directly with `cProfile` showed where the CPU went.

| `POST /api/loans/recommend` | Before | After |
|---|---|---|
| CPU per request | 13.5 ms | **7.2 ms (-46%)** |
| Python function calls per 60 requests | 3,167,065 | **281,843 (-91%)** |

Cause: `emi.monthly_irr` ran a fixed 200 bisection steps, and every step summed the whole payment stream (`O(tenure)`), so ranking eight
products at a 36-month tenure cost about 60,000 present-value evaluations per 60 requests. The fix: stop when the bracket is below float
precision (about 50 steps) and use the closed-form annuity value for level EMI streams (`O(1)` per step). Equivalence is pinned by
`tests/test_irr_fast.py`: 300 random level streams and 100 uneven streams agree with the original algorithm to within `1e-12`.
Across the whole mix this lifted saturation throughput by about 14%, because loan ranking is one request type in six.

## Where the remaining time goes (profiled)

- **`GET /api/dashboard`** is about 10 ms of CPU and issues **15 queries** per request. Most of the time is waiting on the database. The
  `financial_profiles` row (a large JSON document) is the single most expensive statement by total time. This is the target of the
  query-count and caching work (see `docs/FUTURE.md`, items 3 and 9).
- **`POST /api/loans/recommend`** writes a `calculation_runs` row per call (13.7 ms average insert under load). Moving that audit write off the
  request path is a candidate.
- Every authenticated request reads the `users` row once (about 0.6 ms); acceptable.

## SLOs this suite checks

- Reads fail less than 1% (met: 0%).
- Read p95 below 300 ms at 50 realistic users (met: 151 ms).
