import { useQuery } from '@tanstack/react-query'
import { get } from './api'

/** What this VITTRM server can read. Photos and scans need OCR; digital PDFs and CSVs never do. */
export interface VisionStatus { provider: 'macos' | 'gemini' | 'none'; configured: boolean; on_device: boolean; note: string }

export function useAiStatus() {
  return useQuery({ queryKey: ['ai-status'], queryFn: () => get<any>('/ai/status'), staleTime: 300_000 })
}

export function useVision(): VisionStatus | undefined {
  return useAiStatus().data?.vision
}

export const IMAGE_EXT = '.jpg,.jpeg,.png,.webp'

/** File types to offer for a document type, given whether scans/photos can be read here. */
export function acceptFor(type: 'bank_statement' | 'insurance_policy' | 'loan_document' | 'receipt', vision?: VisionStatus): string {
  const base = type === 'bank_statement' ? '.pdf,.csv' : '.pdf'
  return vision?.configured ? `${base},${IMAGE_EXT}` : base
}
