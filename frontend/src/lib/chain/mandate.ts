// Mandate form <-> the contract's Mandate struct. Pure, so it is unit tested.
// Amounts are tINR with 6 decimals; percentages become basis points (1% = 100).
import { formatUnits, parseUnits } from 'ethers'

export const DECIMALS = 6
export const FUNDS = ['tEquityFund', 'tDebtFund', 'tGoldFund'] as const
export type FundLabel = (typeof FUNDS)[number]

export const toUnits = (rupees: string | number) => parseUnits(String(rupees || 0), DECIMALS)
export const fromUnits = (units: bigint) => Number(formatUnits(units, DECIMALS))

export interface MandateForm {
  startDate: string // YYYY-MM-DD
  endDate: string
  perTradeCap: string
  dailyCap: string
  monthlyCap: string
  userSignAbove: string
  maxEquityPct: string
  maxSlippagePct: string
  maxLossPct: string
  maxTradesPerDay: string
  confidenceThresholdPct: string
  requireSentiment: boolean
  requireStock: boolean
  askUserOnNoData: boolean
  funds: FundLabel[]
}

export interface Mandate {
  start: bigint
  end: bigint
  perTradeCap: bigint
  dailyCap: bigint
  monthlyCap: bigint
  userSignAbove: bigint
  maxEquityBps: number
  maxSlippageBps: number
  maxLossBps: number
  maxTradesPerDay: number
  confidenceThreshold: number
  requireSentiment: boolean
  requireStock: boolean
  askUserOnNoData: boolean
}

const isoDate = (d: Date) => d.toISOString().slice(0, 10)

export function defaultMandateForm(today = new Date()): MandateForm {
  const end = new Date(today)
  end.setUTCFullYear(end.getUTCFullYear() + 1)
  return {
    startDate: isoDate(today),
    endDate: isoDate(end),
    perTradeCap: '5000',
    dailyCap: '10000',
    monthlyCap: '25000',
    userSignAbove: '5000',
    maxEquityPct: '60',
    maxSlippagePct: '1',
    maxLossPct: '10',
    maxTradesPerDay: '3',
    confidenceThresholdPct: '60',
    requireSentiment: true,
    requireStock: true,
    askUserOnNoData: true,
    funds: ['tEquityFund', 'tDebtFund'],
  }
}

/** Loss limit by risk profile; the user can change it. */
const LOSS_BY_PROFILE: Record<string, number> = {
  conservative: 5,
  moderately_conservative: 7,
  moderate: 10,
  moderately_aggressive: 12,
  aggressive: 15,
}

export interface Prefill {
  goal?: { name: string; monthly: number; horizonMonths: number } | null
  plan?: { profile: string; equityPct: number } | null
}

/** Suggested values from the user's goal (Phase 8) and portfolio plan
 * (Phase 7). Only suggestions: the user signs whatever they end up with. */
export function prefillMandate(base: MandateForm, { goal, plan }: Prefill, today = new Date()): MandateForm {
  const form = { ...base }
  if (goal && goal.monthly > 0) {
    const monthly = Math.ceil(goal.monthly)
    const end = new Date(today)
    end.setUTCMonth(end.getUTCMonth() + Math.max(1, goal.horizonMonths))
    form.monthlyCap = String(monthly)
    form.perTradeCap = String(monthly)
    form.dailyCap = String(monthly)
    form.userSignAbove = String(Math.ceil(monthly / 2))
    form.endDate = isoDate(end)
  }
  if (plan) {
    form.maxEquityPct = String(Math.round(plan.equityPct))
    form.maxLossPct = String(LOSS_BY_PROFILE[plan.profile] ?? 10)
  }
  return form
}

const pct = (v: string) => Math.round(Number(v) * 100)

export function validateMandate(form: MandateForm): Record<string, string> {
  const errors: Record<string, string> = {}
  const money = ['perTradeCap', 'dailyCap', 'monthlyCap', 'userSignAbove'] as const
  for (const key of money) {
    const v = Number(form[key])
    if (!Number.isFinite(v) || v < 0) errors[key] = 'Enter an amount of 0 or more'
  }
  if (!errors.perTradeCap && !errors.dailyCap && Number(form.perTradeCap) > Number(form.dailyCap))
    errors.perTradeCap = 'Per-trade cap cannot exceed the daily cap'
  if (!errors.dailyCap && !errors.monthlyCap && Number(form.dailyCap) > Number(form.monthlyCap))
    errors.dailyCap = 'Daily cap cannot exceed the monthly cap'
  for (const key of ['maxEquityPct', 'maxSlippagePct', 'maxLossPct', 'confidenceThresholdPct'] as const) {
    const v = Number(form[key])
    if (form[key] === '' || !Number.isFinite(v) || v < 0 || v > 100) errors[key] = 'Enter 0 to 100'
  }
  const trades = Number(form.maxTradesPerDay)
  if (!Number.isInteger(trades) || trades < 0 || trades > 1000) errors.maxTradesPerDay = 'Enter a whole number'
  if (!form.startDate || !form.endDate || form.endDate <= form.startDate)
    errors.endDate = 'End date must be after the start date'
  if (form.funds.length === 0) errors.funds = 'Allow at least one fund'
  return errors
}

export function toMandate(form: MandateForm): Mandate {
  const seconds = (date: string) => BigInt(Math.floor(Date.parse(`${date}T00:00:00Z`) / 1000))
  return {
    start: seconds(form.startDate),
    end: seconds(form.endDate) + 86_399n, // through the end date
    perTradeCap: toUnits(form.perTradeCap),
    dailyCap: toUnits(form.dailyCap),
    monthlyCap: toUnits(form.monthlyCap),
    userSignAbove: toUnits(form.userSignAbove),
    maxEquityBps: pct(form.maxEquityPct),
    maxSlippageBps: pct(form.maxSlippagePct),
    maxLossBps: pct(form.maxLossPct),
    maxTradesPerDay: Number(form.maxTradesPerDay),
    confidenceThreshold: pct(form.confidenceThresholdPct),
    requireSentiment: form.requireSentiment,
    requireStock: form.requireStock,
    askUserOnNoData: form.askUserOnNoData,
  }
}

/** The signed mandate back into form values, to show or edit it. */
export function fromMandate(m: Mandate, funds: FundLabel[]): MandateForm {
  const date = (s: bigint) => isoDate(new Date(Number(s) * 1000))
  const p = (bps: number) => String(Number(bps) / 100)
  return {
    startDate: date(m.start),
    endDate: date(m.end),
    perTradeCap: String(fromUnits(m.perTradeCap)),
    dailyCap: String(fromUnits(m.dailyCap)),
    monthlyCap: String(fromUnits(m.monthlyCap)),
    userSignAbove: String(fromUnits(m.userSignAbove)),
    maxEquityPct: p(m.maxEquityBps),
    maxSlippagePct: p(m.maxSlippageBps),
    maxLossPct: p(m.maxLossBps),
    maxTradesPerDay: String(m.maxTradesPerDay),
    confidenceThresholdPct: p(m.confidenceThreshold),
    requireSentiment: m.requireSentiment,
    requireStock: m.requireStock,
    askUserOnNoData: m.askUserOnNoData,
    funds,
  }
}
