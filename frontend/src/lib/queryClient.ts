import { QueryClient } from '@tanstack/react-query'
import { ApiError } from './api'

/** One shared client. Auth/permission/validation errors are final, so they are never retried. */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: (n, e) => !(e instanceof ApiError && [401, 403, 404, 422].includes(e.status)) && n < 2, refetchOnWindowFocus: false },
  },
})
