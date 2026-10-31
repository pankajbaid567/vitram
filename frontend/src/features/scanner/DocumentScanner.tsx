/* eslint-disable @typescript-eslint/no-explicit-any */
import clsx from 'clsx'
import { ArrowLeft, Camera, Check, CircleAlert, Loader2, RotateCw, ScanLine, Upload, X } from 'lucide-react'
import { Dialog as D } from 'radix-ui'
import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import { loadOpenCV, type CV } from './opencv'
import { applyFilter, detectDocument, quadDrift, rotate90, warpDocument, type Pt, type Quad, type ScanFilter } from './vision'

type Phase = 'starting' | 'live' | 'adjust' | 'preview' | 'error'
const PROC_W = 640 // frames are analysed at this width (fast, ~10 fps on a laptop)
const STABLE_FRAMES = 12 // ~1.2 s holding still → auto-capture
const CORNER_NAMES = ['Top-left', 'Top-right', 'Bottom-right', 'Bottom-left']

function cameraError(e: any): string {
  if (!window.isSecureContext) return 'The camera only works on a secure page (https or localhost). Upload a photo instead.'
  if (e?.name === 'NotAllowedError') return 'Camera access was blocked. Allow the camera for this site in your browser settings, or upload a photo instead.'
  if (e?.name === 'NotFoundError' || e?.name === 'OverconstrainedError') return 'No camera was found on this device. Upload a photo instead.'
  if (e?.name === 'NotReadableError') return 'The camera is being used by another app. Close it and try again.'
  if (String(e?.message ?? '').includes('OpenCV')) return 'The scanner could not load. Check your connection and try again, or upload a photo instead.'
  return 'The camera could not start. Upload a photo instead.'
}

/** Full-screen document scanner: live camera with real-time edge detection (OpenCV.js), auto-capture when steady,
 * adjustable corners, perspective correction and scan filters. Nothing leaves the browser until "Use this scan". */
