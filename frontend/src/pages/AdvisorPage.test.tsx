import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Advice, ModuleResult } from '../api/advisor'
import { moduleLabels } from '../lib/advisor'
import { AdvisorPage } from './AdvisorPage'

afterEach(() => vi.unstubAllGlobals())

const reply = (status: number, body: unknown) => ({ ok: status < 400, status, json: async () => body })

const module = (id: string, label: string, status: ModuleResult['status'], reason: string | null = null): ModuleResult => ({
  module: id, label, phase: 8, status, as_of: null, version: null, facts: [], reason, elapsed_ms: 2,
})

const ADVICE: Advice = {
  id: 'a1',
  actions: [
    { id: 'emergency_fund', priority: 20, severity: 'high', title: 'Build your emergency fund: ₹65,000 to go',
      detail: 'Aim for at least ₹1,05,000 first.', facts: ['Covers 1.1 months of essentials.'],
      contributors: ['budget'], link: '/budget' },
    { id: 'invest_per_plan', priority: 50, severity: 'low', title: 'Invest ₹10,000 a month',
      detail: 'Your plan: 45% stocks, 45% debt, 10% gold.', facts: [], contributors: ['risk_profile', 'portfolio_plan'],
      link: '/portfolio-plan' },
  ],
  setup: [{ module: 'goals', title: 'Add a goal', detail: 'So we can check it.', link: '/budget' }],
  modules: [
    module('budget', 'Budget health', 'ok'),
    module('risk_profile', 'Risk profile', 'ok'),
    module('portfolio_plan', 'Portfolio plan', 'stale', 'Based on data from 2026-10-01.'),
    module('predictions', 'Stock return ranges', 'unavailable', "Didn't respond within 5 seconds."),
  ],
  modules_used: ['budget', 'risk_profile', 'portfolio_plan'],
  modules_unavailable: ['predictions'],
  partial: true,
  summary: { text: '2 things to look at, most important first.', source: 'template' },
  version: 'advisor-v1',
  disclaimer: 'Educational guidance, not investment advice.',
  created_at: '2026-11-27T10:00:00',
}

function mockApi(overrides: Record<string, ReturnType<typeof reply>> = {}) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? 'GET'} ${new URL(url).pathname}`
    if (overrides[key]) return overrides[key]
    if (key === 'GET /api/v1/advisor/advice/latest') return reply(200, ADVICE)
    if (key === 'POST /api/v1/advisor/advice') return reply(201, ADVICE)
    throw new Error(`Unexpected request ${key}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const renderPage = () => render(<MemoryRouter><AdvisorPage /></MemoryRouter>)
const posts = (fetchMock: ReturnType<typeof vi.fn>) => fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')

describe('AdvisorPage', () => {
  it('shows saved advice in priority order with its sources', async () => {
    const fetchMock = mockApi()
    renderPage()
    const actions = await screen.findByRole('region', { name: 'Actions' })
    const titles = within(actions).getAllByRole('heading').map((h) => h.textContent)
    expect(titles).toEqual(['Build your emergency fund: ₹65,000 to go', 'Invest ₹10,000 a month'])
    expect(within(actions).getByText('1. Do first')).toBeInTheDocument()
    expect(within(actions).getAllByRole('link', { name: /Open/ })[0]).toHaveAttribute('href', '/budget')
    expect(within(actions).getByText('Portfolio plan')).toBeInTheDocument() // chip from module label
    expect(screen.getByText('Covers 1.1 months of essentials.')).toBeInTheDocument()
    expect(posts(fetchMock)).toHaveLength(0) // saved advice is shown, not rebuilt
  })

  it('reports partial advice and each module status', async () => {
    mockApi()
    renderPage()
    expect(await screen.findByText(/Some information couldn't be loaded \(Stock return ranges\)/)).toBeInTheDocument()
    const panel = screen.getByRole('region', { name: 'What the advisor looked at' })
    expect(within(panel).getByText('Old data')).toBeInTheDocument()
    expect(within(panel).getByText("Didn't respond within 5 seconds.")).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Go' })).toHaveAttribute('href', '/budget')
    expect(screen.getByText(/not investment advice/)).toBeInTheDocument()
  })

  it('builds advice automatically on the first visit', async () => {
    const fetchMock = mockApi({ 'GET /api/v1/advisor/advice/latest': reply(404, { detail: 'No advice yet.' }) })
    renderPage()
    expect(await screen.findByText('2 things to look at, most important first.')).toBeInTheDocument()
    expect(posts(fetchMock)).toHaveLength(1)
  })

  it('updates on request and shows a rate-limit message', async () => {
    const fetchMock = mockApi({ 'POST /api/v1/advisor/advice': reply(429, { detail: 'Too many advice requests; try again shortly.' }) })
    renderPage()
    await userEvent.setup().click(await screen.findByRole('button', { name: /Update advice/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Too many advice requests')
    expect(posts(fetchMock)).toHaveLength(1)
    expect(screen.getByRole('heading', { name: 'Your next steps' })).toBeInTheDocument() // old advice stays
  })

  it('marks AI-worded summaries', async () => {
    mockApi({ 'GET /api/v1/advisor/advice/latest': reply(200, { ...ADVICE, summary: { text: 'Start with savings.', source: 'llm' } }) })
    renderPage()
    expect(await screen.findByText(/Worded by an AI model/)).toBeInTheDocument()
  })

  it('maps module ids to labels', () => {
    expect(moduleLabels(ADVICE.modules)).toMatchObject({ budget: 'Budget health', predictions: 'Stock return ranges' })
  })
})
