import type { HorizonUnit } from '../api/instruments'

/** Same limits as the backend (about 2 years in every unit). */
export const HORIZON_LIMITS: Record<HorizonUnit, number> = { days: 730, months: 24, years: 2 }

export const HORIZON_PRESETS: { label: string; amount: number; unit: HorizonUnit }[] = [
  { label: '1 week', amount: 7, unit: 'days' },
  { label: '1 month', amount: 1, unit: 'months' },
  { label: '3 months', amount: 3, unit: 'months' },
  { label: '1 year', amount: 1, unit: 'years' },
]

/** Error message for a prediction horizon, or null if it's valid. */
export function validateHorizon(raw: string, unit: HorizonUnit): string | null {
  const trimmed = raw.trim()
  if (!/^\d+$/.test(trimmed) || Number(trimmed) < 1) return 'Enter a whole number'
  const max = HORIZON_LIMITS[unit]
  if (Number(trimmed) > max) return `Up to ${max} ${unit}`
  return null
}

/** "7 days", "1 month", "2 years". */
export function describeHorizon(amount: number, unit: HorizonUnit): string {
  return `${amount} ${amount === 1 ? unit.slice(0, -1) : unit}`
}
