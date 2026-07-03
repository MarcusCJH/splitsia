/**
 * Benchmark parse quality on pre-OCR'd text files (optional local files).
 * Drop .txt files (one per receipt, raw OCR text) into samples/ to run.
 * Run: npx vitest run src/utils/__tests__/benchmarkSamples.test.ts
 */
import { describe, it } from 'vitest'
import { existsSync, readFileSync } from 'fs'
import { parseReceipt } from '../parseReceipt'
import { scoreParsedReceipt } from '../receiptOcr'
import { reconcileReceipt } from '../receiptReconcile'

const SAMPLES = ['sample.txt', 'sample2.txt', 'sample3.txt', 'sample4.txt']

describe('benchmark samples', () => {
  for (const file of SAMPLES) {
    it(`parses ${file}`, () => {
      const path = `samples/${file}`
      if (!existsSync(path)) return

      const text = readFileSync(path, 'utf8')
      const score = scoreParsedReceipt(text)
      const result = parseReceipt(text)
      const recon = reconcileReceipt(result)

      console.log(`\n${'='.repeat(60)}\n${file} (score ${score})\n${'='.repeat(60)}`)
      console.log('\n--- ITEMS ---')
      for (const it of result.items) {
        console.log(
          `  qty=${it.quantity} unit=$${it.unitPrice.toFixed(2)} total=$${it.totalPrice.toFixed(2)}  ${it.name}`,
        )
      }
      console.log('\n--- CHARGES ---')
      for (const c of result.charges) {
        console.log(`  ${c.type}: ${c.amount}`)
      }
      if (result.warnings.length) console.log('\n--- WARNINGS ---', result.warnings)
      console.log('\n--- RECON ---', recon.status, recon.messages)
      console.log('\n--- TEXT (first 40 lines) ---')
      console.log(text.split('\n').slice(0, 40).join('\n'))
    })
  }
})
