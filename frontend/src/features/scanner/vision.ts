/* eslint-disable @typescript-eslint/no-explicit-any */
/** Document detection, perspective correction and scan enhancement with OpenCV.js.
 * Classic pipeline: grey → blur → Canny edges → close gaps → contours → largest convex quadrilateral. */
import type { CV } from './opencv'

export type Pt = { x: number; y: number }
export type Quad = [Pt, Pt, Pt, Pt] // top-left, top-right, bottom-right, bottom-left

/** Order 4 points TL, TR, BR, BL (sum / difference of coordinates). */
export function orderQuad(pts: Pt[]): Quad {
  const bySum = [...pts].sort((a, b) => a.x + a.y - (b.x + b.y))
  const byDiff = [...pts].sort((a, b) => a.y - a.x - (b.y - b.x))
  return [bySum[0], byDiff[0], bySum[3], byDiff[3]]
}

export function quadArea(q: Quad): number {
  let a = 0
  for (let i = 0; i < 4; i++) { const p = q[i], n = q[(i + 1) % 4]; a += p.x * n.y - n.x * p.y }
  return Math.abs(a) / 2
}

/** Average corner movement between two quads, as a fraction of `scale` (frame width). */
export function quadDrift(a: Quad, b: Quad, scale: number): number {
  return a.reduce((s, p, i) => s + Math.hypot(p.x - b[i].x, p.y - b[i].y), 0) / 4 / scale
}

/** Find the document in an RGBA Mat. Returns the quad in the Mat's pixel coordinates, or null. */
export function detectDocument(cv: CV, src: any, minAreaFraction = 0.18): Quad | null {
  const gray = new cv.Mat(), blur = new cv.Mat(), edges = new cv.Mat(), closed = new cv.Mat()
  const contours = new cv.MatVector(), hierarchy = new cv.Mat()
  const kernel = cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(5, 5))
  let best: Quad | null = null
  try {
    cv.cvtColor(src, gray, cv.COLOR_RGBA2GRAY)
    cv.GaussianBlur(gray, blur, new cv.Size(5, 5), 0)
    // thresholds from the median brightness keep edges stable in dim and bright light
    const mean = cv.mean(blur)[0]
    cv.Canny(blur, edges, Math.max(10, 0.67 * mean), Math.min(255, 1.33 * mean))
    cv.morphologyEx(edges, closed, cv.MORPH_CLOSE, kernel)
    cv.findContours(closed, contours, hierarchy, cv.RETR_LIST, cv.CHAIN_APPROX_SIMPLE)
    const frameArea = src.cols * src.rows
    let bestArea = minAreaFraction * frameArea
    for (let i = 0; i < contours.size(); i++) {
      const c = contours.get(i)
      const area = cv.contourArea(c)
      if (area > bestArea) {
        const approx = new cv.Mat()
        cv.approxPolyDP(c, approx, 0.02 * cv.arcLength(c, true), true)
        if (approx.rows === 4 && cv.isContourConvex(approx)) {
          const pts: Pt[] = []
          for (let k = 0; k < 4; k++) pts.push({ x: approx.data32S[k * 2], y: approx.data32S[k * 2 + 1] })
          best = orderQuad(pts)
          bestArea = area
        }
        approx.delete()
      }
      c.delete()
    }
  } finally {
    gray.delete(); blur.delete(); edges.delete(); closed.delete(); contours.delete(); hierarchy.delete(); kernel.delete()
  }
  return best
}

/** Flatten the quad to a straight-on rectangle (perspective transform). Returns a new RGBA Mat. */
export function warpDocument(cv: CV, src: any, q: Quad): any {
  const d = (a: Pt, b: Pt) => Math.hypot(a.x - b.x, a.y - b.y)
  const w = Math.round(Math.max(d(q[0], q[1]), d(q[3], q[2])))
  const h = Math.round(Math.max(d(q[0], q[3]), d(q[1], q[2])))
  const from = cv.matFromArray(4, 1, cv.CV_32FC2, q.flatMap((p) => [p.x, p.y]))
  const to = cv.matFromArray(4, 1, cv.CV_32FC2, [0, 0, w, 0, w, h, 0, h])
  const M = cv.getPerspectiveTransform(from, to)
  const out = new cv.Mat()
  cv.warpPerspective(src, out, M, new cv.Size(w, h), cv.INTER_CUBIC, cv.BORDER_REPLICATE)
  from.delete(); to.delete(); M.delete()
  // trim a hair off each edge so a sliver of the desk behind the page doesn't show as a dark border
  const m = Math.max(2, Math.round(Math.min(w, h) * 0.012))
  if (w <= 4 * m || h <= 4 * m) return out
  const roi = out.roi(new cv.Rect(m, m, w - 2 * m, h - 2 * m))
  const trimmed = roi.clone()
  roi.delete(); out.delete()
  return trimmed
}

export type ScanFilter = 'enhanced' | 'colour' | 'bw'

/** Scan look. `enhanced` divides out uneven lighting (shadow removal) and boosts contrast; `bw` adds adaptive
 * thresholding for crisp text; `colour` keeps the photo as is. Returns a new RGBA Mat. */
export function applyFilter(cv: CV, src: any, filter: ScanFilter): any {
  const out = new cv.Mat()
  if (filter === 'colour') { src.copyTo(out); return out }
  const gray = new cv.Mat(), bg = new cv.Mat(), flat = new cv.Mat()
  const k = Math.max(15, Math.round(Math.min(src.cols, src.rows) / 25) | 1)
  const kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE, new cv.Size(k, k))
  cv.cvtColor(src, gray, cv.COLOR_RGBA2GRAY)
  cv.morphologyEx(gray, bg, cv.MORPH_CLOSE, kernel) // estimate the paper background (text removed)
  cv.GaussianBlur(bg, bg, new cv.Size(0, 0), k / 3)
  cv.divide(gray, bg, flat, 255) // background → white, shadows gone
  cv.normalize(flat, flat, 0, 255, cv.NORM_MINMAX)
  if (filter === 'bw') {
    cv.adaptiveThreshold(flat, flat, 255, cv.ADAPTIVE_THRESH_GAUSSIAN_C, cv.THRESH_BINARY, 25, 12)
  } else {
    flat.convertTo(flat, -1, 1.25, -30) // a little extra contrast for print
  }
  cv.cvtColor(flat, out, cv.COLOR_GRAY2RGBA)
  gray.delete(); bg.delete(); flat.delete(); kernel.delete()
  return out
}

export function rotate90(cv: CV, src: any): any {
  const out = new cv.Mat()
  cv.rotate(src, out, cv.ROTATE_90_CLOCKWISE)
  return out
}
