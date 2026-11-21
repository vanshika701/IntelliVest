import { AlertCircle, ExternalLink, RefreshCw } from 'lucide-react'
import type { NewsSummaries as NewsSummariesData, NewsSummaryItem } from '../../api/instruments'
import { formatDate } from '../../lib/format'
import { Skeleton } from '../ui/Skeleton'

interface NewsSummariesProps {
  data: NewsSummariesData | undefined
  loading: boolean
  error: string | null
  onRetry: () => void
}

function fallbackNote(item: NewsSummaryItem): string | null {
  if (item.summary_failed) return 'Summary unavailable — showing the headline.'
  if (item.input_kind === 'snippet') return 'Summarised from the article snippet; full text was not available.'
  if (item.input_kind === 'headline') return 'Only the headline was available for this article.'
  return null
}

function SummaryCard({ item }: { item: NewsSummaryItem }) {
  const note = fallbackNote(item)
  const showSummary = item.summary && item.summary !== item.title
  return (
    <li className="rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-background-primary)]/40 p-4">
      <a
        href={item.url}
        target="_blank"
        rel="noreferrer"
        className="group inline-flex items-start gap-1.5 rounded text-sm font-semibold leading-snug text-[var(--color-text-primary)] hover:text-[var(--color-brand)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]"
      >
        {item.title}
        <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0 opacity-50 group-hover:opacity-100" aria-hidden="true" />
        <span className="sr-only">(opens the original article in a new tab)</span>
      </a>
      <p className="mt-1 text-xs text-[var(--color-text-muted)]">
        {item.source ?? 'Unknown source'} · {formatDate(item.published_at)}
      </p>
      {showSummary && (
        <p className="mt-2 text-sm leading-relaxed text-[var(--color-text-secondary)]">{item.summary}</p>
      )}
      {note && <p className="mt-2 text-[11px] italic text-[var(--color-text-muted)]">{note}</p>}
    </li>
  )
}

export function NewsSummaries({ data, loading, error, onRetry }: NewsSummariesProps) {
  return (
    <section aria-labelledby="news-summaries-heading" aria-busy={loading} className="mt-5">
      <div className="mb-3 flex items-center gap-2">
        <h4 id="news-summaries-heading" className="text-sm font-semibold text-[var(--color-text-primary)]">
          Top stories
        </h4>
        <span className="rounded-full bg-[var(--color-brand-light)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-brand)]">
          Auto-summary
        </span>
      </div>

      {loading ? (
        <ul className="space-y-3" aria-label="Loading summaries">
          {[0, 1, 2].map((i) => (
            <li key={i} className="space-y-2 rounded-xl border border-[var(--color-border-subtle)] p-4">
              <Skeleton className="h-4 w-4/5" />
              <Skeleton className="h-3 w-32" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-11/12" />
            </li>
          ))}
        </ul>
      ) : error ? (
        <div className="flex flex-wrap items-center gap-3 text-sm text-[var(--color-text-secondary)]">
          <AlertCircle className="h-4 w-4 text-[var(--color-losses)]" aria-hidden="true" />
          <span>Couldn't load news summaries. {error}</span>
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-border-strong)] px-2.5 py-1 text-xs font-medium text-[var(--color-text-primary)] hover:bg-[var(--color-background-tertiary)]"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" /> Retry
          </button>
        </div>
      ) : !data || data.items.length === 0 ? (
        <p className="text-sm text-[var(--color-text-muted)]">No recent news found.</p>
      ) : (
        <>
          <ul className="space-y-3">
            {data.items.map((item) => (
              <SummaryCard key={item.url} item={item} />
            ))}
          </ul>
          <p className="mt-3 text-[11px] text-[var(--color-text-muted)]">
            Summaries of up to {data.max_words} words are extracted automatically from each article's own sentences
            and may miss context. Read the original before acting on them.
          </p>
        </>
      )}
    </section>
  )
}
