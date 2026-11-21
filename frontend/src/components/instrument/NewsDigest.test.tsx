import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { DigestArticle, NewsDigest as NewsDigestData } from '../../api/instruments'
import { NewsDigest } from './NewsDigest'

function article(overrides: Partial<DigestArticle>): DigestArticle {
  return {
    title: 'Infosys wins $1.5 billion deal',
    url: `https://example.com/${Math.random()}`,
    source: 'Mint',
    published_at: '2026-11-20T10:00:00Z',
    input_kind: 'full_text',
    label: 'positive',
    score: 0.8,
    ...overrides,
  }
}

function digest(overrides: Partial<NewsDigestData> = {}): NewsDigestData {
  return {
    instrument_id: 'stock-INFY.NS',
    provider: 'extractive',
    method: 'tfidf-extractive@1.2.0',
    max_words: 100,
    summary: 'Infosys signed a large deal with a European bank. Shares slid 2.5% on Thursday.',
    word_count: 14,
    summary_failed: false,
    sources: { full_text: 1, snippet: 1, headline: 0 },
    sentiment_engine: 'ProsusAI/finbert',
    articles: [
      article({ url: 'https://example.com/a' }),
      article({ title: 'Infosys slides 2.5% intraday', source: 'BusinessLine', label: 'negative', input_kind: 'snippet' }),
    ],
    generated_at: '2026-11-21T10:00:00Z',
    ...overrides,
  }
}

describe('NewsDigest', () => {
  it('shows one combined summary, then the top stories with their sentiment tags', () => {
    render(<NewsDigest data={digest()} loading={false} error={null} onRetry={() => {}} />)

    expect(screen.getByText('Auto-summary')).toBeInTheDocument()
    expect(screen.queryByText(/AI-generated/i)).not.toBeInTheDocument()
    expect(screen.getByText(/signed a large deal/)).toBeInTheDocument()
    expect(screen.getByText(/Built from the top 2 stories below\./)).toBeInTheDocument()

    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(2)
    expect(links[0]).toHaveAttribute('href', 'https://example.com/a')
    expect(links[0]).toHaveAttribute('target', '_blank')
    expect(screen.getByText(/BusinessLine · 20 Nov 2026/)).toBeInTheDocument()
    expect(screen.getByText('Negative')).toBeInTheDocument()
    expect(screen.getByText('Positive')).toBeInTheDocument()
  })

  it('says when the summary only had snippets and headlines to work with', () => {
    render(<NewsDigest data={digest({ sources: { full_text: 0, snippet: 2, headline: 0 } })} loading={false} error={null} onRetry={() => {}} />)
    expect(screen.getByText(/full articles weren’t available/)).toBeInTheDocument()
  })

  it('keeps the story list when the summary itself failed', () => {
    render(<NewsDigest data={digest({ summary: null, summary_failed: true })} loading={false} error={null} onRetry={() => {}} />)
    expect(screen.getByText(/summary isn't available right now/)).toBeInTheDocument()
    expect(screen.getAllByRole('link')).toHaveLength(2)
  })

  it('shows the empty state', () => {
    render(<NewsDigest data={digest({ summary: null, articles: [] })} loading={false} error={null} onRetry={() => {}} />)
    expect(screen.getByText('No recent news found.')).toBeInTheDocument()
  })

  it('shows a skeleton while loading', () => {
    render(<NewsDigest data={undefined} loading error={null} onRetry={() => {}} />)
    expect(screen.getByLabelText('Loading news summary')).toHaveAttribute('aria-busy', 'true')
  })

  it('offers a retry on error', async () => {
    const onRetry = vi.fn()
    render(<NewsDigest data={undefined} loading={false} error="Server error" onRetry={onRetry} />)
    await userEvent.click(screen.getByRole('button', { name: /Retry/ }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
