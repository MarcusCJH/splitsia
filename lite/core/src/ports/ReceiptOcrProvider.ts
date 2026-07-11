import type { ParseResult } from '../parseReceipt'
import type { Reconciliation } from '../receiptReconcile'

export interface OcrScanResult {
  rawText: string
  parseResult: ParseResult
  reconciliation: Reconciliation
  processedImageUrl: string
}

export interface ReceiptOcrProvider {
  scan(
    image: Blob | string,
    onProgress?: (status: string, pct: number) => void,
    signal?: AbortSignal,
  ): Promise<OcrScanResult>
}
