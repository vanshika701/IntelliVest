import { useEffect, useState } from 'react'
import { ZeroAddress } from 'ethers'
import type { Contracts } from '../../lib/chain/wallet'
import { FUNDS, type FundLabel, type Mandate } from '../../lib/chain/mandate'

export interface VaultState {
  vault: string | null
  cash: bigint
  wallet: bigint // tINR in the wallet, not the vault
  units: Record<FundLabel, bigint>
  prices: Record<FundLabel, { value: bigint; updatedAt: number }>
  aiPaused: boolean
  mandateActive: boolean
  mandate: Mandate | null
  allowedFunds: FundLabel[]
  sip: { fund: string; amount: bigint; maxSlippageBps: number; dayOfMonth: number; nextRun: number; end: number } | null
}

/** Reads the vault from the chain (not the backend). Re-reads when `refresh` changes. */
export function useVaultState(contracts: Contracts | null, owner: string | null, refresh: number) {
  const [state, setState] = useState<VaultState | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!contracts || !owner) return
    let cancelled = false
    load(contracts, owner).then(
      (s) => !cancelled && (setState(s), setError(null)),
      () => !cancelled && setError('Could not read your vault from the chain. Is the network running?'),
    )
    return () => {
      cancelled = true
    }
  }, [contracts, owner, refresh])

  return { state, error }
}

async function load(c: Contracts, owner: string): Promise<VaultState> {
  const address: string = await c.factory.vaultOf(owner)
  const wallet: bigint = await c.inr.balanceOf(owner)
  const prices = {} as VaultState['prices']
  for (const fund of FUNDS) {
    const [value, updatedAt] = await c.feed.price(await c.funds[fund].getAddress())
    prices[fund] = { value, updatedAt: Number(updatedAt) }
  }
  const empty = { tEquityFund: 0n, tDebtFund: 0n, tGoldFund: 0n }
  if (address === ZeroAddress) {
    return { vault: null, cash: 0n, wallet, units: empty, prices, aiPaused: false, mandateActive: false,
      mandate: null, allowedFunds: [], sip: null }
  }
  const vault = c.vault(address)
  const units = { ...empty }
  const allowedFunds: FundLabel[] = []
  for (const fund of FUNDS) {
    const token = c.funds[fund]
    units[fund] = await token.balanceOf(address)
    if (await c.mandates.fundAllowed(address, await token.getAddress())) allowedFunds.push(fund)
  }
  const mandateActive: boolean = await c.mandates.active(address)
  const m = await c.mandates.mandateOf(address)
  const sip = await vault.sip()
  return {
    vault: address,
    cash: await c.inr.balanceOf(address),
    wallet,
    units,
    prices,
    aiPaused: await vault.aiPaused(),
    mandateActive,
    mandate: Number(m.end) === 0 ? null : {
      start: m.start, end: m.end, perTradeCap: m.perTradeCap, dailyCap: m.dailyCap, monthlyCap: m.monthlyCap,
      userSignAbove: m.userSignAbove, maxEquityBps: Number(m.maxEquityBps), maxSlippageBps: Number(m.maxSlippageBps),
      maxLossBps: Number(m.maxLossBps), maxTradesPerDay: Number(m.maxTradesPerDay),
      confidenceThreshold: Number(m.confidenceThreshold), requireSentiment: m.requireSentiment,
      requireStock: m.requireStock, askUserOnNoData: m.askUserOnNoData,
    },
    allowedFunds,
    sip: sip.amount > 0n ? {
      fund: sip.fund, amount: sip.amount, maxSlippageBps: Number(sip.maxSlippageBps),
      dayOfMonth: Number(sip.dayOfMonth), nextRun: Number(sip.nextRun), end: Number(sip.end),
    } : null,
  }
}
