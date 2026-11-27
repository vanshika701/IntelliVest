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

/** Ahead of / behind the Nifty, e.g. "+3.20% ahead", "-1.50% behind". */
function versus(value: number): string {
  return `${formatSignedPct(value)} ${value >= 0 ? 'ahead' : 'behind'}`
}

function RangeBar({ p }: { p: StockPrediction }) {
  const lo = Math.min(p.low_pct, 0)
  const hi = Math.max(p.high_pct, 0)
  const span = hi - lo || 1
  const at = (v: number) => `${((v - lo) / span) * 100}%`
  return (
    <div className="pt-6 pb-1">
      <div className="relative h-2 rounded-full bg-[var(--color-background-tertiary)]">
        <div
          className="absolute h-2 rounded-full bg-[var(--color-brand)]/40"
          style={{ left: at(p.low_pct), width: `calc(${at(p.high_pct)} - ${at(p.low_pct)})` }}
        />
        <div
          className="absolute -top-1 h-4 w-1 -translate-x-1/2 rounded bg-[var(--color-brand)]"
          style={{ left: at(p.mid_pct) }}
          title={`Middle case ${versus(p.mid_pct)}`}
        />
        <div className="absolute -top-6 -translate-x-1/2 text-[10px] text-[var(--color-text-muted)]" style={{ left: at(0) }}>
          Nifty 50
        </div>
        <div className="absolute -top-1.5 h-5 w-0.5 -translate-x-1/2 bg-[var(--color-text-secondary)]" style={{ left: at(0) }} />
      </div>
      <div className="mt-2 flex justify-between text-xs">
        <span className={tone(p.low_pct)}>{versus(p.low_pct)}</span>
        <span className={tone(p.high_pct)}>{versus(p.high_pct)}</span>
      </div>
    </div>
  )
}

function Result({ p, name }: { p: StockPrediction; name: string }) {
  const test = p.test_result
  const years = test ? `${test.test_years[0]}–${test.test_years[test.test_years.length - 1]}` : null
  const majority = test && test.beat_share >= 0.5 ? 'beat' : 'lag'
  return (
    <div className="space-y-4" aria-live="polite">
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-xs text-[var(--color-text-muted)]">
            By {formatDate(p.target_date)} · {p.trading_days} trading day{p.trading_days === 1 ? '' : 's'}
          </p>
          <p className="mt-1 text-xs text-[var(--color-text-secondary)]">Chance of beating the Nifty 50</p>
          <p className={cn('text-2xl font-semibold', p.chance_beat >= 0.5 ? 'text-[var(--color-gains)]' : 'text-[var(--color-losses)]')}>
            {pct(p.chance_beat)}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs text-[var(--color-text-muted)]">Middle case</p>
          <p className={cn('text-lg font-semibold', tone(p.mid_pct))}>{versus(p.mid_pct)}</p>
        </div>
      </div>

      <div>
        <p className="text-xs font-medium text-[var(--color-text-secondary)]">Likely result against the Nifty 50 (low to high case)</p>
        <RangeBar p={p} />
        {test && (
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            In tests on {years}, the real result ended inside the range {pct(test.range_hit_rate)} of the time.
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
            <dt className="text-[var(--color-text-muted)]">Beat/lag call right in tests</dt>
            <dd className="text-[var(--color-text-primary)]">
              {pct(test.call_accuracy)}{' '}
              <span className="text-xs text-[var(--color-text-muted)]">
                (always "{majority}": {pct(test.majority_call_accuracy)})
              </span>
            </dd>
          </>
        )}
        <dt className="text-[var(--color-text-muted)]">Based on</dt>
        <dd className="text-[var(--color-text-primary)]">
          Closes to {formatDate(p.as_of)} ({formatINR(p.last_close)})
        </dd>
      </dl>
      <p className="text-xs text-[var(--color-text-muted)]">
        Ahead means the stock does better than the Nifty 50 index over the same days, whether the market rises or falls.
      </p>
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
