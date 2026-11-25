import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Sector } from '../api/sectors'
import { SearchPage } from './SearchPage'
import { SectorsPage } from './SectorsPage'

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body })
afterEach(() => vi.unstubAllGlobals())

function sector(id: string, name: string, month: number): Sector {
  const changes = { '1d': 0.5, '1w': null, '1m': month, '3m': null }
  return {
    sector: id, name, stock_count: 1, priced_count: 1, as_of: '2026-11-23T00:00:00', changes, trend: 'up', advancers: 1, decliners: 0,
    sentiment: { score: null, label: null, article_count: 0, label_counts: {}, window_days: 7 },
    series: [], computed_at: '2026-11-24T00:00:00',
    stocks: [{ ticker: `${id}.NS`, name: `${name} Co`, price: 10, changes, sentiment_score: null, sentiment_label: null, article_count: 0 }],
  }
}

describe('SearchPage', () => {
  it('lists every match as a link to its page', async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok({ query: 'gold', partial: false, results: [{ id: 'mf-1', name: 'Gold A', type: 'MF', symbol: '1', subtitle: null }, { id: 'mf-2', name: 'Gold B', type: 'ETF', symbol: '2', subtitle: null }] }))
    vi.stubGlobal('fetch', fetchMock)
    render(<MemoryRouter initialEntries={['/search?q=gold']}><SearchPage /></MemoryRouter>)
    expect(await screen.findByRole('link', { name: /Gold B/ })).toHaveAttribute('href', '/instrument/mf-2')
    expect(screen.getAllByRole('link')).toHaveLength(2)
    expect(fetchMock.mock.calls[0][0]).toContain('limit=25')
  })
})

describe('SectorsPage', () => {
  it('ranks sectors, and shows the selected sector’s stocks', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok([sector('a', 'Auto', 1), sector('b', 'Banking', 5)])))
    const user = userEvent.setup()
    render(<MemoryRouter><SectorsPage /></MemoryRouter>)
    expect(await screen.findByRole('link', { name: 'Banking Co' })).toHaveAttribute('href', '/instrument/stock-b.NS')
    await user.click(screen.getByRole('button', { name: /Auto/ }))
    expect(screen.getByRole('link', { name: 'Auto Co' })).toBeInTheDocument()
  })

  it('explains when nothing has been computed', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok([])))
    render(<MemoryRouter><SectorsPage /></MemoryRouter>)
    expect(await screen.findByText(/hasn't been computed yet/)).toBeInTheDocument()
  })
})
