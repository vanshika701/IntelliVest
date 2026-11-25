import { useState } from 'react'
import { Minus, RefreshCw, TrendingDown, TrendingUp } from 'lucide-react'
import { Link } from 'react-router-dom'
import { sectorsApi, type Sector, type SectorWindow } from '../api/sectors'
import { Skeleton } from '../components/ui/Skeleton'
import { useApi } from '../hooks/useApi'
import { DASH, formatDate, formatINR, formatSignedPct } from '../lib/format'
import { cn } from '../lib/utils'

const WINDOWS: { id: SectorWindow; label: string }[] = [
  { id: '1d', label: '1 day' },
  { id: '1w', label: '1 week' },
  { id: '1m', label: '1 month' },
  { id: '3m', label: '3 months' },
]
const TREND = {
  up: { Icon: TrendingUp, label: 'Rising' },
  down: { Icon: TrendingDown, label: 'Falling' },
  flat: { Icon: Minus, label: 'Flat' },
} as const

function changeColor(value: number | null) {
  if (value === null || value === 0) return 'text-[var(--color-text-secondary)]'
  return value > 0 ? 'text-[var(--color-gains)]' : 'text-[var(--color-losses)]'
}

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

function SectorCard({ sector, window, selected, onSelect }: { sector: Sector; window: SectorWindow; selected: boolean; onSelect: () => void }) {
  const change = sector.changes[window]
  const trend = sector.trend ? TREND[sector.trend] : null
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
      className={cn('glass-card rounded-2xl p-5 text-left focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]', selected && 'ring-2 ring-[var(--color-brand)]')}
    >
      <span className="flex items-start justify-between gap-3">
        <span>
          <span className="block font-semibold text-[var(--color-text-primary)]">{sector.name}</span>
          <span className="block text-xs text-[var(--color-text-muted)]">{sector.stock_count} stock{sector.stock_count === 1 ? '' : 's'}</span>
        </span>
        <Sparkline points={sector.series} />
      </span>
      <span className={cn('mt-3 block text-2xl font-bold', changeColor(change))}>{formatSignedPct(change)}</span>
      <span className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--color-text-secondary)]">
        {trend && <span className="inline-flex items-center gap-1"><trend.Icon className="h-3.5 w-3.5" aria-hidden /> {trend.label} (1 month)</span>}
        <span className="capitalize">{sector.sentiment.label ? `${sector.sentiment.label} news` : 'Not enough news'}</span>
      </span>
    </button>
  )
}

function SectorDetail({ sector }: { sector: Sector }) {
  const s = sector.sentiment
  return (
    <section aria-label={`${sector.name} details`} className="glass-card overflow-hidden rounded-2xl">
      <div className="border-b border-[var(--color-border-subtle)] px-5 py-4">
        <h3 className="font-semibold text-[var(--color-text-primary)]">{sector.name}</h3>
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">
          {sector.advancers} up, {sector.decliners} down on the last trading day. {s.article_count} news article{s.article_count === 1 ? '' : 's'} in {s.window_days} days
          {s.article_count > 0 && ` (${s.label_counts.positive ?? 0} positive, ${s.label_counts.neutral ?? 0} neutral, ${s.label_counts.negative ?? 0} negative)`}.
          {sector.priced_count < sector.stock_count && ` Recent prices for ${sector.priced_count} of ${sector.stock_count} stocks.`}
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-[var(--color-text-muted)]">
              <th className="px-5 py-2 text-left font-medium">Stock</th>
              <th className="px-3 py-2 text-right font-medium">Price</th>
              {WINDOWS.map((w) => <th key={w.id} className="px-3 py-2 text-right font-medium">{w.label}</th>)}
              <th className="px-5 py-2 text-right font-medium">News</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border-subtle)]">
            {sector.stocks.map((stock) => (
              <tr key={stock.ticker}>
                <td className="px-5 py-2.5"><Link to={`/instrument/${encodeURIComponent(`stock-${stock.ticker}`)}`} className="text-[var(--color-text-primary)] hover:text-[var(--color-brand)]">{stock.name}</Link></td>
                <td className="px-3 py-2.5 text-right font-mono">{formatINR(stock.price)}</td>
                {WINDOWS.map((w) => <td key={w.id} className={cn('px-3 py-2.5 text-right font-mono', changeColor(stock.changes[w.id]))}>{formatSignedPct(stock.changes[w.id])}</td>)}
                <td className="px-5 py-2.5 text-right capitalize text-[var(--color-text-secondary)]">{stock.sentiment_label ?? DASH}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

/** Phase 6: sector-level price trend and news sentiment. */
export function SectorsPage() {
  const { data, error, loading, reload } = useApi('sectors', sectorsApi.list)
  const [window, setWindow] = useState<SectorWindow>('1m')
  const [selectedId, setSelectedId] = useState<string | null>(null)

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
  const selected = data.find((s) => s.sector === selectedId) ?? sorted[0]
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
        {sorted.map((s) => <SectorCard key={s.sector} sector={s} window={window} selected={s.sector === selected.sector} onSelect={() => setSelectedId(s.sector)} />)}
      </div>
      <SectorDetail sector={selected} />
    </div>
  )
}
