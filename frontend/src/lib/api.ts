/** Thin fetch wrapper for the VITRAM API. Session is an HttpOnly cookie; no tokens in JS. */

export class ApiError extends Error {
  code: string
  field?: string
  status: number
  /** Non-sensitive context from the server, e.g. which existing document a duplicate upload matches. */
  details?: Record<string, any>
  constructor(status: number, code: string, message: string, field?: string, details?: Record<string, any>) {
    super(message)
    this.status = status
    this.code = code
    this.field = field
    this.details = details
  }
}

let onUnauthenticated: (() => void) | null = null
export function setUnauthenticatedHandler(fn: () => void) {
  onUnauthenticated = fn
}

async function parse(res: Response) {
  const text = await res.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = null
  }
  if (!res.ok) {
    const b = body as { error?: { code: string; message: string; field?: string; details?: Record<string, any> }; detail?: unknown } | null
    if (b?.error) throw new ApiError(res.status, b.error.code, b.error.message, b.error.field, b.error.details)
    if (res.status === 422 && Array.isArray(b?.detail)) {
      const first = b.detail[0] as { loc?: string[]; msg?: string }
      const field = first?.loc?.[first.loc.length - 1]
      const msg = (first?.msg ?? 'Check the highlighted field.').replace(/^Value error, /, '')
      throw new ApiError(422, 'VALIDATION', msg, typeof field === 'string' ? field : undefined)
    }
    throw new ApiError(res.status, 'HTTP_' + res.status, 'Something went wrong. Try again.')
  }
  return body
}

export async function api<T = any>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init
  let res: Response
  try {
    res = await fetch('/api' + path, {
      credentials: 'same-origin',
      ...rest,
      headers: {
        ...(json !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...headers,
      },
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    })
  } catch {
    throw new ApiError(0, 'NETWORK', "VITRAM can't reach the server. Check your connection and try again.")
  }
  if (res.status === 401 && onUnauthenticated && !path.startsWith('/auth/')) onUnauthenticated()
  return (await parse(res)) as T
}

export const get = <T = any>(p: string) => api<T>(p)
export const post = <T = any>(p: string, json?: unknown) => api<T>(p, { method: 'POST', json: json ?? {} })
export const patch = <T = any>(p: string, json: unknown) => api<T>(p, { method: 'PATCH', json })
export const put = <T = any>(p: string, json: unknown) => api<T>(p, { method: 'PUT', json })
export const del = <T = any>(p: string) => api<T>(p, { method: 'DELETE' })

/** Multipart upload. With `onProgress`, uses XHR so the UI can show a real upload percentage. */
export function upload<T = any>(path: string, form: FormData, onProgress?: (pct: number) => void): Promise<T> {
  if (!onProgress) return api<T>(path, { method: 'POST', body: form })
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api' + path)
    xhr.withCredentials = true
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100)) }
    xhr.onerror = () => reject(new ApiError(0, 'NETWORK', "VITRAM can't reach the server. Check your connection and try again."))
    xhr.onload = () => {
      if (xhr.status === 401 && onUnauthenticated) onUnauthenticated()
      parse(new Response(xhr.responseText, { status: xhr.status })).then((b) => resolve(b as T), reject)
    }
    xhr.send(form)
  })
}
