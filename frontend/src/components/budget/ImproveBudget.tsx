import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, MessageSquareText, ShieldAlert, XCircle } from 'lucide-react'
import { budgetApi, type BudgetAnalysis, type BudgetMeta, type ImproveResult } from '../../api/budget'
import { formatINR } from '../../lib/format'
import { cn } from '../../lib/utils'
import { Button } from '../ui/Button'

const STATUS = {
  good: { color: '#0ca30c', Icon: CheckCircle2, label: 'On track' },
  warning: { color: '#fab219', Icon: AlertTriangle, label: 'Needs attention' },
  critical: { color: '#f43f5e', Icon: XCircle, label: 'Over' },
} as const

function StatusChip({ kind, label }: { kind: keyof typeof STATUS; label?: string }) {
  const { color, Icon, label: fallback } = STATUS[kind]
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-[var(--color-text-secondary)]">
      <Icon className="w-3.5 h-3.5" style={{ color }} aria-hidden /> {label ?? fallback}
    </span>
  )
}

interface Props {
  meta: BudgetMeta
  analysis: BudgetAnalysis
}

/** "Improve my budgeting": pick a category (or the whole budget) and see the rule-based verdict. */
export function ImproveBudget({ meta, analysis }: Props) {
  const [focus, setFocus] = useState('all')
  const [result, setResult] = useState<ImproveResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [explanation, setExplanation] = useState<string | null>(null)
  const [explaining, setExplaining] = useState(false)

  useEffect(() => {
    let cancelled = false
    budgetApi
      .improve(focus)
      .then((r) => { if (!cancelled) { setResult(r); setError(null) } })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load') })
    return () => { cancelled = true }
  }, [focus, analysis])

  async function explain() {
    setExplaining(true)
    try {
      const r = await budgetApi.explain({ kind: 'improve', focus })
      setExplanation(r.text)
    } catch {
      setExplanation(null)
    } finally {
      setExplaining(false)
    }
  }

  const fc = result?.focus_category
  const ef = analysis.emergency_fund

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 space-y-6">
        <div className="glass-card p-5 rounded-2xl space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <label htmlFor="focus" className="text-sm font-medium text-[var(--color-text-primary)]">What do you want to improve?</label>
            <select
              id="focus"
              value={focus}
              onChange={(e) => { setFocus(e.target.value); setExplanation(null) }}
              className="h-9 rounded-md border border-[var(--color-border-strong)] bg-[var(--color-background-secondary)] px-3 text-sm text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]"
            >
              <option value="all">My whole budget</option>
              {meta.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <span className="text-xs text-[var(--color-text-muted)] sm:ml-auto">
              Based on {analysis.basis === 'actual' ? 'your logged expenses' : 'your estimates'}
            </span>
          </div>

          {analysis.filled_from_estimate.length > 0 && (
            <p className="text-xs text-[var(--color-text-muted)]">Using your estimates for categories without complete logs: {analysis.filled_from_estimate.join(', ')}.</p>
          )}
          {error && <p className="text-sm text-[var(--color-losses)]">{error}</p>}
          {result && (
            <>
              {fc && (
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                  {fc.status === 'over' || fc.status === 'critical' ? (
                    <StatusChip kind="critical" label={fc.status === 'critical' ? 'Critical' : 'Over benchmark'} />
                  ) : fc.status === 'below_target' ? (
                    <StatusChip kind="warning" label="Below target" />
                  ) : fc.status === 'no_benchmark' || fc.status === 'no_income' ? null : (
                    <StatusChip kind="good" label="Within guideline" />
                  )}
                  {fc.pct_of_income != null && <span className="text-xs text-[var(--color-text-muted)]">{fc.pct_of_income}% of income · guideline {fc.benchmark_text}</span>}
                </div>
              )}
              <p className="text-[var(--color-text-primary)] leading-relaxed">{result.summary}</p>
              {fc?.suggested_target != null && (fc.status === 'over' || fc.status === 'critical') && (
                <div className="grid grid-cols-3 gap-3 text-center">
                  {[
                    ['Now', formatINR(fc.amount, 0)],
                    ['Overspend', formatINR(fc.overspend_amount, 0)],
                    ['Target', formatINR(fc.suggested_target, 0)],
                  ].map(([k, v]) => (
                    <div key={k} className="rounded-lg bg-[var(--color-background-tertiary)] p-3">
                      <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">{k}</p>
                      <p className="font-mono text-[var(--color-text-primary)] mt-0.5">{v}<span className="text-xs text-[var(--color-text-muted)]">/mo</span></p>
                    </div>
                  ))}
                </div>
              )}

              {result.other_overspends.length > 0 && (
                <div>
                  <h4 className="text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)] mb-2">
                    {fc ? 'Also over benchmark' : 'Biggest overspends'}
                  </h4>
                  <ul className="space-y-2">
                    {result.other_overspends.map((o) => (
                      <li key={o.category} className="flex items-center justify-between gap-3 text-sm">
                        <span className="text-[var(--color-text-primary)]">{o.name}</span>
                        <span className="text-xs text-[var(--color-text-muted)]">{o.pct_of_income}% vs {o.benchmark_text}</span>
                        <span className="font-mono text-[var(--color-losses)]">+{formatINR(o.overspend_amount, 0)}/mo</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="pt-2 border-t border-[var(--color-border-subtle)]">
                {explanation ? (
                  <p className="text-sm text-[var(--color-text-secondary)] whitespace-pre-line">{explanation}</p>
                ) : (
                  meta.llm_explanations && (
                    <Button variant="ghost" size="sm" onClick={explain} disabled={explaining}>
                      <MessageSquareText className="w-4 h-4 mr-1.5" /> {explaining ? 'Writing…' : 'Explain in plain words'}
                    </Button>
                  )
                )}
              </div>
            </>
          )}
        </div>

        <div className="glass-card p-5 rounded-2xl">
          <h3 className="text-sm font-medium text-[var(--color-text-primary)] mb-1">50 / 30 / 20 check</h3>
          <p className="text-xs text-[var(--color-text-muted)] mb-4">Needs, wants and savings as a share of take-home income. Savings = income left after needs and wants.</p>
          <ul className="space-y-4">
            {analysis.buckets.map((b) => {
              const pct = b.pct_of_income ?? 0
              const bad = b.status === 'over' || b.status === 'below_target'
              return (
                <li key={b.bucket}>
                  <div className="flex justify-between text-sm mb-1.5">
                    <span className="capitalize text-[var(--color-text-primary)]">{b.bucket}</span>
                    <span className="text-[var(--color-text-secondary)]">
                      <span className="font-mono text-[var(--color-text-primary)]">{b.pct_of_income ?? '—'}%</span> · target {b.bucket === 'savings' ? '≥' : '≤'} {b.target_pct}% · {formatINR(b.amount, 0)}
                    </span>
                  </div>
                  <div className="relative h-2 rounded-full bg-[var(--color-background-tertiary)]" aria-hidden>
                    <div className={cn('h-2 rounded-full')} style={{ width: `${Math.min(pct, 100)}%`, backgroundColor: bad ? STATUS.critical.color : '#3987e5' }} />
                    <div className="absolute -top-1 h-4 w-0.5 bg-[var(--color-text-secondary)]" style={{ left: `${b.target_pct}%` }} />
                  </div>
                  {bad && (
                    <p className="text-xs text-[var(--color-text-muted)] mt-1">
                      {b.status === 'over' ? `${formatINR(b.difference, 0)}/month over the guideline` : `${formatINR(-b.difference, 0)}/month short of the target`}
                    </p>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      </div>

      <div className="space-y-6">
        <div className="glass-card p-5 rounded-2xl">
          <div className="flex items-center gap-2 mb-2">
            <ShieldAlert className="w-4 h-4 text-[var(--color-text-secondary)]" />
            <h3 className="text-sm font-medium text-[var(--color-text-primary)]">Emergency fund</h3>
          </div>
          <div className="mb-2">
            {ef.status === 'adequate' && <StatusChip kind="good" label="Adequate" />}
            {ef.status === 'partial' && <StatusChip kind="warning" label="Partial" />}
            {ef.status === 'missing' && <StatusChip kind="critical" label="Missing" />}
          </div>
          <p className="text-sm text-[var(--color-text-secondary)]">{ef.message}</p>
        </div>

        <div className="glass-card p-5 rounded-2xl text-sm space-y-2">
          <div className="flex justify-between"><span className="text-[var(--color-text-secondary)]">Income</span><span className="font-mono">{formatINR(analysis.income, 0)}</span></div>
          <div className="flex justify-between"><span className="text-[var(--color-text-secondary)]">Needs + wants</span><span className="font-mono">{formatINR(analysis.total_spend, 0)}</span></div>
          <div className="flex justify-between border-t border-[var(--color-border-subtle)] pt-2">
            <span className="text-[var(--color-text-secondary)]">Monthly surplus</span>
            <span className={cn('font-mono', analysis.surplus < 0 && 'text-[var(--color-losses)]')}>{analysis.surplus < 0 ? '−' : ''}{formatINR(Math.abs(analysis.surplus), 0)}</span>
          </div>
          {analysis.warnings.map((w) => <p key={w} className="text-xs text-[#fab219] pt-1">{w}</p>)}
        </div>
      </div>
    </div>
  )
}
