import { ArrowLeft, RefreshCw } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { sectorsApi, type Sector } from '../api/sectors'
import { SectorNews } from '../components/SectorNews'
import { Skeleton } from '../components/ui/Skeleton'
import { useApi } from '../hooks/useApi'
import { DASH, formatDate, formatINR, formatSignedPct } from '../lib/format'
import { changeColor, WINDOWS } from '../lib/sectorView'
import { cn } from '../lib/utils'

function SectorDetail({ sector }: { sector: Sector }) {
  const s = sector.sentiment
  return (
    <section aria-label={`${sector.name} details`} className="glass-card overflow-hidden rounded-2xl">
      <div className="border-b border-[var(--color-border-subtle)] px-5 py-4">
        <h3 className="font-semibold text-[var(--color-text-primary)]">Stocks used for this sector</h3>
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

/** One sector: every stock its figures are built from, and its news. */
export function SectorPage() {
  const { id = '' } = useParams()
  const { data, error, status, loading, reload } = useApi(id, () => sectorsApi.get(id))

  return (
    <div className="space-y-6">
      <Link to="/sectors" className="inline-flex items-center gap-1 text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]">
        <ArrowLeft className="h-4 w-4" aria-hidden /> All sectors
      </Link>
      {loading ? (
        <Skeleton className="h-64 w-full rounded-2xl" />
      ) : error || !data ? (
        <div className="space-y-3">
          <p role="alert" className="text-sm text-[var(--color-losses)]">{status === 404 ? "We couldn't find this sector." : `This sector couldn't be loaded. ${error}`}</p>
          <button type="button" onClick={reload} className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-border-strong)] px-3 py-1.5 text-sm text-[var(--color-text-primary)]"><RefreshCw className="h-4 w-4" aria-hidden /> Retry</button>
        </div>
      ) : (
        <>
          <header className="glass-card rounded-2xl p-5">
            <h2 className="text-2xl font-bold text-[var(--color-text-primary)]">{data.name}</h2>
            <p className="mt-1 text-xs text-[var(--color-text-muted)]">Average of the {data.priced_count} stock{data.priced_count === 1 ? '' : 's'} below, each weighted equally. Prices up to {formatDate(data.as_of)}.</p>
            <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
              {WINDOWS.map((w) => (
                <div key={w.id}>
                  <dt className="text-xs text-[var(--color-text-muted)]">{w.label}</dt>
                  <dd className={cn('mt-1 text-lg font-semibold', changeColor(data.changes[w.id]))}>{formatSignedPct(data.changes[w.id])}</dd>
                </div>
              ))}
            </dl>
          </header>
          <SectorDetail sector={data} />
          <SectorNews sector={data.sector} name={data.name} limit={15} />
        </>
      )}
    </div>
  )
}
