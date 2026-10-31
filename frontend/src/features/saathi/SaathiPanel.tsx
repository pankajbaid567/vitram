import { useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Maximize2, Mic, MicOff, Minimize2, SendHorizontal, Square, X } from 'lucide-react'
import { Dialog as D } from 'radix-ui'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { SourceLink } from '../../components/ui/data'
import { errorMessage } from '../../components/ui/feedback'
import { get, post } from '../../lib/api'
import { useSaathi } from './context'
import { ToolCard } from './ToolCards'
import { AttachButton, AttachStatus } from './Attach'
import { useAttach } from './useAttach'
import { VoiceSession, type VoiceState } from './voice'

interface Msg {
  id: string
  role: 'user' | 'assistant'
  content: string
  mode?: string | null
  modality?: string
  cards: any[]
  citations: any[]
  flags?: string[]
  lang?: string | null
  pending?: boolean
}

/** BCP-47 tag for a message so screen readers pronounce Hindi and Hinglish correctly. */
function langTag(m: Msg): string | undefined {
  const l = m.lang ?? (/[\u0900-\u097F]/.test(m.content) ? 'hi' : null)
  return l === 'hi' ? 'hi' : l === 'hinglish' ? 'hi-Latn' : l === 'en' ? 'en' : undefined
}

const VOICE_LABEL: Partial<Record<VoiceState, string>> = { connecting: 'Connecting voice…', listening: 'Listening', speaking: 'Vitt Saathi is speaking' }

export function SaathiMark({ className }: { className?: string }) {
  return (
    <span aria-hidden className={clsx('relative inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-marigold text-ink', className)}>
      <svg viewBox="0 0 24 24" className="size-[60%]" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M5 7l7 11 7-11" /><path d="M9 7h6" />
      </svg>
    </span>
  )
}

function useStatus() {
  return useQuery({ queryKey: ['ai-status'], queryFn: () => get<any>('/ai/status'), staleTime: 300_000 })
}

