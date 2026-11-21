import { describe, expect, it } from 'vitest'
import {
  computeCagr,
  estimateReturns,
  lumpsumFutureValue,
  projectionByYear,
  sipFutureValue,
} from './returns'

describe('sipFutureValue', () => {
  it('matches the standard SIP formula (₹5,000/month, 12%, 10 years)', () => {
    // i = 0.01, n = 120: 5000 × ((1.01^120 − 1) / 0.01) × 1.01
    expect(sipFutureValue(5000, 12, 120)).toBeCloseTo(1_161_695.38, 1)
  })

  it('compounds a single month correctly', () => {
    // One payment at the start of the month earns one month of interest.
    expect(sipFutureValue(1000, 12, 1)).toBeCloseTo(1010, 6)
  })

  it('degrades to plain saving at 0% return', () => {
    expect(sipFutureValue(1000, 0, 24)).toBe(24_000)
  })
})

describe('lumpsumFutureValue', () => {
  it('matches P × (1 + r)^t', () => {
    expect(lumpsumFutureValue(100_000, 12, 10)).toBeCloseTo(310_584.82, 1)
    expect(lumpsumFutureValue(50_000, 8, 1)).toBeCloseTo(54_000, 6)
  })

  it('returns the principal for 0 years or 0%', () => {
    expect(lumpsumFutureValue(10_000, 12, 0)).toBe(10_000)
    expect(lumpsumFutureValue(10_000, 0, 5)).toBe(10_000)
  })

  it('handles negative returns', () => {
    expect(lumpsumFutureValue(10_000, -10, 2)).toBeCloseTo(8_100, 6)
  })
})

describe('estimateReturns', () => {
  it('splits SIP totals into invested and gains', () => {
    const e = estimateReturns('sip', 5000, 10, 12)
    expect(e.invested).toBe(600_000)
    expect(e.totalValue).toBeCloseTo(1_161_695.38, 1)
    expect(e.estimatedReturns).toBeCloseTo(561_695.38, 1)
  })

  it('splits one-time totals into invested and gains', () => {
    const e = estimateReturns('one_time', 100_000, 10, 12)
    expect(e.invested).toBe(100_000)
    expect(e.estimatedReturns).toBeCloseTo(210_584.82, 1)
  })
})

describe('projectionByYear', () => {
  it('starts at zero for SIP and ends at the estimate', () => {
    const points = projectionByYear('sip', 1000, 3, 12)
    expect(points).toHaveLength(4)
    expect(points[0]).toEqual({ year: 0, invested: 0, value: 0 })
    expect(points[3].invested).toBe(36_000)
    expect(points[3].value).toBe(Math.round(sipFutureValue(1000, 12, 36)))
  })
})

describe('computeCagr', () => {
  it('computes CAGR over the last 3 years of a longer series', () => {
    const points = [
      { t: '2020-01-01', v: 10 }, // outside the 3-year window
      { t: '2023-01-02', v: 100 },
      { t: '2026-01-02', v: 133.1 },
    ]
    expect(computeCagr(points)).toBeCloseTo(10, 0)
  })

  it('needs at least a year of history', () => {
    expect(computeCagr([{ t: '2026-01-01', v: 100 }, { t: '2026-10-01', v: 120 }])).toBeNull()
    expect(computeCagr([])).toBeNull()
  })

  it('rejects implausible results such as an unadjusted unit split', () => {
    expect(computeCagr([{ t: '2023-01-01', v: 1500 }, { t: '2026-01-01', v: 100 }])).toBeNull()
  })
})
