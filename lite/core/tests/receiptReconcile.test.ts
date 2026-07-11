import { describe, it, expect } from 'vitest'
import { parseReceipt } from '../src/parseReceipt'
import { reconcileReceipt, chargesFromParse, extractMerchant } from '../src/receiptReconcile'
import { POS_NATURELAND_RECEIPT } from './fixtures/receipts'

const POS_RECEIPT = POS_NATURELAND_RECEIPT

describe('reconcileReceipt', () => {
  it('validates Natureland subtotal + service + GST = total', () => {
    const parse = parseReceipt(POS_RECEIPT)
    const r = reconcileReceipt(parse)

    expect(r.detectedSubtotal).toBeCloseTo(371.8)
    expect(r.serviceCharge).toBeCloseTo(37.18)
    expect(r.gst).toBeCloseTo(36.81)
    expect(r.detectedTotal).toBeCloseTo(445.79)
    expect(r.computedTotal).toBeCloseTo(445.79)
    expect(r.totalDiff).toBeLessThanOrEqual(0.03)
    expect(r.status).toBe('warn')
    expect(r.messages[0]).toMatch(/checks out/i)
  })

  it('warns when items do not match printed subtotal', () => {
    const parse = parseReceipt(`
Foo $10.00
SUBTOTAL $50.00
9% GST $4.50
TOTAL $54.50
`.trim())
    const r = reconcileReceipt(parse)
    expect(r.subtotalDiff).toBeGreaterThan(1)
    expect(r.status).not.toBe('ok')
    expect(r.messages.some((m) => /subtotal/i.test(m))).toBe(true)
  })
})

describe('chargesFromParse', () => {
  it('maps footer lines to Review charges with detected amounts', () => {
    const parse = parseReceipt(POS_RECEIPT)
    const charges = chargesFromParse(parse)

    expect(charges.find((c) => c.id === 'svc')?.amount).toBeCloseTo(37.18)
    expect(charges.find((c) => c.id === 'gst')?.amount).toBeCloseTo(36.81)
    expect(charges.find((c) => c.id === 'discount')?.amount).toBeCloseTo(-136.8)
  })

  it('sets rounding charge to splitStrategy none', () => {
    const parse = parseReceipt(`
Burger $10.00
Rounding -0.02
Total $9.98
`.trim())
    const charges = chargesFromParse(parse)
    expect(charges.find((c) => c.id === 'rounding')?.splitStrategy).toBe('none')
  })
})

describe('extractMerchant', () => {
  it('reads shop name from first line', () => {
    expect(extractMerchant(POS_RECEIPT)).toBe('Natureland Cafe')
  })
})
