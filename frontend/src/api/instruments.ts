// Typed wrappers for /api/v1/instruments — components never call fetch directly.
import { apiGet } from './client'

export type InstrumentType = 'STOCK' | 'MF' | 'ETF'
export type SentimentLabel = 'positive' | 'negative' | 'neutral'

export interface InstrumentSearchResult {
  id: string
  name: string
  type: InstrumentType
  symbol: string
  subtitle: string | null
}

export interface InstrumentSearchResponse {
  query: string
  results: InstrumentSearchResult[]
  partial: boolean
}

export interface InstrumentStats {
  rating: number | null
  rating_source: string | null
  analyst_rating: string | null
  analyst_count: number | null
  market_cap_crore: number | null
  aum_crore: number | null
  aum_period: string | null
  min_sip: number | null
  min_investment: number | null
  placeholder_fields: string[]
  source: string
}

export interface InstrumentDetail {
  id: string
  name: string
  type: InstrumentType
  symbol: string
  subtitle: string | null
  category: string | null
  sector: { id: string; name: string } | null
  /** One of the 20 tracked stocks: stored prices, news and daily predictions. */
  tracked: boolean
  currency: string
  price: number | null
  price_date: string | null
  previous_price: number | null
  day_change: number | null
  day_change_pct: number | null
  quote_fetched_at: string | null
  quote_delay_minutes: number | null
  market_open: boolean
  supports_intraday: boolean
  stats: InstrumentStats
}

export interface PricePoint {
  t: string // ISO date (daily) or ISO datetime (intraday)
  v: number
}

export interface PriceHistory {
  interval: '1d' | '5m'
  points: PricePoint[]
}

export interface SentimentArticle {
  title: string
  url: string
  source: string | null
  published_at: string
  label: SentimentLabel
  score: number
}

export interface InstrumentSentiment {
  instrument_id: string
  label: SentimentLabel | null
  average_score: number | null
  article_count: number
  min_articles: number
  window_days: number
  engine: string
  articles: SentimentArticle[]
  generated_at: string
}

export type SummaryInputKind = 'full_text' | 'snippet' | 'headline'

export interface DigestArticle {
  title: string
  url: string
  source: string | null
  published_at: string
  input_kind: SummaryInputKind
  label: SentimentLabel
  score: number
}

/** The instrument's own price change, from our data rather than the news. */
export interface PriceMove {
  as_of: string
  day_pct: number | null
  week_pct: number | null
  month_pct: number | null
  text: string
}

/** One combined summary of the top recent articles, plus those articles. */
export interface NewsDigest {
  instrument_id: string
  /** 'sector' = too little news about the instrument, so scope_name's news is shown. */
  scope: 'instrument' | 'sector'
  scope_name: string
  price_move: PriceMove | null
  provider: string
  method: string
  max_words: number
  summary: string | null
  word_count: number
  summary_failed: boolean
  sources: Record<SummaryInputKind, number>
  sentiment_engine: string | null
  articles: DigestArticle[]
  generated_at: string
}

export type HorizonUnit = 'days' | 'months' | 'years'

/** How the model did on past years it never trained on (Phase 4). */
export interface PredictionTestResult {
  horizon_group: string
  test_years: number[]
  range_hit_rate: number
  /** Beat/lag call (chance above or below 50%) right. */
  call_accuracy: number
  /** Always making the more common call. */
  majority_call_accuracy: number
  /** Share of test cases where the stock beat the Nifty. */
  beat_share: number
}

/** Stored prediction against the Nifty 50; percentages are (1 + stock) / (1 + Nifty) - 1. */
export interface StockPrediction {
  instrument_id: string
  ticker: string
  amount: number
  unit: HorizonUnit
  trading_days: number
  as_of: string
  target_date: string
  last_close: number
  chance_beat: number
  low_pct: number
  mid_pct: number
  high_pct: number
  rank: number
  rank_of: number
  /** False: not one of the 20 stocks the model was tested on. */
  tracked: boolean
  model_version: string
  artifact_hash: string
  test_result: PredictionTestResult | null
}

const base = (id: string) => `/api/v1/instruments/${encodeURIComponent(id)}`

export const instrumentsApi = {
  search: (query: string, signal?: AbortSignal, limit = 12) =>
    apiGet<InstrumentSearchResponse>(`/api/v1/instruments/search?q=${encodeURIComponent(query)}&limit=${limit}`, { signal }),
  detail: (id: string) => apiGet<InstrumentDetail>(base(id)),
  history: (id: string) => apiGet<PriceHistory>(`${base(id)}/history`),
  intraday: (id: string) => apiGet<PriceHistory>(`${base(id)}/intraday`),
  sentiment: (id: string) => apiGet<InstrumentSentiment>(`${base(id)}/sentiment`),
  newsDigest: (id: string) => apiGet<NewsDigest>(`${base(id)}/news-summary`),
  prediction: (id: string, amount: number, unit: HorizonUnit) =>
    apiGet<StockPrediction>(`${base(id)}/prediction?amount=${amount}&unit=${unit}`),
}

export const TYPE_LABEL: Record<InstrumentType, string> = { STOCK: 'Stock', MF: 'MF', ETF: 'ETF' }
