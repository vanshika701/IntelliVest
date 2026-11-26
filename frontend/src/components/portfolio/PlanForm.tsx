import { useState } from 'react'
import type { SavedGoal } from '../../api/budget'
import type { RecommendationInput } from '../../api/portfolioPlan'
import { formatHorizon, type PlanErrors, type PlanForm as FormState, validatePlanForm, yearsToMonths } from '../../lib/portfolioPlan'
import { cn } from '../../lib/utils'
import { Button } from '../ui/Button'
import { FieldError } from '../ui/FieldError'
import { NumberInput } from '../ui/NumberInput'

const label = 'block text-xs font-medium text-[var(--color-text-secondary)] mb-1 uppercase tracking-wider'

interface Props {
  goals: SavedGoal[]
  saving: boolean
  error: string | null
  onSubmit: (input: RecommendationInput) => void
}

/** Amount and horizon (or a saved goal) for a recommendation. */
export function PlanForm({ goals, saving, error, onSubmit }: Props) {
  const [form, setForm] = useState<FormState>({ mode: 'horizon', years: '7', goalId: '', lumpSum: '', monthly: '' })
  const [useSentiment, setUseSentiment] = useState(true)
  const [errors, setErrors] = useState<PlanErrors>({})
  const set = (patch: Partial<FormState>) => setForm((f) => ({ ...f, ...patch }))

  function submit(e: React.FormEvent) {
    e.preventDefault()
    const found = validatePlanForm(form)
    setErrors(found)
    if (Object.keys(found).length) return
    onSubmit({
      ...(form.mode === 'horizon' ? { horizon_months: yearsToMonths(form.years) } : { goal_id: form.goalId }),
      lump_sum: Number(form.lumpSum || 0),
      monthly_sip: Number(form.monthly || 0),
      use_sentiment: useSentiment,
    })
  }

  return (
    <form onSubmit={submit} noValidate className="glass-card space-y-4 rounded-2xl p-5">
      <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">Build a portfolio plan</h2>

      <div role="group" aria-label="Plan for" className="flex w-fit gap-1 rounded-lg border border-[var(--color-border-subtle)] p-1">
        {(['horizon', 'goal'] as const).map((m) => (
          <button
            key={m}
            type="button"
            aria-pressed={form.mode === m}
            disabled={m === 'goal' && goals.length === 0}
            title={m === 'goal' && goals.length === 0 ? 'Save a goal on the Budgeting page first' : undefined}
            onClick={() => set({ mode: m })}
            className={cn('rounded-md px-3 py-1.5 text-xs font-medium disabled:opacity-40',
              form.mode === m ? 'bg-[var(--color-brand)] text-white' : 'text-[var(--color-text-secondary)]')}
          >
            {m === 'horizon' ? 'A time frame' : 'A saved goal'}
          </button>
        ))}
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        {form.mode === 'horizon' ? (
          <div>
            <label htmlFor="plan-years" className={label}>Years until you need it</label>
            <NumberInput id="plan-years" value={form.years} onValueChange={(v) => set({ years: v })} decimals={1}
              aria-invalid={!!errors.years} aria-describedby="plan-years-error" />
            <FieldError id="plan-years-error" message={errors.years} />
          </div>
        ) : (
          <div>
            <label htmlFor="plan-goal" className={label}>Goal</label>
            <select id="plan-goal" value={form.goalId} onChange={(e) => set({ goalId: e.target.value })}
              aria-invalid={!!errors.goalId} aria-describedby="plan-goal-error"
              className="h-10 w-full rounded-md border border-[var(--color-border-strong)] bg-[var(--color-background-secondary)] px-3 text-sm text-[var(--color-text-primary)]">
              <option value="">Choose…</option>
              {goals.map((g) => <option key={g.id} value={g.id}>{g.name} ({formatHorizon(g.horizon_months)})</option>)}
            </select>
            <FieldError id="plan-goal-error" message={errors.goalId} />
          </div>
        )}
        <div>
          <label htmlFor="plan-lump" className={label}>One-time amount (₹)</label>
          <NumberInput id="plan-lump" value={form.lumpSum} onValueChange={(v) => set({ lumpSum: v })} decimals={0}
            placeholder="0" aria-describedby="plan-amounts-error" />
        </div>
        <div>
          <label htmlFor="plan-monthly" className={label}>Monthly amount (₹)</label>
          <NumberInput id="plan-monthly" value={form.monthly} onValueChange={(v) => set({ monthly: v })} decimals={0}
            placeholder="0" aria-describedby="plan-amounts-error" />
        </div>
      </div>
      <FieldError id="plan-amounts-error" message={errors.amounts} />

      <label className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
        <input type="checkbox" checked={useSentiment} onChange={(e) => setUseSentiment(e.target.checked)} className="accent-[var(--color-brand)]" />
        Let recent news sentiment adjust stock weights slightly
      </label>

      {error && <p role="alert" className="text-sm text-[var(--color-losses)]">{error}</p>}
      <Button type="submit" disabled={saving}>{saving ? 'Building…' : 'Build plan'}</Button>
    </form>
  )
}
