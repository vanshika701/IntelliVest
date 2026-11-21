import type { ReactNode } from 'react'
import { AlertCircle, Newspaper, RefreshCw } from 'lucide-react'
import type { InstrumentSentiment, SentimentLabel } from '../../api/instruments'
import { formatDate } from '../../lib/format'
import { cn } from '../../lib/utils'
import { Skeleton } from '../ui/Skeleton'

const LABEL_TEXT: Record<SentimentLabel, string> = { positive: 'Positive', negative: 'Negative', neutral: 'Neutral' }
const LABEL_STYLE: Record<SentimentLabel, string> = {
  positive: 'bg-[var(--color-gains-light)] text-[var(--color-gains)]',
  negative: 'bg-[var(--color-losses-light)] text-[var(--color-losses)]',
  neutral: 'bg-[var(--color-background-tertiary)] text-[var(--color-text-secondary)]',
}

export function SentimentBadge({ label, size = 'md' }: { label: SentimentLabel; size?: 'sm' | 'md' }) {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center rounded-full font-semibold',
        size === 'sm' ? 'px-2 py-0.5 text-[10px] uppercase tracking-wide' : 'px-2.5 py-1 text-xs',
        LABEL_STYLE[label],
      )}
    >
      {LABEL_TEXT[label]}
    </span>
  )
}

interface SentimentSectionProps {
  name: string
  sentiment: InstrumentSentiment | null
  loading: boolean
  error: string | null
  onRetry: () => void
  /** Rendered right below the sentiment headline (the news summaries). */
  children?: ReactNode
}

export function SentimentSection({ name, sentiment, loading, error, onRetry, children }: SentimentSectionProps) {
  return (
    <section aria-labelledby="sentiment-heading" className="glass-card rounded-2xl">
      <div className="flex items-center gap-2 border-b border-[var(--color-border-subtle)] p-5">
        <Newspaper className="h-5 w-5 text-[var(--color-text-secondary)]" aria-hidden="true" />
        <h3 id="sentiment-heading" className="text-base font-semibold text-[var(--color-text-primary)]">
          News &amp; sentiment
        </h3>
      </div>

      <div className="p-5">
        <div aria-live="polite" aria-busy={loading}>
          {loading ? (
            <div className="space-y-2">
              <Skeleton className="h-5 w-3/4" />
              <p className="text-xs text-[var(--color-text-muted)]">Reading recent headlines…</p>
            </div>
          ) : error ? (
            <div className="flex flex-wrap items-center gap-3 text-sm text-[var(--color-text-secondary)]">
              <AlertCircle className="h-4 w-4 text-[var(--color-losses)]" aria-hidden="true" />
              <span>Couldn't load news sentiment. {error}</span>
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-border-strong)] px-2.5 py-1 text-xs font-medium text-[var(--color-text-primary)] hover:bg-[var(--color-background-tertiary)]"
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" /> Retry
              </button>
            </div>
          ) : sentiment?.label ? (
            <p className="flex flex-wrap items-center gap-2 text-sm text-[var(--color-text-primary)]">
              <span>
                Current market sentiment for <span className="font-semibold">{name}</span>:
              </span>
              <SentimentBadge label={sentiment.label} />
            </p>
          ) : sentiment ? (
            <p className="text-sm text-[var(--color-text-secondary)]">
              Not enough news to determine sentiment
              <span className="text-[var(--color-text-muted)]">
                {' '}
                ({sentiment.article_count} headline{sentiment.article_count === 1 ? '' : 's'} in the last{' '}
                {sentiment.window_days} days; at least {sentiment.min_articles} needed).
              </span>
            </p>
          ) : null}
        </div>

        {children}

        {sentiment && sentiment.articles.length > 0 && (
          <details className="group mt-5 rounded-xl border border-[var(--color-border-subtle)]">
            <summary className="cursor-pointer select-none rounded-xl px-4 py-3 text-sm font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]">
              Headlines behind this sentiment ({sentiment.articles.length})
            </summary>
            <ul className="divide-y divide-[var(--color-border-subtle)] px-4 pb-3">
              {sentiment.articles.map((article) => (
                <li key={article.url} className="py-3">
                  <a
                    href={article.url}
                    target="_blank"
                    rel="noreferrer"
                    className="group/link flex items-start gap-3 rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="line-clamp-2 text-sm font-medium leading-snug text-[var(--color-text-primary)] group-hover/link:text-[var(--color-brand)]">
                        {article.title}
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
            <p className="px-4 pb-3 text-[11px] text-[var(--color-text-muted)]">
              Scored by {sentiment.engine === 'lexicon' ? 'a keyword lexicon (fallback)' : sentiment.engine} from
              headlines in the last {sentiment.window_days} days. Not investment advice.
            </p>
          </details>
        )}
      </div>
    </section>
  )
}
