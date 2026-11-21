// Return calculator maths. Deliberately formula-based, not ML: compounding
// is deterministic. Rates are annual percentages (12 = 12%).
import { differenceInCalendarDays, parseISO, subYears, format } from 'date-fns'
import type { PricePoint } from '../api/instruments'

export type InvestmentMode = 'one_time' | 'sip'

export const DEFAULT_ANNUAL_RETURN = 12
// CAGRs outside this band are treated as bad data (e.g. an unadjusted unit
// split in a NAV series) rather than shown as a default assumption.
export const PLAUSIBLE_CAGR_RANGE: [number, number] = [-50, 60]

/** SIP future value: FV = P × [((1 + i)^n − 1) / i] × (1 + i),
 * with i = annual rate / 12 and n = months (payments at the start of each month). */
export function sipFutureValue(monthlyAmount: number, annualRatePct: number, months: number): number {
  const i = annualRatePct / 100 / 12
  if (i === 0) return monthlyAmount * months
  return monthlyAmount * ((Math.pow(1 + i, months) - 1) / i) * (1 + i)
}

/** Lumpsum future value: FV = P × (1 + r)^t. */
export function lumpsumFutureValue(principal: number, annualRatePct: number, years: number): number {
  return principal * Math.pow(1 + annualRatePct / 100, years)
}

export interface ReturnEstimate {
  invested: number
  estimatedReturns: number
  totalValue: number
}

export function estimateReturns(
  mode: InvestmentMode,
  amount: number,
  years: number,
  annualRatePct: number,
): ReturnEstimate {
  const invested = mode === 'sip' ? amount * years * 12 : amount
  const totalValue =
    mode === 'sip' ? sipFutureValue(amount, annualRatePct, years * 12) : lumpsumFutureValue(amount, annualRatePct, years)
  return { invested, estimatedReturns: totalValue - invested, totalValue }
}

export interface ProjectionPoint {
  year: number
  invested: number
  value: number
}

/** Year-by-year invested vs. estimated value, for the calculator chart. */
export function projectionByYear(
  mode: InvestmentMode,
  amount: number,
  years: number,
  annualRatePct: number,
): ProjectionPoint[] {
  const points: ProjectionPoint[] = []
  for (let year = 0; year <= years; year++) {
    const e = estimateReturns(mode, amount, year, annualRatePct)
    points.push({ year, invested: Math.round(e.invested), value: Math.round(e.totalValue) })
  }
  return points
}

/** Historical CAGR (%) from daily points (t = 'YYYY-MM-DD', oldest first),
 * over the last `maxYears` (or all history if shorter). Null if there's
 * under a year of data or the result is implausible. */
export function computeCagr(points: PricePoint[], maxYears = 3): number | null {
  if (points.length < 2) return null
  const last = points[points.length - 1]
  const lastDate = parseISO(last.t)
  const windowStart = format(subYears(lastDate, maxYears), 'yyyy-MM-dd')
  const first = points.find((p) => p.t >= windowStart) ?? points[0]

  const days = differenceInCalendarDays(lastDate, parseISO(first.t))
  if (days < 365 || first.v <= 0 || last.v <= 0) return null

  const cagr = (Math.pow(last.v / first.v, 365.25 / days) - 1) * 100
  const [low, high] = PLAUSIBLE_CAGR_RANGE
  return cagr >= low && cagr <= high ? Math.round(cagr * 100) / 100 : null
}
