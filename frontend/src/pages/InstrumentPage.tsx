import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AlertCircle, ArrowLeft, RefreshCw, SearchX } from 'lucide-react'
import { instrumentsApi } from '../api/instruments'
import { useApi } from '../hooks/useApi'
import { useModelChoice } from '../hooks/useModelChoice'
import { ModelSelect } from '../components/ui/ModelSelect'
import { getRangeAvailability, pickDefaultRange, pointsForRange, type RangeKey } from '../lib/ranges'
import { computeCagr } from '../lib/returns'
import { InstrumentHeader, InstrumentHeaderSkeleton } from '../components/instrument/InstrumentHeader'
import { PriceChart } from '../components/instrument/PriceChart'
import { StatsStrip } from '../components/instrument/StatsStrip'
import { SentimentSection } from '../components/instrument/SentimentSection'
import { NewsDigest } from '../components/instrument/NewsDigest'
import { ReturnCalculator } from '../components/instrument/ReturnCalculator'
import { InvestPanel } from '../components/instrument/InvestPanel'
import { SectorNews } from '../components/SectorNews'
import { Skeleton } from '../components/ui/Skeleton'

export function InstrumentPage() {
  const { id = '' } = useParams()
  // Keyed so range selection and calculator inputs reset per instrument.
  return <InstrumentView key={id} id={id} />
}

function InstrumentView({ id }: { id: string }) {
  const isStock = id.startsWith('stock-')
  const detail = useApi(id, () => instrumentsApi.detail(id), isStock ? 60_000 : undefined)
  const history = useApi(id, () => instrumentsApi.history(id))
  const intraday = useApi(isStock ? id : null, () => instrumentsApi.intraday(id))
  const [sentimentModel, setSentimentModel] = useModelChoice('sentiment')
  const [summarizer, setSummarizer] = useModelChoice('summarizer')
  const sentiment = useApi(`${id}|${sentimentModel}`, () => instrumentsApi.sentiment(id, sentimentModel))
  // The news summary can take a few seconds (article fetching), so it
  // starts only after the header, chart and stats have rendered.
  const digestReady = Boolean(detail.data) && !history.loading
  const digest = useApi(digestReady ? `${id}|${summarizer}|${sentimentModel}` : null, () =>
    instrumentsApi.newsDigest(id, summarizer, sentimentModel),
  )

  const [selectedRange, setSelectedRange] = useState<RangeKey | null>(null)
  const now = useMemo(() => new Date(), [])

  const dailyPoints = history.data?.points
  const intradayPoints = intraday.data?.points ?? null
  const availability = useMemo(
    () => (dailyPoints ? getRangeAvailability(dailyPoints, intradayPoints, isStock, now) : null),
    [dailyPoints, intradayPoints, isStock, now],
  )
  const range =
    selectedRange && availability?.[selectedRange].available
      ? selectedRange
      : availability
        ? pickDefaultRange(availability)
        : null
  const points = range && dailyPoints ? pointsForRange(range, dailyPoints, intradayPoints, now) : []
  const cagr = useMemo(() => (dailyPoints ? computeCagr(dailyPoints) : null), [dailyPoints])

  if (detail.error) {
    const notFound = detail.status === 404
    return (
      <div className="mx-auto flex max-w-md flex-col items-center gap-4 py-20 text-center">
        {notFound ? (
          <SearchX className="h-10 w-10 text-[var(--color-text-muted)]" aria-hidden="true" />
        ) : (
          <AlertCircle className="h-10 w-10 text-[var(--color-losses)]" aria-hidden="true" />
        )}
        <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
          {notFound ? "We couldn't find this instrument" : "This instrument couldn't be loaded"}
        </h2>
        <p className="text-sm text-[var(--color-text-secondary)]">
          {notFound ? 'Try searching for it again from the bar at the top.' : detail.error}
        </p>
        {notFound ? (
          <Link to="/dashboard" className="text-sm font-medium text-[var(--color-brand)] hover:text-[var(--color-brand-hover)]">
            Back to dashboard
          </Link>
        ) : (
          <button
            type="button"
            onClick={detail.reload}
            className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-border-strong)] px-3 py-1.5 text-sm text-[var(--color-text-primary)] hover:bg-[var(--color-background-tertiary)]"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" /> Retry
          </button>
        )}
      </div>
    )
  }

  const instrument = detail.data

  return (
    <div className="mx-auto max-w-5xl space-y-6 animate-in fade-in duration-300">
      <Link
        to="/dashboard"
        className="inline-flex items-center gap-1 text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Dashboard
      </Link>

      {instrument ? <InstrumentHeader instrument={instrument} /> : <InstrumentHeaderSkeleton />}

      <PriceChart
        range={range}
        onRangeChange={setSelectedRange}
        availability={availability}
        points={points}
        loading={history.loading || (isStock && intraday.loading && range === '1D')}
        error={history.error}
        onRetry={history.reload}
      />

      {instrument ? <StatsStrip instrument={instrument} /> : <Skeleton className="h-20 w-full rounded-2xl" />}

      <SentimentSection
        name={instrument?.name ?? 'this instrument'}
        sentiment={sentiment.data ?? null}
        loading={sentiment.loading}
        error={sentiment.error}
        onRetry={sentiment.reload}
        controls={
          <>
            <ModelSelect kind="sentiment" label="Sentiment model" value={sentimentModel} onChange={setSentimentModel} />
            <ModelSelect kind="summarizer" label="Summary model" value={summarizer} onChange={setSummarizer} />
          </>
        }
      >
        <NewsDigest
          data={digest.data}
          loading={digest.loading || !digestReady}
          error={digest.error}
          onRetry={digest.reload}
        />
      </SentimentSection>

      {instrument?.sector && (
        <SectorNews sector={instrument.sector.id} name={instrument.sector.name} excludeTicker={instrument.symbol} limit={6} />
      )}

      {history.loading ? (
        <Skeleton className="h-80 w-full rounded-2xl" />
      ) : (
        <ReturnCalculator key={String(cagr)} historicalCagr={cagr} />
      )}

      {instrument ? <InvestPanel instrument={instrument} /> : <Skeleton className="h-72 w-full rounded-2xl" />}
    </div>
  )
}
