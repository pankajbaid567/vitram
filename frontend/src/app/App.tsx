import { QueryClientProvider } from '@tanstack/react-query'
import { Suspense, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { SourceProvider } from '../components/ui/data'
import { PageSkeleton, ToastProvider } from '../components/ui/feedback'
import { SaathiProvider } from '../features/saathi/context'
import { AuthProvider } from '../lib/auth'
import { queryClient } from '../lib/queryClient'
import { ErrorBoundary } from './ErrorBoundary'
import { AppRoutes } from './routes'

function ScrollTop() {
  const { pathname } = useLocation()
  useEffect(() => { window.scrollTo(0, 0) }, [pathname])
  return null
}

/** Provider tree + routes. The router itself is supplied by the caller (BrowserRouter in production, MemoryRouter in tests). */
export function App() {
  const { pathname } = useLocation()
  return (
    <QueryClientProvider client={queryClient}>
      <ScrollTop />
      <ToastProvider>
        <AuthProvider>
          <SaathiProvider>
            <SourceProvider>
              {/* One failing screen must not unmount the whole app: reset whenever the user navigates. */}
              <ErrorBoundary resetKey={pathname}>
                <Suspense fallback={<div className="mx-auto max-w-3xl p-8"><PageSkeleton /></div>}>
                  <AppRoutes />
                </Suspense>
              </ErrorBoundary>
            </SourceProvider>
          </SaathiProvider>
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>
  )
}
