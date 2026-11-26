// Pure helpers for the Phase 7 portfolio plan page (unit-tested).
import type { AssetClass, RecommendedHolding } from '../api/portfolioPlan'

export const ASSET_CLASSES: { id: AssetClass; label: string; color: string }[] = [
  { id: 'equity', label: 'Stocks', color: 'var(--color-brand)' },
  { id: 'debt', label: 'Debt', color: 'var(--color-gains)' },
  { id: 'gold', label: 'Gold', color: '#d4a72c' },
]

/** 0.1234 -> "12.3%"; null -> "—". */
export function formatFraction(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

/** 18 -> "1 year 6 months"; 24 -> "2 years". */
export function formatHorizon(months: number): string {
  const years = Math.floor(months / 12)
  const rest = months % 12
  const parts = []
  if (years) parts.push(`${years} year${years === 1 ? '' : 's'}`)
  if (rest) parts.push(`${rest} month${rest === 1 ? '' : 's'}`)
  return parts.join(' ') || '0 months'
}

export function groupByClass(holdings: RecommendedHolding[]): { id: AssetClass; label: string; holdings: RecommendedHolding[] }[] {
  return ASSET_CLASSES
    .map((c) => ({ id: c.id, label: c.label, holdings: holdings.filter((h) => h.asset_class === c.id) }))
    .filter((group) => group.holdings.length > 0)
}

export interface PlanForm {
  mode: 'horizon' | 'goal'
  years: string
  goalId: string
  lumpSum: string
  monthly: string
}

export type PlanErrors = Partial<Record<'years' | 'goalId' | 'amounts', string>>

const MAX_YEARS = 50 // matches the backend's 600-month limit

export function validatePlanForm(form: PlanForm): PlanErrors {
  const errors: PlanErrors = {}
  if (form.mode === 'horizon') {
    const years = Number(form.years)
    if (!form.years.trim()) errors.years = 'Enter how many years until you need the money'
    else if (!(years > 0)) errors.years = 'Use a number of years above 0'
    else if (years > MAX_YEARS) errors.years = `Use at most ${MAX_YEARS} years`
  } else if (!form.goalId) {
    errors.goalId = 'Choose a goal'
  }
  const lump = Number(form.lumpSum || 0)
  const monthly = Number(form.monthly || 0)
  if (lump + monthly < 1) errors.amounts = 'Enter a one-time amount, a monthly amount, or both'
  return errors
}

/** Years (decimals allowed) -> whole months, at least 1. */
export function yearsToMonths(years: string): number {
  return Math.max(1, Math.round(Number(years) * 12))
}
