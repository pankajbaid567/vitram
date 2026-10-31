# VITRAM web

React 19 + TypeScript + Vite + Tailwind v4 + Radix. Talks to the API only through `src/lib/api.ts` (cookie session, stable `{error:{code,message}}` contract → `ApiError`).

```bash
npm install
npm run dev          # http://localhost:5173, proxies /api to http://127.0.0.1:8000
                     # API on another port?  API_PROXY_TARGET=http://127.0.0.1:8001 npm run dev
npm test             # Vitest + Testing Library (jsdom)
npm run typecheck && npm run lint && npm run build
make a11y            # axe on every route + keyboard checks (needs the stack running and Chrome)
make e2e             # drive the demo path in Chrome and assert (same prerequisites)
```

## Structure

```
src/
  main.tsx            mount only: BrowserRouter + root ErrorBoundary
  app/                App (providers), routes (lazy, code-split), AppShell, ErrorBoundary
  features/<journey>/ one folder per journey: screens + their hooks (loans, cards, emis, insurance, documents, …)
  components/ui/      design-system primitives: button, field, feedback, overlay, data (Money, TrustMark, source citations)
  lib/                api client, auth context, formatting (Indian digit grouping), shared types
  styles/index.css    design tokens
  __tests__/          unit + app-level tests (the real route tree against a mocked fetch)
```

Conventions that matter:

- **A screen failing must not take the app down.** `ErrorBoundary` wraps the routed area and resets on navigation.
- **Money is never shown as zero when unknown.** Use `inr()` / `<Money>`: missing values read "Not available".
- **Provenance is part of the UI.** Facts render with `TrustMark` (extracted / confirmed / conflicted / missing) and open their source page.
- **Server state lives in React Query**; local state stays local.
