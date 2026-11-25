import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { GlobalSearch, SEARCH_DEBOUNCE_MS } from './GlobalSearch'

const GOLD_RESULTS = {
  query: 'gold',
  partial: false,
  results: [
    { id: 'mf-1', name: 'SBI GOLD FUND - Direct Plan - Growth', type: 'MF', symbol: '1', subtitle: 'Mutual fund scheme' },
    { id: 'mf-2', name: 'Edelweiss Gold ETF', type: 'ETF', symbol: '2', subtitle: 'Mutual fund scheme' },
  ],
}

function jsonResponse(body: unknown, ok = true) {
  return { ok, status: ok ? 200 : 502, json: async () => body }
}

function InstrumentStub() {
  const { id } = useParams()
  return <p>Instrument page {id}</p>
}

function SearchStub() {
  return <p>Search page {useLocation().search}</p>
}

function renderSearch() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <GlobalSearch />
      <Routes>
        <Route path="/" element={null} />
        <Route path="/instrument/:id" element={<InstrumentStub />} />
        <Route path="/search" element={<SearchStub />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('GlobalSearch', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('debounces typing into a single search request', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(GOLD_RESULTS))
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderSearch()

    await user.type(screen.getByRole('combobox'), 'gold')
    expect(fetchMock).not.toHaveBeenCalled()

    await act(async () => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS)
    })

    expect(await screen.findByText('Edelweiss Gold ETF')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toContain('/api/v1/instruments/search?q=gold')
    expect(screen.getByText('ETF')).toBeInTheDocument()
    expect(screen.getByText('MF')).toBeInTheDocument()
  })

  it('supports arrow keys and Enter to open a result', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(GOLD_RESULTS)))
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderSearch()

    const input = screen.getByRole('combobox')
    await user.type(input, 'gold')
    await act(async () => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS)
    })
    await screen.findByText('Edelweiss Gold ETF')

    const options = screen.getAllByRole('option')
    expect(options[0]).toHaveAttribute('aria-selected', 'false')
    await user.keyboard('{ArrowDown}{ArrowDown}')
    expect(screen.getAllByRole('option')[1]).toHaveAttribute('aria-selected', 'true')
    expect(input).toHaveAttribute('aria-activedescendant', screen.getAllByRole('option')[1].id)

    await user.keyboard('{Enter}')
    expect(await screen.findByText('Instrument page mf-2')).toBeInTheDocument()
  })

  it('lists all matches when Enter is pressed without choosing one, even while hovering', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(GOLD_RESULTS)))
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderSearch()

    await user.type(screen.getByRole('combobox'), 'gold')
    await act(async () => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS)
    })
    await user.hover(await screen.findByText('Edelweiss Gold ETF'))
    await user.keyboard('{Enter}')
    expect(await screen.findByText('Search page ?q=gold')).toBeInTheDocument()
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('lists matches when Enter is pressed before results arrive', async () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderSearch()
    await user.type(screen.getByRole('combobox'), 'sbi gold{Enter}')
    expect(await screen.findByText('Search page ?q=sbi%20gold')).toBeInTheDocument()
  })

  it('closes the dropdown on Escape', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(GOLD_RESULTS)))
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderSearch()

    await user.type(screen.getByRole('combobox'), 'gold')
    await act(async () => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS)
    })
    await screen.findByText('Edelweiss Gold ETF')

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(screen.getByRole('combobox')).toHaveAttribute('aria-expanded', 'false')
  })

  it('shows the empty state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ query: 'zzz', partial: false, results: [] })))
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderSearch()

    await user.type(screen.getByRole('combobox'), 'zzz')
    await act(async () => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS)
    })
    expect(await screen.findByText('No results for “zzz”')).toBeInTheDocument()
  })

  it('shows the error state when search fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'down' }, false)))
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderSearch()

    await user.type(screen.getByRole('combobox'), 'gold')
    await act(async () => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS)
    })
    expect(await screen.findByText(/Search is unavailable/)).toBeInTheDocument()
  })

  it('does not search for a single character', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderSearch()

    await user.type(screen.getByRole('combobox'), 'g')
    await act(async () => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS * 2)
    })
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByText('Type at least 2 characters')).toBeInTheDocument()
  })
})
