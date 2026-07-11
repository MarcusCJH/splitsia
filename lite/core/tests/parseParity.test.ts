import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { parseReceipt } from '../src/parseReceipt'
import { loadReceipt } from './fixtures/receipts'

const golden = JSON.parse(
  readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), 'fixtures', 'parseGolden.json'),
    'utf8',
  ),
) as Record<string, Record<string, unknown>>

describe('parseReceipt golden parity', () => {
  for (const [name, expected] of Object.entries(golden)) {
    it(`matches golden fixture: ${name}`, () => {
      const result = parseReceipt(loadReceipt(name))

      if (typeof expected.itemCount === 'number') {
        expect(result.items).toHaveLength(expected.itemCount)
      }

      if (typeof expected.itemCountMin === 'number') {
        expect(result.items.length).toBeGreaterThanOrEqual(expected.itemCountMin)
      }

      for (const spec of (expected.items as Array<Record<string, unknown>>) ?? []) {
        const match = result.items.find((it) => it.name === spec.name)
        expect(match).toBeDefined()
        if (typeof spec.totalPrice === 'number') {
          expect(match!.totalPrice).toBeCloseTo(spec.totalPrice as number)
        }
        if (typeof spec.quantity === 'number') {
          expect(match!.quantity).toBe(spec.quantity)
        }
      }

      for (const spec of (expected.charges as Array<Record<string, unknown>>) ?? []) {
        const charge = result.charges.find((c) => c.type === spec.type)
        expect(charge).toBeDefined()
        expect(charge!.amount).toBeCloseTo(spec.amount as number)
      }

      if (expected.hasNegativeDiscount) {
        expect(result.charges.some((c) => c.type === 'discount' && c.amount < 0)).toBe(true)
      }

      if (typeof expected.lowConfidenceItem === 'string') {
        const low = result.items.find((it) => it.name === expected.lowConfidenceItem)
        expect(low?.confidence).toBe('low')
      }
    })
  }
})
