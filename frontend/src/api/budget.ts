// Typed wrappers for /api/v1/budget (Phase 8 smart budgeter + goals).
// Every number shown in the budget UI comes from these endpoints; the
// frontend never recomputes benchmarks or SIP amounts itself.
import { apiDelete, apiGet, apiPost, apiPut } from './client'

export type Bucket = 'needs' | 'wants' | 'savings'
export type Basis = 'auto' | 'actual' | 'estimated'

export interface BudgetCategory {
  id: string
  name: string
  bucket: Bucket
  min_pct: number | null
  max_pct: number | null
  note: string | null
}

export type IncomeGroupId = 'job' | 'investments' | 'other'

export interface IncomeGroup {
  id: IncomeGroupId
  name: string
  sources: { id: string; name: string }[]
}

export interface Transaction {
  id: string
  amount: number
  description: string
  category: string
  expense_type: 'income' | 'expense'
  income_source: string | null
  date: string
}

export interface TransactionSummary {
  total_income: number
  total_expense: number
  net: number
  by_category: Record<string, number>
  by_income_source: Record<string, number>
}

export interface HealthScore {
  score: number | null
  band: string | null
  complete: boolean
  components: { id: string; name: string; score: number | null; weight: number; detail: string }[]
  message: string | null
}

export interface BudgetMeta {
  income_groups: IncomeGroup[]
  categories: BudgetCategory[]
  bucket_targets_pct: Record<Bucket, number>
  emergency_fund_months: [number, number]
  return_assumptions: { max_months: number | null; annual_return_pct: number; label: string }[]
  default_step_up_pct: number
  actual_window_months: number
  llm_explanations: boolean
  disclaimer: string
}

export interface BudgetProfile {
  monthly_income: number
  estimates: Record<string, number>
  emergency_fund: number | null
  updated_at?: string
  warnings?: string[]
}

export type CategoryStatus = 'within' | 'over' | 'critical' | 'under' | 'below_target' | 'no_benchmark' | 'no_income'

export interface CategoryAssessment {
  category: string
  name: string
  bucket: Bucket
  amount: number
  pct_of_income: number | null
  benchmark_text: string
  status: CategoryStatus
  overspend_amount: number
  suggested_target: number | null
  estimate: number | null
  vs_estimate: number | null
  message: string
}

export interface BucketAssessment {
  bucket: Bucket
  amount: number
  pct_of_income: number | null
  target_pct: number
  target_amount: number
  difference: number
  status: 'within' | 'over' | 'below_target' | 'no_income'
}

export interface EmergencyFund {
  current: number | null
  monthly_essentials: number
  target_min: number
  target_max: number
  months_covered: number | null
  status: 'unknown' | 'missing' | 'partial' | 'adequate'
  shortfall: number
  message: string
}

export interface BudgetAnalysis {
  basis: 'actual' | 'estimated'
  filled_from_estimate: string[]
  income: number
  total_spend: number
  surplus: number
  savings_rate_pct: number | null
  categories: CategoryAssessment[]
  buckets: BucketAssessment[]
  emergency_fund: EmergencyFund
  overspent: string[]
  total_overspend: number
  warnings: string[]
}

export interface ComparisonRow {
  category: string
  name: string
  bucket: Bucket
  estimated: number
  actual: number | null
  difference: number | null
}

export interface BudgetOverview {
  has_profile: boolean
  profile: BudgetProfile | null
  profile_warnings: string[]
  actual: { has_data: boolean; partial: boolean; months: string[]; window_start: string }
  comparison: ComparisonRow[]
  analysis: BudgetAnalysis | null
}

export interface ImproveResult {
  focus: string
  basis: 'actual' | 'estimated'
  focus_category: CategoryAssessment | null
  summary: string
  other_overspends: CategoryAssessment[]
  emergency_fund: EmergencyFund
  disclaimer: string
}

export interface GoalInput {
  name: string
  target_amount: number
  horizon_months: number
  annual_return_pct?: number | null
  step_up_pct?: number | null
}

export interface GoalOption {
  type: 'step_up' | 'extend_timeline' | 'reduce_target' | 'free_up'
  message: string
  horizon_months?: number
  monthly?: number
  target_amount?: number
  cuts?: { category: string; name: string; amount: number }[]
  total?: number
}

export interface GoalPlan {
  name: string
  target_amount: number
  horizon_months: number
  horizon_text: string
  assumption: { annual_return_pct: number; is_default: boolean; label: string; step_up_pct: number; contribution_timing: string }
  flat: { monthly: number; total_invested: number; estimated_gains: number }
  step_up: {
    start_monthly: number
    final_monthly: number
    schedule: { year: number; monthly: number; months: number }[]
    total_invested: number
    estimated_gains: number
  }
  affordability: {
    status: 'affordable' | 'not_affordable' | 'unknown'
    monthly_surplus: number | null
    gap?: number
    message: string
    options: GoalOption[]
  }
  summary: string
  notes: string[]
  disclaimer: string
}

export interface SavedGoal extends GoalInput {
  id: string
  created_at: string
  plan: GoalPlan
}

export interface GoalsList {
  items: SavedGoal[]
  combined: { total_flat_monthly: number; monthly_surplus: number; fits: boolean; message: string } | null
  disclaimer: string
}

export const budgetApi = {
  meta: () => apiGet<BudgetMeta>('/api/v1/budget/categories'),
  overview: () => apiGet<BudgetOverview>('/api/v1/budget/overview'),
  saveProfile: (body: BudgetProfile) => apiPut<BudgetProfile>('/api/v1/budget/profile', body),
  improve: (focus: string, basis: Basis = 'auto') =>
    apiGet<ImproveResult>(`/api/v1/budget/improve?focus=${encodeURIComponent(focus)}&basis=${basis}`),
  goals: () => apiGet<GoalsList>('/api/v1/budget/goals'),
  previewGoal: (body: GoalInput, goalId?: string | null) =>
    apiPost<GoalPlan>(`/api/v1/budget/goals/preview${goalId ? `?goal_id=${encodeURIComponent(goalId)}` : ''}`, body),
  updateGoal: (id: string, body: GoalInput) => apiPut<SavedGoal>(`/api/v1/budget/goals/${encodeURIComponent(id)}`, body),
  healthScore: () => apiGet<HealthScore>('/api/v1/budget/health-score'),
  createGoal: (body: GoalInput) => apiPost<SavedGoal>('/api/v1/budget/goals', body),
  deleteGoal: (id: string) => apiDelete(`/api/v1/budget/goals/${encodeURIComponent(id)}`),
  explain: (body: { kind: 'improve' | 'goal'; focus?: string; goal_id?: string; basis?: Basis }) =>
    apiPost<{ text: string; source: 'template' | 'llm' }>('/api/v1/budget/explain', body),
}
