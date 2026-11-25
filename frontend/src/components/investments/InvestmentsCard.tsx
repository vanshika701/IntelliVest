import { ArrowRight, PiggyBank } from 'lucide-react'
import { Link } from 'react-router-dom'
import { investmentsApi } from '../../api/investments'
import { useApi } from '../../hooks/useApi'
import { formatINR } from '../../lib/format'
import { Skeleton } from '../ui/Skeleton'
import { Gain } from './Gain'

/** Dashboard section: money invested, what it's worth now, biggest holdings. */
export function InvestmentsCard() {
  const { data, error, loading, reload } = useApi('portfolio', investmentsApi.portfolio)

  return (
    <section aria-labelledby="investments-heading" className="glass-card rounded-2xl">
      <div className="flex items-center gap-2 border-b border-[var(--color-border-subtle)] p-5">
        <PiggyBank className="h-5 w-5 text-[var(--color-text-secondary)]" aria-hidden="true" />
        <h3 id="investments-heading" className="text-base font-semibold text-[var(--color-text-primary)]">Investments</h3>
      </div>
      <div className="p-5">
        {loading ? (
          <Skeleton className="h-24 w-full" />
        ) : error || !data ? (
          <p className="text-sm text-[var(--color-text-muted)]">
            Couldn't load your investments. <button type="button" onClick={reload} className="text-[var(--color-brand)]">Retry</button>
          </p>
        ) : data.holdings.length === 0 ? (
          <p className="text-sm text-[var(--color-text-muted)]">Nothing invested yet. Search for a fund or stock to start.</p>
        ) : (
          <>
            <dl className="grid gap-4 sm:grid-cols-3">
              <div>
                <dt className="text-xs text-[var(--color-text-muted)]">Invested</dt>
                <dd className="mt-1 text-2xl font-bold text-[var(--color-text-primary)]">{formatINR(data.invested)}</dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--color-text-muted)]">Current value</dt>
                <dd className="mt-1 text-2xl font-bold text-[var(--color-text-primary)]">{formatINR(data.current_value)}</dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--color-text-muted)]">Total return</dt>
                <dd className="mt-1 text-2xl font-bold"><Gain gain={data.gain} pct={data.gain_pct} /></dd>
              </div>
            </dl>
            <ul className="mt-4 divide-y divide-[var(--color-border-subtle)] border-t border-[var(--color-border-subtle)]">
              {data.holdings.slice(0, 3).map((h) => (
                <li key={h.instrument_id} className="flex items-center justify-between gap-4 py-3 text-sm">
                  <Link to={`/instrument/${encodeURIComponent(h.instrument_id)}`} className="min-w-0 truncate text-[var(--color-text-primary)] hover:text-[var(--color-brand)]">{h.instrument_name}</Link>
                  <Gain gain={h.gain} pct={h.gain_pct} className="shrink-0 font-medium" />
                </li>
              ))}
            </ul>
            {data.unvalued_count > 0 && <p className="mt-2 text-xs text-[var(--color-text-muted)]">{data.unvalued_count} without a current price left out of the totals.</p>}
          </>
        )}
      </div>
      <Link to="/investments" className="flex items-center justify-center gap-1 border-t border-[var(--color-border-subtle)] p-3 text-sm font-medium text-[var(--color-brand)] hover:text-[var(--color-brand-hover)]">
        Load more <ArrowRight className="h-4 w-4" aria-hidden="true" />
      </Link>
    </section>
  )
}
