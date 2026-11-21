import { describe, expect, it } from 'vitest'
import type { PricePoint } from '../api/instruments'
import {
  NO_INTRADAY_FOR_FUNDS,
  filterDailyPoints,
  getRangeAvailability,
  getRangeStart,
  pickDefaultRange,
  pointsForRange,
} from './ranges'

// Local-time dates, matching how the app evaluates "now".
const NOW = new Date(2026, 10, 21, 15, 30) // 21 Nov 2026, 15:30

function daily(dates: string[]): PricePoint[] {
  return dates.map((t, i) => ({ t, v: 100 + i }))
}

describe('getRangeStart', () => {
  it('counts back from now for 1W/1M/3M/1Y', () => {
    expect(getRangeStart('1W', NOW)).toEqual(new Date(2026, 10, 14, 15, 30))
    expect(getRangeStart('1M', NOW)).toEqual(new Date(2026, 9, 21, 15, 30))
    expect(getRangeStart('3M', NOW)).toEqual(new Date(2026, 7, 21, 15, 30))
    expect(getRangeStart('1Y', NOW)).toEqual(new Date(2025, 10, 21, 15, 30))
  })

  it('uses 1 January of the current year for YTD', () => {
    expect(getRangeStart('YTD', NOW)).toEqual(new Date(2026, 0, 1))
    expect(getRangeStart('YTD', new Date(2027, 0, 1, 0, 5))).toEqual(new Date(2027, 0, 1))
  })

  it('clamps month arithmetic at month ends', () => {
    // 31 March minus one month has no 31 February — date-fns clamps to the 28th.
    expect(getRangeStart('1M', new Date(2026, 2, 31))).toEqual(new Date(2026, 1, 28))
  })
})

describe('filterDailyPoints', () => {
  const points = daily(['2025-12-31', '2026-01-01', '2026-01-02', '2026-11-13', '2026-11-14', '2026-11-20'])

  it('YTD starts exactly on 1 January, excluding the previous year', () => {
    expect(filterDailyPoints(points, 'YTD', NOW).map((p) => p.t)).toEqual([
      '2026-01-01',
      '2026-01-02',
      '2026-11-13',
      '2026-11-14',
      '2026-11-20',
    ])
  })

  it('1W includes the start day and later', () => {
    expect(filterDailyPoints(points, '1W', NOW).map((p) => p.t)).toEqual(['2026-11-14', '2026-11-20'])
  })
})

describe('getRangeAvailability', () => {
  const twoYears = daily(['2024-11-20', '2025-06-01', '2026-01-05', '2026-09-01', '2026-10-25', '2026-11-18', '2026-11-20'])

  it('disables 1D for funds with an explanation', () => {
    const availability = getRangeAvailability(twoYears, null, false, NOW)
    expect(availability['1D']).toEqual({ available: false, reason: NO_INTRADAY_FOR_FUNDS })
    expect(availability['1M'].available).toBe(true)
    expect(availability['1Y'].available).toBe(true)
  })

  it('needs at least two points in a range', () => {
    const sparse = daily(['2026-11-20'])
    const availability = getRangeAvailability(sparse, [], true, NOW)
    expect(Object.values(availability).every((r) => !r.available)).toBe(true)
    expect(pickDefaultRange(availability)).toBeNull()
  })

  it('YTD is unavailable on the first trading days of January', () => {
    const jan2 = new Date(2027, 0, 2)
    const points = daily(['2026-12-30', '2026-12-31', '2027-01-01'])
    expect(getRangeAvailability(points, null, false, jan2).YTD.available).toBe(false)
  })
})

describe('pickDefaultRange', () => {
  it('prefers 1M, then falls back to whatever has data', () => {
    const recentOnly = daily(['2026-11-17', '2026-11-18', '2026-11-20'])
    const availability = getRangeAvailability(recentOnly, null, false, NOW)
    expect(pickDefaultRange(availability)).toBe('1M')

    const intradayOnly = getRangeAvailability([], [{ t: 'a', v: 1 }, { t: 'b', v: 2 }], true, NOW)
    expect(pickDefaultRange(intradayOnly)).toBe('1D')
  })
})

describe('pointsForRange', () => {
  it('uses intraday points for 1D and daily points otherwise', () => {
    const intraday = [{ t: '2026-11-20T04:00:00Z', v: 1 }]
    const points = daily(['2026-11-20'])
    expect(pointsForRange('1D', points, intraday, NOW)).toBe(intraday)
    expect(pointsForRange('1M', points, intraday, NOW)).toEqual(points)
  })
})
