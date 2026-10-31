/**
 * Gemini Live voice client for Vitt Saathi (RD §11.2).
 *
 * STATUS: written against the installed @google/genai Live API types
 * (live.connect / sendRealtimeInput / sendToolResponse) but NOT verified
 * end-to-end here — the server has no Gemini credentials (docs/spec/plan.md §7).
 *
 * Flow: backend mints an ephemeral token → browser connects directly →
 * mic audio streams as 16 kHz PCM → model audio (24 kHz PCM) plays back →
 * tool calls are executed by the VITTRM backend so every number still comes
 * from deterministic code → transcripts are saved to the same conversation.
 */
import { post } from '../../lib/api'
import type { SaathiCtx } from './context'

export type VoiceState = 'idle' | 'connecting' | 'listening' | 'speaking' | 'error'

export interface VoiceEvents {
  onState: (s: VoiceState, detail?: string) => void
  onTranscript: (role: 'user' | 'assistant', text: string, final: boolean) => void
  onCards: (cards: any[], citations: any[]) => void
  onConversation: (id: string) => void
}

const WORKLET = `
class PcmCapture extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) this.port.postMessage(ch.slice(0));
    return true;
  }
}
registerProcessor('pcm-capture', PcmCapture);
`

function floatToPcm16Base64(f32: Float32Array): string {
  const buf = new ArrayBuffer(f32.length * 2)
  const view = new DataView(buf)
  for (let i = 0; i < f32.length; i++) {
    const s = Math.max(-1, Math.min(1, f32[i]))
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
  let bin = ''
  const bytes = new Uint8Array(buf)
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i])
  return btoa(bin)
}

function pcm16Base64ToFloat(b64: string): Float32Array {
  const bin = atob(b64)
  const out = new Float32Array(bin.length / 2)
  for (let i = 0; i < out.length; i++) {
    let v = bin.charCodeAt(i * 2) | (bin.charCodeAt(i * 2 + 1) << 8)
    if (v >= 0x8000) v -= 0x10000
    out[i] = v / 0x8000
  }
  return out
}

export class VoiceSession {
  private session: any = null
  private micStream: MediaStream | null = null
  private inCtx: AudioContext | null = null
  private outCtx: AudioContext | null = null
  private playhead = 0
  private sources: AudioBufferSourceNode[] = []
  private conversationId: string | null = null
  private userText = ''
  private botText = ''
  private closed = false
  private ctx: SaathiCtx
  private ev: VoiceEvents

  constructor(ctx: SaathiCtx, ev: VoiceEvents) {
    this.ctx = ctx
    this.ev = ev
  }

  async start(conversationId: string | null) {
    this.ev.onState('connecting')
    const t = await post<any>('/ai/session-token', {
      context_type: this.ctx.type, context_object_id: this.ctx.objectId, member_key: this.ctx.memberKey, conversation_id: conversationId,
    })
    this.conversationId = t.conversation_id
    this.ev.onConversation(t.conversation_id)
    const { GoogleGenAI, Modality } = await import('@google/genai')
    const ai = new GoogleGenAI({ apiKey: t.token, httpOptions: { apiVersion: t.api_version } })
    this.session = await ai.live.connect({
      model: t.model,
      config: {
        responseModalities: [Modality.AUDIO],
        systemInstruction: t.system_instruction,
        tools: [{ functionDeclarations: t.function_declarations.map((d: any) => ({ name: d.name, description: d.description, parametersJsonSchema: d.parameters })) }],
        inputAudioTranscription: {},
        outputAudioTranscription: {},
      },
      callbacks: {
        onopen: () => this.ev.onState('listening'),
        onmessage: (m: any) => this.onMessage(m),
        onerror: () => this.ev.onState('error', 'The voice connection had a problem. You can keep using chat.'),
        onclose: () => { if (!this.closed) this.ev.onState('idle') },
      },
    })
    await this.startMic()
  }

