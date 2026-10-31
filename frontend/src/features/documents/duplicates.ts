import { ApiError } from '../../lib/api'

export const isDuplicate = (e: unknown): boolean => e instanceof ApiError && e.code === 'DUPLICATE_DOCUMENT'

export function documentLink(d: { type: string; id?: string; document_id?: string; policy_id?: string | null }) {
  const id = d.document_id ?? d.id
  if (d.type === 'insurance_policy') return d.policy_id ? `/insurance/policies/${d.policy_id}` : `/documents?focus=${id}`
  if (d.type === 'loan_document') return `/loans/documents/${id}`
  if (d.type === 'receipt') return `/documents/receipts/${id}`
  return `/documents?focus=${id}`
}
