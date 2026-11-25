// Typed wrapper for /api/v1/sectors (Phase 6, precomputed rollups).
import { apiGet } from './client'
import type { SentimentLabel } from './instruments'

export type SectorWindow = '1d' | '1w' | '1m' | '3m'
export type SectorChanges = Record<SectorWindow, number | null>

export interface SectorStock {
  ticker: string
  name: string
  price: number | null
  changes: SectorChanges
  sentiment_score: number | null
  sentiment_label: SentimentLabel | null
  article_count: number
}

export interface Sector {
  sector: string
  name: string
  stock_count: number
  priced_count: number
  as_of: string | null
  changes: SectorChanges
  trend: 'up' | 'down' | 'flat' | null
  advancers: number
  decliners: number
  sentiment: {
    score: number | null
    label: SentimentLabel | null
    article_count: number
    label_counts: Record<string, number>
    window_days: number
  }
  series: { t: string; v: number }[]
  stocks: SectorStock[]
  computed_at: string
}

export interface SectorArticle {
  url: string
  title: string
  source: string | null
  published_at: string
  label: SentimentLabel | null
}

const base = (id: string) => `/api/v1/sectors/${encodeURIComponent(id)}`

export const sectorsApi = {
  list: () => apiGet<Sector[]>('/api/v1/sectors'),
  get: (id: string) => apiGet<Sector>(base(id)),
  news: (id: string, options: { excludeTicker?: string; limit?: number } = {}) => {
    const params = new URLSearchParams({ limit: String(options.limit ?? 8) })
    if (options.excludeTicker) params.set('exclude_ticker', options.excludeTicker)
    return apiGet<SectorArticle[]>(`${base(id)}/news?${params}`)
  },
}
