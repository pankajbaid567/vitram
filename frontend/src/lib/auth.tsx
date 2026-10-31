import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useContext, useEffect, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, get, post, setUnauthenticatedHandler } from './api'
import type { User } from './types'

interface AuthState {
  user: User | null
  loading: boolean
  refresh: () => Promise<unknown>
  logout: () => Promise<void>
}

const Ctx = createContext<AuthState>({ user: null, loading: true, refresh: async () => {}, logout: async () => {} })

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const q = useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      try {
        return await get<User>('/auth/me')
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null
        throw e
      }
    },
    staleTime: 60_000,
  })
  useEffect(() => {
    setUnauthenticatedHandler(() => {
      // A request was refused although the app thought it was signed in: the session ended.
      const wasSignedIn = !!qc.getQueryData(['me'])
      qc.setQueryData(['me'], null)
      navigate(wasSignedIn ? '/login?expired=1' : '/login')
    })
  }, [qc, navigate])
  const value: AuthState = {
    user: q.data ?? null,
    loading: q.isLoading,
    refresh: () => qc.invalidateQueries({ queryKey: ['me'] }),
    logout: async () => {
      await post('/auth/logout')
      qc.clear()
      qc.setQueryData(['me'], null)
      navigate('/login')
    },
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export const useAuth = () => useContext(Ctx)
