// Typed wrappers for Phase 9: /api/v1/advisor.
import { apiGet, apiPost } from './client'

export type ModuleStatus = 'ok' | 'stale' | 'not_set_up' | 'unavailable' | 'not_built'

export interface ModuleResult {
  module: string
  label: string
  phase: number | null
  status: ModuleStatus
  as_of: string | null
  version: string | null
  facts: string[]
  reason: string | null
  elapsed_ms: number
}

export interface AdviceAction {
  id: string
  priority: number
  severity: 'high' | 'medium' | 'low'
  title: string
  detail: string
  facts: string[]
  contributors: string[]
  link: string
}

export interface SetupStep {
  module: string
  title: string
  detail: string
  link: string
}

export interface Advice {
  id: string
  actions: AdviceAction[]
  setup: SetupStep[]
  modules: ModuleResult[]
  modules_used: string[]
  modules_unavailable: string[]
  partial: boolean
  summary: { text: string; source: 'template' | 'llm' }
  version: string
  disclaimer: string
  created_at: string
}

export const advisorApi = {
  latest: () => apiGet<Advice>('/api/v1/advisor/advice/latest'),
  refresh: () => apiPost<Advice>('/api/v1/advisor/advice', {}),
}
