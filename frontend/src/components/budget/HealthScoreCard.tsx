import { Link } from 'react-router-dom'
import { budgetApi } from '../../api/budget'
import { useApi } from '../../hooks/useApi'
import { Skeleton } from '../ui/Skeleton'

const BAND_COLOR: Record<string, string> = { Good: '#0ca30c', Fair: '#fab219', 'Needs attention': '#f43f5e' }

/** Dashboard card: the combined financial health score and what it's made of. */
export function HealthScoreCard() {
  const { data, error, loading, reload } = useApi('health-score', budgetApi.healthScore)

  return (
    <div className="glass-card p-6 rounded-2xl">
      <p className="text-sm font-medium text-[var(--color-text-secondary)] mb-1">Financial health</p>
      {loading ? (
        <Skeleton className="h-20 w-full" />
      ) : error || !data ? (
        <p className="text-sm text-[var(--color-text-muted)]">
          Couldn't load your score. <button type="button" onClick={reload} className="text-[var(--color-brand)]">Retry</button>
        </p>
      ) : data.score === null ? (
        <p className="text-sm text-[var(--color-text-muted)] mt-3">
          {data.message} <Link to="/budget" className="text-[var(--color-brand)]">Go to budgeting</Link>
        </p>
      ) : (
        <>
          <div className="flex items-end gap-3">
            <h3 className="text-3xl font-bold tracking-tight text-[var(--color-text-primary)]">
              {data.score}<span className="text-base font-normal text-[var(--color-text-muted)]">/100</span>
            </h3>
            <span className="flex items-center gap-1.5 pb-1 text-sm text-[var(--color-text-secondary)]">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: BAND_COLOR[data.band ?? ''] }} aria-hidden /> {data.band}
            </span>
          </div>
          <details className="mt-3 text-xs">
            <summary className="cursor-pointer text-[var(--color-text-secondary)]">What's in this score</summary>
            <p className="mt-2 text-[var(--color-text-muted)]">Points show how much each part counts towards the score, not how much of your income it should take.</p>
            <ul className="mt-2 space-y-2">
              {data.components.map((c) => (
                <li key={c.id}>
                  <div className="flex justify-between text-[var(--color-text-primary)]">
                    <span>{c.name} <span className="text-[var(--color-text-muted)]">({c.weight} of 100 points)</span></span>
                    <span className="font-mono">{c.score ?? '—'}</span>
                  </div>
                  <p className="text-[var(--color-text-muted)]">{c.detail}</p>
                </li>
              ))}
            </ul>
            {!data.complete && <p className="mt-2 text-[var(--color-text-muted)]">Some parts couldn't be measured, so the rest count for more.</p>}
          </details>
        </>
      )}
    </div>
  )
}
