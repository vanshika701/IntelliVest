import { TrendingDown, TrendingUp } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { InstrumentDetail } from '../../api/instruments'
import { DASH, formatDate, formatINR, formatSignedPct } from '../../lib/format'
import { cn } from '../../lib/utils'
import { Skeleton } from '../ui/Skeleton'
import { TypeTag } from '../ui/TypeTag'

export function InstrumentHeader({ instrument }: { instrument: InstrumentDetail }) {
  const change = instrument.day_change
  const isUp = (change ?? 0) >= 0
  const priceLabel = instrument.type === 'STOCK' ? 'Price' : 'NAV'

  return (
    <header className="glass-card rounded-2xl p-5 sm:p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <TypeTag type={instrument.type} />
            {instrument.category && (
              <span className="text-xs text-[var(--color-text-muted)]">{instrument.category}</span>
            )}
            {instrument.sector && (
              <Link
                to={`/sectors/${instrument.sector.id}`}
                className="rounded-full bg-[var(--color-brand-light)] px-2 py-0.5 text-xs font-medium text-[var(--color-brand)] hover:text-[var(--color-brand-hover)]"
              >
                Sector: {instrument.sector.name}
              </Link>
            )}
          </div>
          <h2 className="text-xl font-bold tracking-tight text-[var(--color-text-primary)] sm:text-2xl">
            {instrument.name}
          </h2>
          {instrument.subtitle && (
            <p className="mt-1 text-sm text-[var(--color-text-secondary)]">{instrument.subtitle}</p>
          )}
        </div>

        <div className="shrink-0 sm:text-right">
          <p className="text-xs text-[var(--color-text-muted)]">
            {priceLabel} · {formatDate(instrument.price_date)}
          </p>
          {instrument.quote_fetched_at && (
            <p className="text-xs text-[var(--color-text-muted)]">
              {instrument.market_open
                ? `Market open · about ${instrument.quote_delay_minutes} min delayed · updated ${formatDate(instrument.quote_fetched_at, 'h:mm a')}`
                : 'Market closed · last traded price'}
            </p>
          )}
          <p className="text-3xl font-bold tracking-tight text-[var(--color-text-primary)]">
            {formatINR(instrument.price)}
          </p>
          {change === null ? (
            <p className="text-sm text-[var(--color-text-muted)]">{DASH}</p>
          ) : (
            <p
              className={cn(
                'inline-flex items-center gap-1 text-sm font-semibold',
                isUp ? 'text-[var(--color-gains)]' : 'text-[var(--color-losses)]',
              )}
            >
              {isUp ? <TrendingUp className="h-4 w-4" aria-hidden="true" /> : <TrendingDown className="h-4 w-4" aria-hidden="true" />}
              <span className="sr-only">{isUp ? 'Up' : 'Down'} today:</span>
              {isUp ? '+' : '−'}
              {formatINR(Math.abs(change))} ({formatSignedPct(instrument.day_change_pct)})
              <span className="font-normal text-[var(--color-text-muted)]">1D</span>
            </p>
          )}
        </div>
      </div>
    </header>
  )
}

export function InstrumentHeaderSkeleton() {
  return (
    <div className="glass-card rounded-2xl p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:justify-between">
        <div className="space-y-2">
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-7 w-72 max-w-full" />
          <Skeleton className="h-4 w-40" />
        </div>
        <div className="space-y-2 sm:items-end">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-8 w-36" />
          <Skeleton className="h-4 w-28" />
        </div>
      </div>
    </div>
  )
}
