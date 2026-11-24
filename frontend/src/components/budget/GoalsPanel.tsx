import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, Info, MessageSquareText, Target, Trash2 } from 'lucide-react'
import { budgetApi, type BudgetMeta, type GoalInput, type GoalPlan, type GoalsList } from '../../api/budget'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { toMonths, validateMoney } from '../../lib/budget'
import { formatINR } from '../../lib/format'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'

const label = 'block text-xs font-medium text-[var(--color-text-secondary)] mb-1 uppercase tracking-wider'

function goalErrors(name: string, target: string, months: number, ret: string, step: string): string | null {
  if (!name.trim()) return 'Give the goal a name'
  const t = validateMoney(target, { required: true })
  if (t) return `Target: ${t}`
  if (Number(target) <= 0) return 'Target must be more than ₹0'
  if (months < 1) return 'Horizon must be at least 1 month'
  if (months > 600) return 'Horizon can be at most 50 years'
  if (ret.trim() !== '' && (Number.isNaN(Number(ret)) || Number(ret) < 0 || Number(ret) > 30)) return 'Expected return must be 0–30%'
  if (step.trim() !== '' && (Number.isNaN(Number(step)) || Number(step) < 0 || Number(step) > 50)) return 'Step-up must be 0–50%'
  return null
}

