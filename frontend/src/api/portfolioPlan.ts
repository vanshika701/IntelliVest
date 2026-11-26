// Typed wrappers for Phase 7: /api/v1/risk-profile and /api/v1/recommendations.
import { apiGet, apiPost, apiPut } from './client'

export type ProfileId =
  | 'conservative'
  | 'moderately_conservative'
  | 'moderate'
  | 'moderately_aggressive'
  | 'aggressive'

export interface Questionnaire {
  version: string
  questions: {
    id: string
    dimension: 'capacity' | 'tolerance'
    text: string
    options: { id: string; label: string }[]
  }[]
  profiles: { id: ProfileId; label: string; description: string }[]
}

export interface RiskProfile {
  profile: ProfileId
  label: string
  description: string
  capacity_score: number
  tolerance_score: number
  limited_by: 'capacity' | 'tolerance' | 'both'
  caps_applied: { question: string; answer: string; max_profile: ProfileId }[]
  notes: string[]
  version: string
  answers: Record<string, string>
  updated_at: string
}

export interface Allocation {
  profile: ProfileId
  horizon_months: number
  equity_pct: number
  debt_pct: number
  gold_pct: number
  debt_style: string
  base: { equity_pct: number; debt_pct: number; gold_pct: number }
  base_is_sourced: boolean
  adjustments: { asset: string; from_pct: number; to_pct: number; reason: string }[]
  version: string
}

export type AssetClass = 'equity' | 'debt' | 'gold'

export interface RecommendedHolding {
  asset_class: AssetClass
  instrument_id: string | null
  name: string
  kind: 'stock' | 'fund'
  sector?: string
  fund_role?: string
  weight: number
  weight_in_class: number
  lump_sum_amount: number
  monthly_amount: number
  already_held_value: number | null
  reasons: string[]
  warnings: string[]
}

export interface EquitySummary {
  annual_volatility: number
  holdings: number
  effective_holdings: number
  sector_weights: Record<string, number>
}

export interface Recommendation {
  id: string
  inputs: {
    lump_sum: number
    monthly_sip: number
    horizon_months: number
    goal: { id: string; name: string } | null
  }
  profile: Pick<RiskProfile, 'profile' | 'label' | 'capacity_score' | 'tolerance_score' | 'limited_by'>
  allocation: Allocation
  holdings: RecommendedHolding[]
  risk: {
    class_volatility: Record<AssetClass, number | null>
    volatility_upper_bound: number | null
    bad_year_loss: number | null
    explanation: string
    missing: AssetClass[]
  }
  equity_comparison: {
    optimized: EquitySummary
    minimum_variance: EquitySummary
    equal_weight: EquitySummary
  } | null
  not_held: { instrument_id: string; name: string; current_value: number | null }[]
  notes: string[]
  versions: Record<string, string | number | null>
  disclaimer: string
  created_at: string
}

export interface RecommendationInput {
  horizon_months?: number
  goal_id?: string
  lump_sum: number
  monthly_sip: number
  use_sentiment: boolean
}

export const portfolioPlanApi = {
  questions: () => apiGet<Questionnaire>('/api/v1/risk-profile/questions'),
  riskProfile: () => apiGet<RiskProfile>('/api/v1/risk-profile'),
  saveRiskProfile: (answers: Record<string, string>) =>
    apiPut<RiskProfile>('/api/v1/risk-profile', { answers }),
  latest: () => apiGet<Recommendation>('/api/v1/recommendations/latest'),
  create: (body: RecommendationInput) => apiPost<Recommendation>('/api/v1/recommendations', body),
}
