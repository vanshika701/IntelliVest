import { describe, expect, it } from 'vitest'
import {
  defaultMandateForm, fromMandate, fromUnits, prefillMandate, toMandate, toUnits, validateMandate,
} from './mandate'

const today = new Date('2026-11-27T10:00:00Z')

describe('mandate form', () => {
  it('turns rupees into 6-decimal units and percentages into basis points', () => {
    const m = toMandate({ ...defaultMandateForm(today), perTradeCap: '1234.5', maxEquityPct: '62.5', maxSlippagePct: '0.5' })
    expect(m.perTradeCap).toBe(1_234_500_000n)
    expect(m.maxEquityBps).toBe(6250)
    expect(m.maxSlippageBps).toBe(50)
    expect(m.start).toBe(BigInt(Date.parse('2026-11-27T00:00:00Z') / 1000))
    expect(m.end).toBe(BigInt(Date.parse('2027-11-27T00:00:00Z') / 1000) + 86_399n)
  })

  it('round-trips through the contract shape', () => {
    const form = { ...defaultMandateForm(today), dailyCap: '7000', requireStock: false }
    expect(fromMandate(toMandate(form), form.funds)).toEqual(form)
  })

  it('prefills caps and end date from a goal and limits from the portfolio plan', () => {
    const form = prefillMandate(defaultMandateForm(today), {
      goal: { name: 'House', monthly: 8333.4, horizonMonths: 24 },
      plan: { profile: 'conservative', equityPct: 34.6 },
    }, today)
    expect(form).toMatchObject({
      monthlyCap: '8334', perTradeCap: '8334', dailyCap: '8334', userSignAbove: '4167',
      endDate: '2028-11-27', maxEquityPct: '35', maxLossPct: '5',
    })
  })

  it('keeps defaults without a goal or plan', () => {
    expect(prefillMandate(defaultMandateForm(today), {}, today)).toEqual(defaultMandateForm(today))
  })

  it('rejects inconsistent terms', () => {
    const errors = validateMandate({
      ...defaultMandateForm(today), perTradeCap: '20000', dailyCap: '10000', maxEquityPct: '120',
      endDate: '2026-01-01', funds: [], maxTradesPerDay: '1.5',
    })
    expect(Object.keys(errors).sort()).toEqual(['endDate', 'funds', 'maxEquityPct', 'maxTradesPerDay', 'perTradeCap'])
    expect(validateMandate(defaultMandateForm(today))).toEqual({})
  })

  it('converts units both ways', () => {
    expect(toUnits('0.000001')).toBe(1n)
    expect(fromUnits(2_500_000n)).toBe(2.5)
  })
})
