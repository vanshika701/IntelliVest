import { useState } from 'react'
import { Bot } from 'lucide-react'
import { blockchainApi, type ChainTask } from '../../api/blockchain'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import type { Contracts } from '../../lib/chain/wallet'
import { FUNDS, fromUnits, type FundLabel } from '../../lib/chain/mandate'
import type { VaultState } from './useVaultState'
import { ActionMessage, Card, label, muted, useAction } from './shared'

const STATE_TEXT: Record<ChainTask['state'], string> = {
  queued: 'Queued',
  opening: 'Opening on chain',
  evidence: 'Collecting evidence',
  proposing: 'Advisor deciding',
  submitted: 'Waiting for the chain',
  pending_user: 'Needs your approval',
  executed: 'Executed',
  rejected: 'Rejected',
  no_trade: 'No trade proposed',
  expired: 'Expired',
  failed: 'Failed',
}

const REASON_TEXT: Record<string, string> = {
  USER_DECLINED: 'you declined it',
  NO_DATA_NOT_ALLOWED: 'evidence was missing and your mandate rejects that',
  MISSING_EVIDENCE: 'a required evidence step was missing',
  OVER_TRADE_CAP: 'it was above your per-trade cap',
  OVER_DAILY_CAP: 'it was above your daily cap',
  OVER_MONTHLY_CAP: 'it was above your 30-day cap',
  OVER_EQUITY_LIMIT: 'it would take equity above your limit',
  STALE_PRICE: 'the test price was out of date',
  AI_PAUSED: 'the AI is paused',
  MODEL_NOT_ACCEPTED: 'your mandate does not accept that model version',
  EXPIRED: 'it ran out of time',
}

const units = (s: string | null) => (s ? fromUnits(BigInt(s)).toLocaleString('en-IN', { maximumFractionDigits: 4 }) : '0')