export default function DocumentScanner({ open, onOpenChange, onDone, onUploadInstead, title = 'Scan a document' }: {
  open: boolean; onOpenChange: (v: boolean) => void; onDone: (file: File) => void; onUploadInstead?: () => void; title?: string
}) {
  const [phase, setPhase] = useState<Phase>('starting')
  const [error, setError] = useState<string | null>(null)
  const [found, setFound] = useState(false)
  const [stability, setStability] = useState(0)
  const [auto, setAuto] = useState(true)
  const [flash, setFlash] = useState(false)
  const [still, setStill] = useState<{ url: string; w: number; h: number } | null>(null)
  const [corners, setCorners] = useState<Quad | null>(null)
  const [filter, setFilter] = useState<ScanFilter>('enhanced')
  const [turns, setTurns] = useState(0)
  const [busy, setBusy] = useState(false)

  const video = useRef<HTMLVideoElement>(null)
  const overlay = useRef<HTMLCanvasElement>(null)
  const preview = useRef<HTMLCanvasElement>(null)
  const svg = useRef<SVGSVGElement>(null)
  const stream = useRef<MediaStream | null>(null)
  const cv = useRef<CV | null>(null)
  const proc = useRef<HTMLCanvasElement | null>(null)
  const full = useRef<HTMLCanvasElement | null>(null)
  const warped = useRef<any>(null)
  const loop = useRef<number | null>(null)
  const track = useRef<{ quad: Quad | null; shown: Quad | null; stable: number; misses: number; last: number }>({ quad: null, shown: null, stable: 0, misses: 0, last: 0 })
  const autoRef = useRef(true)

  const stopLoop = () => { if (loop.current) cancelAnimationFrame(loop.current); loop.current = null }
  const stopCamera = () => { stopLoop(); stream.current?.getTracks().forEach((t) => t.stop()); stream.current = null }
  const freeWarp = () => { warped.current?.delete?.(); warped.current = null }

  const drawOverlay = useCallback((q: Quad | null, stable: number) => {
    const c = overlay.current, v = video.current
    if (!c || !v || !v.videoWidth) return
    const dpr = window.devicePixelRatio || 1
    const cw = c.clientWidth, ch = c.clientHeight
    if (c.width !== Math.round(cw * dpr)) { c.width = Math.round(cw * dpr); c.height = Math.round(ch * dpr) }
    const g = c.getContext('2d')!
    g.setTransform(dpr, 0, 0, dpr, 0, 0)
    g.clearRect(0, 0, cw, ch)
    const s = Math.min(cw / v.videoWidth, ch / v.videoHeight)
    const ox = (cw - v.videoWidth * s) / 2, oy = (ch - v.videoHeight * s) / 2
    const k = v.videoWidth / PROC_W
    const map = (p: Pt) => ({ x: ox + p.x * k * s, y: oy + p.y * k * s })
    if (!q) {
      // guide frame while searching
      const w = v.videoWidth * s * 0.72, h = v.videoHeight * s * 0.8
      g.setLineDash([10, 8]); g.lineWidth = 2; g.strokeStyle = 'rgba(255,255,255,0.55)'
      g.beginPath(); g.roundRect(ox + (v.videoWidth * s - w) / 2, oy + (v.videoHeight * s - h) / 2, w, h, 18); g.stroke(); g.setLineDash([])
      return
    }
    const pts = q.map(map)
    const done = Math.min(stable / STABLE_FRAMES, 1)
    // dim everything outside the document
    g.fillStyle = 'rgba(7,11,36,0.45)'
    g.beginPath(); g.rect(0, 0, cw, ch); g.moveTo(pts[0].x, pts[0].y); pts.slice(1).forEach((p) => g.lineTo(p.x, p.y)); g.closePath(); g.fill('evenodd')
    g.fillStyle = `rgba(${done >= 1 ? '23,116,74' : '52,67,181'},0.16)`
    g.beginPath(); g.moveTo(pts[0].x, pts[0].y); pts.slice(1).forEach((p) => g.lineTo(p.x, p.y)); g.closePath(); g.fill()
    g.lineWidth = 3; g.strokeStyle = done >= 1 ? '#3ddc97' : '#9aa6ff'; g.shadowColor = g.strokeStyle; g.shadowBlur = 14
    g.stroke(); g.shadowBlur = 0
    for (const p of pts) {
      g.beginPath(); g.arc(p.x, p.y, 9, 0, Math.PI * 2); g.fillStyle = '#fff'; g.fill()
      g.lineWidth = 3; g.strokeStyle = done >= 1 ? '#17744a' : '#3443b5'; g.stroke()
    }
  }, [])

  const capture = useCallback(() => {
    const v = video.current
    if (!v || !v.videoWidth) return
    stopLoop()
    const c = full.current ?? (full.current = document.createElement('canvas'))
    c.width = v.videoWidth; c.height = v.videoHeight
    c.getContext('2d')!.drawImage(v, 0, 0)
    const k = v.videoWidth / PROC_W
    const q = track.current.quad
    const inset = (x: number, y: number) => ({ x: v.videoWidth * x, y: v.videoHeight * y })
    setCorners(q ? (q.map((p) => ({ x: p.x * k, y: p.y * k })) as Quad) : [inset(0.08, 0.08), inset(0.92, 0.08), inset(0.92, 0.92), inset(0.08, 0.92)])
    setStill({ url: c.toDataURL('image/jpeg', 0.92), w: v.videoWidth, h: v.videoHeight })
    setFlash(true); setTimeout(() => setFlash(false), 260)
    setPhase('adjust')
  }, [])

  const step = useCallback((ts: number) => {
    const v = video.current, lib = cv.current
    const t = track.current
    if (!v || !lib || !v.videoWidth || ts - t.last < 90) return
    t.last = ts
    const ph = Math.round((v.videoHeight * PROC_W) / v.videoWidth)
    const pc = proc.current ?? (proc.current = document.createElement('canvas'))
    if (pc.width !== PROC_W) { pc.width = PROC_W; pc.height = ph }
    pc.getContext('2d', { willReadFrequently: true })!.drawImage(v, 0, 0, PROC_W, ph)
    const src = lib.imread(pc)
    let q: Quad | null = null
    try { q = detectDocument(lib, src) } finally { src.delete() }
    if (q) {
      t.misses = 0
      t.stable = t.quad && quadDrift(q, t.quad, PROC_W) < 0.012 ? t.stable + 1 : 0
      t.quad = q
      t.shown = t.shown ? (t.shown.map((p, i) => ({ x: p.x + (q![i].x - p.x) * 0.55, y: p.y + (q![i].y - p.y) * 0.55 })) as Quad) : q
    } else if (++t.misses > 4) {
      t.quad = t.shown = null
      t.stable = 0
    }
    drawOverlay(t.shown, t.stable)
    setFound(!!t.quad)
    setStability(Math.min(t.stable / STABLE_FRAMES, 1))
    if (autoRef.current && t.quad && t.stable >= STABLE_FRAMES) capture()
  }, [capture, drawOverlay])

  const startLive = useCallback(() => {
    track.current = { quad: null, shown: null, stable: 0, misses: 0, last: 0 }
    setStability(0); setFound(false)
    setPhase('live')
    stopLoop()
    const frame = (ts: number) => { loop.current = requestAnimationFrame(frame); step(ts) }
    loop.current = requestAnimationFrame(frame)
  }, [step])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    ;(async () => {
      try {
        if (!navigator.mediaDevices?.getUserMedia) throw Object.assign(new Error('unsupported'), { name: 'NotFoundError' })
        const [s, lib] = await Promise.all([
          navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } } }),
          loadOpenCV(),
        ])
        if (cancelled) { s.getTracks().forEach((t) => t.stop()); return }
        stream.current = s
        cv.current = lib
        const v = video.current!
        v.srcObject = s
        await v.play()
        if (!cancelled) startLive()
      } catch (e) {
        if (!cancelled) { setError(cameraError(e)); setPhase('error') }
      }
    })()
    return () => {
      cancelled = true; stopCamera(); freeWarp()
      // start fresh next time the scanner opens
      setPhase('starting'); setError(null); setStill(null); setCorners(null); setTurns(0); setFilter('enhanced')
    }
  }, [open, startLive])

  // --- adjust: draggable corners (pointer and keyboard) ---------------------------------
  const dragging = useRef<number | null>(null)
  function toImage(e: PointerEvent): Pt | null {
    const el = svg.current
    const m = el?.getScreenCTM()
    if (!el || !m) return null
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m.inverse())
    return { x: Math.max(0, Math.min(still!.w, p.x)), y: Math.max(0, Math.min(still!.h, p.y)) }
  }
  function onMove(e: PointerEvent) {
    if (dragging.current == null || !corners) return
    const p = toImage(e)
    if (p) setCorners(corners.map((c, i) => (i === dragging.current ? p : c)) as Quad)
  }
  function onKeyCorner(i: number, e: KeyboardEvent) {
    if (!corners || !still) return
    const step = (e.shiftKey ? 0.05 : 0.01) * still.w
    const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key]
    if (!d) return
    e.preventDefault()
    setCorners(corners.map((c, j) => (j === i ? { x: Math.max(0, Math.min(still.w, c.x + d[0])), y: Math.max(0, Math.min(still.h, c.y + d[1])) } : c)) as Quad)
  }

  // --- preview: warp once, then filters/rotation re-render -------------------------------
  const cropAndPreview = () => {
    const lib = cv.current
    if (!lib || !full.current || !corners) return
    setBusy(true)
    requestAnimationFrame(() => {
      freeWarp()
      const src = lib.imread(full.current!)
      try { warped.current = warpDocument(lib, src, corners) } finally { src.delete() }
      setBusy(false)
      setPhase('preview')
    })
  }
  useEffect(() => {
    const lib = cv.current
    if (phase !== 'preview' || !lib || !warped.current || !preview.current) return
    let m = warped.current.clone()
    for (let i = 0; i < turns % 4; i++) { const r = rotate90(lib, m); m.delete(); m = r }
    const out = applyFilter(lib, m, filter)
    lib.imshow(preview.current, out)
    m.delete(); out.delete()
  }, [phase, filter, turns])

  function useScan() {
    const c = preview.current
    if (!c) return
    setBusy(true)
    c.toBlob((b) => {
      setBusy(false)
      if (!b) return
      const stamp = new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-')
      onDone(new File([b], `scan-${stamp}.jpg`, { type: 'image/jpeg' }))
      onOpenChange(false)
    }, 'image/jpeg', 0.92)
  }

  const status = phase === 'starting' ? 'Starting the camera and scanner…'
    : !found ? 'Point the camera at the document — fit all four corners in view'
    : stability >= 1 ? 'Got it — capturing' : auto ? 'Document found — hold steady' : 'Document found — tap the shutter'

  return (
    <D.Root open={open} onOpenChange={(v) => { if (!v) stopCamera(); onOpenChange(v) }}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-[80] bg-[#050818]" />
        <D.Content className="fixed inset-0 z-[80] flex flex-col text-white outline-none" onEscapeKeyDown={() => stopCamera()}>
          <D.Title className="sr-only">{title}</D.Title>
          <D.Description className="sr-only">Live camera with automatic document detection. Frames are processed on this device.</D.Description>
          {/* header */}
          <div className="flex items-center gap-3 px-4 py-3">
            {phase === 'adjust' || phase === 'preview' ? (
              <button type="button" onClick={() => (phase === 'preview' ? setPhase('adjust') : startLive())} aria-label={phase === 'preview' ? 'Back to corners' : 'Retake'}
                className="inline-flex size-11 items-center justify-center rounded-full bg-white/10 hover:bg-white/15"><ArrowLeft className="size-5" aria-hidden /></button>
            ) : <span className="flex size-11 items-center justify-center rounded-full bg-white/10" aria-hidden><ScanLine className="size-5" /></span>}
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold">{title}</p>
              <p className="text-xs text-white/60">{phase === 'adjust' ? 'Drag the corners to the edges of the page' : phase === 'preview' ? 'Choose a look, then use the scan' : 'OpenCV edge detection · processed on this device'}</p>
            </div>
            <D.Close aria-label="Close scanner" className="inline-flex size-11 items-center justify-center rounded-full bg-white/10 hover:bg-white/15"><X className="size-5" aria-hidden /></D.Close>
          </div>

          {/* stage */}
          <div className="relative min-h-0 flex-1 overflow-hidden">
            <video ref={video} playsInline muted autoPlay aria-hidden
              className={clsx('absolute inset-0 size-full object-contain', phase !== 'live' && phase !== 'starting' && 'invisible')} />
            <canvas ref={overlay} aria-hidden className={clsx('pointer-events-none absolute inset-0 size-full', phase !== 'live' && 'invisible')} />
            {flash && <div className="scan-flash pointer-events-none absolute inset-0 bg-white" aria-hidden />}

            {(phase === 'live' || phase === 'starting') && (
              <p aria-live="polite" className={clsx('glass-dark absolute left-1/2 top-4 flex max-w-[90%] -translate-x-1/2 items-center gap-2 rounded-full px-4 py-2 text-sm font-medium')}>
                {phase === 'starting' ? <Loader2 className="size-4 animate-spin" aria-hidden />
                  : <span className={clsx('size-2.5 rounded-full', found ? (stability >= 1 ? 'bg-[#3ddc97]' : 'bg-[#9aa6ff]') : 'bg-marigold')} aria-hidden />}
                {status}
              </p>
            )}

            {phase === 'adjust' && still && corners && (
              <div className="absolute inset-0 flex items-center justify-center p-3">
                <svg ref={svg} viewBox={`0 0 ${still.w} ${still.h}`} preserveAspectRatio="xMidYMid meet" className="size-full touch-none select-none"
                  onPointerMove={onMove} onPointerUp={() => (dragging.current = null)} onPointerLeave={() => (dragging.current = null)}>
                  <image href={still.url} width={still.w} height={still.h} />
                  <path fillRule="evenodd" fill="rgba(5,8,24,0.55)"
                    d={`M0 0H${still.w}V${still.h}H0Z M${corners.map((p) => `${p.x} ${p.y}`).join(' L')} Z`} />
                  <polygon points={corners.map((p) => `${p.x},${p.y}`).join(' ')} fill="rgba(52,67,181,0.14)" stroke="#9aa6ff" strokeWidth={still.w / 320} />
                  {corners.map((p, i) => (
                    <g key={i} tabIndex={0} role="slider" aria-label={`${CORNER_NAMES[i]} corner`} aria-valuetext={`${Math.round((p.x / still.w) * 100)}% across, ${Math.round((p.y / still.h) * 100)}% down`}
                      onKeyDown={(e) => onKeyCorner(i, e)} onPointerDown={(e) => { (e.target as Element).setPointerCapture?.(e.pointerId); dragging.current = i }}
                      className="cursor-grab outline-none focus-visible:[&>circle:last-child]:stroke-marigold">
                      <circle cx={p.x} cy={p.y} r={still.w / 28} fill="transparent" />
                      <circle cx={p.x} cy={p.y} r={still.w / 80} fill="#fff" stroke="#3443b5" strokeWidth={still.w / 300} />
                    </g>
                  ))}
                </svg>
              </div>
            )}

            {phase === 'preview' && (
              <div className="absolute inset-0 flex items-center justify-center p-4">
                <canvas ref={preview} role="img" aria-label="Scanned document preview" className="max-h-full max-w-full rounded-[10px] bg-white shadow-[0_20px_60px_rgb(0_0_0/0.5)]" />
              </div>
            )}

            {phase === 'error' && (
              <div className="absolute inset-0 flex items-center justify-center p-6">
                <div className="glass-dark max-w-md rounded-[var(--radius-panel)] p-6 text-center">
                  <CircleAlert className="mx-auto size-10 text-marigold" aria-hidden />
                  <p role="alert" className="mt-3 text-[0.95rem]">{error}</p>
                  {onUploadInstead && <button type="button" onClick={() => { onOpenChange(false); onUploadInstead() }}
                    className="mt-5 inline-flex min-h-11 items-center gap-2 rounded-full bg-white px-5 font-semibold text-ink"><Upload className="size-4" aria-hidden />Upload a photo instead</button>}
                </div>
              </div>
            )}
          </div>

          {/* controls */}
          <div className="flex min-h-28 items-center justify-center gap-6 px-4 pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-4">
            {(phase === 'live' || phase === 'starting') && (<>
              <label className="flex w-28 cursor-pointer items-center justify-end gap-2 text-sm text-white/80">
                <input type="checkbox" role="switch" checked={auto} onChange={(e) => { autoRef.current = e.target.checked; setAuto(e.target.checked) }} className="size-4 accent-[#9aa6ff]" />Auto
              </label>
              <button type="button" onClick={capture} disabled={phase !== 'live'} aria-label="Capture"
                className="relative inline-flex size-[4.75rem] items-center justify-center rounded-full disabled:opacity-40" autoFocus>
                <svg viewBox="0 0 80 80" className="absolute inset-0 size-full -rotate-90" aria-hidden>
                  <circle cx="40" cy="40" r="36" fill="none" stroke="rgba(255,255,255,0.35)" strokeWidth="5" />
                  <circle cx="40" cy="40" r="36" fill="none" stroke="#3ddc97" strokeWidth="5" strokeLinecap="round" strokeDasharray={`${226 * stability} 226`} />
                </svg>
                <span className="size-[3.6rem] rounded-full bg-white shadow-[0_4px_16px_rgb(0_0_0/0.4)] transition-transform active:scale-90" />
              </button>
              <span className="w-28">
                {onUploadInstead && <button type="button" onClick={() => { onOpenChange(false); onUploadInstead() }} className="inline-flex min-h-11 items-center gap-1.5 rounded-full px-3 text-sm text-white/80 hover:bg-white/10"><Upload className="size-4" aria-hidden />Upload</button>}
              </span>
            </>)}
            {phase === 'adjust' && (<>
              <button type="button" onClick={startLive} className="inline-flex min-h-12 items-center gap-2 rounded-full bg-white/10 px-5 font-medium hover:bg-white/15"><Camera className="size-4" aria-hidden />Retake</button>
              <button type="button" onClick={cropAndPreview} disabled={busy} className="inline-flex min-h-12 items-center gap-2 rounded-full bg-[image:var(--grad-indigo)] px-6 font-semibold shadow-[0_8px_24px_rgb(52_67_181/0.45)]">
                {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Check className="size-4" aria-hidden />}Crop & continue
              </button>
            </>)}
            {phase === 'preview' && (
              <div className="flex w-full max-w-xl flex-wrap items-center justify-center gap-3">
                <div role="radiogroup" aria-label="Scan look" className="flex rounded-full bg-white/10 p-1">
                  {([['enhanced', 'Enhanced'], ['colour', 'Colour'], ['bw', 'Black & white']] as const).map(([k, l]) => (
                    <button key={k} type="button" role="radio" aria-checked={filter === k} onClick={() => setFilter(k)}
                      className={clsx('min-h-10 rounded-full px-4 text-sm font-medium transition-colors', filter === k ? 'bg-white text-ink' : 'text-white/80 hover:text-white')}>{l}</button>
                  ))}
                </div>
                <button type="button" onClick={() => setTurns((t) => t + 1)} aria-label="Rotate 90 degrees" className="inline-flex size-11 items-center justify-center rounded-full bg-white/10 hover:bg-white/15"><RotateCw className="size-5" aria-hidden /></button>
                <button type="button" onClick={useScan} disabled={busy} className="inline-flex min-h-12 items-center gap-2 rounded-full bg-[image:var(--grad-saathi)] px-6 font-semibold text-ink shadow-[var(--glow-saathi)]">
                  {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Check className="size-4" aria-hidden />}Use this scan
                </button>
              </div>
            )}
          </div>
        </D.Content>
      </D.Portal>
    </D.Root>
  )
}
