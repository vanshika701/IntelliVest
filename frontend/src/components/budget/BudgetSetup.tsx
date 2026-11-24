import { useState } from 'react'
import { AlertTriangle, X } from 'lucide-react'
import { budgetApi, type BudgetMeta, type BudgetProfile, type Bucket } from '../../api/budget'
import { checkSetup } from '../../lib/budget'
import { formatINR } from '../../lib/format'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'

const BUCKET_LABEL: Record<Bucket, string> = { needs: 'Needs', wants: 'Wants', savings: 'Savings' }

interface Props {
  meta: BudgetMeta
  initial: BudgetProfile | null
  onSaved: () => void
  onClose: () => void
}

/** Two-step setup: income (+ emergency fund), then a monthly estimate per category. */
export function BudgetSetup({ meta, initial, onSaved, onClose }: Props) {
  const [step, setStep] = useState<1 | 2>(1)
  const [income, setIncome] = useState(initial ? String(initial.monthly_income) : '')
  const [emergency, setEmergency] = useState(initial?.emergency_fund != null ? String(initial.emergency_fund) : '')
  const [estimates, setEstimates] = useState<Record<string, string>>(() =>
    Object.fromEntries(meta.categories.map((c) => [c.id, initial?.estimates[c.id] ? String(initial.estimates[c.id]) : ''])),
  )
  const [touched, setTouched] = useState(false)
  const [saving, setSaving] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)

  const check = checkSetup(income, estimates, emergency)
  const step1Errors = check.errors.income || check.errors.emergency_fund
  const incomeValue = Number(income || 0)

  async function save() {
    setTouched(true)
    if (Object.keys(check.errors).length) return
    setSaving(true)
    setServerError(null)
    try {
      await budgetApi.saveProfile({
        monthly_income: incomeValue,
        emergency_fund: emergency.trim() === '' ? null : Number(emergency),
        estimates: Object.fromEntries(Object.entries(estimates).map(([k, v]) => [k, Number(v || 0)])),
      })
      onSaved()
    } catch (e) {
      setServerError(e instanceof Error ? e.message : 'Could not save your budget')
    } finally {
      setSaving(false)
    }
  }

  const fieldError = (key: string) =>
    touched && check.errors[key] ? (
      <p className="text-xs text-[var(--color-losses)] mt-1" role="alert">{check.errors[key]}</p>
    ) : null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4" role="dialog" aria-modal="true" aria-labelledby="budget-setup-title">
      <div className="bg-[var(--color-background-secondary)] border border-[var(--color-border-subtle)] rounded-xl w-full max-w-lg shadow-2xl max-h-[90vh] flex flex-col">
        <div className="flex items-start justify-between p-6 pb-3">
          <div>
            <h3 id="budget-setup-title" className="text-xl font-bold text-[var(--color-text-primary)]">Set up your budget</h3>
            <p className="text-xs text-[var(--color-text-muted)] mt-1">Step {step} of 2 · amounts are per month, in ₹</p>
          </div>
          <button onClick={onClose} aria-label="Close" className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] p-1">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="overflow-y-auto px-6 pb-2 space-y-4">
          {step === 1 ? (
            <>
              <div>
                <label htmlFor="income" className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1 uppercase tracking-wider">Monthly take-home income (₹)</label>
                <Input id="income" inputMode="decimal" value={income} onChange={(e) => setIncome(e.target.value)} placeholder="e.g. 80000" autoFocus className="font-mono" />
                {fieldError('income')}
              </div>
              <div>
                <label htmlFor="emergency" className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1 uppercase tracking-wider">
                  Emergency savings you already have (₹) <span className="normal-case font-normal text-[var(--color-text-muted)]">optional</span>
                </label>
                <Input id="emergency" inputMode="decimal" value={emergency} onChange={(e) => setEmergency(e.target.value)} placeholder="e.g. 150000" className="font-mono" />
                <p className="text-xs text-[var(--color-text-muted)] mt-1">
                  Used to check the {meta.emergency_fund_months[0]}–{meta.emergency_fund_months[1]} month emergency-fund guideline.
                </p>
                {fieldError('emergency_fund')}
              </div>
            </>
          ) : (
            <>
              <p className="text-sm text-[var(--color-text-secondary)]">How much do you think you spend per month on each of these? Leave blank for ₹0.</p>
              <ul className="space-y-3">
                {meta.categories.map((c) => (
                  <li key={c.id}>
                    <div className="flex items-center gap-3">
                      <label htmlFor={`est-${c.id}`} className="flex-1 text-sm text-[var(--color-text-primary)]">
                        {c.name}
                        <span className="ml-2 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">{BUCKET_LABEL[c.bucket]}</span>
                      </label>
                      <Input
                        id={`est-${c.id}`}
                        inputMode="decimal"
                        value={estimates[c.id]}
                        onChange={(e) => setEstimates((prev) => ({ ...prev, [c.id]: e.target.value }))}
                        placeholder="0"
                        className="w-32 font-mono text-right"
                      />
                    </div>
                    {fieldError(c.id)}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>

        <div className="p-6 pt-4 border-t border-[var(--color-border-subtle)] space-y-3">
          {step === 2 && (
            <div className="flex justify-between text-sm">
              <span className="text-[var(--color-text-secondary)]">Total estimated</span>
              <span className="font-mono text-[var(--color-text-primary)]">
                {formatINR(check.total, 0)} <span className="text-[var(--color-text-muted)]">of {formatINR(incomeValue, 0)}</span>
              </span>
            </div>
          )}
          {check.warning && (
            <p className="flex items-start gap-2 text-xs text-[#fab219]" role="status">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" /> {check.warning}
            </p>
          )}
          {serverError && <p className="text-xs text-[var(--color-losses)]" role="alert">{serverError}</p>}
          <div className="flex gap-3">
            {step === 1 ? (
              <>
                <Button type="button" variant="ghost" className="flex-1" onClick={onClose}>Cancel</Button>
                <Button type="button" className="flex-1" onClick={() => { setTouched(true); if (!step1Errors) { setTouched(false); setStep(2) } }}>Next</Button>
              </>
            ) : (
              <>
                <Button type="button" variant="ghost" className="flex-1" onClick={() => setStep(1)}>Back</Button>
                <Button type="button" className="flex-1" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save budget'}</Button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
