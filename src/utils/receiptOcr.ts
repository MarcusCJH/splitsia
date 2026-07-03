import { PaddleOcrService } from 'ppu-paddle-ocr/web'
import { parseReceipt } from './parseReceipt'
import type { ParseResult } from './parseReceipt'
import { reconcileReceipt } from './receiptReconcile'
import type { Reconciliation } from './receiptReconcile'
import { preprocessReceiptImageGrayscale, preprocessRawGrayscale } from './receiptImage'

// Singleton — reused across scans within the same session.
let _service: PaddleOcrService | null = null

async function getService(
  onUpdate: (status: string, pct: number) => void,
): Promise<PaddleOcrService> {
  if (_service) return _service

  onUpdate('Downloading OCR model…', 5)
  const svc = new PaddleOcrService({
    // Force WASM so it works on iOS Safari (no WebGPU there yet).
    session: { executionProviders: ['wasm'] },
  })
  await svc.initialize()
  onUpdate('OCR model ready', 42)
  _service = svc
  return svc
}

function dataUrlToCanvas(dataUrl: string): Promise<HTMLCanvasElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = img.naturalWidth
      canvas.height = img.naturalHeight
      canvas.getContext('2d')!.drawImage(img, 0, 0)
      resolve(canvas)
    }
    img.onerror = reject
    img.src = dataUrl
  })
}

export interface OcrResult {
  rawText: string
  parseResult: ParseResult
  reconciliation: Reconciliation
  processedImageUrl: string
}

// Kept for the benchmark test which scores parse quality.
export function scoreParseResult(result: ParseResult): number {
  const { items, charges, warnings } = result
  let score = 0
  for (const item of items) {
    const alpha = (item.name.match(/[a-zA-Z]/g) ?? []).length
    const ratio = item.name.length > 0 ? alpha / item.name.length : 0
    if (ratio < 0.4 || item.name.length > 55) { score -= 12; continue }
    if (item.totalPrice > 500) { score -= 8; continue }
    score += 10
    if (item.confidence === 'high') score += 4
    if (item.quantity > 1) score += 2
  }
  score += charges.filter((c) => c.type === 'subtotal').length * 25
  score += charges.filter((c) => c.type === 'total').length * 25
  score += charges.filter((c) => ['gst', 'service_charge', 'discount'].includes(c.type)).length * 10
  score -= warnings.length * 8
  return score
}

export function scoreParsedReceipt(text: string): number {
  return scoreParseResult(parseReceipt(text))
}

export async function runReceiptOcr(
  dataUrl: string,
  onUpdate: (status: string, progress: number) => void,
  alreadyProcessed?: string,
): Promise<OcrResult> {
  // Prepare the display image (CLAHE-enhanced) and the OCR input (raw gray, cropped).
  let processedImageUrl: string
  let ocrImageUrl: string
  if (alreadyProcessed) {
    processedImageUrl = alreadyProcessed
    ocrImageUrl = await preprocessRawGrayscale(dataUrl)
  } else {
    onUpdate('Preparing image…', 2)
    ;[processedImageUrl, ocrImageUrl] = await Promise.all([
      preprocessReceiptImageGrayscale(dataUrl),
      preprocessRawGrayscale(dataUrl),
    ])
  }

  const service = await getService(onUpdate)

  onUpdate('Reading receipt…', 45)
  const ocrCanvas = await dataUrlToCanvas(ocrImageUrl)
  const result = await service.recognize(ocrCanvas)

  onUpdate('Checking receipt math…', 95)
  // PaddleOcrResult.text already contains all lines joined with newlines.
  const rawText = result.text.trim()

  const parseResult = parseReceipt(rawText)
  const reconciliation = reconcileReceipt(parseResult)
  return { rawText, parseResult, reconciliation, processedImageUrl }
}
