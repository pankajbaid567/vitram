import clsx from 'clsx'
import { Camera, FileUp, FileText, ScanLine, X } from 'lucide-react'
import { lazy, Suspense, useEffect, useId, useMemo, useRef, useState, type DragEvent } from 'react'

// The live scanner (and OpenCV.js) only load when someone opens it.
const DocumentScanner = lazy(() => import('../../features/scanner/DocumentScanner'))

const MAX_MB = 15

/** Drop zone + file picker. `camera` adds a "Take a photo" button (rear camera on phones) when images are accepted.
 * `progress` (0–100) shows the upload percentage once the file is being sent. */
export function FileDrop({ accept, file, onFile, hint, error, camera, progress, scanNote }: {
  accept: string; file: File | null; onFile: (f: File | null) => void; hint?: string; error?: string | null; camera?: boolean; progress?: number | null
  /** Shown as a visible label when photos and scans can be read (e.g. "Photos and scans are read on this device"). */
  scanNote?: string
}) {
  const id = useId()
  const camId = useId()
  const input = useRef<HTMLInputElement>(null)
  const preview = useMemo(() => (file && file.type.startsWith('image/') ? URL.createObjectURL(file) : null), [file])
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])
  const imagesOk = /\.(jpe?g|png|webp)/.test(accept)
  const [scanning, setScanning] = useState(false)
  const liveCamera = typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia
  const [over, setOver] = useState(false)
  const [localErr, setLocalErr] = useState<string | null>(null)

  function take(f: File | undefined | null) {
    if (!f) return
    if (f.size > MAX_MB * 1024 * 1024) {
      setLocalErr(`This file is ${(f.size / 1024 / 1024).toFixed(1)} MB. Files can be up to ${MAX_MB} MB.`)
      return
    }
    const okExt = accept.split(',').some((a) => f.name.toLowerCase().endsWith(a.trim().replace('*', '')))
      || (imagesOk && /^image\/(jpeg|png|webp)$/.test(f.type))
    if (!okExt) {
      setLocalErr(`Choose a ${accept.replaceAll(',', ' or ')} file.`)
      return
    }
    setLocalErr(null)
    onFile(f)
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setOver(false)
    take(e.dataTransfer.files?.[0])
  }

  const err = localErr ?? error
  if (file) {
    return (
      <div className="surface-card flex flex-col gap-3 rounded-[var(--radius-card)] p-3 pl-4">
        <div className="flex items-center gap-3">
          {preview ? <img src={preview} alt="" className="size-14 shrink-0 rounded-[12px] object-cover shadow-[var(--elev-1)]" />
            : <span className="flex size-11 shrink-0 items-center justify-center rounded-[14px] bg-indigo-soft text-indigo" aria-hidden><FileText className="size-5" /></span>}
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{file.name}</p>
            <p className="text-sm text-muted">{(file.size / 1024).toFixed(0)} KB{preview ? ' · photo' : ''}</p>
          </div>
          {progress == null && (
            <button type="button" onClick={() => onFile(null)} className="inline-flex size-11 items-center justify-center rounded-[var(--radius-control)] text-muted hover:bg-ink/5 hover:text-ink" aria-label="Remove file">
              <X className="size-5" />
            </button>
          )}
        </div>
        {err && progress == null && <p className="text-sm text-critical" role="alert">{err}</p>}
        {progress != null && (
          <div role="progressbar" aria-label="Uploading" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress} className="flex items-center gap-3">
            <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink/[0.08]"><span className="block h-full rounded-full bg-[image:var(--grad-indigo)] transition-[width] duration-200" style={{ width: `${progress}%` }} /></span>
            <span className="num w-10 text-right text-xs text-muted">{progress}%</span>
          </div>
        )}
      </div>
    )
  }
  return (
    <div className="[&:has(input:focus-visible)_label]:border-indigo [&:has(input:focus-visible)_label]:shadow-[var(--ring)]">
      <label htmlFor={id}
        onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)} onDrop={onDrop}
        className={clsx('flex cursor-pointer flex-col items-center justify-center gap-2.5 rounded-[var(--radius-panel)] border-2 border-dashed px-6 py-10 text-center transition-[border-color,background-color,box-shadow] duration-[var(--dur)]',
          over ? 'border-indigo bg-indigo-soft' : err ? 'border-critical/50 bg-critical-soft/40' : 'border-indigo/25 bg-white/75 hover:border-indigo/60 hover:bg-white')}>
        <span className="flex size-14 items-center justify-center rounded-[18px] bg-[image:var(--grad-indigo)] text-white shadow-[0_8px_20px_rgb(52_67_181/0.28)]" aria-hidden><FileUp className="size-6" /></span>
        <span className="font-medium">Drop the file here or <span className="text-indigo underline underline-offset-2">choose a file</span></span>
        <span className="text-sm text-muted">{hint ?? `${accept.toUpperCase().replaceAll('.', '')} up to ${MAX_MB} MB`}</span>
        {scanNote && imagesOk && (
          <span className="mt-1 inline-flex items-center gap-1.5 rounded-full bg-positive-soft px-3 py-1 text-xs font-medium text-positive">
            <ScanLine className="size-3.5" aria-hidden />{scanNote}
          </span>
        )}
      </label>
      <input ref={input} id={id} type="file" accept={accept} className="sr-only" onChange={(e) => take(e.target.files?.[0])} />
      {camera && imagesOk && (
        <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
          {liveCamera && (
            <button type="button" onClick={() => setScanning(true)}
              className="inline-flex min-h-11 items-center gap-2 rounded-full bg-[image:var(--grad-indigo)] px-5 text-sm font-semibold text-white shadow-[0_6px_16px_rgb(52_67_181/0.3)] transition-[filter] hover:brightness-110">
              <ScanLine className="size-4" aria-hidden />Scan with camera
            </button>
          )}
          <label htmlFor={camId} className={liveCamera
            ? 'inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-full px-3 text-sm font-medium text-indigo hover:bg-indigo-soft [&:has(+input:focus-visible)]:shadow-[var(--ring)]'
            : 'inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-full bg-[image:var(--grad-indigo)] px-5 text-sm font-semibold text-white shadow-[0_6px_16px_rgb(52_67_181/0.3)] hover:brightness-110 [&:has(+input:focus-visible)]:shadow-[var(--ring)]'}>
            <Camera className="size-4" aria-hidden />{liveCamera ? 'Use camera app' : 'Take a photo'}
          </label>
          <input id={camId} type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => take(e.target.files?.[0])} />
        </div>
      )}
      {scanning && (
        <Suspense fallback={null}>
          <DocumentScanner open={scanning} onOpenChange={setScanning} onDone={(f) => take(f)} onUploadInstead={() => input.current?.click()} />
        </Suspense>
      )}
      {err && <p className="mt-2 text-sm text-critical" role="alert">{err}</p>}
    </div>
  )
}
