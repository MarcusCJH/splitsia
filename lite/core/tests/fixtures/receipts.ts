import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const receiptsDir = join(dirname(fileURLToPath(import.meta.url)), 'receipts')

export function loadReceipt(name: string): string {
  return readFileSync(join(receiptsDir, `${name}.txt`), 'utf8').trim()
}

export const CLEAN_RECEIPT = loadReceipt('clean')
export const QTY_RECEIPT = loadReceipt('qty')
export const CODES_RECEIPT = loadReceipt('codes')
export const NOISY_RECEIPT = loadReceipt('noisy')
export const DISCOUNT_RECEIPT = loadReceipt('discount')
export const DISCOUNT_POSITIVE_RECEIPT = loadReceipt('discount_positive')
export const MISMATCH_RECEIPT = loadReceipt('mismatch')
export const TWO_TOTALS_RECEIPT = loadReceipt('two_totals')
export const NO_TOTAL_RECEIPT = loadReceipt('no_total')
export const LOW_CONF_RECEIPT = loadReceipt('low_conf')
export const POS_NATURELAND_RECEIPT = loadReceipt('pos_natureland')

export const PARSE_FIXTURES = [
  ['clean', CLEAN_RECEIPT, 3],
  ['qty', QTY_RECEIPT, 3],
  ['codes', CODES_RECEIPT, 3],
  ['noisy', NOISY_RECEIPT, 2],
  ['discount', DISCOUNT_RECEIPT, 3],
] as const
