import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { BudgetMeta, Transaction } from '../../api/budget'
import { BudgetingPage } from '../../pages/BudgetingPage'
import { BudgetSetup } from './BudgetSetup'
import { GoalsPanel } from './GoalsPanel'
import { HealthScoreCard } from './HealthScoreCard'
import { TransactionModal } from './TransactionModal'

const META = {
  categories: [
    { id: 'groceries', name: 'Groceries', bucket: 'needs', min_pct: 8, max_pct: 12, note: null },
    { id: 'other', name: 'Other', bucket: 'wants', min_pct: null, max_pct: null, note: null },
  ],
  income_groups: [
    { id: 'job', name: 'Job', sources: [{ id: 'salary', name: 'Salary' }, { id: 'bonus', name: 'Bonus' }] },
    { id: 'investments', name: 'Investments', sources: [{ id: 'dividends', name: 'Dividends' }] },
    { id: 'other', name: 'Other', sources: [{ id: 'freelance', name: 'Freelance' }] },
  ],
  bucket_targets_pct: { needs: 50, wants: 30, savings: 20 },
  emergency_fund_months: [3, 6],
  return_assumptions: [{ max_months: null, annual_return_pct: 11, label: 'equity' }],
  default_step_up_pct: 10,
  actual_window_months: 3,
  llm_explanations: false,
  disclaimer: 'Illustrative only.',
} as BudgetMeta

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body })
const calls = (mock: ReturnType<typeof vi.fn>, method: string) =>
  mock.mock.calls.filter(([, init]) => init?.method === method).map(([url, init]) => ({ url: String(url), body: JSON.parse(init.body) }))

afterEach(() => vi.unstubAllGlobals())

describe('TransactionModal', () => {
  it('logs income with a group and a specific source', async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok({}))
    vi.stubGlobal('fetch', fetchMock)
    const onSaved = vi.fn()
    const user = userEvent.setup()
    render(<TransactionModal meta={META} initial={null} onClose={() => {}} onSaved={onSaved} />)

    await user.click(screen.getByRole('button', { name: 'Income' }))
    expect(screen.getByRole('option', { name: 'Salary' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Investments' }))
    expect(screen.queryByRole('option', { name: 'Salary' })).not.toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Type of income'), 'dividends')
    await user.type(screen.getByLabelText('Amount (₹)'), '500')
    await user.type(screen.getByLabelText('Description'), 'TCS')
    await user.click(screen.getByRole('button', { name: 'Save log' }))

    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    expect(calls(fetchMock, 'POST')[0].body).toEqual({ amount: 500, description: 'TCS', income_source: 'dividends', expense_type: 'income' })
  })

  it('edits an expense category', async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok({}))
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    const tx: Transaction = { id: 'e1', amount: 20, description: 'Milk', category: 'other', expense_type: 'expense', income_source: null, date: '2026-11-01' }
    render(<TransactionModal meta={META} initial={tx} onClose={() => {}} onSaved={() => {}} />)
    await user.selectOptions(screen.getByLabelText('Category'), 'groceries')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    const [patch] = calls(fetchMock, 'PATCH')
    expect(patch.url).toContain('/expenses/e1')
    expect(patch.body.category).toBe('groceries')
  })
})

describe('HealthScoreCard', () => {
  it('shows the score, or why there is none', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ score: 70, band: 'Fair', complete: false, message: null, components: [{ id: 'emergency', name: 'Emergency fund', score: null, weight: 25, detail: 'Add it.' }] })))
    const { unmount } = render(<MemoryRouter><HealthScoreCard /></MemoryRouter>)
    expect(await screen.findByText('70')).toBeInTheDocument()
    expect(screen.getByText('Fair')).toBeInTheDocument()
    unmount()

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ score: null, band: null, complete: false, components: [], message: 'Set up your budget.' })))
    render(<MemoryRouter><HealthScoreCard /></MemoryRouter>)
    expect(await screen.findByText(/Set up your budget/)).toBeInTheDocument()
  })
})

describe('BudgetingPage', () => {
  it('shows an error with a retry instead of loading forever', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('network down'))
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    render(<MemoryRouter><BudgetingPage /></MemoryRouter>)
    expect(await screen.findByRole('alert')).toHaveTextContent('network down')
    const before = fetchMock.mock.calls.length
    await user.click(screen.getByRole('button', { name: /Retry/ }))
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(before))
  })
})

describe('BudgetSetup', () => {
  it('requires income before moving on', async () => {
    const user = userEvent.setup()
    render(<BudgetSetup meta={META} initial={null} onClose={() => {}} onSaved={() => {}} />)
    await user.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Required')
  })

  it('only takes numbers for income', async () => {
    const user = userEvent.setup()
    render(<BudgetSetup meta={META} initial={null} onClose={() => {}} onSaved={() => {}} />)
    const income = screen.getByLabelText(/income/i)
    await user.type(income, 'abc8-0e0.505x')
    expect(income).toHaveValue('800.50')
  })
})

describe('GoalsPanel', () => {
  it('edits a saved goal', async () => {
    const plan = {
      name: 'Car', target_amount: 800000, horizon_months: 30, horizon_text: '2y 6m',
      assumption: { annual_return_pct: 7, is_default: true, label: 'debt', step_up_pct: 10, contribution_timing: 'start of each month' },
      flat: { monthly: 1, total_invested: 1, estimated_gains: 1 },
      step_up: { start_monthly: 1, final_monthly: 1, schedule: [], total_invested: 1, estimated_gains: 1 },
      affordability: { status: 'unknown', monthly_surplus: null, message: 'm', options: [] },
      summary: 'Summary', notes: [], disclaimer: 'd',
    }
    const goal = { id: 'g1', name: 'Car', target_amount: 800000, horizon_months: 30, annual_return_pct: null, step_up_pct: 10, created_at: '2026-11-01', plan }
    const fetchMock = vi.fn().mockImplementation(async (url: string) => ok(String(url).includes('preview') ? plan : { items: [goal], combined: null, disclaimer: 'd' }))
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    render(<GoalsPanel meta={META} refreshKey={0} />)

    await user.click(await screen.findByRole('button', { name: 'Edit Car' }))
    const name = screen.getByLabelText('Goal')
    expect(name).toHaveValue('Car')
    await user.clear(name)
    await user.type(name, 'Bike')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(calls(fetchMock, 'PUT')).toHaveLength(1))
    const [put] = calls(fetchMock, 'PUT')
    expect(put.url).toContain('/goals/g1')
    expect(put.body).toMatchObject({ name: 'Bike', horizon_months: 30, annual_return_pct: null })
  })
})
