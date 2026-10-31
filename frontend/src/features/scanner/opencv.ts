/* eslint-disable @typescript-eslint/no-explicit-any */
// OpenCV.js (Apache-2.0, @techstark/opencv-js 4.12) is ~10 MB, so it is served as a separate static asset and
// loaded only when the camera scanner opens. Everything runs in the browser: no frame leaves the device.
import cvUrl from '@techstark/opencv-js/dist/opencv.js?url'

export type CV = any

let loading: Promise<CV> | null = null

export function loadOpenCV(): Promise<CV> {
  if (loading) return loading
  loading = new Promise<CV>((resolve, reject) => {
    const w = window as any
    // The Emscripten module is a "thenable" whose then() returns itself: resolving a Promise with it would make
    // the Promise adopt it forever (an endless microtask loop that freezes the page). Wait on its own then(), and
    // drop that method before handing the module out.
    const hand = (mod: any) => { if (typeof mod.then === 'function') delete mod.then; resolve(mod) }
    const ready = (mod: any) => {
      if (!mod) reject(new Error('OpenCV did not load'))
      else if (mod.Mat) hand(mod)
      else if (typeof mod.then === 'function') mod.then(() => hand(mod))
      else mod.onRuntimeInitialized = () => hand(mod)
    }
    if (w.cv) return ready(w.cv)
    const s = document.createElement('script')
    s.src = cvUrl
    s.async = true
    s.onload = () => ready(w.cv)
    s.onerror = () => { loading = null; reject(new Error('OpenCV could not be downloaded')) }
    document.head.appendChild(s)
  })
  return loading
}
