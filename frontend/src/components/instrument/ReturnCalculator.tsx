import { useId, useMemo, useState } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Info } from 'lucide-react'
import {
  DEFAULT_ANNUAL_RETURN,
  estimateReturns,
  projectionByYear,
  type InvestmentMode,
} from '../../lib/returns'
import { formatINR, formatINRAxis, formatINRCompact } from '../../lib/format'
import { cn } from '../../lib/utils'
import { Input } from '../ui/Input'

interface ReturnCalculatorProps {
  /** Historical CAGR (%) when computable; null falls back to 12%. */
  historicalCagr: number | null
}

const LIMITS = { amount: [100, 10_000_000], years: [1, 40], rate: [-20, 50] } as const

export function ModeToggle({
  mode,
  onChange,
  labels = { one_time: 'One-time', sip: 'SIP' },
  name,
}: {
  mode: InvestmentMode
  onChange: (mode: InvestmentMode) => void
  labels?: Record<InvestmentMode, string>
  name: string
}) {
  return (
    <div role="radiogroup" aria-label={name} className="inline-flex rounded-lg border border-[var(--color-border-strong)] p-0.5">
      {(['one_time', 'sip'] as InvestmentMode[]).map((key) => (
        <button
          key={key}
          type="button"
          role="radio"
          aria-checked={mode === key}
          onClick={() => onChange(key)}
          className={cn(
            'rounded-md px-4 py-1.5 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]',
            mode === key
              ? 'bg-[var(--color-brand)] text-white'
              : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]',
          )}
        >
          {labels[key]}
        </button>
      ))}
    </div>
  )
}

function Field({
  id,
  label,
  value,
  onChange,
  min,
  max,
  step,
  suffix,
  error,
  help,
}: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
  min: number
  max: number
  step?: number
  suffix?: string
  error?: string
  help?: string
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-xs font-medium text-[var(--color-text-secondary)]">
        {label}
      </label>
      <div className="relative">
        <Input
          id={id}
          type="number"
          inputMode="decimal"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? `${id}-error` : help ? `${id}-help` : undefined}
          className={cn(suffix && 'pr-12', error && 'border-[var(--color-losses)]')}
        />
        {suffix && (
          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-[var(--color-text-muted)]">
            {suffix}
          </span>
        )}
      </div>
      {error ? (
        <p id={`${id}-error`} className="mt-1 text-xs text-[var(--color-losses)]">
          {error}
        </p>
      ) : help ? (
        <p id={`${id}-help`} className="mt-1 text-xs text-[var(--color-text-muted)]">
          {help}
        </p>
      ) : null}
    </div>
  )
}

function rangeError(raw: string, [min, max]: readonly [number, number], what: string): string | undefined {
  const value = Number(raw)
  if (raw.trim() === '' || Number.isNaN(value)) return `Enter ${what}`
  if (value < min || value > max) return `Must be between ${min.toLocaleString('en-IN')} and ${max.toLocaleString('en-IN')}`
  return undefined
}

