// Typed wrappers for /api/v1/investments (mock orders and SIPs).
import { apiGet, apiPost } from './client'
import type { InstrumentType } from './instruments'

export interface InvestmentAccount {
  id: string
  label: string
  kind: 'folio' | 'demat'
  supports: InstrumentType[]
  is_demo: boolean
}

export type InvestmentStatus = 'pending_payment' | 'completed' | 'pending_mandate' | 'active' | 'failed'

export interface Investment {
  id: string
  kind: 'one_time' | 'sip'
  status: InvestmentStatus
  instrument_id: string
  instrument_name: string
  instrument_type: InstrumentType
  amount: number
  account_id: string
  account_label: string
  price_at_order: number | null
  estimated_units: number | null
  day_of_month: number | null
  next_installment_date: string | null
  payment_reference: string | null
  failure_reason: string | null
  is_mock: boolean
  created_at: string
  updated_at: string
}

export interface PaymentResultIn {
  status: 'success' | 'failed'
  reference?: string | null
  failure_reason?: string | null
}

export interface Holding {
  instrument_id: string
  instrument_name: string
  instrument_type: InstrumentType
  invested: number
  current_value: number | null
  gain: number | null
  gain_pct: number | null
}

/** Totals cover only the holdings that could be valued. */
export interface Portfolio {
  invested: number
  current_value: number
  gain: number | null
  gain_pct: number | null
  unvalued_count: number
  holdings: Holding[]
}

export const investmentsApi = {
  portfolio: () => apiGet<Portfolio>('/api/v1/investments/portfolio'),
  accounts: (type: InstrumentType) =>
    apiGet<InvestmentAccount[]>(`/api/v1/investments/accounts?instrument_type=${type}`),
  list: () => apiGet<Investment[]>('/api/v1/investments'),
  createOneTime: (body: { instrument_id: string; amount: number; account_id: string }) =>
    apiPost<Investment>('/api/v1/investments/one-time', body),
  createSip: (body: { instrument_id: string; amount: number; account_id: string; day_of_month: number }) =>
    apiPost<Investment>('/api/v1/investments/sip', body),
  recordPaymentResult: (id: string, body: PaymentResultIn) =>
    apiPost<Investment>(`/api/v1/investments/${encodeURIComponent(id)}/payment-result`, body),
}