/** Plan A vs Plan B, affordability and options. Shared by the preview and saved goals. */
export function PlanView({ plan }: { plan: GoalPlan }) {
  const a = plan.affordability
  return (
    <div className="space-y-4">
      <p className="text-[var(--color-text-primary)] leading-relaxed">{plan.summary}</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="rounded-xl border border-[var(--color-border-strong)] p-4">
          <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Plan A · Flat SIP</p>
          <p className="text-2xl font-bold font-mono mt-1">{formatINR(plan.flat.monthly, 0)}<span className="text-sm font-normal text-[var(--color-text-muted)]">/month</span></p>
          <p className="text-xs text-[var(--color-text-secondary)] mt-2">Same amount every month for {plan.horizon_text}.</p>
          <dl className="text-xs mt-3 space-y-1">
            <div className="flex justify-between"><dt className="text-[var(--color-text-muted)]">You invest</dt><dd className="font-mono">{formatINR(plan.flat.total_invested, 0)}</dd></div>
            <div className="flex justify-between"><dt className="text-[var(--color-text-muted)]">Estimated growth</dt><dd className="font-mono">{formatINR(plan.flat.estimated_gains, 0)}</dd></div>
          </dl>
        </div>
        <div className="rounded-xl border border-[var(--color-border-strong)] p-4">
          <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Plan B · Step-up SIP ({plan.assumption.step_up_pct}%/yr)</p>
          <p className="text-2xl font-bold font-mono mt-1">{formatINR(plan.step_up.start_monthly, 0)}<span className="text-sm font-normal text-[var(--color-text-muted)]">/month to start</span></p>
          <p className="text-xs text-[var(--color-text-secondary)] mt-2">
            {plan.step_up.schedule.length > 1
              ? `Rises each year, reaching ${formatINR(plan.step_up.final_monthly, 0)}/month in year ${plan.step_up.schedule.length}.`
              : 'No step-up within a single year.'}
          </p>
          <dl className="text-xs mt-3 space-y-1">
            <div className="flex justify-between"><dt className="text-[var(--color-text-muted)]">You invest</dt><dd className="font-mono">{formatINR(plan.step_up.total_invested, 0)}</dd></div>
            <div className="flex justify-between"><dt className="text-[var(--color-text-muted)]">Estimated growth</dt><dd className="font-mono">{formatINR(plan.step_up.estimated_gains, 0)}</dd></div>
          </dl>
          {plan.step_up.schedule.length > 1 && (
            <details className="mt-2 text-xs">
              <summary className="cursor-pointer text-[var(--color-text-secondary)]">Year-by-year amounts</summary>
              <ul className="mt-1 space-y-0.5 font-mono">
                {plan.step_up.schedule.map((r) => (
                  <li key={r.year} className="flex justify-between"><span>Year {r.year}{r.months < 12 ? ` (${r.months} mo)` : ''}</span><span>{formatINR(r.monthly, 0)}</span></li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </div>

      <p className="text-xs text-[var(--color-text-muted)]">
        Assumes {plan.assumption.annual_return_pct}% a year ({plan.assumption.label}), invested at the {plan.assumption.contribution_timing}.
      </p>

      <div className="rounded-xl bg-[var(--color-background-tertiary)] p-4 space-y-2">
        <p className="flex items-start gap-2 text-sm text-[var(--color-text-primary)]">
          {a.status === 'affordable' ? <CheckCircle2 className="w-4 h-4 mt-0.5 flex-shrink-0 text-[#0ca30c]" aria-hidden /> : <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0 text-[#fab219]" aria-hidden />}
          <span><span className="sr-only">{a.status === 'affordable' ? 'Fits: ' : 'Check: '}</span>{a.message}</span>
        </p>
        {a.options.length > 0 && (
          <ul className="list-disc pl-10 space-y-1 text-sm text-[var(--color-text-secondary)]">
            {a.options.map((o) => <li key={o.type}>{o.message}</li>)}
          </ul>
        )}
      </div>

      {plan.notes.map((n) => (
        <p key={n} className="flex items-start gap-2 text-xs text-[var(--color-text-secondary)]">
          <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" aria-hidden /> {n}
        </p>
      ))}
    </div>
  )
}

export function GoalsPanel({ meta, refreshKey }: { meta: BudgetMeta; refreshKey: number }) {
  const [name, setName] = useState('')
  const [target, setTarget] = useState('')
  const [years, setYears] = useState('3')
  const [months, setMonths] = useState('')
  const [ret, setRet] = useState('')
  const [step, setStep] = useState(String(meta.default_step_up_pct))
  const [preview, setPreview] = useState<GoalPlan | null>(null)
  const [goals, setGoals] = useState<GoalsList | null>(null)
  const [saving, setSaving] = useState(false)
  const [explanations, setExplanations] = useState<Record<string, string>>({})

  const horizon = toMonths(years, months)
  const error = goalErrors(name || 'x', target, horizon, ret, step)
  const input: GoalInput | null = error
    ? null
    : {
        name: name.trim() || 'My goal',
        target_amount: Number(target),
        horizon_months: horizon,
        annual_return_pct: ret.trim() === '' ? null : Number(ret),
        step_up_pct: step.trim() === '' ? null : Number(step),
      }
  const debouncedKey = useDebouncedValue(input ? JSON.stringify(input) : '', 300)

  useEffect(() => {
    if (!debouncedKey) return
    let cancelled = false
    budgetApi.previewGoal(JSON.parse(debouncedKey)).then((p) => { if (!cancelled) setPreview(p) }).catch(() => {})
    return () => { cancelled = true }
  }, [debouncedKey, refreshKey])

  function loadGoals() {
    budgetApi.goals().then(setGoals).catch(() => setGoals(null))
  }
  useEffect(loadGoals, [refreshKey])

  async function save() {
    if (!input || !name.trim()) return
    setSaving(true)
    try {
      await budgetApi.createGoal({ ...input, name: name.trim() })
      setName('')
      setTarget('')
      loadGoals()
    } finally {
      setSaving(false)
    }
  }

  async function remove(id: string) {
    if (!confirm('Delete this goal?')) return
    await budgetApi.deleteGoal(id)
    loadGoals()
  }

  async function explain(id: string) {
    const r = await budgetApi.explain({ kind: 'goal', goal_id: id })
    setExplanations((prev) => ({ ...prev, [id]: r.text }))
  }

  const defaultFor = meta.return_assumptions.find((r) => r.max_months == null || horizon <= r.max_months)

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="glass-card p-5 rounded-2xl space-y-4">
          <h3 className="text-sm font-medium text-[var(--color-text-primary)] flex items-center gap-2"><Target className="w-4 h-4" /> New savings goal</h3>
          <div>
            <label htmlFor="g-name" className={label}>Goal</label>
            <Input id="g-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Car" maxLength={80} />
          </div>
          <div>
            <label htmlFor="g-target" className={label}>Target amount (₹)</label>
            <Input id="g-target" inputMode="decimal" value={target} onChange={(e) => setTarget(e.target.value)} placeholder="e.g. 800000" className="font-mono" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="g-years" className={label}>Years</label>
              <Input id="g-years" inputMode="numeric" value={years} onChange={(e) => setYears(e.target.value)} className="font-mono" />
            </div>
            <div>
              <label htmlFor="g-months" className={label}>+ Months</label>
              <Input id="g-months" inputMode="numeric" value={months} onChange={(e) => setMonths(e.target.value)} placeholder="0" className="font-mono" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="g-ret" className={label}>Return % / yr</label>
              <Input id="g-ret" inputMode="decimal" value={ret} onChange={(e) => setRet(e.target.value)} placeholder={defaultFor ? String(defaultFor.annual_return_pct) : ''} className="font-mono" />
            </div>
            <div>
              <label htmlFor="g-step" className={label}>Step-up % / yr</label>
              <Input id="g-step" inputMode="decimal" value={step} onChange={(e) => setStep(e.target.value)} className="font-mono" />
            </div>
          </div>
          {defaultFor && ret.trim() === '' && <p className="text-xs text-[var(--color-text-muted)]">Default return for this horizon: {defaultFor.label}.</p>}
          {target && error && <p className="text-xs text-[var(--color-losses)]" role="alert">{error}</p>}
          <Button className="w-full" onClick={save} disabled={!input || !name.trim() || saving}>{saving ? 'Saving…' : 'Save goal'}</Button>
        </div>

        <div className="lg:col-span-2 glass-card p-5 rounded-2xl" aria-live="polite">
          {preview && input ? <PlanView plan={preview} /> : (
            <p className="text-sm text-[var(--color-text-muted)] py-10 text-center">Enter a target and horizon to see the SIP plans.</p>
          )}
        </div>
      </div>

      {goals && goals.items.length > 0 && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="font-semibold text-[var(--color-text-primary)]">Your goals</h3>
            {goals.combined && <p className="text-xs text-[var(--color-text-secondary)]">{goals.combined.message}</p>}
          </div>
          {goals.items.map((g) => (
            <div key={g.id} className="glass-card p-5 rounded-2xl">
              <div className="flex items-start justify-between gap-3 mb-3">
                <div>
                  <h4 className="font-semibold text-[var(--color-text-primary)]">{g.name}</h4>
                  <p className="text-xs text-[var(--color-text-muted)]">{formatINR(g.target_amount, 0)} in {g.plan.horizon_text}</p>
                </div>
                <div className="flex gap-1">
                  {meta.llm_explanations && !explanations[g.id] && (
                    <Button variant="ghost" size="sm" onClick={() => explain(g.id)} aria-label={`Explain ${g.name} in plain words`}>
                      <MessageSquareText className="w-4 h-4" />
                    </Button>
                  )}
                  <Button variant="ghost" size="sm" onClick={() => remove(g.id)} aria-label={`Delete ${g.name}`}><Trash2 className="w-4 h-4" /></Button>
                </div>
              </div>
              <PlanView plan={g.plan} />
              {explanations[g.id] && <p className="mt-3 text-sm text-[var(--color-text-secondary)] whitespace-pre-line">{explanations[g.id]}</p>}
            </div>
          ))}
        </div>
      )}

      <p className="text-xs text-[var(--color-text-muted)] flex items-start gap-2">
        <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" aria-hidden /> {meta.disclaimer}
      </p>
    </div>
  )
}
