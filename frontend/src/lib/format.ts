import { format, parseISO } from 'date-fns'

export const DASH = '—'

export function formatINR(value: number | null | undefined, fractionDigits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH
  return `₹${value.toLocaleString('en-IN', { minimumFractionDigits: fractionDigits, maximumFractionDigits: fractionDigits })}`
}

/** Compact Indian notation for large amounts: ₹1.2 L, ₹3.45 Cr. */
export function formatINRCompact(value: number): string {
  const abs = Math.abs(value)
  const sign = value < 0 ? '−' : ''
  if (abs >= 1e7) return `${sign}₹${(abs / 1e7).toFixed(2)} Cr`
  if (abs >= 1e5) return `${sign}₹${(abs / 1e5).toFixed(2)} L`
  return `${sign}${formatINR(abs, 0)}`
}

/** Short labels for chart axes: ₹28L, ₹1.2Cr, ₹50k. */
export function formatINRAxis(value: number): string {
  const abs = Math.abs(value)
  const trim = (n: number) => String(Number(n.toFixed(1)))
  if (abs >= 1e7) return `₹${trim(value / 1e7)}Cr`
  if (abs >= 1e5) return `₹${trim(value / 1e5)}L`
  if (abs >= 1e3) return `₹${trim(value / 1e3)}k`
  return `₹${Math.round(value)}`
}

export function formatSignedPct(value: number | null | undefined): string {
  if (value === null || value === undefined) return DASH
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

export function formatDate(iso: string | null | undefined, pattern = 'd MMM yyyy'): string {
  if (!iso) return DASH
  return format(parseISO(iso), pattern)
}
