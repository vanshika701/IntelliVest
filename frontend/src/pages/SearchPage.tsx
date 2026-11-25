import { RefreshCw } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { instrumentsApi } from '../api/instruments'
import { Skeleton } from '../components/ui/Skeleton'
import { TypeTag } from '../components/ui/TypeTag'
import { useApi } from '../hooks/useApi'

const MIN_LENGTH = 2
const MAX_RESULTS = 25

/** Full list of matches, opened by pressing Enter in the navbar search. */
export function SearchPage() {
  const [params] = useSearchParams()
  const query = (params.get('q') ?? '').trim()
  const tooShort = query.length < MIN_LENGTH
  const { data, error, loading, reload } = useApi(tooShort ? null : `search:${query}`, () =>
    instrumentsApi.search(query, undefined, MAX_RESULTS),
  )

  if (tooShort) return <p className="text-sm text-[var(--color-text-muted)]">Type at least {MIN_LENGTH} characters in the search bar.</p>

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
        Results for “{query}”
        {data && <span className="ml-2 text-sm font-normal text-[var(--color-text-muted)]">{data.results.length}{data.results.length === MAX_RESULTS ? ' (top matches)' : ''}</span>}
      </h2>
      {data?.partial && <p className="text-xs text-[var(--color-text-muted)]">Fund results are temporarily unavailable; showing stocks only.</p>}

      {loading ? (
        <div className="space-y-2" aria-label="Searching">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16 w-full rounded-xl" />)}</div>
      ) : error ? (
        <div className="space-y-3">
          <p role="alert" className="text-sm text-[var(--color-losses)]">Search is unavailable right now.</p>
          <button type="button" onClick={reload} className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-border-strong)] px-3 py-1.5 text-sm text-[var(--color-text-primary)]">
            <RefreshCw className="h-4 w-4" aria-hidden /> Retry
          </button>
        </div>
      ) : data?.results.length === 0 ? (
        <p className="text-sm text-[var(--color-text-muted)]">No stocks, funds or ETFs match “{query}”.</p>
      ) : (
        <ul className="glass-card divide-y divide-[var(--color-border-subtle)] overflow-hidden rounded-2xl">
          {data?.results.map((r) => (
            <li key={r.id}>
              <Link to={`/instrument/${encodeURIComponent(r.id)}`} className="flex items-center gap-3 px-5 py-4 hover:bg-[var(--color-background-tertiary)]">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-[var(--color-text-primary)]">{r.name}</span>
                  {r.subtitle && <span className="block truncate text-xs text-[var(--color-text-muted)]">{r.subtitle}</span>}
                </span>
                <TypeTag type={r.type} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