function Thread() {
  const { ctx, pending, consumePending, setOpen, expanded, setExpanded } = useSaathi()
  const attach = useAttach()
  const qc = useQueryClient()
  const status = useStatus()
  const key = ['conv', ctx.type, ctx.objectId ?? '', ctx.memberKey ?? '']
  const conv = useQuery({
    queryKey: key,
    queryFn: () => get<any>(`/ai/conversations/latest?context_type=${ctx.type}${ctx.objectId ? `&object_id=${ctx.objectId}` : ''}${ctx.memberKey ? `&member_key=${ctx.memberKey}` : ''}`),
  })
  const [messages, setMessages] = useState<Msg[]>([])
  const [cid, setCid] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [voice, setVoice] = useState<VoiceState>('idle')
  const [voiceNote, setVoiceNote] = useState<string | null>(null)
  const voiceRef = useRef<VoiceSession | null>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (conv.data) {
      setMessages(conv.data.messages)
      setCid(conv.data.id)
    }
  }, [conv.data])
  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }) }, [messages, busy])
  useEffect(() => () => { voiceRef.current?.stop() }, [])

  async function send(t: string) {
    const msg = t.trim()
    if (!msg || busy) return
    setErr(null)
    setText('')
    setMessages((m) => [...m, { id: 'tmp' + Date.now(), role: 'user', content: msg, cards: [], citations: [] }])
    setBusy(true)
    try {
      const r = await post<any>('/ai/chat', {
        message: msg, conversation_id: cid, context_type: ctx.type, context_object_id: ctx.objectId, member_key: ctx.memberKey,
      })
      setCid(r.conversation_id)
      setMessages((m) => [...m, r.message])
      qc.invalidateQueries({ queryKey: key })
    } catch (e) {
      setErr(errorMessage(e))
      setText(msg)
      setMessages((m) => m.filter((x) => !x.id.startsWith('tmp') || x.content !== msg))
    } finally {
      setBusy(false)
      inputRef.current?.focus()
    }
  }

  useEffect(() => {
    if (pending) {
      send(pending)
      consumePending()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending])

  async function toggleVoice() {
    if (voiceRef.current) {
      await voiceRef.current.stop()
      voiceRef.current = null
      return
    }
    if (!status.data?.voice_available) {
      setVoiceNote(status.data?.voice_note ?? 'Voice needs Gemini Live to be configured on the server.')
      return
    }
    const s = new VoiceSession(ctx, {
      onState: (st, detail) => { setVoice(st); if (detail) setVoiceNote(detail) },
      onConversation: (id) => setCid(id),
      onCards: (cards, citations) => setMessages((m) => [...m, { id: 'v' + Date.now(), role: 'assistant', content: '', cards, citations, mode: 'gemini', modality: 'voice' }]),
      onTranscript: (role, t, final) => setMessages((m) => {
        const liveId = `live-${role}`
        const rest = m.filter((x) => x.id !== liveId)
        return [...rest, { id: final ? `v${role}${Date.now()}` : liveId, role, content: t, cards: [], citations: [], modality: 'voice', pending: !final }]
      }),
    })
    voiceRef.current = s
    try {
      await s.start(cid)
    } catch (e) {
      voiceRef.current = null
      setVoice('idle')
      setVoiceNote(errorMessage(e))
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    send(text)
  }

  const toolMode = status.data?.chat_mode === 'tool'
  const label = conv.data?.context_label ?? 'General'
  const suggestions: string[] = conv.data?.suggestions ?? []
  const voiceActive = voice !== 'idle' && voice !== 'error'

  return (
    <div className="flex h-full flex-col">
      <div className="surface-hero relative flex items-center gap-3 px-4 pb-4 pt-4">
        <span className="pointer-events-none absolute -right-10 -top-16 size-40 rounded-full bg-marigold/25 blur-3xl" aria-hidden />
        <SaathiMark className="size-10 shadow-[var(--glow-saathi)]" />
        <div className="min-w-0 flex-1">
          <p className="font-semibold leading-tight text-white">Vitt Saathi <span lang="hi" className="font-normal text-white/70">वित्त साथी</span></p>
          <p className="mt-1 inline-flex max-w-full items-center gap-1.5 rounded-full bg-white/10 px-2.5 py-0.5 text-xs text-white/85 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]">
            <span className="size-1.5 shrink-0 rounded-full bg-marigold" aria-hidden />
            <span className="truncate"><span className="sr-only">Context: </span>{label}</span>
          </p>
        </div>
        <button type="button" onClick={() => setExpanded(!expanded)} aria-pressed={expanded}
          className="relative hidden size-10 items-center justify-center rounded-full text-white/75 transition-colors hover:bg-white/10 hover:text-white lg:inline-flex" aria-label={expanded ? 'Make Vitt Saathi narrower' : 'Make Vitt Saathi wider'}>
          {expanded ? <Minimize2 className="size-[1.05rem]" aria-hidden /> : <Maximize2 className="size-[1.05rem]" aria-hidden />}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="relative inline-flex size-11 items-center justify-center rounded-full text-white/75 transition-colors hover:bg-white/10 hover:text-white" aria-label="Close Vitt Saathi">
          <X className="size-5" />
        </button>
      </div>
      {toolMode && (
        <p className="mx-3 mt-3 rounded-[var(--radius-control)] border border-marigold/35 bg-marigold-soft px-3 py-2 text-xs leading-relaxed text-marigold-deep">
          <b>Tool mode.</b> Answers come from VITTRM's calculators and your data. Free-form AI is off because Gemini isn't configured.
        </p>
      )}

      <div className="flex-1 overflow-y-auto overscroll-contain px-4 py-4" aria-live="polite" aria-busy={busy}>
        {conv.isLoading && <p className="text-sm text-muted">Loading conversation…</p>}
        {!conv.isLoading && messages.length === 0 && (
          <div className="flex flex-col gap-3">
            <p className="text-[0.95rem] leading-relaxed">Ask about this page. I use your confirmed profile and documents, and I'll show where each number comes from.</p>
            <div className="flex flex-col items-start gap-2">
              {suggestions.map((s) => (
                <button key={s} type="button" onClick={() => send(s)}
                  className="min-h-10 rounded-[14px] border border-[var(--glass-hairline)] bg-white/90 px-3.5 py-2 text-left text-sm shadow-[var(--elev-1)] transition-[border-color,color,box-shadow] duration-[var(--dur)] hover:border-indigo/40 hover:text-indigo-dark hover:shadow-[var(--elev-2)]">{s}</button>
              ))}
            </div>
          </div>
        )}
        <ol className="flex flex-col gap-4">
          {messages.map((m) => (
            <li key={m.id} lang={langTag(m)} className={clsx('flex flex-col', m.role === 'user' ? 'items-end' : 'items-start')}>
              {m.role === 'user' ? (
                <p className={clsx('max-w-[85%] rounded-[18px] rounded-br-md bg-[image:var(--grad-indigo)] px-3.5 py-2 text-[0.95rem] text-white shadow-[0_4px_12px_rgb(52_67_181/0.22)]', m.pending && 'opacity-70')}>
                  {m.content}{m.modality === 'voice' && <span className="sr-only"> (spoken)</span>}
                </p>
              ) : (
                <div className="w-full">
                  {m.content && <p className={clsx('w-fit max-w-full whitespace-pre-wrap rounded-[18px] rounded-bl-md border border-[var(--glass-hairline)] bg-white/95 px-3.5 py-2.5 text-[0.95rem] leading-relaxed shadow-[var(--elev-1)]', m.pending && 'text-muted')}>{m.content}</p>}
                  {m.cards?.map((c, i) => <ToolCard key={i} card={c} onQuick={send} />)}
                  {m.citations?.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap items-center gap-1 text-xs text-muted">Sources:
                      {m.citations.slice(0, 5).map((c: any, i: number) => <SourceLink key={i} citation={c} label={c.document_name?.replace(/\.pdf$/, '') ?? 'Source'} />)}
                    </div>
                  )}
                  {m.flags?.some((f) => f.startsWith('unverified_amount')) && (
                    <p className="mt-1 text-xs text-caution">Some amounts in this reply couldn't be matched to a calculation. Rely on the cards above.</p>
                  )}
                  {m.flags?.includes('ai_unavailable') && <p className="mt-1 text-xs text-muted">The AI service didn't respond, so this answer used Tool mode.</p>}
                </div>
              )}
            </li>
          ))}
          {busy && (
            <li className="flex items-center gap-2 text-sm text-muted">
              <span className="flex gap-1" aria-hidden>{[0, 1, 2].map((i) => <span key={i} className="size-1.5 animate-pulse rounded-full bg-marigold" style={{ animationDelay: `${i * 0.2}s` }} />)}</span>
              Vitt Saathi is working it out…
            </li>
          )}
        </ol>
        <div ref={endRef} />
      </div>

      {err && <p role="alert" className="mx-3 mb-2 rounded-[var(--radius-control)] border border-critical/25 bg-critical-soft px-3 py-2 text-sm text-critical">{err}</p>}
      <AttachStatus state={attach.state} stage={attach.stage} onClear={attach.clear} />
      {voiceNote && (
        <div className="mx-3 mb-2 flex items-start gap-2 rounded-[var(--radius-control)] border border-[var(--glass-hairline)] bg-white/90 px-3 py-2 text-sm text-muted">
          <MicOff className="mt-0.5 size-4 shrink-0" aria-hidden /><span className="flex-1">{voiceNote}</span>
          <button type="button" className="-my-1 min-h-8 rounded-full px-2 text-xs font-medium text-indigo hover:bg-indigo-soft" onClick={() => setVoiceNote(null)}>Dismiss</button>
        </div>
      )}
      {voiceActive && VOICE_LABEL[voice] && (
        <p className="mx-3 mb-2 inline-flex w-fit items-center gap-2 rounded-full bg-marigold-soft px-3 py-1 text-xs font-medium text-marigold-deep" aria-hidden>
          <span className="size-1.5 rounded-full bg-marigold" />{VOICE_LABEL[voice]}
        </p>
      )}
      <form onSubmit={submit} className="m-3 mt-0 flex items-end gap-1 rounded-[22px] border border-[var(--glass-hairline)] bg-white/95 p-1.5 shadow-[var(--glass-highlight),var(--elev-2)] focus-within:shadow-[var(--glass-highlight),var(--elev-2),var(--ring)]">
        <AttachButton onPick={attach.start} disabled={!!attach.state && !attach.state.error} />
        <button type="button" onClick={toggleVoice}
          aria-label={voiceActive ? 'Stop voice' : 'Speak to Vitt Saathi'} aria-pressed={voiceActive}
          title={status.data?.voice_available ? 'Speak' : 'Voice needs Gemini Live setup'}
          className={clsx('inline-flex size-11 shrink-0 items-center justify-center rounded-full transition-colors',
            voiceActive ? 'bg-marigold text-ink listening' : status.data?.voice_available ? 'bg-marigold-soft text-marigold-deep hover:bg-marigold' : 'text-muted hover:bg-ink/5')}>
          {voice === 'speaking' ? (
            <span className="flex h-4 items-end gap-0.5" aria-hidden>{[0, 1, 2].map((i) => <span key={i} className="speaking-bar w-1 rounded bg-ink" style={{ height: 16, animationDelay: `${i * 0.15}s` }} />)}</span>
          ) : voiceActive ? <Square className="size-4" aria-hidden /> : <Mic className="size-5" aria-hidden />}
        </button>
        <span className="sr-only" aria-live="assertive">{voice === 'listening' ? 'Listening' : voice === 'speaking' ? 'Vitt Saathi is speaking' : voice === 'connecting' ? 'Connecting voice' : ''}</span>
        <label className="sr-only" htmlFor="saathi-input">Message Vitt Saathi</label>
        <textarea id="saathi-input" ref={inputRef} rows={1} value={text} onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(text) } }}
          placeholder={voice === 'listening' ? 'Listening… you can also type' : 'Ask in English, Hindi or Hinglish'}
          className="max-h-32 min-h-11 flex-1 resize-none bg-transparent px-1 py-2.5 text-[0.95rem] placeholder:text-muted focus:outline-none focus-visible:outline-none" />
        <button type="submit" disabled={!text.trim() || busy} aria-label="Send"
          className="inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-[image:var(--grad-indigo)] text-white shadow-[0_4px_12px_rgb(52_67_181/0.3)] transition-[filter,opacity] hover:brightness-110 disabled:opacity-40 disabled:shadow-none">
          <SendHorizontal className="size-5" aria-hidden />
        </button>
      </form>
    </div>
  )
}

