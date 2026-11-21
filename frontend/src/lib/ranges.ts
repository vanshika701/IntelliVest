// Chart range logic, kept free of React so it can be unit tested.
import { format, subDays, subMonths, subYears } from 'date-fns'
import type { PricePoint } from '../api/instruments'

export type RangeKey = '1D' | '1W' | '1M' | '3M' | '1Y' | 'YTD'
export const RANGES: RangeKey[] = ['1D', '1W', '1M', '3M', '1Y', 'YTD']
type DailyRange = Exclude<RangeKey, '1D'>

export const NO_INTRADAY_FOR_FUNDS =
  'Mutual funds and ETFs here publish one NAV per day, so there is no intraday chart.'

/** First day included in a daily range. YTD = 1 January of the current
 * year (local time); the others count back from `now`. */
export function getRangeStart(range: DailyRange, now: Date): Date {
  switch (range) {
    case '1W':
      return subDays(now, 7)
    case '1M':
      return subMonths(now, 1)
    case '3M':
      return subMonths(now, 3)
    case '1Y':
      return subYears(now, 1)
    case 'YTD':
      return new Date(now.getFullYear(), 0, 1)
  }
}

/** Daily points (t = 'YYYY-MM-DD') inside the range. Compared as date
 * strings so time zones can't shift a day in or out. */
export function filterDailyPoints(points: PricePoint[], range: DailyRange, now: Date): PricePoint[] {
  const start = format(getRangeStart(range, now), 'yyyy-MM-dd')
  return points.filter((p) => p.t >= start)
}

export interface RangeState {
  available: boolean
  reason?: string
}

/** A range is usable when it has at least two points to draw a line. */
export function getRangeAvailability(
  daily: PricePoint[],
  intraday: PricePoint[] | null,
  supportsIntraday: boolean,
  now: Date,
): Record<RangeKey, RangeState> {
  const result = {} as Record<RangeKey, RangeState>
  for (const range of RANGES) {
    if (range === '1D') {
      result[range] = !supportsIntraday
        ? { available: false, reason: NO_INTRADAY_FOR_FUNDS }
        : (intraday?.length ?? 0) >= 2
          ? { available: true }
          : { available: false, reason: 'No intraday prices for the last trading session.' }
      continue
    }
    result[range] =
      filterDailyPoints(daily, range, now).length >= 2
        ? { available: true }
        : { available: false, reason: 'Not enough price history for this range yet.' }
  }
  return result
}

const DEFAULT_ORDER: RangeKey[] = ['1M', '3M', '1Y', 'YTD', '1W', '1D']

export function pickDefaultRange(availability: Record<RangeKey, RangeState>): RangeKey | null {
  return DEFAULT_ORDER.find((r) => availability[r].available) ?? null
}

export function pointsForRange(
  range: RangeKey,
  daily: PricePoint[],
  intraday: PricePoint[] | null,
  now: Date,
): PricePoint[] {
  return range === '1D' ? (intraday ?? []) : filterDailyPoints(daily, range, now)
}
