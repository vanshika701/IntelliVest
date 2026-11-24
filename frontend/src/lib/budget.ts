// Budget setup validation + chart data shaping. Pure functions, unit-tested.
// Benchmarks/SIP maths live in the backend; this only checks form input.
import type { BudgetCategory } from '../api/budget'
import { formatINR } from './format'

export const MAX_BUDGET_AMOUNT = 1e10

/** Error for one money field ('' allowed when optional), or null if valid. */
export function validateMoney(raw: string, { required = false } = {}): string | null {
  const trimmed = raw.trim()
  if (trimmed === '') return required ? 'Required' : null
  const value = Number(trimmed)
  if (Number.isNaN(value)) return 'Enter a number'
  if (value < 0) return "Can't be negative"
  if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) return 'Use at most 2 decimal places'
  if (value > MAX_BUDGET_AMOUNT) return 'That looks too large'
  return null
}

export interface SetupCheck {
  errors: Record<string, string>
  total: number
  /** Non-blocking: shown, but the user can still save. */
  warning: string | null
}

export function checkSetup(income: string, estimates: Record<string, string>, emergency: string): SetupCheck {
  const errors: Record<string, string> = {}
  const incomeErr = validateMoney(income, { required: true })
  if (incomeErr) errors.income = incomeErr
  const efErr = validateMoney(emergency)
  if (efErr) errors.emergency_fund = efErr

  let total = 0
  for (const [id, raw] of Object.entries(estimates)) {
    const err = validateMoney(raw)
    if (err) errors[id] = err
    else total += Number(raw || 0)
  }

  const incomeValue = Number(income || 0)
  let warning: string | null = null
  if (!errors.income && incomeValue === 0) {
    warning = 'With income at ₹0, benchmarks and goal checks can’t be calculated.'
  } else if (!errors.income && total > incomeValue) {
    warning = `Your estimates total ${formatINR(total, 0)}, ${formatINR(total - incomeValue, 0)} more than your income.`
  }
  return { errors, total, warning }
}

export interface PieSlice {
  id: string
  name: string
  value: number
  color: string
}

// Categorical slots validated for the dark surface (see dataviz palette);
// slate is reserved for the folded "Everything else" slice.
export const SLICE_COLORS = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#0ca30c', '#9085e9']
export const OTHER_SLICE_COLOR = '#64748b'
export const MAX_SLICES = SLICE_COLORS.length

/**
 * Which categories get their own slice: the top MAX_SLICES by the larger of
 * estimated/actual, so toggling between the two never repaints a slice.
 * Colors follow the category's position in the fixed list, not its rank.
 */
export function sliceCategories(
  categories: BudgetCategory[],
  estimated: Record<string, number>,
  actual: Record<string, number>,
): string[] {
  const size = (id: string) => Math.max(estimated[id] ?? 0, actual[id] ?? 0)
  const top = categories
    .filter((c) => size(c.id) > 0)
    .sort((a, b) => size(b.id) - size(a.id))
    .slice(0, MAX_SLICES)
    .map((c) => c.id)
  return categories.map((c) => c.id).filter((id) => top.includes(id))
}

export function pieSlices(
  categories: BudgetCategory[],
  values: Record<string, number>,
  sliceIds: string[],
): PieSlice[] {
  const slices: PieSlice[] = []
  let rest = 0
  for (const c of categories) {
    const v = values[c.id] ?? 0
    const idx = sliceIds.indexOf(c.id)
    if (idx >= 0) {
      if (v > 0) slices.push({ id: c.id, name: c.name, value: v, color: SLICE_COLORS[idx] })
    } else {
      rest += v
    }
  }
  if (rest > 0) slices.push({ id: 'rest', name: 'Everything else', value: rest, color: OTHER_SLICE_COLOR })
  return slices
}

/** Months <-> "years + months" for the goal form. */
export function toMonths(years: string, months: string): number {
  return Math.round(Number(years || 0) * 12 + Number(months || 0))
}
