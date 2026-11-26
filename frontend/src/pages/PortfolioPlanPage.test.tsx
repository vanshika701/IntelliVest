import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Questionnaire, Recommendation, RiskProfile } from '../api/portfolioPlan'
import { formatFraction, formatHorizon, validatePlanForm, yearsToMonths } from '../lib/portfolioPlan'
import { PortfolioPlanPage } from './PortfolioPlanPage'

afterEach(() => vi.unstubAllGlobals())

const reply = (status: number, body: unknown) => ({ ok: status < 400, status, json: async () => body })

const QUESTIONS: Questionnaire = {
  version: 'risk-v1',
  questions: [
    { id: 'horizon', dimension: 'capacity', text: 'When will you need it?', options: [{ id: 'short', label: 'Soon' }, { id: 'long', label: 'Later' }] },
    { id: 'drop', dimension: 'tolerance', text: 'Markets fall 20%?', options: [{ id: 'sell', label: 'Sell' }, { id: 'hold', label: 'Hold' }] },
  ],
  profiles: [],
}

const PROFILE: RiskProfile = {
  profile: 'moderate', label: 'Moderate', description: 'A balance.', capacity_score: 62.5, tolerance_score: 50,
  limited_by: 'tolerance', caps_applied: [], notes: [], version: 'risk-v1',
  answers: { horizon: 'long', drop: 'hold' }, updated_at: '2026-11-26T00:00:00',
}

const REC: Recommendation = {
  id: 'r1',
  inputs: { lump_sum: 100000, monthly_sip: 0, horizon_months: 84, goal: null },
  profile: { profile: 'moderate', label: 'Moderate', capacity_score: 62.5, tolerance_score: 50, limited_by: 'tolerance' },
  allocation: { profile: 'moderate', horizon_months: 84, equity_pct: 45, debt_pct: 45, gold_pct: 10, debt_style: 'medium_duration',
    base: { equity_pct: 45, debt_pct: 45, gold_pct: 10 }, base_is_sourced: true, adjustments: [], version: 'alloc-v1' },
  holdings: [
    { asset_class: 'equity', instrument_id: 'stock-TCS.NS', name: 'Tata Consultancy Services', kind: 'stock', sector: 'it', weight: 0.45,
      weight_in_class: 1, lump_sum_amount: 45000, monthly_amount: 0, already_held_value: 2000,
      reasons: ['One of the calmer stocks.'], warnings: ['The monthly amount (₹200) is less than one share (₹2,460).'] },
    { asset_class: 'debt', instrument_id: 'mf-118987', name: 'HDFC Corporate Bond Fund', kind: 'fund', fund_role: 'medium_duration',
      weight: 0.45, weight_in_class: 1, lump_sum_amount: 45000, monthly_amount: 0, already_held_value: null, reasons: ['Corporate bond fund.'], warnings: [] },
    { asset_class: 'gold', instrument_id: null, name: 'Gold fund of funds (no fund available right now)', kind: 'fund', fund_role: 'gold',
      weight: 0.1, weight_in_class: 1, lump_sum_amount: 10000, monthly_amount: 0, already_held_value: null, reasons: ['No listed fund passed.'], warnings: [] },
  ],
  risk: { class_volatility: { equity: 0.12, debt: 0.02, gold: 0.3 }, volatility_upper_bound: 0.093, bad_year_loss: -0.1535,
    explanation: 'Volatility is how much it swings.', missing: [] },
  equity_comparison: null,
  not_held: [{ instrument_id: 'mf-999', name: 'Old Fund', current_value: 5000 }],
  notes: ['News sentiment wasn\'t used.'],
  versions: { market_stats_as_of: '2026-11-22T00:00:00' },
  disclaimer: 'Educational illustration, not investment advice.',
  created_at: '2026-11-26T10:00:00',
}

/** Route fetch calls by URL; `overrides` replace the default replies. */
function mockApi(overrides: Record<string, ReturnType<typeof reply>> = {}) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? 'GET'} ${new URL(url).pathname}`
    if (overrides[key]) return overrides[key]
    if (key === 'GET /api/v1/risk-profile/questions') return reply(200, QUESTIONS)
    if (key === 'GET /api/v1/risk-profile') return reply(404, { detail: 'Answer the risk questionnaire first.' })
    if (key === 'GET /api/v1/recommendations/latest') return reply(404, { detail: 'No recommendation yet.' })
    if (key === 'GET /api/v1/budget/goals') return reply(200, { items: [], combined: null, disclaimer: '' })
    throw new Error(`Unexpected request ${key}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const renderPage = () => render(<MemoryRouter><PortfolioPlanPage /></MemoryRouter>)

