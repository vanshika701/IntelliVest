import { Layers } from 'lucide-react'
import { sectorsApi } from '../api/sectors'
import { useApi } from '../hooks/useApi'
import { formatDate } from '../lib/format'
import { SentimentBadge } from './instrument/SentimentSection'
import { Skeleton } from './ui/Skeleton'

/** Recent sector headlines; `excludeTicker` hides stories its own page shows. */
export function SectorNews({ sector, name, excludeTicker, limit = 8 }: { sector: string; name: string; excludeTicker?: string; limit?: number }) {
  const { data, error, loading, reload } = useApi(`${sector}|${excludeTicker ?? ''}`, () => sectorsApi.news(sector, { excludeTicker, limit }))
  return (
    <section aria-labelledby="sector-news-heading" className="glass-card rounded-2xl">
      <div className="flex items-center gap-2 border-b border-[var(--color-border-subtle)] p-5">
        <Layers className="h-5 w-5 text-[var(--color-text-secondary)]" aria-hidden="true" />
        <h3 id="sector-news-heading" className="text-base font-semibold text-[var(--color-text-primary)]">{name} sector news</h3>
      </div>
      <div className="px-5 py-2">
        {loading ? (
          <Skeleton className="my-3 h-24 w-full" />
        ) : error || !data ? (
          <p className="py-3 text-sm text-[var(--color-text-muted)]">
            Couldn't load sector news. <button type="button" onClick={reload} className="text-[var(--color-brand)]">Retry</button>
          </p>
        ) : data.length === 0 ? (
          <p className="py-3 text-sm text-[var(--color-text-muted)]">No sector news in the last 7 days.</p>
        ) : (
          <ul className="divide-y divide-[var(--color-border-subtle)]">
            {data.map((article) => (
              <li key={article.url} className="py-3">
                <a href={article.url} target="_blank" rel="noreferrer" className="group flex items-start gap-3">
                  <span className="min-w-0 flex-1">
                    <span className="line-clamp-2 text-sm font-medium text-[var(--color-text-primary)] group-hover:text-[var(--color-brand)]">
                      {article.title}
                      <span className="sr-only"> (opens in a new tab)</span>
                    </span>
                    <span className="mt-1 block text-xs text-[var(--color-text-muted)]">{article.source ?? 'Unknown source'} · {formatDate(article.published_at)}</span>
                  </span>
                  {article.label && <SentimentBadge label={article.label} size="sm" />}
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
