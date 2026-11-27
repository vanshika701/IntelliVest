import { useState } from 'react'
import { Vault } from 'lucide-react'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import type { Contracts } from '../../lib/chain/wallet'
import { FUNDS, fromUnits, toUnits } from '../../lib/chain/mandate'
import type { VaultState } from './useVaultState'
import { ActionMessage, Card, label, muted, shortAddress, useAction } from './shared'

const FAUCET_AMOUNT = '10000'
const tokenNames = { tINR: 'tINR (cash)', tEquityFund: 'Equity fund', tDebtFund: 'Debt fund', tGoldFund: 'Gold fund' }
type Token = keyof typeof tokenNames

const fmt = (units: bigint) => fromUnits(units).toLocaleString('en-IN', { maximumFractionDigits: 2 })

/** Create the vault, get test tINR, deposit and withdraw. Withdrawing goes
 * from the wallet to the vault contract only; IntelliVest can't block it. */
export function VaultCard({ contracts, owner, state, onChange }: {
  contracts: Contracts
  owner: string
  state: VaultState
  onChange: () => void
}) {
  const { busy, error, done, run } = useAction()
  const [deposit, setDeposit] = useState('')
  const [withdrawToken, setWithdrawToken] = useState<Token>('tINR')
  const [withdraw, setWithdraw] = useState('')

  const act = async (name: string, action: () => Promise<unknown>, success: string) => {
    if (await run(name, action, success)) onChange()
  }
  const send = async (tx: Promise<any>) => (await tx).wait()

  if (!state.vault) {
    return (
      <Card id="vault-heading" icon={Vault} title="Your vault">
        <p className={muted}>
          A vault is a contract that only your wallet controls. IntelliVest can propose trades inside the limits
          you sign, but can never withdraw or move your tokens out.
        </p>
        <Button onClick={() => act('create', () => send(contracts.factory.createVault()), 'Vault created.')} disabled={busy !== null}>
          {busy === 'create' ? 'Creating…' : 'Create vault'}
        </Button>
        <ActionMessage error={error} done={done} />
      </Card>
    )
  }

  const vault = contracts.vault(state.vault)
  const amountOk = (v: string) => Number(v) > 0

  async function doDeposit() {
    const amount = toUnits(deposit)
    const allowance: bigint = await contracts.inr.allowance(owner, state.vault!)
    if (allowance < amount) await send(contracts.inr.approve(state.vault!, amount))
    await send(vault.deposit(amount))
    setDeposit('')
  }

  async function doWithdraw() {
    const token = withdrawToken === 'tINR' ? contracts.inr : contracts.funds[withdrawToken]
    await send(vault.withdraw(await token.getAddress(), toUnits(withdraw)))
    setWithdraw('')
  }

  return (
    <Card id="vault-heading" icon={Vault} title="Your vault" aside={<span className="font-mono text-xs text-[var(--color-text-muted)]">{shortAddress(state.vault)}</span>}>
      <dl className="grid gap-3 sm:grid-cols-4">
        <div>
          <dt className={label}>tINR (cash)</dt>
          <dd className="mt-1 text-lg font-semibold text-[var(--color-text-primary)]">{fmt(state.cash)}</dd>
        </div>
        {FUNDS.map((fund) => (
          <div key={fund}>
            <dt className={label}>{tokenNames[fund]}</dt>
            <dd className="mt-1 text-lg font-semibold text-[var(--color-text-primary)]">{fmt(state.units[fund])} units</dd>
            <dd className="text-xs text-[var(--color-text-muted)]">₹{fmt(state.prices[fund].value)} per unit (test price)</dd>
          </div>
        ))}
      </dl>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <p className={label}>In your wallet: {fmt(state.wallet)} tINR</p>
          <Button variant="outline" size="sm" disabled={busy !== null}
            onClick={() => act('faucet', () => send(contracts.inr.faucet(toUnits(FAUCET_AMOUNT))), `Added ${FAUCET_AMOUNT} test tINR to your wallet.`)}>
            {busy === 'faucet' ? 'Waiting…' : `Get ${FAUCET_AMOUNT} test tINR`}
          </Button>
          <label className="block">
            <span className={label}>Deposit tINR into the vault</span>
            <div className="mt-1 flex gap-2">
              <Input type="number" min="0" step="any" value={deposit} onChange={(e) => setDeposit(e.target.value)} aria-label="Deposit amount" />
              <Button disabled={busy !== null || !amountOk(deposit)} onClick={() => act('deposit', doDeposit, 'Deposited.')}>
                {busy === 'deposit' ? 'Waiting…' : 'Deposit'}
              </Button>
            </div>
          </label>
        </div>
        <div className="space-y-2">
          <span className={label}>Withdraw to your wallet (works even if IntelliVest is down)</span>
          <div className="flex gap-2">
            <select value={withdrawToken} onChange={(e) => setWithdrawToken(e.target.value as Token)} aria-label="Token to withdraw"
              className="h-10 rounded-md border border-[var(--color-border-strong)] bg-transparent px-2 text-sm text-[var(--color-text-primary)]">
              {(Object.keys(tokenNames) as Token[]).map((t) => <option key={t} value={t}>{tokenNames[t]}</option>)}
            </select>
            <Input type="number" min="0" step="any" value={withdraw} onChange={(e) => setWithdraw(e.target.value)} aria-label="Withdraw amount" />
            <Button variant="outline" disabled={busy !== null || !amountOk(withdraw)} onClick={() => act('withdraw', doWithdraw, 'Withdrawn to your wallet.')}>
              {busy === 'withdraw' ? 'Waiting…' : 'Withdraw'}
            </Button>
          </div>
        </div>
      </div>
      <ActionMessage error={error} done={done} />
    </Card>
  )
}
