import type { ReceiptOcrProvider, OcrScanResult } from '@splitleh/core'
import { runReceiptOcr } from '../utils/receiptOcr'

export async function scanReceipt(
  dataUrl: string,
  onProgress: (status: string, pct: number) => void,
  alreadyProcessed?: string,
): Promise<OcrScanResult> {
  return runReceiptOcr(dataUrl, onProgress, alreadyProcessed)
}

export const browserPaddleOcrProvider: ReceiptOcrProvider = {
  scan: (image, onProgress) => {
    if (typeof image !== 'string') {
      return Promise.reject(new Error('Lite OCR requires a data URL'))
    }
    return runReceiptOcr(image, onProgress ?? (() => {}))
  },
}
