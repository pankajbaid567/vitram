// VITTRM on-device OCR helper (macOS only).
// Uses Apple's Vision framework, so document images never leave this machine.
//
//   vitram-ocr <file> [max_pages]
//
// Reads a JPEG/PNG/WebP/HEIC image or a PDF (each page is rendered at 2x and read separately)
// and prints JSON: {"pages":[{"page":1,"width":W,"height":H,"lines":[{"text":..,"confidence":..,"box":[x,y,w,h]}]}]}
// Boxes are normalised to 0..1 with the origin at the top-left. Nothing is written to disk or logged.
import AppKit
import Foundation
import PDFKit
import Vision

struct Line: Encodable { let text: String; let confidence: Float; let box: [Double] }
struct Page: Encodable { let page: Int; let width: Int; let height: Int; let lines: [Line] }
struct Output: Encodable { let pages: [Page]; let engine: String }

func fail(_ code: String, _ message: String) -> Never {
    FileHandle.standardError.write("\(code): \(message)\n".data(using: .utf8)!)
    exit(code == "USAGE" ? 64 : 65)
}

func recognise(_ image: CGImage) -> [Line] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    let wanted = ["en-US", "en-GB", "hi-IN"]
    if let supported = try? request.supportedRecognitionLanguages() {
        request.recognitionLanguages = wanted.filter { supported.contains($0) }
    }
    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    do { try handler.perform([request]) } catch { return [] }
    return (request.results ?? []).compactMap { obs in
        guard let best = obs.topCandidates(1).first else { return nil }
        let b = obs.boundingBox  // normalised, origin bottom-left
        return Line(text: best.string, confidence: best.confidence,
                    box: [Double(b.minX), Double(1 - b.maxY), Double(b.width), Double(b.height)])
    }
}

func render(_ page: PDFPage) -> CGImage? {
    let bounds = page.bounds(for: .mediaBox)
    let scale: CGFloat = 2
    let w = Int(bounds.width * scale), h = Int(bounds.height * scale)
    guard w > 0, h > 0, w * h < 60_000_000,
          let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                              space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)
    else { return nil }
    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.scaleBy(x: scale, y: scale)
    page.draw(with: .mediaBox, to: ctx)
    return ctx.makeImage()
}

let args = CommandLine.arguments
guard args.count >= 2 else { fail("USAGE", "vitram-ocr <file> [max_pages]") }
let url = URL(fileURLWithPath: args[1])
let maxPages = args.count >= 3 ? max(1, Int(args[2]) ?? 50) : 50
guard let data = try? Data(contentsOf: url) else { fail("UNREADABLE", "The file couldn't be opened.") }

var pages: [Page] = []
if data.starts(with: [0x25, 0x50, 0x44, 0x46]) {  // %PDF
    guard let doc = PDFDocument(data: data) else { fail("UNREADABLE_PDF", "The PDF couldn't be opened.") }
    if doc.isLocked { fail("PASSWORD_PROTECTED", "The PDF is password-protected.") }
    for i in 0..<min(doc.pageCount, maxPages) {
        guard let p = doc.page(at: i), let img = render(p) else { continue }
        pages.append(Page(page: i + 1, width: img.width, height: img.height, lines: recognise(img)))
    }
} else {
    guard let src = CGImageSourceCreateWithData(data as CFData, nil),
          let img = CGImageSourceCreateImageAtIndex(src, 0, [kCGImageSourceShouldCacheImmediately: true] as CFDictionary)
    else { fail("UNSUPPORTED_IMAGE", "The image format isn't supported.") }
    pages.append(Page(page: 1, width: img.width, height: img.height, lines: recognise(img)))
}

let encoder = JSONEncoder()
FileHandle.standardOutput.write(try! encoder.encode(Output(pages: pages, engine: "apple-vision")))
