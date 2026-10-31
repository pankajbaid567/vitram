import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { ApiError, get, upload } from '../../lib/api'
import type { DocumentRow } from '../../lib/types'
import { useSaathi } from './context'

export type AttachKind = 'receipt' | 'insurance_policy' | 'loan_document'
export interface AttachState { name: string; progress: number | null; docId: string | null; error: string | null; consent?: boolean }

/** Upload a document from the chat. It goes through the normal pipeline; when it has been read, Vitt Saathi switches
 * to that document's context and summarises it. Nothing is confirmed on the user's behalf. */
export function useAttach() {
  const { setCtx, ask } = useSaathi()
  const [upl, setUpl] = useState<AttachState | null>(null)
  const done = useRef<string | null>(null)
  const poll = useQuery({
    queryKey: ['doc', upl?.docId], queryFn: () => get<DocumentRow>(`/documents/${upl!.docId}`), enabled: !!upl?.docId,
    refetchInterval: (q) => (q.state.data && ['queued', 'processing'].includes(q.state.data.status) ? 1000 : false),
  })
  const d = poll.data
  const finished = !!d && d.id === upl?.docId && ['ready', 'needs_review'].includes(d.status)
  useEffect(() => {
    if (!finished || !d || done.current === d.id) return
    done.current = d.id
    setCtx({ type: 'document', objectId: d.id })
    ask(d.type === 'receipt' ? 'Summarise this receipt' : 'Summarise this document')
  }, [finished, d, setCtx, ask])
  const failed = d && d.id === upl?.docId && d.status === 'failed' ? (d.error_message ?? "Couldn't read this file.") : null
  const state: AttachState | null = upl && !finished ? { ...upl, error: upl.error ?? failed } : null

  async function start(kind: AttachKind, file: File) {
    setUpl({ name: file.name, progress: 0, docId: null, error: null })
    const fd = new FormData()
    fd.append('file', file)
    fd.append('type', kind)
    try {
      const doc = await upload<DocumentRow>('/documents', fd, (p) => setUpl((s) => s && { ...s, progress: p }))
      setUpl((s) => s && { ...s, progress: null, docId: doc.id })
    } catch (e) {
      if (e instanceof ApiError && e.code === 'DUPLICATE_DOCUMENT' && e.details?.document_id) {
        // Already in the workspace: talk about that copy instead of failing.
        setUpl(null)
        setCtx({ type: 'document', objectId: e.details.document_id })
        ask(e.details.type === 'receipt' ? 'Summarise this receipt' : 'Summarise this document')
        return
      }
      const consent = e instanceof ApiError && e.code === 'CONSENT_REQUIRED'
      setUpl((s) => s && { ...s, progress: null, error: e instanceof Error ? e.message : 'Upload failed.', consent })
    }
  }
  return { state, start, clear: () => setUpl(null), stage: d?.stage }
}
