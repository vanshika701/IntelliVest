import { useState } from 'react'
import { CalendarClock } from 'lucide-react'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import type { Contracts } from '../../lib/chain/wallet'
import { FUNDS, fromUnits, toUnits, type FundLabel } from '../../lib/chain/mandate'
import type { VaultState } from './useVaultState'
import { ActionMessage, Card, label, muted, useAction } from './shared'

const day = (s: number) => new Date(s * 1000).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })

/** A monthly buy the vault itself enforces. Rule-based, with no AI and no
 * evidence; anyone may trigger it on the day, but only for your amount. */
export function SipCard({ contracts, state, onChange }: {
  contracts: Contracts
  state: VaultState
  onChange: () => void
}) {
  const { busy, error, done, run } = useAction()
  const [fund, setFund] = useState<FundLabel>('tEquityFund')
  const [amount, setAmount] = useState('1000')
  const [dayOfMonth, setDayOfMonth] = useState('5')
  const [slippage, setSlippage] = useState('1')
  const [months, setMonths] = useState('12')
  const vault = contracts.vault(state.vault!)

  const dayNum = Number(dayOfMonth)
  const valid = Number(amount) > 0 && Number.isInteger(dayNum) && dayNum >= 1 && dayNum <= 28 &&
    Number(slippage) >= 0 && Number(slippage) <= 100 && Number(months) >= 1

  async function setSip() {
    const end = Math.floor(Date.now() / 1000) + Math.round(Number(months) * 30.44 * 86_400)
    const address = await contracts.funds[fund].getAddress()
    const ok = await run('set', async () =>
      (await vault.setSip(address, toUnits(amount), dayNum, Math.round(Number(slippage) * 100), end)).wait(),
    'SIP set. The vault buys on that day each month while it holds enough tINR.')
    if (ok) onChange()
  }

  async function cancel() {
    if (await run('cancel', async () => (await vault.cancelSip()).wait(), 'SIP cancelled.')) onChange()
  }

  const current = state.sip
  const currentFund = current && FUNDS.find((f) => String(contracts.funds[f].target).toLowerCase() === current.fund.toLowerCase())

  return (
    <Card id="sip-heading" icon={CalendarClock} title="Vault SIP">
      {current ? (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-sm text-[var(--color-text-primary)]">
            {fromUnits(current.amount).toLocaleString('en-IN')} tINR into {currentFund ?? 'a fund'} on day {current.dayOfMonth} · next {day(current.nextRun)} · until {day(current.end)}
          </p>
          <Button variant="outline" size="sm" disabled={busy !== null} onClick={cancel}>Cancel SIP</Button>
        </div>
      ) : (
        <p className={muted}>No SIP set.</p>
      )}
      <div className="flex flex-wrap items-end gap-2">
        <label>
          <span className={label}>Fund</span>
          <select value={fund} onChange={(e) => setFund(e.target.value as FundLabel)} aria-label="SIP fund"
            className="mt-1 block h-10 rounded-md border border-[var(--color-border-strong)] bg-transparent px-2 text-sm text-[var(--color-text-primary)]">
            {FUNDS.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </label>
        <label><span className={label}>tINR each month</span><Input className="mt-1 w-32" type="number" min="0" value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
        <label><span className={label}>Day (1-28)</span><Input className="mt-1 w-20" type="number" min="1" max="28" value={dayOfMonth} onChange={(e) => setDayOfMonth(e.target.value)} /></label>
        <label><span className={label}>Max slippage %</span><Input className="mt-1 w-24" type="number" min="0" step="any" value={slippage} onChange={(e) => setSlippage(e.target.value)} /></label>
        <label><span className={label}>For months</span><Input className="mt-1 w-24" type="number" min="1" value={months} onChange={(e) => setMonths(e.target.value)} /></label>
        <Button disabled={busy !== null || !valid} onClick={setSip}>{busy === 'set' ? 'Waiting…' : current ? 'Replace SIP' : 'Set SIP'}</Button>
      </div>
      <ActionMessage error={error} done={done} />
    </Card>
  )
}