  private async startMic() {
    this.micStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } })
    this.inCtx = new AudioContext({ sampleRate: 16000 })
    const url = URL.createObjectURL(new Blob([WORKLET], { type: 'application/javascript' }))
    await this.inCtx.audioWorklet.addModule(url)
    const src = this.inCtx.createMediaStreamSource(this.micStream)
    const node = new AudioWorkletNode(this.inCtx, 'pcm-capture')
    let chunk: number[] = []
    node.port.onmessage = (e) => {
      chunk.push(...(e.data as Float32Array))
      if (chunk.length >= 1600) { // ~100 ms
        this.session?.sendRealtimeInput({ audio: { data: floatToPcm16Base64(Float32Array.from(chunk)), mimeType: 'audio/pcm;rate=16000' } })
        chunk = []
      }
    }
    src.connect(node)
  }

  private play(b64: string) {
    if (!this.outCtx) this.outCtx = new AudioContext({ sampleRate: 24000 })
    const f = pcm16Base64ToFloat(b64)
    const buf = this.outCtx.createBuffer(1, f.length, 24000)
    buf.copyToChannel(f as Float32Array<ArrayBuffer>, 0)
    const s = this.outCtx.createBufferSource()
    s.buffer = buf
    s.connect(this.outCtx.destination)
    const at = Math.max(this.playhead, this.outCtx.currentTime)
    s.start(at)
    this.playhead = at + buf.duration
    this.sources.push(s)
    s.onended = () => {
      this.sources = this.sources.filter((x) => x !== s)
      if (!this.sources.length) this.ev.onState('listening')
    }
    this.ev.onState('speaking')
  }

  private stopPlayback() {
    this.sources.forEach((s) => { try { s.stop() } catch { /* already stopped */ } })
    this.sources = []
    this.playhead = 0
  }

  private async onMessage(m: any) {
    const sc = m.serverContent
    if (sc?.interrupted) {
      this.stopPlayback()
      this.ev.onState('listening')
    }
    if (sc?.inputTranscription?.text) {
      this.userText += sc.inputTranscription.text
      this.ev.onTranscript('user', this.userText, false)
    }
    if (sc?.outputTranscription?.text) {
      this.botText += sc.outputTranscription.text
      this.ev.onTranscript('assistant', this.botText, false)
    }
    for (const p of sc?.modelTurn?.parts ?? []) {
      if (p.inlineData?.data && String(p.inlineData.mimeType ?? '').startsWith('audio/')) this.play(p.inlineData.data)
    }
    if (sc?.turnComplete) await this.flushTranscripts()
    if (m.toolCall?.functionCalls?.length) {
      const responses = []
      for (const fc of m.toolCall.functionCalls) {
        try {
          const r = await post<any>(`/ai/tools/${fc.name}`, {
            args: fc.args ?? {}, conversation_id: this.conversationId, context_type: this.ctx.type,
            context_object_id: this.ctx.objectId, member_key: this.ctx.memberKey,
          })
          this.ev.onCards(r.cards ?? [], r.citations ?? [])
          responses.push({ id: fc.id, name: fc.name, response: { result: r.result } })
        } catch (e: any) {
          responses.push({ id: fc.id, name: fc.name, response: { error: e?.message ?? 'Tool failed' } })
        }
      }
      this.session?.sendToolResponse({ functionResponses: responses })
    }
  }

  private async flushTranscripts() {
    const u = this.userText.trim()
    const a = this.botText.trim()
    this.userText = ''
    this.botText = ''
    if (u) this.ev.onTranscript('user', u, true)
    if (a) this.ev.onTranscript('assistant', a, true)
    if (!this.conversationId) return
    try {
      if (u) await post(`/ai/conversations/${this.conversationId}/transcript`, { role: 'user', text: u })
      if (a) await post(`/ai/conversations/${this.conversationId}/transcript`, { role: 'assistant', text: a })
    } catch { /* transcript persistence is best-effort */ }
  }

  async stop() {
    this.closed = true
    await this.flushTranscripts()
    this.stopPlayback()
    this.micStream?.getTracks().forEach((t) => t.stop())
    try { this.session?.close() } catch { /* ignore */ }
    await this.inCtx?.close().catch(() => {})
    await this.outCtx?.close().catch(() => {})
    this.ev.onState('idle')
  }
}
