import { useState, type FormEvent } from 'react'
import { apiPatch, apiPost } from '../../api/client'
import type { BudgetMeta, IncomeGroupId, Transaction } from '../../api/budget'
import { cn } from '../../lib/utils'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'

const label = 'block text-xs font-medium text-[var(--color-text-secondary)] mb-1 uppercase tracking-wider'
const select =
  'h-10 w-full rounded-md border border-[var(--color-border-strong)] bg-[var(--color-background-secondary)] px-3 text-sm text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]'

interface Props {
  meta: BudgetMeta
  /** The record being edited, or null to add a new one. */
  initial: Transaction | null
  onClose: () => void
  onSaved: () => void
}

/** Add or edit a transaction. Income asks for a group (Job / Investments /
 * Other) and then the specific source; expenses ask for a category. */
export function TransactionModal({ meta, initial, onClose, onSaved }: Props) {
  const [type, setType] = useState<'income' | 'expense'>(initial?.expense_type ?? 'expense')
  const [amount, setAmount] = useState(initial ? String(initial.amount) : '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [category, setCategory] = useState(initial?.expense_type === 'expense' ? initial.category : '')
  const [source, setSource] = useState(initial?.income_source ?? '')
  const [group, setGroup] = useState<IncomeGroupId>(
    () => meta.income_groups.find((g) => g.sources.some((s) => s.id === initial?.income_source))?.id ?? 'job',
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const sources = meta.income_groups.find((g) => g.id === group)?.sources ?? []

  async function save(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    const body = {
      amount: parseFloat(amount),
      description,
      ...(type === 'expense' ? { category } : { income_source: source }),
    }
    try {
      if (initial) await apiPatch(`/api/v1/expenses/${initial.id}`, body)
      else await apiPost('/api/v1/expenses', { ...body, expense_type: type })
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save')
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4" role="dialog" aria-modal="true" aria-labelledby="tx-title">
      <div className="bg-[var(--color-background-secondary)] border border-[var(--color-border-subtle)] p-6 rounded-xl w-full max-w-sm shadow-2xl max-h-[90vh] overflow-y-auto">
        <h3 id="tx-title" className="text-xl font-bold text-[var(--color-text-primary)] mb-5">{initial ? 'Edit transaction' : 'Add transaction'}</h3>
        <form onSubmit={save} className="space-y-4">
          {!initial && (
            <div className="flex bg-[var(--color-background-tertiary)] rounded-md p-1 border border-[var(--color-border-strong)]">
              <button type="button" aria-pressed={type === 'expense'} onClick={() => setType('expense')} className={cn('flex-1 py-1.5 text-sm font-medium rounded-sm transition-colors', type === 'expense' ? 'bg-[var(--color-losses)] text-white' : 'text-[var(--color-text-secondary)] hover:text-white')}>Expense</button>
              <button type="button" aria-pressed={type === 'income'} onClick={() => setType('income')} className={cn('flex-1 py-1.5 text-sm font-medium rounded-sm transition-colors', type === 'income' ? 'bg-[var(--color-gains)] text-white' : 'text-[var(--color-text-secondary)] hover:text-white')}>Income</button>
            </div>
          )}

          <div>
            <label htmlFor="tx-amount" className={label}>Amount (₹)</label>
            <Input id="tx-amount" required type="number" step="0.01" min="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" autoFocus className="font-mono text-lg" />
          </div>
          <div>
            <label htmlFor="tx-description" className={label}>Description</label>
            <Input id="tx-description" required maxLength={300} value={description} onChange={(e) => setDescription(e.target.value)} placeholder={type === 'income' ? 'e.g. November salary' : 'e.g. Weekly groceries'} />
          </div>

          {type === 'expense' ? (
            <div>
              <label htmlFor="tx-category" className={label}>Category</label>
              <select id="tx-category" required value={category} onChange={(e) => setCategory(e.target.value)} className={select}>
                <option value="" disabled>Pick a category…</option>
                {meta.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
          ) : (
            <>
              <div>
                <span className={label} id="tx-group">Where is it from?</span>
                <div role="group" aria-labelledby="tx-group" className="grid grid-cols-3 gap-2">
                  {meta.income_groups.map((g) => (
                    <button
                      key={g.id}
                      type="button"
                      aria-pressed={group === g.id}
                      onClick={() => { if (g.id !== group) { setGroup(g.id); setSource('') } }}
                      className={cn('rounded-md border px-2 py-2 text-sm font-medium', group === g.id ? 'border-[var(--color-brand)] bg-[var(--color-brand-light)] text-[var(--color-brand)]' : 'border-[var(--color-border-strong)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]')}
                    >
                      {g.name}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label htmlFor="tx-source" className={label}>Type of income</label>
                <select id="tx-source" required value={source} onChange={(e) => setSource(e.target.value)} className={select}>
                  <option value="" disabled>Pick a type…</option>
                  {sources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
            </>
          )}

          {error && <p role="alert" className="text-xs text-[var(--color-losses)]">{error}</p>}
          <div className="flex gap-3 pt-4 border-t border-[var(--color-border-subtle)]">
            <Button type="button" variant="ghost" className="flex-1" onClick={onClose}>Cancel</Button>
            <Button type="submit" className="flex-1" disabled={saving}>{saving ? 'Saving…' : initial ? 'Save changes' : 'Save log'}</Button>
          </div>
        </form>
      </div>
    </div>
  )
}
