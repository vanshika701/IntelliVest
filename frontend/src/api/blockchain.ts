// Typed wrappers for /api/v1/blockchain (Phase 10). Funds never move through
// these calls: deposits, withdrawals, approvals and revokes go from the
// wallet to the contracts directly.
import { apiDelete, apiGet, apiPost } from './client'
import type { FundLabel } from '../lib/chain/mandate'

export interface ModelVersion {
  step: 'sentiment' | 'stock_prediction' | 'advisor'
  name: string
  version: string
  key: string
  mock: boolean
}

export interface BlockchainStatus {
  enabled: boolean
  chain_id?: number | null
  network?: string | null
  contracts?: Record<string, string>
  models?: ModelVersion[]
  privacy_notice: string
}

export interface WalletLink {
  address: string | null
  linked_at?: string | null
}

export type TaskState =
  | 'queued' | 'opening' | 'evidence' | 'proposing' | 'submitted'
  | 'pending_user' | 'executed' | 'rejected' | 'no_trade' | 'expired' | 'failed'

export interface EvidenceView {
  step: 'sentiment' | 'stock_prediction'
  status: 'OK' | 'NO_DATA' | 'FALLBACK'
  score: number
  inputs: Record<string, unknown>
  outputs: Record<string, unknown>
  tx_hash: string | null
}

export interface ChainTask {
  id: string
  fund: FundLabel
  ticker: string | null
  state: TaskState
  task_id: string | null
  vault: string | null
  outcome: string | null
  reason: string | null
  amount_out: string | null
  evidence: EvidenceView[]
  proposal: {
    model: string
    model_version: string
    side: 'BUY' | 'SELL'
    amount: string
    minimum_received: string
    confidence: number
    deadline: number
    explanation: { text: string; contributions: Record<string, unknown> }
  } | null
  last_error: string | null
  mock_advisor: boolean
  created_at: string
  updated_at: string
}

export const blockchainApi = {
  status: () => apiGet<BlockchainStatus>('/api/v1/blockchain/status'),
  wallet: () => apiGet<WalletLink>('/api/v1/blockchain/wallet'),
  challenge: (address: string) =>
    apiPost<{ message: string; expires_at: string }>('/api/v1/blockchain/wallet/challenge', { address }),
  verify: (address: string, signature: string) =>
    apiPost<WalletLink>('/api/v1/blockchain/wallet/verify', { address, signature }),
  unlink: () => apiDelete('/api/v1/blockchain/wallet'),
  tasks: () => apiGet<ChainTask[]>('/api/v1/blockchain/tasks'),
  createTask: (fund: FundLabel, ticker: string | null) =>
    apiPost<ChainTask>('/api/v1/blockchain/tasks', { fund, ticker }),
}
