import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { NewsSummaries as NewsSummariesData, NewsSummaryItem } from '../../api/instruments'
import { NewsSummaries } from './NewsSummaries'

function item(overrides: Partial<NewsSummaryItem>): NewsSummaryItem {
  return {
    title: 'Infosys wins $1.5 billion deal',
    url: `https://example.com/${Math.random()}`,
    source: 'Mint',
    published_at: '2026-11-20T10:00:00Z',
    summary: 'Infosys signed a large deal with a European bank. Shares rose 2%.',
    word_count: 12,
    input_kind: 'full_text',
    used_fallback: false,
    summary_failed: false,
    ...overrides,
  }
}

function data(items: NewsSummaryItem[]): NewsSummariesData {
  return {
    instrument_id: 'stock-INFY.NS',
    provider: 'extractive',
    method: 'tfidf-extractive@1.0.0',
    max_words: 100,
    items,
    generated_at: '2026-11-21T10:00:00Z',
  }
}

describe('NewsSummaries', () => {
  it('renders cards with headline link, source, date, summary and the Auto-summary label', () => {
    render(<NewsSummaries data={data([item({ url: 'https://example.com/a' })])} loading={false} error={null} onRetry={() => {}} />)

    expect(screen.getByText('Auto-summary')).toBeInTheDocument()
    expect(screen.queryByText(/AI-generated/i)).not.toBeInTheDocument()
    const link = screen.getByRole('link', { name: /Infosys wins \$1.5 billion deal/ })
    expect(link).toHaveAttribute('href', 'https://example.com/a')
    expect(link).toHaveAttribute('target', '_blank')
    expect(screen.getByText(/Mint · 20 Nov 2026/)).toBeInTheDocument()
    expect(screen.getByText(/signed a large deal/)).toBeInTheDocument()
  })

  it('explains snippet, headline-only and failed fallbacks', () => {
    render(
      <NewsSummaries
        data={data([
          item({ input_kind: 'snippet', used_fallback: true }),
          item({ title: 'Headline only story', summary: 'Headline only story', input_kind: 'headline', used_fallback: true }),
          item({ title: 'Broken story', summary: 'Broken story', summary_failed: true }),
        ])}
        loading={false}
        error={null}
        onRetry={() => {}}
      />,
    )
    expect(screen.getByText(/Summarised from the article snippet/)).toBeInTheDocument()
    expect(screen.getByText(/Only the headline was available/)).toBeInTheDocument()
    expect(screen.getByText(/Summary unavailable/)).toBeInTheDocument()
    // A summary identical to the headline isn't repeated under it.
    expect(screen.getAllByText('Headline only story')).toHaveLength(1)
  })

  it('shows the empty state', () => {
    render(<NewsSummaries data={data([])} loading={false} error={null} onRetry={() => {}} />)
    expect(screen.getByText('No recent news found.')).toBeInTheDocument()
  })

  it('shows skeletons while loading', () => {
    render(<NewsSummaries data={undefined} loading error={null} onRetry={() => {}} />)
    expect(screen.getByRole('list', { name: 'Loading summaries' })).toBeInTheDocument()
  })

  it('offers a retry on error', async () => {
    const onRetry = vi.fn()
    render(<NewsSummaries data={undefined} loading={false} error="Server error" onRetry={onRetry} />)
    await userEvent.click(screen.getByRole('button', { name: /Retry/ }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
