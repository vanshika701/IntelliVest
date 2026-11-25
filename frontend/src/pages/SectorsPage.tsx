import { useState } from 'react'
import { ArrowRight, Minus, RefreshCw, TrendingDown, TrendingUp } from 'lucide-react'
import { Link } from 'react-router-dom'
import { sectorsApi, type Sector, type SectorWindow } from '../api/sectors'
import { Skeleton } from '../components/ui/Skeleton'
import { useApi } from '../hooks/useApi'
import { formatDate, formatSignedPct } from '../lib/format'
import { changeColor, WINDOWS } from '../lib/sectorView'
import { cn } from '../lib/utils'

const TREND = {
  up: { Icon: TrendingUp, label: 'Rising' },
  down: { Icon: TrendingDown, label: 'Falling' },
  flat: { Icon: Minus, label: 'Flat' },
} as const

function Sparkline({ points }: { points: Sector['series'] }) {
  if (points.length < 2) return null
  const values = points.map((p) => p.v)
  const min = Math.min(...values)
  const span = Math.max(...values) - min || 1
  const path = values.map((v, i) => `${(i / (values.length - 1)) * 120},${30 - ((v - min) / span) * 28}`).join(' ')
  return (
    <svg viewBox="0 0 120 32" className="h-8 w-28" preserveAspectRatio="none" aria-hidden>
      <polyline points={path} fill="none" stroke="var(--color-brand)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

function SectorCard({ sector, window }: { sector: Sector; window: SectorWindow }) {
  const change = sector.changes[window]
  const trend = sector.trend ? TREND[sector.trend] : null
  return (
    <article className="glass-card flex flex-col rounded-2xl">
      <div className="flex-1 p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="font-semibold text-[var(--color-text-primary)]">{sector.name}</h3>
            <p className="text-xs text-[var(--color-text-muted)]">{sector.stock_count} stock{sector.stock_count === 1 ? '' : 's'}</p>
          </div>
          <Sparkline points={sector.series} />
        </div>
        <p className={cn('mt-3 text-2xl font-bold', changeColor(change))}>{formatSignedPct(change)}</p>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--color-text-secondary)]">
          {trend && <span className="inline-flex items-center gap-1"><trend.Icon className="h-3.5 w-3.5" aria-hidden /> {trend.label} (1 month)</span>}
          <span className="capitalize">{sector.sentiment.label ? `${sector.sentiment.label} news` : 'Not enough news'}</span>
        </div>
      </div>
      <Link
        to={`/sectors/${sector.sector}`}
        aria-label={`Load more about ${sector.name}`}
        className="flex items-center justify-center gap-1 border-t border-[var(--color-border-subtle)] p-3 text-sm font-medium text-[var(--color-brand)] hover:text-[var(--color-brand-hover)]"
      >
        Load more <ArrowRight className="h-4 w-4" aria-hidden />
      </Link>
    </article>
  )
}

/** Phase 6: sector-level price trend and news sentiment. */
export function SectorsPage() {
  const { data, error, loading, reload } = useApi('sectors', sectorsApi.list)
  const [window, setWindow] = useState<SectorWindow>('1m')

  if (loading) return <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-label="Loading sectors">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-36 rounded-2xl" />)}</div>
  if (error || !data)
    return (
      <div className="space-y-3">
        <p role="alert" className="text-sm text-[var(--color-losses)]">Sector data couldn't be loaded. {error}</p>
        <button type="button" onClick={reload} className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-border-strong)] px-3 py-1.5 text-sm text-[var(--color-text-primary)]"><RefreshCw className="h-4 w-4" aria-hidden /> Retry</button>
      </div>
    )
  if (data.length === 0) return <p className="text-sm text-[var(--color-text-muted)]">Sector data hasn't been computed yet. It appears after the next price or news update.</p>

  const sorted = [...data].sort((a, b) => (b.changes[window] ?? -Infinity) - (a.changes[window] ?? -Infinity))
  const asOf = data.map((s) => s.as_of).filter((d): d is string => d !== null).sort().at(-1)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-[var(--color-text-muted)]">Prices up to {formatDate(asOf)}. Averages of the tracked stocks, each weighted equally.</p>
        <div role="group" aria-label="Change period" className="flex gap-1 rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-background-secondary)] p-1">
          {WINDOWS.map((w) => (
            <button key={w.id} type="button" aria-pressed={window === w.id} onClick={() => setWindow(w.id)} className={cn('rounded-md px-3 py-1.5 text-xs font-medium', window === w.id ? 'bg-[var(--color-background-tertiary)] text-[var(--color-text-primary)]' : 'text-[var(--color-text-secondary)]')}>{w.label}</button>
          ))}
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {sorted.map((s) => <SectorCard key={s.sector} sector={s} window={window} />)}
      </div>
    </div>
  )
}
