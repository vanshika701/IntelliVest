import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { Portfolio } from '../../api/investments'
import { formatINR } from '../../lib/format'
import { cn } from '../../lib/utils'
import { TypeTag } from '../ui/TypeTag'
import { Gain, type GainView } from './Gain'

const VIEWS: { id: GainView; label: string }[] = [
  { id: 'both', label: 'Both' },
  { id: 'pct', label: '%' },
  { id: 'amount', label: '₹' },
]

export function HoldingsTable({ portfolio }: { portfolio: Portfolio }) {
  const [view, setView] = useState<GainView>('both')
  return (
    <section aria-label="Holdings" className="glass-card overflow-hidden rounded-2xl">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border-subtle)] px-5 py-4">
        <h3 className="text-base font-semibold text-[var(--color-text-primary)]">What you hold</h3>
        <div role="group" aria-label="Show return as" className="flex gap-1 rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-background-secondary)] p-1">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              type="button"
              aria-pressed={view === v.id}
              onClick={() => setView(v.id)}
              className={cn('rounded-md px-3 py-1 text-xs font-medium', view === v.id ? 'bg-[var(--color-background-tertiary)] text-[var(--color-text-primary)]' : 'text-[var(--color-text-secondary)]')}
            >
              {v.label}
            </button>
          ))}
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-[var(--color-text-muted)]">
              <th className="px-5 py-2 text-left font-medium">Fund or stock</th>
              <th className="px-3 py-2 text-right font-medium">Invested</th>
              <th className="px-3 py-2 text-right font-medium">Current value</th>
              <th className="px-5 py-2 text-right font-medium">Return</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border-subtle)]">
            {portfolio.holdings.map((h) => (
              <tr key={h.instrument_id}>
                <td className="px-5 py-3">
                  <TypeTag type={h.instrument_type} />{' '}
                  <Link to={`/instrument/${encodeURIComponent(h.instrument_id)}`} className="text-[var(--color-text-primary)] hover:text-[var(--color-brand)]">{h.instrument_name}</Link>
                </td>
                <td className="px-3 py-3 text-right font-mono">{formatINR(h.invested)}</td>
                <td className="px-3 py-3 text-right font-mono">{formatINR(h.current_value)}</td>
                <td className="whitespace-nowrap px-5 py-3 text-right font-mono"><Gain gain={h.gain} pct={h.gain_pct} view={view} /></td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t border-[var(--color-border-strong)] font-semibold">
              <td className="px-5 py-3 text-[var(--color-text-primary)]">Total</td>
              <td className="px-3 py-3 text-right font-mono">{formatINR(portfolio.invested)}</td>
              <td className="px-3 py-3 text-right font-mono">{formatINR(portfolio.current_value)}</td>
              <td className="whitespace-nowrap px-5 py-3 text-right font-mono"><Gain gain={portfolio.gain} pct={portfolio.gain_pct} view={view} /></td>
            </tr>
          </tfoot>
        </table>
      </div>
      {portfolio.unvalued_count > 0 && (
        <p className="px-5 pb-4 text-xs text-[var(--color-text-muted)]">{portfolio.unvalued_count} without a current price left out of the total.</p>
      )}
    </section>
  )
}
