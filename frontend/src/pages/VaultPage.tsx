import { useCallback, useMemo, useState } from 'react'
import { ShieldAlert } from 'lucide-react'
import { blockchainApi } from '../api/blockchain'
import { budgetApi } from '../api/budget'
import { portfolioPlanApi } from '../api/portfolioPlan'
import { useApi } from '../hooks/useApi'
import { connectWallet, contractsFor, type Connection } from '../lib/chain/wallet'
import type { Prefill } from '../lib/chain/mandate'
import { Skeleton } from '../components/ui/Skeleton'
import { WalletCard } from '../components/vault/WalletCard'
import { VaultCard } from '../components/vault/VaultCard'
import { MandateCard } from '../components/vault/MandateCard'
import { AiTradesCard } from '../components/vault/AiTradesCard'
import { SipCard } from '../components/vault/SipCard'
import { useVaultState } from '../components/vault/useVaultState'

const optional = <T,>(p: Promise<T>) => p.catch(() => null)

/** Phase 10: a vault the user owns, AI trades checked against the user's
 * signed mandate, and a vault SIP. Test tokens only. */
export function VaultPage() {
  const status = useApi('blockchain-status', blockchainApi.status)
  const enabled = status.data?.enabled === true
  const link = useApi(enabled ? 'blockchain-wallet' : null, blockchainApi.wallet)
  const tasks = useApi(enabled ? 'blockchain-tasks' : null, blockchainApi.tasks, 5000)
  const goals = useApi(enabled ? 'vault-goals' : null, () => optional(budgetApi.goals()))
  const plan = useApi(enabled ? 'vault-plan' : null, () => optional(portfolioPlanApi.latest()))

  const [connection, setConnection] = useState<Connection | null>(null)
  const [refresh, setRefresh] = useState(0)
  const bump = useCallback(() => setRefresh((n) => n + 1), [])

  const contracts = useMemo(
    () => (connection && status.data?.contracts ? contractsFor(connection.signer, status.data.contracts) : null),
    [connection, status.data],
  )
  const vault = useVaultState(contracts, connection?.address ?? null, refresh)

  const prefill = useMemo<Prefill>(() => {
    const goal = goals.data?.items?.[0]
    const rec = plan.data
    return {
      goal: goal ? { name: goal.name, monthly: goal.plan.flat.monthly, horizonMonths: goal.horizon_months } : null,
      plan: rec ? { profile: rec.allocation.profile, equityPct: rec.allocation.equity_pct } : null,
    }
  }, [goals.data, plan.data])

  if (status.loading) return <Skeleton className="h-40 w-full" />
  if (!enabled) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">
        The blockchain vault is turned off on this server.
      </p>
    )
  }

  const onChange = () => {
    bump()
    tasks.reload()
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">AI vault</h1>
        <p className="text-sm text-[var(--color-text-muted)]">{status.data?.network} · test tokens only, no real money</p>
      </header>

      <div role="note" className="flex gap-3 rounded-xl border border-[var(--color-border-subtle)] p-4 text-sm text-[var(--color-text-secondary)]">
        <ShieldAlert className="h-5 w-5 shrink-0" aria-hidden="true" />
        <p>{status.data?.privacy_notice}</p>
      </div>

      <WalletCard
        connection={connection}
        link={link.data}
        onConnect={async () => setConnection(await connectWallet(status.data!.chain_id!))}
        onLinkChange={link.reload}
      />

      {contracts && connection && vault.error && <p role="alert" className="text-sm text-[var(--color-losses)]">{vault.error}</p>}
      {contracts && connection && vault.state && (
        <>
          <VaultCard contracts={contracts} owner={connection.address} state={vault.state} onChange={onChange} />
          {vault.state.vault && (
            <>
              <MandateCard
                key={[vault.state.mandate?.start, vault.state.mandate?.end, vault.state.allowedFunds.join(), prefill.goal?.name, prefill.plan?.equityPct].join('|')}
                contracts={contracts} state={vault.state} models={status.data?.models ?? []} prefill={prefill} onChange={onChange} />
              {link.data?.address ? (
                <AiTradesCard contracts={contracts} state={vault.state} tasks={tasks.data ?? []} onChange={onChange} />
              ) : (
                <p className="text-sm text-[var(--color-text-muted)]">Link your wallet to ask the AI for trades.</p>
              )}
              <SipCard contracts={contracts} state={vault.state} onChange={onChange} />
            </>
          )}
        </>
      )}
    </div>
  )
}
