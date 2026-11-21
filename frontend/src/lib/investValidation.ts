import { formatINR } from './format'

export const MAX_ORDER_AMOUNT = 10_000_000

/** Error message for an invest-panel amount, or null if it's valid. */
export function validateAmount(raw: string, minimum: number | null, label: string): string | null {
  const trimmed = raw.trim()
  const value = Number(trimmed)
  if (trimmed === '' || Number.isNaN(value) || value <= 0) return 'Enter an amount'
  if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) return 'Use at most 2 decimal places'
  if (minimum !== null && value < minimum) return `Minimum ${label} is ${formatINR(minimum, 0)}`
  if (value > MAX_ORDER_AMOUNT) return `Maximum per order is ${formatINR(MAX_ORDER_AMOUNT, 0)}`
  return null
}
