import { useId, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { instrumentsApi, type HorizonUnit, type InstrumentDetail, type StockPrediction } from '../../api/instruments'
import { useApi } from '../../hooks/useApi'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { formatDate, formatINR, formatSignedPct } from '../../lib/format'
import { ordinal } from '../../lib/ordinal'
import { describeHorizon, HORIZON_LIMITS, HORIZON_PRESETS, validateHorizon } from '../../lib/predictionHorizon'
import { cn } from '../../lib/utils'
import { NumberInput } from '../ui/NumberInput'
import { Skeleton } from '../ui/Skeleton'

const UNITS: { key: HorizonUnit; label: string }[] = [
  { key: 'days', label: 'Days' },
  { key: 'months', label: 'Months' },
  { key: 'years', label: 'Years' },
]

const pct = (value: number) => `${Math.round(value * 100)}%`
const tone = (value: number) => (value >= 0 ? 'text-[var(--color-gains)]' : 'text-[var(--color-losses)]')

function RangeBar({ p }: { p: StockPrediction }) {
  const lo = Math.min(p.low_price, p.last_close)
  const hi = Math.max(p.high_price, p.last_close)
  const span = hi - lo || 1
  const at = (v: number) => `${((v - lo) / span) * 100}%`
  return (
    <div className="pt-6 pb-1">
      <div className="relative h-2 rounded-full bg-[var(--color-background-tertiary)]">
        <div
          className="absolute h-2 rounded-full bg-[var(--color-brand)]/40"
          style={{ left: at(p.low_price), width: `calc(${at(p.high_price)} - ${at(p.low_price)})` }}
        />
        <div
          className="absolute -top-1 h-4 w-1 -translate-x-1/2 rounded bg-[var(--color-brand)]"
          style={{ left: at(p.mid_price) }}
          title={`Middle case ${formatINR(p.mid_price)}`}
        />
        <div className="absolute -top-6 -translate-x-1/2 text-[10px] text-[var(--color-text-muted)]" style={{ left: at(p.last_close) }}>
          Now
        </div>
        <div
          className="absolute -top-1.5 h-5 w-0.5 -translate-x-1/2 bg-[var(--color-text-secondary)]"
          style={{ left: at(p.last_close) }}
          title={`Last close ${formatINR(p.last_close)}`}
        />
      </div>
      <div className="mt-2 flex justify-between text-xs">
        <span>
          <span className="block font-medium text-[var(--color-text-primary)]">{formatINR(p.low_price)}</span>
          <span className={tone(p.low_pct)}>{formatSignedPct(p.low_pct)}</span>
        </span>
        <span className="text-right">
          <span className="block font-medium text-[var(--color-text-primary)]">{formatINR(p.high_price)}</span>
          <span className={tone(p.high_pct)}>{formatSignedPct(p.high_pct)}</span>
        </span>
      </div>
    </div>
  )
}

function Result({ p, name }: { p: StockPrediction; name: string }) {
  const test = p.test_result
  const years = test ? `${test.test_years[0]}–${test.test_years[test.test_years.length - 1]}` : null
  return (
    <div className="space-y-4" aria-live="polite">
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-xs text-[var(--color-text-muted)]">
            By {formatDate(p.target_date)} · {p.trading_days} trading day{p.trading_days === 1 ? '' : 's'}
          </p>
          <p className="mt-1 text-2xl font-semibold text-[var(--color-text-primary)]">{formatINR(p.mid_price)}</p>
          <p className="text-xs text-[var(--color-text-secondary)]">
            Middle case <span className={cn('font-medium', tone(p.mid_pct))}>{formatSignedPct(p.mid_pct)}</span> from{' '}
            {formatINR(p.last_close)}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs text-[var(--color-text-muted)]">Chance of going up</p>
          <p className={cn('text-2xl font-semibold', p.chance_up >= 0.5 ? 'text-[var(--color-gains)]' : 'text-[var(--color-losses)]')}>
            {pct(p.chance_up)}
          </p>
        </div>
      </div>

      <div>
        <p className="text-xs font-medium text-[var(--color-text-secondary)]">Likely range (low to high case)</p>
        <RangeBar p={p} />
        {test && (
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            In tests on {years}, the real price ended inside the range {pct(test.range_hit_rate)} of the time.
          </p>
        )}
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-xl bg-[var(--color-background-tertiary)]/40 p-4 text-sm">
        <dt className="text-[var(--color-text-muted)]">Rank</dt>
        <dd className="text-[var(--color-text-primary)]">
          {ordinal(p.rank)} of {p.rank_of} {p.tracked ? 'tracked stocks' : 'with the 20 tracked stocks'}
        </dd>
        {test && (
          <>
            <dt className="text-[var(--color-text-muted)]">Up/down right in tests</dt>
            <dd className="text-[var(--color-text-primary)]">
              {pct(test.direction_accuracy)}{' '}
              <span className="text-xs text-[var(--color-text-muted)]">(always "up": {pct(test.always_up_accuracy)})</span>
            </dd>
          </>
        )}
        <dt className="text-[var(--color-text-muted)]">Based on</dt>
        <dd className="text-[var(--color-text-primary)]">Closes to {formatDate(p.as_of)}</dd>
      </dl>
      {!p.tracked && (
        <p className="rounded-md bg-[var(--color-background-tertiary)]/40 px-3 py-2 text-xs text-[var(--color-text-secondary)]">
          The model was trained and tested on 20 large companies. {name} isn't one of them, so its test results may
          not hold here, especially for smaller companies.
        </p>
      )}
      <p className="text-[11px] text-[var(--color-text-muted)]">Model {p.model_version}</p>
    </div>
  )
}

export function PredictionPanel({ instrument }: { instrument: InstrumentDetail }) {
  const idPrefix = useId()
  const [amount, setAmount] = useState('7')
  const [unit, setUnit] = useState<HorizonUnit>('days')
  const error = validateHorizon(amount, unit)
  const query = useDebouncedValue(error ? null : `${amount}|${unit}`, 300)
  const prediction = useApi(query ? `prediction-${instrument.id}-${query}` : null, () => {
    const [value, chosenUnit] = (query ?? '').split('|')
    return instrumentsApi.prediction(instrument.id, Number(value), chosenUnit as HorizonUnit)
  })

  return (
    <div className="space-y-4">
      <div>
        <label htmlFor={`${idPrefix}-amount`} className="mb-1.5 block text-xs font-medium text-[var(--color-text-secondary)]">
          How far ahead
        </label>
        <div className="flex gap-2">
          <NumberInput
            id={`${idPrefix}-amount`}
            decimals={0}
            value={amount}
            onValueChange={setAmount}
            aria-invalid={Boolean(error)}
            aria-describedby={`${idPrefix}-hint`}
            className="w-24"
          />
          <div role="radiogroup" aria-label="Unit" className="grid flex-1 grid-cols-3 rounded-lg border border-[var(--color-border-strong)] p-0.5">
            {UNITS.map(({ key, label }) => (
              <button
                key={key}
                type="button"
                role="radio"
                aria-checked={unit === key}
                onClick={() => setUnit(key)}
                className={cn(
                  'rounded-md py-1.5 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]',
                  unit === key ? 'bg-[var(--color-brand)] text-white' : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]',
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <p id={`${idPrefix}-hint`} className={cn('mt-1 text-xs', error ? 'text-[var(--color-losses)]' : 'text-[var(--color-text-muted)]')}>
          {error ?? `1 to ${HORIZON_LIMITS[unit]} ${unit}`}
        </p>
        <div className="mt-2 flex flex-wrap gap-2" aria-label="Quick horizons">
          {HORIZON_PRESETS.map((preset) => {
            const active = amount === String(preset.amount) && unit === preset.unit
            return (
              <button
                key={preset.label}
                type="button"
                aria-pressed={active}
                onClick={() => {
                  setAmount(String(preset.amount))
                  setUnit(preset.unit)
                }}
                className={cn(
                  'rounded-full border px-3 py-1 text-xs font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]',
                  active
                    ? 'border-[var(--color-brand)] bg-[var(--color-brand-light)] text-[var(--color-brand)]'
                    : 'border-[var(--color-border-strong)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]',
                )}
              >
                {preset.label}
              </button>
            )
          })}
        </div>
      </div>

      {error ? null : prediction.loading || !query ? (
        <Skeleton className="h-56 w-full rounded-xl" />
      ) : prediction.error ? (
        <div className="rounded-md bg-[var(--color-background-tertiary)]/40 px-3 py-3 text-sm text-[var(--color-text-secondary)]">
          {prediction.status === 404
            ? `No prediction for ${instrument.name} yet. Predictions are made after each market close.`
            : prediction.error}
          {prediction.status !== 404 && (
            <button type="button" onClick={prediction.reload} className="ml-2 inline-flex items-center gap-1 underline">
              <RefreshCw className="h-3 w-3" aria-hidden="true" /> Retry
            </button>
          )}
        </div>
      ) : prediction.data ? (
        <>
          <h4 className="sr-only">Prediction for {describeHorizon(prediction.data.amount, prediction.data.unit)}</h4>
          <Result p={prediction.data} name={instrument.name} />
        </>
      ) : null}
    </div>
  )
}