export function ReturnCalculator({ historicalCagr }: ReturnCalculatorProps) {
  const idPrefix = useId()
  const [mode, setMode] = useState<InvestmentMode>('sip')
  const [amount, setAmount] = useState('5000')
  const [years, setYears] = useState('10')
  const [rate, setRate] = useState(String(historicalCagr ?? DEFAULT_ANNUAL_RETURN))

  const errors = {
    amount: rangeError(amount, LIMITS.amount, 'an amount'),
    years: rangeError(years, LIMITS.years, 'a duration'),
    rate: rangeError(rate, LIMITS.rate, 'a return'),
  }
  const valid = !errors.amount && !errors.years && !errors.rate

  const { estimate, projection } = useMemo(() => {
    if (!valid) return { estimate: null, projection: [] }
    const args = [mode, Number(amount), Math.round(Number(years)), Number(rate)] as const
    return { estimate: estimateReturns(...args), projection: projectionByYear(...args) }
  }, [valid, mode, amount, years, rate])

  return (
    <section aria-labelledby={`${idPrefix}-heading`} className="glass-card rounded-2xl p-5 sm:p-6">
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h3 id={`${idPrefix}-heading`} className="text-base font-semibold text-[var(--color-text-primary)]">
          Return calculator
        </h3>
        <ModeToggle mode={mode} onChange={setMode} name="Calculator investment type" />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <Field
            id={`${idPrefix}-amount`}
            label={mode === 'sip' ? 'Monthly amount (₹)' : 'One-time amount (₹)'}
            value={amount}
            onChange={setAmount}
            min={LIMITS.amount[0]}
            max={LIMITS.amount[1]}
            step={100}
            error={errors.amount}
          />
          <Field
            id={`${idPrefix}-years`}
            label="Duration"
            value={years}
            onChange={setYears}
            min={LIMITS.years[0]}
            max={LIMITS.years[1]}
            suffix="years"
            error={errors.years}
          />
          <Field
            id={`${idPrefix}-rate`}
            label="Expected annual return"
            value={rate}
            onChange={setRate}
            min={LIMITS.rate[0]}
            max={LIMITS.rate[1]}
            step={0.1}
            suffix="% p.a."
            error={errors.rate}
            help={
              historicalCagr !== null
                ? `Defaults to this instrument's historical CAGR (${historicalCagr}%, up to the last 3 years).`
                : `Defaults to ${DEFAULT_ANNUAL_RETURN}% — not enough reliable history to compute a CAGR.`
            }
          />
        </div>

        <div>
          <dl className="grid grid-cols-3 gap-2 rounded-xl bg-[var(--color-background-tertiary)]/40 p-4">
            <div>
              <dt className="text-xs text-[var(--color-text-muted)]">Invested</dt>
              <dd className="mt-1 text-sm font-semibold text-[var(--color-text-primary)] sm:text-base">
                {estimate ? formatINRCompact(estimate.invested) : '—'}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-[var(--color-text-muted)]">Est. returns</dt>
              <dd
                className={cn(
                  'mt-1 text-sm font-semibold sm:text-base',
                  estimate && estimate.estimatedReturns < 0 ? 'text-[var(--color-losses)]' : 'text-[var(--color-gains)]',
                )}
              >
                {estimate ? formatINRCompact(estimate.estimatedReturns) : '—'}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-[var(--color-text-muted)]">Total value</dt>
              <dd className="mt-1 text-sm font-bold text-[var(--color-text-primary)] sm:text-base" aria-live="polite">
                {estimate ? formatINRCompact(estimate.totalValue) : '—'}
              </dd>
            </div>
          </dl>

          <div className="mt-4 h-40" aria-hidden="true">
            {projection.length > 1 && (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={projection} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="year" stroke="#64748b" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} tickFormatter={(y: number) => `${y}y`} />
                  <YAxis stroke="#64748b" tick={{ fontSize: 11 }} width={48} tickLine={false} axisLine={false} tickFormatter={(v: number) => formatINRAxis(v)} />
                  <Tooltip
                    contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                    labelFormatter={(y) => `Year ${y}`}
                    formatter={(v, key) => [formatINR(Number(v), 0), key === 'value' ? 'Estimated value' : 'Invested']}
                  />
                  <Area type="monotone" dataKey="value" stroke="#6366f1" fill="#6366f1" fillOpacity={0.15} strokeWidth={2} isAnimationActive={false} />
                  <Area type="monotone" dataKey="invested" stroke="#94a3b8" fill="#94a3b8" fillOpacity={0.1} strokeWidth={1.5} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      <p className="mt-4 flex items-start gap-1.5 text-xs text-[var(--color-text-muted)]">
        <Info className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        Estimates are based on assumed returns and are not guaranteed.
      </p>
    </section>
  )
}
