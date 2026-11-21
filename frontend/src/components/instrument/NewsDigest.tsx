import { AlertCircle, RefreshCw } from 'lucide-react'
import type { NewsDigest as NewsDigestData } from '../../api/instruments'
import { formatDate } from '../../lib/format'
import { Skeleton } from '../ui/Skeleton'
import { SentimentBadge } from './SentimentSection'

interface NewsDigestProps {
  data: NewsDigestData | undefined
  loading: boolean
  error: string | null
  onRetry: () => void
}

/** One combined summary of the top stories, then the stories themselves.
 * Rendered directly beneath the overall sentiment line. */
export function NewsDigest({ data, loading, error, onRetry }: NewsDigestProps) {
  if (loading) {
    return (
      <div className="mt-4 space-y-4" aria-busy="true" aria-label="Loading news summary">
        <div className="space-y-2">
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-11/12" />
          <Skeleton className="h-3 w-4/5" />
        </div>
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="space-y-1.5">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-32" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="mt-4 flex flex-wrap items-center gap-3 text-sm text-[var(--color-text-secondary)]">
        <AlertCircle className="h-4 w-4 text-[var(--color-losses)]" aria-hidden="true" />
        <span>Couldn't load the news summary. {error}</span>
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-border-strong)] px-2.5 py-1 text-xs font-medium text-[var(--color-text-primary)] hover:bg-[var(--color-background-tertiary)]"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" /> Retry
        </button>
      </div>
    )
  }

  if (!data || data.articles.length === 0) {
    return <p className="mt-4 text-sm text-[var(--color-text-muted)]">No recent news found.</p>
  }

  const noFullText = data.sources.full_text === 0

  return (
    <div className="mt-4">
      <div className="rounded-xl bg-[var(--color-background-tertiary)]/40 p-4">
        <span className="mb-2 inline-block rounded-full bg-[var(--color-brand-light)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-brand)]">
          Auto-summary
        </span>
        {data.summary ? (
          <p className="text-sm leading-relaxed text-[var(--color-text-primary)]">{data.summary}</p>
        ) : (
          <p className="text-sm text-[var(--color-text-secondary)]">
            A summary isn't available right now — see the top stories below.
          </p>
        )}
        <p className="mt-2 text-[11px] text-[var(--color-text-muted)]">
          Built from the top {data.articles.length} {data.articles.length === 1 ? 'story' : 'stories'} below
          {noFullText ? ' using their snippets and headlines (full articles weren’t available)' : ''}. Extracted
          automatically and may miss context — read the originals before acting on it.
        </p>
      </div>

      <h4 className="mb-1 mt-5 text-sm font-semibold text-[var(--color-text-primary)]">Top stories</h4>
      <ul className="divide-y divide-[var(--color-border-subtle)]">
        {data.articles.map((article) => (
          <li key={article.url} className="py-3">
            <a
              href={article.url}
              target="_blank"
              rel="noreferrer"
              className="group flex items-start gap-3 rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]"
            >
              <div className="min-w-0 flex-1">
                <p className="line-clamp-2 text-sm font-medium leading-snug text-[var(--color-text-primary)] group-hover:text-[var(--color-brand)]">
                  {article.title}
                  <span className="sr-only"> (opens in a new tab)</span>
                </p>
                <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                  {article.source ?? 'Unknown source'} · {formatDate(article.published_at)}
                </p>
              </div>
              <SentimentBadge label={article.label} size="sm" />
            </a>
          </li>
        ))}
      </ul>
    </div>
  )
}
