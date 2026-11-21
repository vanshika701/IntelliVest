import { useId, useMemo } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { format, parseISO } from 'date-fns'
import { AlertCircle, RefreshCw } from 'lucide-react'
import type { PricePoint } from '../../api/instruments'
import { RANGES, type RangeKey, type RangeState } from '../../lib/ranges'
import { formatINR, formatSignedPct } from '../../lib/format'
import { cn } from '../../lib/utils'
import { Skeleton } from '../ui/Skeleton'

interface PriceChartProps {
  range: RangeKey | null
  onRangeChange: (range: RangeKey) => void
  availability: Record<RangeKey, RangeState> | null
  points: PricePoint[]
  loading: boolean
  error: string | null
  onRetry: () => void
}

const GAINS = '#10B981'
const LOSSES = '#f43f5e'

function axisLabel(t: string, range: RangeKey): string {
  const date = parseISO(t)
  if (range === '1D') return format(date, 'HH:mm')
  if (range === '1Y' || range === 'YTD') return format(date, 'MMM yy')
  return format(date, 'd MMM')
}

function tooltipLabel(t: string, range: RangeKey): string {
  return format(parseISO(t), range === '1D' ? 'd MMM, HH:mm' : 'd MMM yyyy')
}

export function PriceChart({ range, onRangeChange, availability, points, loading, error, onRetry }: PriceChartProps) {
  const gradientId = useId()
  const change = useMemo(() => {
    if (points.length < 2) return null
    const first = points[0].v
    const last = points[points.length - 1].v
    return { abs: last - first, pct: ((last - first) / first) * 100 }
  }, [points])
  const color = (change?.abs ?? 0) >= 0 ? GAINS : LOSSES

  return (
    <section aria-labelledby="price-chart-heading" className="glass-card rounded-2xl p-5 sm:p-6">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 id="price-chart-heading" className="text-base font-semibold text-[var(--color-text-primary)]">
            Price history
          </h3>
          {change && range && (
            <p className={cn('text-sm font-medium', change.abs >= 0 ? 'text-[var(--color-gains)]' : 'text-[var(--color-losses)]')}>
              {formatSignedPct(change.pct)} over {range === '1D' ? 'the last session' : range}
            </p>
          )}
        </div>

        <div role="group" aria-label="Chart range" className="flex flex-wrap gap-1">
          {RANGES.map((key) => {
            const state = availability?.[key]
            const disabled = !state?.available
            const tooltipId = `${gradientId}-${key}-reason`
            return (
              <span key={key} className="group relative">
                <button
                  type="button"
                  aria-pressed={range === key}
                  aria-disabled={disabled}
                  aria-describedby={disabled && state?.reason ? tooltipId : undefined}
                  onClick={() => !disabled && onRangeChange(key)}
                  className={cn(
                    'rounded-md px-3 py-1.5 text-xs font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]',
                    range === key
                      ? 'bg-[var(--color-brand)] text-white'
                      : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-background-tertiary)] hover:text-[var(--color-text-primary)]',
                    disabled && 'cursor-not-allowed opacity-40 hover:bg-transparent hover:text-[var(--color-text-secondary)]',
                  )}
                >
                  {key}
                </button>
                {disabled && state?.reason && (
                  <span
                    id={tooltipId}
                    role="tooltip"
                    className="pointer-events-none invisible absolute right-0 top-full z-20 mt-1 w-56 rounded-md border border-[var(--color-border-strong)] bg-[var(--color-background-tertiary)] px-2.5 py-1.5 text-xs text-[var(--color-text-secondary)] opacity-0 shadow-lg transition-opacity group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100"
                  >
                    {state.reason}
                  </span>
                )}
              </span>
            )
          })}
        </div>
      </div>

      <div className="h-64 sm:h-72">
        {loading ? (
          <Skeleton className="h-full w-full" />
        ) : error ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-sm text-[var(--color-text-secondary)]">
            <AlertCircle className="h-6 w-6 text-[var(--color-losses)]" aria-hidden="true" />
            <p>{error}</p>
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-border-strong)] px-3 py-1.5 text-xs font-medium text-[var(--color-text-primary)] hover:bg-[var(--color-background-tertiary)]"
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" /> Retry
            </button>
          </div>
        ) : !range || points.length < 2 ? (
          <div className="flex h-full items-center justify-center text-sm text-[var(--color-text-muted)]">
            No price history available yet.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1e293b" vertical={false} />
              <XAxis
                dataKey="t"
                tickFormatter={(t: string) => axisLabel(t, range)}
                stroke="#64748b"
                tick={{ fontSize: 11 }}
                minTickGap={40}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                domain={['auto', 'auto']}
                stroke="#64748b"
                tick={{ fontSize: 11 }}
                width={64}
                tickFormatter={(v: number) => `₹${v.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: '#94a3b8' }}
                labelFormatter={(t) => tooltipLabel(String(t), range)}
                formatter={(v) => [formatINR(Number(v)), 'Price']}
              />
              <Area type="monotone" dataKey="v" stroke={color} strokeWidth={2} fill={`url(#${gradientId})`} isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  )
}
