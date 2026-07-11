import { PaddleOcrService } from 'ppu-paddle-ocr/web'
import {
  parseReceipt,
  reconcileReceipt,
  type ParseResult,
  type Reconciliation,
} from '@splitleh/core'
import { preprocessReceiptImageGrayscale, preprocessRawGrayscale } from './receiptImage'

export type { ParseResult, Reconciliation }

export interface OcrResult {
  rawText: string
  parseResult: ParseResult
  reconciliation: Reconciliation
  processedImageUrl: string
}

let _service: PaddleOcrService | null = null

async function getService(
  onUpdate: (status: string, pct: number) => void,
): Promise<PaddleOcrService> {
  if (_service) return _service

  onUpdate('Downloading OCR model…', 5)
  const svc = new PaddleOcrService({
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
      const ctx = canvas.getContext('2d')
      if (!ctx) { reject(new Error('Canvas 2D context unavailable - device may be low on memory.')); return }
      ctx.drawImage(img, 0, 0)
      resolve(canvas)
    }
    img.onerror = reject
    img.src = dataUrl
  })
}

export async function runReceiptOcr(
  dataUrl: string,
  onUpdate: (status: string, progress: number) => void,
  alreadyProcessed?: string,
): Promise<OcrResult> {
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
  const rawText = result.text.trim()

  const parseResult = parseReceipt(rawText)
  const reconciliation = reconcileReceipt(parseResult)
  return { rawText, parseResult, reconciliation, processedImageUrl }
}
