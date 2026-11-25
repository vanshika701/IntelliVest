import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Sector } from '../api/sectors'
import { HoldingsTable } from '../components/investments/HoldingsTable'
import { InvestmentsCard } from '../components/investments/InvestmentsCard'
import { SearchPage } from './SearchPage'
import { SectorPage } from './SectorPage'
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
  it('ranks sectors, each linking to its own page', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok([sector('a', 'Auto', 1), sector('b', 'Banking', 5)])))
    render(<MemoryRouter><SectorsPage /></MemoryRouter>)
    const links = await screen.findAllByRole('link', { name: /Load more/ })
    expect(links.map((l) => l.getAttribute('href'))).toEqual(['/sectors/b', '/sectors/a'])
  })

  it('shows every stock used and the sector news', async () => {
    const news = [{ url: 'https://x.test/1', title: 'Auto sales rise', source: 'S', published_at: '2026-11-24T00:00:00', label: 'positive' }]
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string) => ok(url.includes('/news') ? news : sector('a', 'Auto', 1))))
    render(<MemoryRouter initialEntries={['/sectors/a']}><Routes><Route path="/sectors/:id" element={<SectorPage />} /></Routes></MemoryRouter>)
    expect(await screen.findByRole('link', { name: 'Auto Co' })).toHaveAttribute('href', '/instrument/stock-a.NS')
    expect(await screen.findByRole('link', { name: /Auto sales rise/ })).toHaveAttribute('href', 'https://x.test/1')
  })

  it('explains when nothing has been computed', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok([])))
    render(<MemoryRouter><SectorsPage /></MemoryRouter>)
    expect(await screen.findByText(/hasn't been computed yet/)).toBeInTheDocument()
  })
})

describe('investments', () => {
  const holding = (id: string, gain: number | null, pct: number | null) => ({ instrument_id: id, instrument_name: id, instrument_type: 'MF' as const, invested: 100, current_value: gain === null ? null : 100 + gain, gain, gain_pct: pct })
  const portfolio = { invested: 300, current_value: 305, gain: 5, gain_pct: 1.67, unvalued_count: 1, holdings: [holding('Up', 10, 10), holding('Down', -5, -5), holding('Flat', 0, 0), holding('Unpriced', null, null)] }

  it('colours profit, loss and no change, and switches between % and ₹', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><HoldingsTable portfolio={portfolio} /></MemoryRouter>)
    expect(screen.getByText('+₹10.00 (+10.00%)')).toHaveClass('text-[var(--color-gains)]')
    expect(screen.getByText('−₹5.00 (-5.00%)')).toHaveClass('text-[var(--color-losses)]')
    expect(screen.getByText('₹0.00 (0.00%)')).toHaveClass('text-white')
    await user.click(screen.getByRole('button', { name: '%' }))
    expect(screen.getByText('-5.00%')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '₹' }))
    expect(screen.getByText('−₹5.00')).toBeInTheDocument()
  })

  it('summarises on the dashboard and links to the full page', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(portfolio)))
    render(<MemoryRouter><InvestmentsCard /></MemoryRouter>)
    expect(await screen.findByText('₹305.00')).toBeInTheDocument()
    expect(screen.queryByText('Unpriced')).not.toBeInTheDocument() // top three only
    expect(screen.getByRole('link', { name: /Load more/ })).toHaveAttribute('href', '/investments')
  })
})
