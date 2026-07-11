import { parseReceipt, type ParseResult } from './parseReceipt'

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