describe('portfolio plan helpers', () => {
  it('formats and converts', () => {
    expect(formatFraction(0.1234)).toBe('12.3%')
    expect(formatFraction(null)).toBe('—')
    expect(formatHorizon(18)).toBe('1 year 6 months')
    expect(formatHorizon(24)).toBe('2 years')
    expect(yearsToMonths('1.5')).toBe(18)
    expect(yearsToMonths('0.01')).toBe(1)
  })

  it('validates the plan form', () => {
    const base = { mode: 'horizon' as const, years: '7', goalId: '', lumpSum: '1000', monthly: '' }
    expect(validatePlanForm(base)).toEqual({})
    expect(validatePlanForm({ ...base, years: '' }).years).toMatch(/Enter/)
    expect(validatePlanForm({ ...base, years: '0' }).years).toMatch(/above 0/)
    expect(validatePlanForm({ ...base, years: '51' }).years).toMatch(/at most 50/)
    expect(validatePlanForm({ ...base, lumpSum: '' }).amounts).toMatch(/one-time amount/)
    expect(validatePlanForm({ ...base, mode: 'goal' }).goalId).toBe('Choose a goal')
  })
})

describe('PortfolioPlanPage', () => {
  it('asks the questionnaire first and saves every answer', async () => {
    const fetchMock = mockApi({ 'PUT /api/v1/risk-profile': reply(200, PROFILE) })
    renderPage()
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'See my profile' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Answer every question (2 left)')

    await user.click(screen.getByLabelText('Later'))
    await user.click(screen.getByLabelText('Hold'))
    await user.click(screen.getByRole('button', { name: 'See my profile' }))

    expect(await screen.findByRole('heading', { name: 'Moderate' })).toBeInTheDocument()
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT')!
    expect(JSON.parse(put[1]!.body as string)).toEqual({ answers: { horizon: 'long', drop: 'hold' } })
  })

  it('builds a plan and shows holdings, warnings and risk', async () => {
    const fetchMock = mockApi({
      'GET /api/v1/risk-profile': reply(200, PROFILE),
      'POST /api/v1/recommendations': reply(201, REC),
    })
    renderPage()
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Build plan' }))
    expect(screen.getByText(/Enter a one-time amount/)).toBeInTheDocument()

    await user.type(screen.getByLabelText('One-time amount (₹)'), '100000')
    await user.click(screen.getByRole('button', { name: 'Build plan' }))

    expect(await screen.findByRole('heading', { name: /Plan for 7 years/ })).toBeInTheDocument()
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')!
    expect(JSON.parse(post[1]!.body as string)).toEqual({ horizon_months: 84, lump_sum: 100000, monthly_sip: 0, use_sentiment: true })

    expect(screen.getByRole('link', { name: 'Tata Consultancy Services' })).toHaveAttribute('href', '/instrument/stock-TCS.NS')
    expect(screen.getByText(/less than one share/)).toBeInTheDocument()
    expect(screen.getByText(/You already hold ₹2,000/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Gold fund of funds/ })).not.toBeInTheDocument()
    expect(screen.getByText('9.3%')).toBeInTheDocument()
    expect(screen.getByText('-15.3%')).toBeInTheDocument()
    expect(within(screen.getByRole('list', { name: 'Asset split' })).getAllByRole('listitem')).toHaveLength(3)
    expect(screen.getByRole('link', { name: 'Old Fund' })).toBeInTheDocument()
    expect(screen.getByText(/not investment advice/)).toBeInTheDocument()
  })

  it('shows the latest saved plan and server errors', async () => {
    mockApi({
      'GET /api/v1/risk-profile': reply(200, PROFILE),
      'GET /api/v1/recommendations/latest': reply(200, REC),
      'POST /api/v1/recommendations': reply(409, { detail: "Market statistics haven't been computed yet." }),
    })
    renderPage()
    const user = userEvent.setup()
    expect(await screen.findByRole('heading', { name: /Plan for 7 years/ })).toBeInTheDocument()

    await user.type(screen.getByLabelText('Monthly amount (₹)'), '5000')
    await user.click(screen.getByRole('button', { name: 'Build plan' }))
    expect(await screen.findByText(/Market statistics haven't been computed yet/)).toBeInTheDocument()
  })

  it('reports a failed load with a retry', async () => {
    mockApi({ 'GET /api/v1/risk-profile': reply(500, { detail: 'Database down' }) })
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('Database down')
    expect(screen.getByRole('button', { name: /Retry/ })).toBeInTheDocument()
  })
})
