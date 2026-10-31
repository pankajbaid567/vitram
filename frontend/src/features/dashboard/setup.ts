import { useQuery } from '@tanstack/react-query'
import { get } from '../../lib/api'

/** Real setup progress, derived only from what VITTRM holds for this user (no score, no estimates). */
export type SetupStep = { key: string; label: string; done: boolean; to: string }

export function setupSteps(d: any): SetupStep[] {
  if (!d) return []
  const j = d.journeys
  return [
    { key: 'statement', label: 'Upload a bank statement', done: d.data_quality.statements_processed > 0, to: '/onboarding/statement' },
    { key: 'policy', label: 'Add at least one policy', done: j.insurance.active_policies > 0, to: '/insurance/upload' },
    { key: 'cards', label: 'Add your cards', done: j.cards.count > 0, to: '/cards' },
    { key: 'emis', label: 'Confirm your EMIs', done: j.emis.count > 0 && j.emis.confirmed === j.emis.count, to: '/emis' },
  ]
}

export function useDashboard() {
  return useQuery({
    queryKey: ['dashboard'], queryFn: () => get<any>('/dashboard'), staleTime: 30_000,
    refetchInterval: (q) => (q.state.data?.data_quality?.documents_processing ? 2000 : false),
  })
}
