export type FactState = 'extracted' | 'confirmed' | 'conflicted' | 'missing' | 'rejected'

export interface Fact<T = number | null> {
  value: T
  state: FactState
  source: string
  confidence?: number
  statement_value?: number | null
  needs_review?: boolean
}

export interface Citation {
  document_id: string
  document_type: string
  document_name?: string | null
  page?: number | null
  section?: string | null
  snippet?: string | null
  fact_key?: string | null
  confidence?: number | null
  user_verified?: boolean
}

export interface CatalogueMeta {
  source: string
  last_updated: string
  is_mock: boolean
  is_stale: boolean
}

export interface User {
  id: string
  name: string
  email: string
  email_verified: boolean
  dob: string | null
  city: string | null
  employment_type: string | null
  employer: string | null
  designation: string | null
  salary_manual: number | null
  preferred_language: string
  phone_masked: string | null
  phone_verified: boolean
  onboarding_step: string
  is_sample: boolean
  consents: string[]
}

export interface DocFact {
  id: string
  fact_type: string
  key: string
  label: string
  value: any
  unit: string | null
  state: FactState
  confidence: number
  user_verified: boolean
  citation: Citation
}

export interface DocumentRow {
  id: string
  type: 'bank_statement' | 'insurance_policy' | 'loan_document' | 'card_document' | 'receipt'
  type_label: string
  display_name: string
  status: 'queued' | 'processing' | 'needs_review' | 'ready' | 'failed'
  stage: string
  error_code: string | null
  error_message: string | null
  period_months: number | null
  period_start: string | null
  period_end: string | null
  page_count: number | null
  upload_time: string
  warnings: string[]
  transactions_found?: number | null
  facts_found?: number | null
  policy_id?: string | null
  user_loan_id?: string | null
  account_label?: string | null
  size_bytes: number
  read_from_scan?: boolean
  ocr?: { provider: 'macos' | 'gemini'; on_device: boolean; mean_confidence: number } | null
  receipt?: { merchant?: string | null; total?: number | null; purchase_date?: string | null } | null
  linked_transaction_id?: string | null
  mime?: string
}

export interface Member {
  key: string
  name: string
  relation: string
  age?: number | null
}
