import type { InstrumentDetail } from '../../api/instruments'
import { DASH, formatINR } from '../../lib/format'

function Stat({ label, value, placeholder, hint }: { label: string; value: string; placeholder?: boolean; hint?: string }) {
  return (
    <div className="min-w-0 px-4 py-3">
      <dt className="flex items-center gap-1.5 text-xs text-[var(--color-text-muted)]">
        {label}
        {placeholder && (
          <span
            title="Placeholder value — not real data for this instrument"
            className="rounded bg-amber-500/10 px-1 py-px text-[9px] font-bold uppercase tracking-wide text-amber-400"
          >
            Placeholder
          </span>
        )}
      </dt>
      <dd className="mt-1 truncate text-base font-semibold text-[var(--color-text-primary)]" title={hint}>
        {value}
      </dd>
    </div>
  )
}

export function StatsStrip({ instrument }: { instrument: InstrumentDetail }) {
  const { stats, type } = instrument
  const isPlaceholder = (field: string) => stats.placeholder_fields.includes(field)
  const isStock = type === 'STOCK'
  const crore = (value: number | null) => (value === null ? DASH : `₹${Math.round(value).toLocaleString('en-IN')} Cr`)
  const unavailable = 'Not available from our free data sources'

  return (
    <section aria-label="Key stats" className="glass-card rounded-2xl">
      <dl className="grid grid-cols-2 divide-[var(--color-border-subtle)] sm:grid-cols-4 sm:divide-x">
        <Stat label={type === 'STOCK' ? 'Price' : 'NAV'} value={formatINR(instrument.price)} />
        <Stat
          label={isStock ? 'Analyst rating' : 'Rating'}
          value={
            isStock
              ? stats.analyst_rating
                ? `${stats.analyst_rating} (${stats.analyst_count})`
                : DASH
              : stats.rating === null
                ? DASH
                : `${stats.rating} / 5`
          }
          hint={stats.rating_source ?? 'Not rated, or the rating is unavailable right now'}
        />
        <Stat
          label={type === 'STOCK' ? 'Min. SIP (1 share)' : 'Min. SIP'}
          value={formatINR(stats.min_sip, 0)}
          placeholder={isPlaceholder('min_sip')}
        />
        <Stat
          label={isStock ? 'Market cap' : 'Fund size (AUM)'}
          value={crore(isStock ? stats.market_cap_crore : stats.aum_crore)}
          hint={(isStock ? stats.market_cap_crore : stats.aum_crore) === null ? unavailable : undefined}
        />
      </dl>
    </section>
  )
}
