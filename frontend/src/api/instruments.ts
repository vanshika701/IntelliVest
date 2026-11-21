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
  aum_crore: number | null
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
  currency: string
  price: number | null
  price_date: string | null
  previous_price: number | null
  day_change: number | null
  day_change_pct: number | null
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

const base = (id: string) => `/api/v1/instruments/${encodeURIComponent(id)}`

export const instrumentsApi = {
  search: (query: string, signal?: AbortSignal) =>
    apiGet<InstrumentSearchResponse>(`/api/v1/instruments/search?q=${encodeURIComponent(query)}&limit=12`, { signal }),
  detail: (id: string) => apiGet<InstrumentDetail>(base(id)),
  history: (id: string) => apiGet<PriceHistory>(`${base(id)}/history`),
  intraday: (id: string) => apiGet<PriceHistory>(`${base(id)}/intraday`),
  sentiment: (id: string) => apiGet<InstrumentSentiment>(`${base(id)}/sentiment`),
}

export const TYPE_LABEL: Record<InstrumentType, string> = { STOCK: 'Stock', MF: 'MF', ETF: 'ETF' }
