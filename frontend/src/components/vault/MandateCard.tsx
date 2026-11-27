import { useState } from 'react'
import { ScrollText } from 'lucide-react'
import type { ModelVersion } from '../../api/blockchain'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import type { Contracts } from '../../lib/chain/wallet'
import {
  FUNDS, defaultMandateForm, fromMandate, prefillMandate, toMandate, validateMandate,
  type FundLabel, type MandateForm, type Prefill,
} from '../../lib/chain/mandate'
import type { VaultState } from './useVaultState'
import { ActionMessage, Card, label, muted, useAction } from './shared'

const fundNames: Record<FundLabel, string> = { tEquityFund: 'Equity fund', tDebtFund: 'Debt fund', tGoldFund: 'Gold fund' }

const FIELDS: { key: keyof MandateForm; text: string; hint?: string; type?: string }[] = [
  { key: 'startDate', text: 'Start date', type: 'date' },
  { key: 'endDate', text: 'End date', type: 'date' },
  { key: 'perTradeCap', text: 'Most per trade (tINR)' },
  { key: 'dailyCap', text: 'Most per day (tINR)' },
  { key: 'monthlyCap', text: 'Most per 30 days (tINR)' },
  { key: 'userSignAbove', text: 'Ask me for trades above (tINR)' },
  { key: 'maxEquityPct', text: 'Most in equity (%)' },
  { key: 'maxSlippagePct', text: 'Most slippage (%)' },
  { key: 'maxLossPct', text: 'Pause AI after a loss of (%)' },
  { key: 'maxTradesPerDay', text: 'Most AI trades per day' },
  { key: 'confidenceThresholdPct', text: 'Ask me when AI confidence is below (%)' },
]

/** The terms the vault enforces on every AI trade. Signed by the owner's
 * wallet; IntelliVest has no way to change them. */
export function MandateCard({ contracts, state, models, prefill, onChange }: {
  contracts: Contracts
  state: VaultState
  models: ModelVersion[]
  prefill: Prefill
  onChange: () => void
}) {
  const { busy, error, done, run } = useAction()
  // The signed terms when there are some; otherwise suggestions. The page
  // remounts this card (via `key`) when either changes.
  const [form, setForm] = useState<MandateForm>(() =>
    state.mandate ? fromMandate(state.mandate, state.allowedFunds) : prefillMandate(defaultMandateForm(), prefill),
  )
  const [errors, setErrors] = useState<Record<string, string>>({})
  const prefilledFrom = [prefill.goal && `goal "${prefill.goal.name}"`, prefill.plan && 'portfolio plan'].filter(Boolean)

  const set = (key: keyof MandateForm, value: string | boolean) => setForm((f) => ({ ...f, [key]: value }))
  const toggleFund = (fund: FundLabel) =>
    setForm((f) => ({ ...f, funds: f.funds.includes(fund) ? f.funds.filter((x) => x !== fund) : [...f.funds, fund] }))

  async function sign() {
    const found = validateMandate(form)
    setErrors(found)
    if (Object.keys(found).length) return
    const funds = await Promise.all(form.funds.map((f) => contracts.funds[f].getAddress()))
    const ok = await run('sign', async () => {
      const tx = await contracts.mandates.setMandate(state.vault, toMandate(form), funds, models.map((m) => m.key))
      await tx.wait()
    }, 'Mandate signed. The vault enforces it from now on.')
    if (ok) onChange()
  }

  async function revoke() {
    const ok = await run('revoke', async () => (await contracts.mandates.revokeMandate(state.vault)).wait(),
      'Mandate revoked. No AI trade can run until you sign a new one.')
    if (ok) onChange()
  }

  return (
    <Card id="mandate-heading" icon={ScrollText} title="Mandate"
      aside={<span className={muted}>{state.mandateActive ? 'Active' : state.mandate ? 'Not active' : 'Not signed'}</span>}>
      {!state.mandate && prefilledFrom.length > 0 && (
        <p className={muted}>Suggested from your {prefilledFrom.join(' and ')}. Change anything before signing.</p>
      )}
      <div className="grid gap-3 sm:grid-cols-3">
        {FIELDS.map(({ key, text, type }) => (
          <label key={key} className="block">
            <span className={label}>{text}</span>
            <Input className="mt-1" type={type ?? 'number'} min="0" step="any" value={form[key] as string}
              onChange={(e) => set(key, e.target.value)} aria-invalid={!!errors[key]} />
            {errors[key] && <span className="text-xs text-[var(--color-losses)]">{errors[key]}</span>}
          </label>
        ))}
      </div>

      <fieldset className="space-y-1">
        <legend className={label}>Funds the AI may trade</legend>
        <div className="flex flex-wrap gap-4">
          {FUNDS.map((fund) => (
            <label key={fund} className="flex items-center gap-2 text-sm text-[var(--color-text-primary)]">
              <input type="checkbox" checked={form.funds.includes(fund)} onChange={() => toggleFund(fund)} />
              {fundNames[fund]}
            </label>
          ))}
        </div>
        {errors.funds && <span className="text-xs text-[var(--color-losses)]">{errors.funds}</span>}
      </fieldset>

      <fieldset className="space-y-1">
        <legend className={label}>Evidence</legend>
        {([
          ['requireSentiment', 'Require news sentiment (FinBERT)'],
          ['requireStock', 'Require a stock prediction'],
          ['askUserOnNoData', 'If data is missing or not FinBERT, ask me (otherwise reject)'],
        ] as const).map(([key, text]) => (
          <label key={key} className="flex items-center gap-2 text-sm text-[var(--color-text-primary)]">
            <input type="checkbox" checked={form[key]} onChange={(e) => set(key, e.target.checked)} />
            {text}
          </label>
        ))}
      </fieldset>

      <div className="space-y-1">
        <p className={label}>Model versions you accept</p>
        {models.length === 0 ? (
          <p className={muted}>No model versions are registered yet.</p>
        ) : (
          <ul className="text-sm text-[var(--color-text-secondary)]">
            {models.map((m) => (
              <li key={m.key}>
                {m.step.replace('_', ' ')}: {m.name} v{m.version}
                {m.mock && <span className="ml-2 rounded bg-[var(--color-background-tertiary)] px-1.5 text-[10px] uppercase">mock</span>}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        <Button onClick={sign} disabled={busy !== null}>{busy === 'sign' ? 'Check your wallet…' : state.mandate ? 'Sign new terms' : 'Sign mandate'}</Button>
        {state.mandateActive && (
          <Button variant="outline" onClick={revoke} disabled={busy !== null}>{busy === 'revoke' ? 'Waiting…' : 'Revoke mandate'}</Button>
        )}
      </div>
      <ActionMessage error={error} done={done} />
    </Card>
  )
}