/** AI trade requests, what the vault decided, and the evidence behind each. */
export function AiTradesCard({ contracts, state, tasks, onChange }: {
  contracts: Contracts
  state: VaultState
  tasks: ChainTask[]
  onChange: () => void
}) {
  const { busy, error, done, run } = useAction()
  const [fund, setFund] = useState<FundLabel>('tEquityFund')
  const [ticker, setTicker] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  const vault = contracts.vault(state.vault!)

  const act = async (name: string, action: () => Promise<unknown>, success: string) => {
    if (await run(name, action, success)) onChange()
  }

  return (
    <Card id="ai-heading" icon={Bot} title="AI trades"
      aside={<span className={muted}>{state.aiPaused ? 'AI paused' : 'AI allowed'}</span>}>
      <p className={muted}>
        Uses a <strong>mock advisor</strong> for now: results are for testing the contracts, not advice.
      </p>
      <div className="flex flex-wrap items-end gap-2">
        <label>
          <span className={label}>Fund</span>
          <select value={fund} onChange={(e) => setFund(e.target.value as FundLabel)} aria-label="Fund for the AI trade"
            className="mt-1 block h-10 rounded-md border border-[var(--color-border-strong)] bg-transparent px-2 text-sm text-[var(--color-text-primary)]">
            {FUNDS.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </label>
        <label>
          <span className={label}>Stock for evidence (optional)</span>
          <Input className="mt-1 w-40" value={ticker} placeholder="RELIANCE" onChange={(e) => setTicker(e.target.value.toUpperCase())} />
        </label>
        <Button disabled={busy !== null || state.aiPaused || !state.mandateActive}
          onClick={() => act('request', () => blockchainApi.createTask(fund, ticker || null), 'Requested. The worker runs it in the background.')}>
          {busy === 'request' ? 'Requesting…' : 'Ask the AI'}
        </Button>
        {state.aiPaused ? (
          <Button variant="outline" disabled={busy !== null}
            onClick={() => act('resume', async () => (await vault.setAiPaused(false)).wait(), 'AI trading resumed.')}>Resume AI</Button>
        ) : (
          <Button variant="danger" disabled={busy !== null}
            onClick={() => act('revoke', async () => (await vault.setAiPaused(true)).wait(), 'AI trading paused. You can still withdraw and trade yourself.')}>
            Revoke AI
          </Button>
        )}
      </div>
      {!state.mandateActive && <p className={muted}>Sign a mandate before asking the AI.</p>}
      <ActionMessage error={error} done={done} />

      {tasks.length === 0 ? (
        <p className={muted}>No AI trades yet.</p>
      ) : (
        <ul className="divide-y divide-[var(--color-border-subtle)]">
          {tasks.map((t) => (
            <li key={t.id} className="py-3">
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-sm font-medium text-[var(--color-text-primary)]">{t.fund}{t.ticker ? ` · ${t.ticker}` : ''}</span>
                <span className="rounded bg-[var(--color-background-tertiary)] px-2 py-0.5 text-xs text-[var(--color-text-secondary)]">{STATE_TEXT[t.state]}</span>
                {t.proposal && (
                  <span className="text-sm text-[var(--color-text-secondary)]">
                    {t.proposal.side} {units(t.proposal.amount)} {t.proposal.side === 'BUY' ? 'tINR' : 'units'} · confidence {t.proposal.confidence / 100}%
                  </span>
                )}
                {t.state === 'pending_user' && t.task_id && (
                  <span className="flex gap-2">
                    <Button size="sm" variant="success" disabled={busy !== null}
                      onClick={() => act('approve', async () => (await contracts.tasks.approve(t.task_id)).wait(), 'Approved. Every limit was checked again.')}>Approve</Button>
                    <Button size="sm" variant="outline" disabled={busy !== null}
                      onClick={() => act('decline', async () => (await contracts.tasks.decline(t.task_id)).wait(), 'Declined.')}>Decline</Button>
                  </span>
                )}
                <button type="button" className="ml-auto text-xs text-[var(--color-brand)]" onClick={() => setOpen(open === t.id ? null : t.id)}
                  aria-expanded={open === t.id}>
                  {open === t.id ? 'Hide evidence' : 'Evidence'}
                </button>
              </div>
              {t.state === 'rejected' && t.reason && (
                <p className="mt-1 text-xs text-[var(--color-text-muted)]">Rejected because {REASON_TEXT[t.reason] ?? t.reason}.</p>
              )}
              {t.state === 'executed' && <p className="mt-1 text-xs text-[var(--color-text-muted)]">Received {units(t.amount_out)}.</p>}
              {t.state === 'failed' && t.last_error && <p className="mt-1 text-xs text-[var(--color-losses)]">{t.last_error}</p>}
              {open === t.id && <EvidenceDetails task={t} />}
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function EvidenceDetails({ task }: { task: ChainTask }) {
  return (
    <div className="mt-2 space-y-2 rounded-lg bg-[var(--color-background-tertiary)] p-3 text-xs text-[var(--color-text-secondary)]">
      {task.task_id && <p>Task ID: <span className="break-all font-mono">{task.task_id}</span></p>}
      {task.evidence.length === 0 && <p>No evidence submitted.</p>}
      {task.evidence.map((e) => (
        <div key={e.step}>
          <p className="font-medium text-[var(--color-text-primary)]">
            {e.step === 'sentiment' ? 'News sentiment' : 'Stock prediction'}: {e.status}
            {e.status !== 'NO_DATA' && ` · score ${e.step === 'sentiment' ? e.score / 100 : `${e.score / 100}% chance up`}`}
          </p>
          {e.tx_hash && <p>Transaction: <span className="break-all font-mono">{e.tx_hash}</span></p>}
          <details>
            <summary className="cursor-pointer">Inputs and outputs (hashed on chain)</summary>
            <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap">{JSON.stringify({ inputs: e.inputs, outputs: e.outputs }, null, 2)}</pre>
          </details>
        </div>
      ))}
      {task.proposal && (
        <div>
          <p className="font-medium text-[var(--color-text-primary)]">
            Advisor: {task.proposal.model} v{task.proposal.model_version}{task.mock_advisor && ' (mock)'}
          </p>
          <p>{task.proposal.explanation.text}</p>
          <p>Minimum received: {units(task.proposal.minimum_received)}</p>
        </div>
      )}
    </div>
  )
}
