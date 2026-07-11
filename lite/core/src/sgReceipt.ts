/** Singapore F&B receipt conventions - IRAS / POS patterns shared by parse + OCR. */

export const SG_GST_RATE = 0.09
export const SG_SERVICE_CHARGE_RATE = 0.10

/** Dine-in tax / service signals only - not "GST Reg No" (registration). */
const SG_TAX_OR_SERVICE_RE =
  /\b(service\s*cha(?:r(?:ge)?)?|service\s*charge|svr\s*ch|s\/c|gst\s*\d+\s*%|\d+\s*%\s*gst|(?<!reg\s)\bgst\b(?!\s*reg)|\d+\s*%\s*(?:tax|svc|svr|sur))\b/i

const SG_FNB_FOOTER_RE =
  /\b(service\s*cha(?:r(?:ge)?)?|service\s*charge|svr\s*ch|s\/c|gst\s*\d+\s*%|\d+\s*%\s*gst|(?<!reg\s)\bgst\b(?!\s*reg)|sub[\s-]?total|subttl|cubtota|subtota|item\s*disc|%disc|staff\s*disc|member\s*disc|nett?\s*total|grand\s*total)\b/i

export function looksLikeSgFnbFooter(rawText: string | null | undefined): boolean {
  return Boolean(rawText && SG_FNB_FOOTER_RE.test(rawText))
}

export function looksLikeSgTaxOrServiceFooter(rawText: string | null | undefined): boolean {
  return Boolean(rawText && SG_TAX_OR_SERVICE_RE.test(rawText))
}

export function netFoodSubtotal(subtotal: number, discountSum: number): number {
  return round2(subtotal + discountSum)
}

function round2(n: number): number {
  return Math.round(n * 100) / 100
}

export function expectedServiceCharge(subtotal: number, discountSum: number): number {
  return round2(netFoodSubtotal(subtotal, discountSum) * SG_SERVICE_CHARGE_RATE)
}

export function serviceChargeCandidates(subtotal: number, discountSum: number): number[] {
  const gross = round2(subtotal)
  const net = netFoodSubtotal(subtotal, discountSum)
  return [round2(gross * SG_SERVICE_CHARGE_RATE), round2(net * SG_SERVICE_CHARGE_RATE)]
}

export function expectedGst(subtotal: number, discountSum: number, serviceCharge: number): number {
  return round2((netFoodSubtotal(subtotal, discountSum) + serviceCharge) * SG_GST_RATE)
}

export function gstCandidates(
  subtotal: number,
  discountSum: number,
  serviceCharge: number,
): number[] {
  const gross = round2(subtotal)
  const net = netFoodSubtotal(subtotal, discountSum)
  return [
    round2((net + serviceCharge) * SG_GST_RATE),
    round2((gross + serviceCharge) * SG_GST_RATE),
  ]
}
