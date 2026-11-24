import { describe, expect, it } from 'vitest'
import type { BudgetCategory } from '../api/budget'
import { checkSetup, MAX_SLICES, OTHER_SLICE_COLOR, pieSlices, sliceCategories, toMonths, validateMoney } from './budget'

const cats: BudgetCategory[] = Array.from({ length: 10 }, (_, i) => ({
  id: `c${i}`,
  name: `Cat ${i}`,
  bucket: 'needs',
  min_pct: null,
  max_pct: null,
  note: null,
}))

describe('validateMoney', () => {
  it('accepts blanks when optional and non-negative amounts', () => {
    expect(validateMoney('')).toBeNull()
    expect(validateMoney('0')).toBeNull()
    expect(validateMoney('1500.5')).toBeNull()
  })
  it('rejects negatives, junk, precision and required blanks', () => {
    expect(validateMoney('-1')).toBe("Can't be negative")
    expect(validateMoney('abc')).toBe('Enter a number')
    expect(validateMoney('1.234')).toBe('Use at most 2 decimal places')
    expect(validateMoney('', { required: true })).toBe('Required')
  })
})

describe('checkSetup', () => {
  it('totals estimates and warns (without blocking) when over income', () => {
    const r = checkSetup('10000', { housing: '8000', groceries: '4000' }, '')
    expect(r.errors).toEqual({})
    expect(r.total).toBe(12000)
    expect(r.warning).toMatch(/₹2,000 more than your income/)
  })
  it('flags zero income and per-field errors', () => {
    expect(checkSetup('0', {}, '').warning).toMatch(/income at ₹0/)
    expect(checkSetup('', { housing: '-5' }, '-1').errors).toEqual({
      income: 'Required',
      housing: "Can't be negative",
      emergency_fund: "Can't be negative",
    })
  })
})

describe('pie slices', () => {
  const est = Object.fromEntries(cats.map((c, i) => [c.id, (i + 1) * 100]))

  it('keeps at most MAX_SLICES categories and folds the rest', () => {
    const ids = sliceCategories(cats, est, {})
    expect(ids).toHaveLength(MAX_SLICES)
    const slices = pieSlices(cats, est, ids)
    expect(slices.at(-1)).toMatchObject({ id: 'rest', color: OTHER_SLICE_COLOR, value: 100 + 200 + 300 })
  })

  it('keeps the same color per category when switching basis', () => {
    const actual = { c0: 5000 }
    const ids = sliceCategories(cats, est, actual)
    const color = (vals: Record<string, number>) => pieSlices(cats, vals, ids).find((s) => s.id === 'c0')?.color
    expect(color(est)).toBe(color(actual))
  })
})

it('toMonths', () => {
  expect(toMonths('3', '')).toBe(36)
  expect(toMonths('0', '8')).toBe(8)
  expect(toMonths('1.5', '0')).toBe(18)
})
