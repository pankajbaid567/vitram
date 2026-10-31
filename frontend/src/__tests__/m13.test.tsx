import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { FileDrop } from '../components/ui/filedrop'
import { acceptFor, IMAGE_EXT } from '../lib/vision'

afterEach(cleanup)

const on = { provider: 'macos' as const, configured: true, on_device: true, note: '' }
const off = { provider: 'none' as const, configured: false, on_device: false, note: '' }

describe('What each upload accepts', () => {
  it('offers photos only when this server can read them', () => {
    expect(acceptFor('receipt', on)).toBe(`.pdf,${IMAGE_EXT}`)
    expect(acceptFor('receipt', off)).toBe('.pdf')
    expect(acceptFor('bank_statement', on)).toBe(`.pdf,.csv,${IMAGE_EXT}`)
    expect(acceptFor('bank_statement', undefined)).toBe('.pdf,.csv')
  })
})

describe('FileDrop', () => {
  it('offers the camera only when images are accepted', () => {
    const { rerender } = render(<FileDrop accept=".pdf" file={null} onFile={() => {}} camera />)
    expect(screen.queryByText('Take a photo')).toBeNull()
    expect(screen.queryByText('Scan with camera')).toBeNull()
    rerender(<FileDrop accept={`.pdf,${IMAGE_EXT}`} file={null} onFile={() => {}} camera />)
    expect(screen.getByText('Take a photo')).toBeTruthy()  // jsdom has no live camera → native camera fallback
  })
  it('accepts a camera photo by MIME type even without an extension, and rejects others', () => {
    const onFile = vi.fn()
    const { container } = render(<FileDrop accept={`.pdf,${IMAGE_EXT}`} file={null} onFile={onFile} camera />)
    const inputs = container.querySelectorAll('input[type=file]')
    fireEvent.change(inputs[1], { target: { files: [new File(['x'], 'image', { type: 'image/jpeg' })] } })
    expect(onFile).toHaveBeenCalledTimes(1)
    fireEvent.change(inputs[0], { target: { files: [new File(['x'], 'notes.docx', { type: 'application/msword' })] } })
    expect(onFile).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('alert').textContent).toMatch(/Choose a/)
  })
  it('shows upload progress and hides "remove" while uploading', () => {
    render(<FileDrop accept=".pdf" file={new File(['x'], 'kfs.pdf', { type: 'application/pdf' })} onFile={() => {}} progress={42} />)
    expect(screen.getByRole('progressbar', { name: 'Uploading' })).toHaveAttribute('aria-valuenow', '42')
    expect(screen.queryByRole('button', { name: 'Remove file' })).toBeNull()
  })
})

describe('Scanner geometry', () => {
  it('orders any four corners as top-left, top-right, bottom-right, bottom-left', async () => {
    const { orderQuad, quadArea, quadDrift } = await import('../features/scanner/vision')
    const q = orderQuad([{ x: 90, y: 110 }, { x: 10, y: 5 }, { x: 5, y: 100 }, { x: 95, y: 8 }])
    expect(q).toEqual([{ x: 10, y: 5 }, { x: 95, y: 8 }, { x: 90, y: 110 }, { x: 5, y: 100 }])
    expect(quadArea([{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 5 }, { x: 0, y: 5 }])).toBe(50)
    expect(quadDrift(q, q, 100)).toBe(0)
  })
})

describe('OpenCV loader', () => {
  it('resolves with the Emscripten module even though its then() returns itself', async () => {
    // Promise-resolving such a thenable directly would adopt it forever and freeze the page
    const mod: any = { then(f: (m: unknown) => void) { setTimeout(() => { mod.Mat = class {}; f(mod) }); return mod } }
    ;(window as any).cv = mod
    const { loadOpenCV } = await import('../features/scanner/opencv')
    const cv = await loadOpenCV()
    expect(cv.Mat).toBeTruthy()
    expect('then' in cv).toBe(false)
    delete (window as any).cv
  })
})