/** Desktop: right-side panel alongside the page. Mobile: full-height sheet (RD §24.1). */
export function SaathiPanel() {
  const { open, setOpen, expanded } = useSaathi()
  const [desktop, setDesktop] = useState(() => typeof window !== 'undefined' && window.matchMedia('(min-width: 1024px)').matches)
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 1024px)')
    const on = () => setDesktop(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  if (desktop) {
    if (!open) return null
    return (
      <div className={clsx('sticky top-0 h-dvh shrink-0 p-3 pl-0 transition-[width] duration-[var(--dur-slow)] ease-[var(--ease-out-soft)]', expanded ? 'w-[min(560px,40vw)]' : 'w-[420px]')}>
        <aside aria-label="Vitt Saathi" className="window-in glass-strong flex h-full flex-col overflow-hidden rounded-[var(--radius-window)]">
          <Thread />
        </aside>
      </div>
    )
  }
  return (
    <D.Root open={open} onOpenChange={setOpen}>
      <D.Portal>
        <D.Overlay className="overlay-in fixed inset-0 z-50 bg-navy-900/35 backdrop-blur-[3px]" />
        <D.Content className="window-in glass-strong fixed inset-x-0 bottom-0 top-8 z-50 flex flex-col overflow-hidden rounded-t-[var(--radius-window)] outline-none">
          <D.Title className="sr-only">Vitt Saathi</D.Title>
          <D.Description className="sr-only">Chat or speak with your financial assistant</D.Description>
          <Thread />
        </D.Content>
      </D.Portal>
    </D.Root>
  )
}
