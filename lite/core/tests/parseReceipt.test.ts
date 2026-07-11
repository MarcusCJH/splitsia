import { describe, it, expect } from 'vitest'
import { parseReceipt } from '../src/parseReceipt'
import { reconcileReceipt } from '../src/receiptReconcile'
import {
  CLEAN_RECEIPT,
  CODES_RECEIPT,
  DISCOUNT_POSITIVE_RECEIPT,
  DISCOUNT_RECEIPT,
  LOW_CONF_RECEIPT,
  MISMATCH_RECEIPT,
  NOISY_RECEIPT,
  NO_TOTAL_RECEIPT,
  POS_NATURELAND_RECEIPT,
  QTY_RECEIPT,
  TWO_TOTALS_RECEIPT,
} from './fixtures/receipts'

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('parseReceipt', () => {

  // ── Item detection ──────────────────────────────────────────────────────────

  describe('item detection', () => {
    it('extracts items with correct names and prices', () => {
      const { items } = parseReceipt(CLEAN_RECEIPT)
      expect(items).toHaveLength(3)
      expect(items[0]).toMatchObject({ name: 'Chicken Rice', totalPrice: 3.50 })
      expect(items[1]).toMatchObject({ name: 'Char Kway Teow', totalPrice: 4.50 })
      expect(items[2]).toMatchObject({ name: 'Teh Tarik', totalPrice: 1.80 })
    })

    it('strips leading 3+ digit item codes from names', () => {
      const { items } = parseReceipt(CODES_RECEIPT)
      expect(items[0].name).toBe('Laksa')
      expect(items[1].name).toBe('Nasi Lemak')
      expect(items[2].name).toBe('Mee Goreng')
    })

    it('parses "N x Name" quantity prefix', () => {
      const { items } = parseReceipt(QTY_RECEIPT)
      expect(items[0]).toMatchObject({ name: 'Nasi Lemak', quantity: 2, unitPrice: 4.00, totalPrice: 8.00 })
    })

    it('parses "Name xN" quantity suffix', () => {
      const { items } = parseReceipt(QTY_RECEIPT)
      expect(items[1]).toMatchObject({ name: 'Milo Dinosaur', quantity: 2, unitPrice: 3.00, totalPrice: 6.00 })
    })

    it('parses "N × Name" unicode multiplication sign', () => {
      const { items } = parseReceipt(QTY_RECEIPT)
      expect(items[2]).toMatchObject({ name: 'Satay', quantity: 3, unitPrice: 3.00, totalPrice: 9.00 })
    })

    it('assigns high confidence to clean alphabetic names with one price', () => {
      const { items } = parseReceipt(CLEAN_RECEIPT)
      expect(items[0].confidence).toBe('high')
      expect(items[1].confidence).toBe('high')
      expect(items[2].confidence).toBe('high')
    })

    it('assigns low confidence to names shorter than 3 characters', () => {
      const { items } = parseReceipt(LOW_CONF_RECEIPT)
      const shortItem = items.find((it) => it.name === 'Xz')
      expect(shortItem?.confidence).toBe('low')
    })

    it('assigns medium confidence when line has two prices (unit + total)', () => {
      const { items } = parseReceipt('Item   2.50  5.00\n'.trim())
      expect(items[0].confidence).toBe('medium')
    })
  })

  // ── Charge detection ────────────────────────────────────────────────────────

  describe('charge detection', () => {
    it('detects subtotal', () => {
      const { charges } = parseReceipt(CLEAN_RECEIPT)
      const sub = charges.find((c) => c.type === 'subtotal')
      expect(sub?.amount).toBe(9.80)
    })

    it('detects "Sub Total" with a space', () => {
      const { charges } = parseReceipt(CODES_RECEIPT)
      const sub = charges.find((c) => c.type === 'subtotal')
      expect(sub?.amount).toBe(20.00)
    })

    it('detects GST', () => {
      const { charges } = parseReceipt(CLEAN_RECEIPT)
      const gst = charges.find((c) => c.type === 'gst')
      expect(gst?.amount).toBe(0.88)
    })

    it('ignores percentage token when extracting GST amount', () => {
      // "GST 9%" should not be parsed as amount 9 - only 0.88 is the charge
      const { charges } = parseReceipt(CLEAN_RECEIPT)
      const gst = charges.find((c) => c.type === 'gst')
      expect(gst?.amount).toBe(0.88)
    })

    it('detects service charge', () => {
      const { charges } = parseReceipt(DISCOUNT_RECEIPT)
      const svc = charges.find((c) => c.type === 'service_charge')
      expect(svc?.amount).toBe(3.84)
    })

    it('preserves explicit negative on discount', () => {
      const { charges } = parseReceipt(DISCOUNT_RECEIPT)
      const disc = charges.find((c) => c.type === 'discount')
      expect(disc?.amount).toBe(-3.84)
    })

    it('forces discount to negative when written as positive', () => {
      const { charges } = parseReceipt(DISCOUNT_POSITIVE_RECEIPT)
      const disc = charges.find((c) => c.type === 'discount')
      expect(disc?.amount).toBe(-2.00)
    })

    it('detects negative rounding adjustment', () => {
      const { charges } = parseReceipt(DISCOUNT_RECEIPT)
      const rounding = charges.find((c) => c.type === 'rounding')
      expect(rounding?.amount).toBe(-0.01)
    })

    it('detects "Grand Total"', () => {
      const { charges } = parseReceipt(DISCOUNT_RECEIPT)
      const total = charges.find((c) => c.type === 'total')
      expect(total?.amount).toBe(43.85)
    })

    it('detects bare "Total" line', () => {
      const { charges } = parseReceipt(CLEAN_RECEIPT)
      const total = charges.find((c) => c.type === 'total')
      expect(total?.amount).toBe(10.68)
    })

    it('detects all charge types from one receipt', () => {
      const { charges } = parseReceipt(DISCOUNT_RECEIPT)
      const types = charges.map((c) => c.type)
      expect(types).toContain('subtotal')
      expect(types).toContain('discount')
      expect(types).toContain('service_charge')
      expect(types).toContain('gst')
      expect(types).toContain('rounding')
      expect(types).toContain('total')
    })

    it('stores trimmed original line text as label', () => {
      const { charges } = parseReceipt(CLEAN_RECEIPT)
      const gst = charges.find((c) => c.type === 'gst')
      expect(gst?.label).toBe('GST 9%              0.88')
    })
  })

  // ── Noise filtering ─────────────────────────────────────────────────────────

  describe('noise filtering', () => {
    it('skips GST Reg No line', () => {
      const { items, charges } = parseReceipt(NOISY_RECEIPT)
      // Should only have 2 items; "GST Reg No" must not appear as an item or charge
      expect(items).toHaveLength(2)
      // GST charge should still be detected (from "GST 9% 0.86"), not the reg line
      const gst = charges.find((c) => c.type === 'gst')
      expect(gst?.amount).toBe(0.86)
    })

    it('skips thank-you and website lines', () => {
      const { items } = parseReceipt(NOISY_RECEIPT)
      expect(items.every((it) => !it.name.toLowerCase().includes('thank'))).toBe(true)
      expect(items.every((it) => !it.name.toLowerCase().includes('www'))).toBe(true)
    })

    it('skips cash and change lines', () => {
      // Cash/Change should not appear as items or charges
      const { items, charges } = parseReceipt(NOISY_RECEIPT)
      expect(items.every((it) => it.name.toLowerCase() !== 'cash')).toBe(true)
      expect(charges.every((c) => c.label.toLowerCase().includes('cash') === false)).toBe(true)
    })

    it('does not turn restaurant name or address into items', () => {
      const { items } = parseReceipt(NOISY_RECEIPT)
      const names = items.map((it) => it.name)
      expect(names).not.toContain('ABC RESTAURANT PTE LTD')
      expect(names).not.toContain('123 Orchard Road Singapore 238859')
    })
  })

  // ── Warnings ────────────────────────────────────────────────────────────────

  describe('warnings', () => {
    it('warns when items do not sum to detected subtotal', () => {
      const { warnings } = parseReceipt(MISMATCH_RECEIPT)
      expect(warnings.some((w) => w.includes('differs from detected subtotal'))).toBe(true)
    })

    it('warning includes both computed sum and subtotal amount', () => {
      const { warnings } = parseReceipt(MISMATCH_RECEIPT)
      const w = warnings.find((w) => w.includes('differs from detected subtotal'))
      expect(w).toContain('$16.50')
      expect(w).toContain('$22.00')
    })

    it('warns when multiple total lines are detected', () => {
      const { warnings } = parseReceipt(TWO_TOTALS_RECEIPT)
      expect(warnings.some((w) => w.includes('Multiple total lines'))).toBe(true)
    })

    it('warns when no total is detected', () => {
      const { warnings } = parseReceipt(NO_TOTAL_RECEIPT)
      expect(warnings.some((w) => w.includes('No total line'))).toBe(true)
    })

    it('warns when items have low confidence', () => {
      const { warnings } = parseReceipt(LOW_CONF_RECEIPT)
      expect(warnings.some((w) => w.includes('low OCR confidence'))).toBe(true)
    })

    it('produces no warnings for a clean, correct receipt', () => {
      const { warnings } = parseReceipt(CLEAN_RECEIPT)
      expect(warnings).toHaveLength(0)
    })
  })

  // ── Edge cases ──────────────────────────────────────────────────────────────

  describe('edge cases', () => {
    it('returns empty result for empty string', () => {
      const result = parseReceipt('')
      expect(result.items).toHaveLength(0)
      expect(result.charges).toHaveLength(0)
      expect(result.warnings).toHaveLength(0)
    })

    it('returns empty result for only noise lines', () => {
      const result = parseReceipt('Cash: 50.00\nChange: 5.00\nThank you!\nwww.shop.com')
      expect(result.items).toHaveLength(0)
      expect(result.charges).toHaveLength(0)
      expect(result.warnings).toHaveLength(0)
    })

    it('returns empty result for lines with no prices', () => {
      const result = parseReceipt('DINE IN\nTable 5\nPax: 3\nDate: 01/07/2026')
      expect(result.items).toHaveLength(0)
    })

    it('does not produce a no-total warning when there are no items either', () => {
      const result = parseReceipt('')
      expect(result.warnings).toHaveLength(0)
    })
  })

  // ── SG POS receipt formats ───────────────────────────────────────────────────

  describe('SG POS receipt formats', () => {
    const POS_RECEIPT = POS_NATURELAND_RECEIPT

    it('does not treat "(Promo)" item label as a discount', () => {
      const { items } = parseReceipt(POS_RECEIPT)
      const guinness = items.find((it) => it.name.toLowerCase().includes('guinness'))
      expect(guinness).toBeDefined()
      expect(guinness?.totalPrice).toBe(13.00)
    })

    it('detects "Svr Chrg" as service charge', () => {
      const { charges } = parseReceipt(POS_RECEIPT)
      const svc = charges.find((c) => c.type === 'service_charge')
      expect(svc).toBeDefined()
      expect(svc?.amount).toBeCloseTo(37.18)
    })

    it('detects "ITEM DISC" parenthetical amount as a negative discount', () => {
      const { charges } = parseReceipt(POS_RECEIPT)
      const disc = charges.find((c) => c.type === 'discount')
      expect(disc).toBeDefined()
      expect(disc?.amount).toBeCloseTo(-136.80)
    })

    it('strips bare leading quantity "2 Foo" and sets quantity correctly', () => {
      const { items } = parseReceipt(POS_RECEIPT)
      const moscato = items.find((it) => it.name.toLowerCase().includes('moscato'))
      expect(moscato).toBeDefined()
      expect(moscato?.quantity).toBe(2)
      expect(moscato?.totalPrice).toBe(22.00)
    })

    it('strips bare leading quantity "2 Foo" from items', () => {
      const { items } = parseReceipt(POS_RECEIPT)
      const juice = items.find((it) => it.name.toLowerCase().includes('apple juice'))
      expect(juice).toBeDefined()
      expect(juice?.quantity).toBe(1)
      expect(juice?.totalPrice).toBe(5.00)
    })

    it('parses qty + item code + name ("2 6657 Honey")', () => {
      const { items } = parseReceipt('2 6657 Honey Butterfly  9.80')
      expect(items).toHaveLength(1)
      expect(items[0]).toMatchObject({
        name: 'Honey Butterfly',
        quantity: 2,
        totalPrice: 9.80,
        unitPrice: 4.90,
      })
    })
  })

  // ── Real OCR output (samples/sample2.jpg, sample3.jpg) ─────────────────────

  describe('real OCR output fixtures', () => {
    it('parses Tsuta receipt: SUBTTL charge, spaced decimal, SLICE BEEF PHO', () => {
      const rawOcr = `
3      SLICE BEEF PHO                    44 40
SUBTTL                             226.50
%DISC 10.00% (STAFF _DISC) STAFF      -22.65
SERVICE CHARGE 10%                   20.39
TOTAL          244.42
KRISPLUS                             244.42
`.trim()
      const { items, charges } = parseReceipt(rawOcr)
      const pho = items.find((it) => it.name.toLowerCase().includes('slice beef pho'))
      expect(pho).toMatchObject({ quantity: 3, totalPrice: 44.40 })
      expect(charges.find((c) => c.type === 'subtotal')?.amount).toBeCloseTo(226.50)
      expect(charges.find((c) => c.type === 'discount')?.amount).toBeCloseTo(-22.65)
      expect(charges.find((c) => c.type === 'total')?.amount).toBeCloseTo(244.42)
      expect(items.some((it) => it.name.toLowerCase().includes('krisplus'))).toBe(false)
      expect(items.some((it) => it.name.toLowerCase() === 'subttl')).toBe(false)
    })

    it('parses Sanook receipt: implicit decimal 990 → 9.90 and footer subtotal', () => {
      const rawOcr = `
1            6302 Deep-fried Chicken                   990 |
3             6201 Grilled Chicken Satay (3              12.10}
239.10
Sub Total
SERVICE CHA
GST 9%
Total
VISA
`.trim()
      const { items, charges } = parseReceipt(rawOcr)
      const chicken = items.find((it) => it.name.toLowerCase().includes('deep'))
      expect(chicken?.totalPrice).toBeCloseTo(9.90)
      expect(charges.find((c) => c.type === 'subtotal')?.amount).toBeCloseTo(239.10)
      expect(items.some((it) => it.name.toLowerCase().includes('visa'))).toBe(false)
    })
  })

  // ── OCR normalization & mobile-world formats ─────────────────────────────────

  describe('OCR normalization', () => {
    it('collapses space after decimal ("13. 00" → 13.00)', () => {
      const { items } = parseReceipt('Chicken Rice  13. 00\nTotal  13. 00')
      expect(items).toHaveLength(1)
      expect(items[0]).toMatchObject({ name: 'Chicken Rice', totalPrice: 13.00 })
    })

    it('handles real-world Tesseract output with spaced decimals on every price', () => {
      // Mirrors SINGLE_COLUMN OCR output from samples/sample.jpg (Natureland Cafe)
      const rawOcr = `
Natureland Cafe
GST REG NO: 201630159%
1 (Promo) Guinness $13. 00
API le J Ce $5. 00
2 Ki No Bi Bt] $456. 00
[TEM DISC 30% ($136. 80)
2 Moscato (WP) $22. 00
SUBTOTAL$371. 80
10% Svr Chrg $37.18
0% GST$36. 81
TOTAL      $445. 79
Vis$445. 79
`.trim()
      const { items, charges } = parseReceipt(rawOcr)
      expect(items.length).toBeGreaterThanOrEqual(2)
      const guinness = items.find((it) => it.name.toLowerCase().includes('guinness'))
      expect(guinness?.totalPrice).toBe(13.00)
      const moscato = items.find((it) => it.name.toLowerCase().includes('moscato'))
      expect(moscato?.totalPrice).toBe(22.00)
      expect(moscato?.quantity).toBe(2)
      expect(items.some((it) => it.name.toLowerCase() === 'vis')).toBe(false)
      const svc = charges.find((c) => c.type === 'service_charge')
      expect(svc?.amount).toBeCloseTo(37.18)
      const gst = charges.find((c) => c.type === 'gst')
      expect(gst?.amount).toBeCloseTo(36.81)
      const total = charges.find((c) => c.type === 'total')
      expect(total?.amount).toBeCloseTo(445.79)
    })

    it('handles comma-as-decimal separator ("3,50" → 3.50)', () => {
      const { items } = parseReceipt('Chicken Rice  3,50\nTotal  3,50')
      expect(items).toHaveLength(1)
      expect(items[0]).toMatchObject({ name: 'Chicken Rice', totalPrice: 3.50 })
    })

    it('handles single-digit decimal ("3.5" treated as 3.50)', () => {
      const { items } = parseReceipt('Kaya Toast  3.5\nTotal  3.5')
      expect(items).toHaveLength(1)
      expect(items[0]).toMatchObject({ name: 'Kaya Toast', totalPrice: 3.50 })
    })

    it('joins orphan price line with preceding name-only line', () => {
      const receipt = 'NASI LEMAK\n3.50\nKOPI O\n1.20\nTotal\n4.70'
      const { items } = parseReceipt(receipt)
      expect(items).toHaveLength(2)
      expect(items[0]).toMatchObject({ name: 'NASI LEMAK', totalPrice: 3.50 })
      expect(items[1]).toMatchObject({ name: 'KOPI O', totalPrice: 1.20 })
    })

    it('correctly detects a charge when orphan name is a charge keyword', () => {
      // "GST" on one line, amount on the next - should become a charge, not an item
      const receipt = 'Roti Prata  2.50\nGST\n0.23\nTotal\n2.73'
      const { items, charges } = parseReceipt(receipt)
      expect(items).toHaveLength(1)
      expect(items[0].name).toBe('Roti Prata')
      const gst = charges.find((c) => c.type === 'gst')
      expect(gst?.amount).toBeCloseTo(0.23)
    })
  })

  describe('garbled OCR fixtures', () => {
    it('recovers sample4 footer (shadow, blurry labels)', () => {
      const rawOcr = `
Natureland Caf-
Natureland Spa Pte Ltd
2 Ki No Bi Bl                              $456. 00
CUBTOTA                                       $319. 20
Se oy                  $31.92
10% Sur Chirge               Puli
Sar ii           $57.60
RR                   $382. 72
`.trim()
      const parse = parseReceipt(rawOcr)
      const recon = reconcileReceipt(parse)
      expect(parse.items.some((it) => /Ki No Bi/i.test(it.name))).toBe(true)
      expect(parse.items.filter((it) => /Ki No Bi/i.test(it.name))).toHaveLength(1)
      expect(parse.charges.find((c) => c.type === 'discount')?.amount).toBeCloseTo(-136.8)
      expect(parse.charges.find((c) => c.type === 'subtotal')?.amount).toBeCloseTo(319.2)
      expect(parse.charges.find((c) => c.type === 'service_charge')?.amount).toBeCloseTo(31.92)
      expect(parse.charges.find((c) => c.type === 'gst')?.amount).toBeCloseTo(31.6)
      expect(parse.charges.find((c) => c.type === 'total')?.amount).toBeCloseTo(382.72)
      expect(recon.computedTotal).toBeCloseTo(382.72)
      expect(recon.totalDiff).toBeLessThanOrEqual(0.03)
      expect(recon.status).toBe('ok')
    })

    it('recovers Natureland phone OCR footer math', () => {
      const rawOcr = `
PERS AEA
Natureland Cafe     :
Natureland Spa Pte Ltd -
ToT $13.00
1 (Promo)  Gul mess
1 Apple Jui      =      $5.00
1 Nika FT barrel bls        $18. 00
{TEM DISC 30%               ($5. 40)
2 Ki No Bi Bt}              $456. 00
ITEM DISC 30%             {$135, 80)
2 Moscato (WP)      Ca $2.00
Tn LR ne $371.80
vr Chegs ©        so $31.18
96ST mT Th $36.81
$445. 79
`.trim()
      const parse = parseReceipt(rawOcr)
      const recon = reconcileReceipt(parse)
      expect(parse.charges.find((c) => c.type === 'subtotal')?.amount).toBeCloseTo(371.8)
      expect(parse.charges.find((c) => c.type === 'total')?.amount).toBeCloseTo(445.79)
      expect(Math.abs(recon.computedTotal - 445.79)).toBeLessThanOrEqual(0.55)
    })
  })

})
