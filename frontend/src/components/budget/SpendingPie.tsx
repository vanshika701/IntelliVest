import { useMemo, useState } from 'react'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip as RechartsTooltip } from 'recharts'
import type { BudgetCategory, ComparisonRow } from '../../api/budget'
import { pieSlices, sliceCategories } from '../../lib/budget'
import { formatINR } from '../../lib/format'
import { cn } from '../../lib/utils'

type Mode = 'estimated' | 'actual'

interface Props {
  categories: BudgetCategory[]
  comparison: ComparisonRow[]
  hasActual: boolean
}

/** Monthly spending by category — the existing donut, now with an Estimated/Actual toggle. */
export function SpendingPie({ categories, comparison, hasActual }: Props) {
  const [mode, setMode] = useState<Mode>(hasActual ? 'actual' : 'estimated')
  const activeMode: Mode = hasActual ? mode : 'estimated'

  const { estimated, actual, sliceIds } = useMemo(() => {
    const est: Record<string, number> = {}
    const act: Record<string, number> = {}
    for (const r of comparison) {
      est[r.category] = r.estimated
      act[r.category] = r.actual ?? 0
    }
    return { estimated: est, actual: act, sliceIds: sliceCategories(categories, est, act) }
  }, [categories, comparison])

  const slices = pieSlices(categories, activeMode === 'actual' ? actual : estimated, sliceIds)
  const total = slices.reduce((s, x) => s + x.value, 0)

  return (
    <div className="glass-card p-5 rounded-2xl">
      <div className="flex items-center justify-between gap-2 mb-3 border-b border-[var(--color-border-subtle)] pb-2">
        <h3 className="text-sm font-medium text-[var(--color-text-primary)]">Monthly spending by category</h3>
        <div className="flex bg-[var(--color-background-tertiary)] rounded-md p-0.5 border border-[var(--color-border-strong)]" role="group" aria-label="Spending basis">
          {(['estimated', 'actual'] as Mode[]).map((m) => (
            <button
              key={m}
              type="button"
              disabled={m === 'actual' && !hasActual}
              title={m === 'actual' && !hasActual ? 'Log some expenses to see actual spending' : undefined}
              aria-pressed={activeMode === m}
              onClick={() => setMode(m)}
              className={cn(
                'px-2.5 py-1 text-xs font-medium rounded-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed',
                activeMode === m ? 'bg-[var(--color-brand)] text-white' : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]',
              )}
            >
              {m === 'estimated' ? 'Estimated' : 'Actual'}
            </button>
          ))}
        </div>
      </div>

      {slices.length === 0 ? (
        <p className="text-sm text-[var(--color-text-muted)] py-10 text-center">
          {activeMode === 'actual' ? 'No expenses logged in this period.' : 'No estimates yet.'}
        </p>
      ) : (
        <>
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={slices} cx="50%" cy="50%" innerRadius={60} outerRadius={85} paddingAngle={2} dataKey="value" nameKey="name" stroke="var(--color-background-secondary)" strokeWidth={2}>
                  {slices.map((s) => <Cell key={s.id} fill={s.color} />)}
                </Pie>
                <RechartsTooltip
                  formatter={(value) => `${formatINR(Number(value), 0)} (${((Number(value) / total) * 100).toFixed(0)}%)`}
                  contentStyle={{ backgroundColor: 'var(--color-background-secondary)', borderColor: 'var(--color-border-subtle)', borderRadius: '0.5rem', color: 'var(--color-text-primary)' }}
                  itemStyle={{ color: 'var(--color-text-primary)' }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <ul className="mt-3 space-y-1.5" aria-label="Legend">
            {slices.map((s) => (
              <li key={s.id} className="flex items-center gap-2 text-xs">
                <span className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ backgroundColor: s.color }} aria-hidden />
                <span className="flex-1 text-[var(--color-text-secondary)]">{s.name}</span>
                <span className="font-mono text-[var(--color-text-primary)]">{formatINR(s.value, 0)}</span>
                <span className="w-9 text-right text-[var(--color-text-muted)]">{((s.value / total) * 100).toFixed(0)}%</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

/** Per-category estimated vs actual table (also the accessible table view of the pie). */
export function EstimateVsActual({ comparison, hasActual, months }: { comparison: ComparisonRow[]; hasActual: boolean; months: string[] }) {
  const rows = comparison.filter((r) => r.estimated > 0 || (r.actual ?? 0) > 0)
  return (
    <div className="glass-card rounded-2xl overflow-hidden">
      <div className="px-5 py-4 border-b border-[var(--color-border-subtle)]">
        <h3 className="text-sm font-medium text-[var(--color-text-primary)]">Estimated vs actual (per month)</h3>
        <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
          {hasActual
            ? `Actual = average of ${months.length} month${months.length === 1 ? '' : 's'} with logged expenses (${months.join(', ')}).`
            : 'Log expenses to compare against your estimates.'}
        </p>
      </div>
      {rows.length === 0 ? (
        <p className="p-5 text-sm text-[var(--color-text-muted)]">Nothing to compare yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-[var(--color-text-muted)] uppercase tracking-wider">
                <th className="text-left font-medium px-5 py-2">Category</th>
                <th className="text-right font-medium px-3 py-2">Estimated</th>
                <th className="text-right font-medium px-3 py-2">Actual</th>
                <th className="text-right font-medium px-5 py-2">Difference</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border-subtle)]">
              {rows.map((r) => (
                <tr key={r.category}>
                  <td className="px-5 py-2 text-[var(--color-text-primary)]">{r.name}</td>
                  <td className="px-3 py-2 text-right font-mono text-[var(--color-text-secondary)]">{formatINR(r.estimated, 0)}</td>
                  <td className="px-3 py-2 text-right font-mono text-[var(--color-text-secondary)]">{r.actual == null ? '—' : formatINR(r.actual, 0)}</td>
                  <td className={cn('px-5 py-2 text-right font-mono', r.difference == null ? 'text-[var(--color-text-muted)]' : r.difference > 0 ? 'text-[var(--color-losses)]' : 'text-[var(--color-gains)]')}>
                    {r.difference == null ? '—' : `${r.difference > 0 ? '+' : r.difference < 0 ? '−' : ''}${formatINR(Math.abs(r.difference), 0)}`}
                    {r.difference != null && r.difference !== 0 && <span className="sr-only">{r.difference > 0 ? ' over estimate' : ' under estimate'}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
