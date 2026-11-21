import { Link } from 'react-router-dom'
import { AlertCircle, PiggyBank, RefreshCw } from 'lucide-react'
import { investmentsApi, type Investment, type InvestmentStatus } from '../api/investments'
import { useApi } from '../hooks/useApi'
import { formatDate, formatINR } from '../lib/format'
import { ordinal } from '../lib/ordinal'
import { cn } from '../lib/utils'
import { Skeleton } from '../components/ui/Skeleton'
import { TypeTag } from '../components/ui/TypeTag'

const STATUS: Record<InvestmentStatus, { label: string; style: string }> = {
  completed: { label: 'Completed', style: 'bg-[var(--color-gains-light)] text-[var(--color-gains)]' },
  active: { label: 'Active', style: 'bg-[var(--color-gains-light)] text-[var(--color-gains)]' },
  failed: { label: 'Failed', style: 'bg-[var(--color-losses-light)] text-[var(--color-losses)]' },
  pending_payment: { label: 'Awaiting payment', style: 'bg-amber-500/10 text-amber-400' },
  pending_mandate: { label: 'Awaiting mandate', style: 'bg-amber-500/10 text-amber-400' },
}

function InvestmentRow({ investment }: { investment: Investment }) {
  const status = STATUS[investment.status]
  const isSip = investment.kind === 'sip'
  return (
    <li className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <TypeTag type={investment.instrument_type} />
          <span className="text-[10px] font-bold uppercase tracking-wide text-[var(--color-text-muted)]">
            {isSip ? 'SIP' : 'One-time'}
          </span>
        </div>
        <Link
          to={`/instrument/${encodeURIComponent(investment.instrument_id)}`}
          className="block truncate text-sm font-medium text-[var(--color-text-primary)] hover:text-[var(--color-brand)]"
        >
          {investment.instrument_name}
        </Link>
        <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
          {investment.account_label} · {formatDate(investment.created_at)}
          {isSip && investment.status === 'active' && investment.next_installment_date && (
            <> · next on {formatDate(investment.next_installment_date)}</>
          )}
          {investment.status === 'failed' && investment.failure_reason && <> · {investment.failure_reason}</>}
        </p>
      </div>
      <div className="flex items-center gap-3 sm:text-right">
        <div>
          <p className="text-sm font-semibold text-[var(--color-text-primary)]">{formatINR(investment.amount, 0)}</p>
          {isSip && investment.day_of_month && (
            <p className="text-xs text-[var(--color-text-muted)]">monthly on the {ordinal(investment.day_of_month)}</p>
          )}
        </div>
        <span className={cn('rounded-full px-2.5 py-1 text-xs font-semibold', status.style)}>{status.label}</span>
      </div>
    </li>
  )
}

export function InvestmentsPage() {
  const investments = useApi('investments', investmentsApi.list)

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-[var(--color-text-secondary)]">One-time orders and SIPs you've placed.</p>
        <span className="rounded-full bg-amber-500/10 px-2.5 py-1 text-[11px] font-medium text-amber-400">
          Demo data — no real money moved
        </span>
      </div>

      <div className="glass-card rounded-2xl">
        {investments.loading ? (
          <div className="space-y-3 p-4">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : investments.error ? (
          <div className="flex flex-col items-center gap-3 p-10 text-center text-sm text-[var(--color-text-secondary)]">
            <AlertCircle className="h-6 w-6 text-[var(--color-losses)]" aria-hidden="true" />
            <p>Couldn't load your investments. {investments.error}</p>
            <button
              type="button"
              onClick={investments.reload}
              className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-border-strong)] px-3 py-1.5 text-xs text-[var(--color-text-primary)] hover:bg-[var(--color-background-tertiary)]"
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" /> Retry
            </button>
          </div>
        ) : !investments.data?.length ? (
          <div className="flex flex-col items-center gap-2 p-12 text-center">
            <PiggyBank className="h-10 w-10 text-[var(--color-text-muted)] opacity-40" aria-hidden="true" />
            <p className="text-sm text-[var(--color-text-secondary)]">No investments yet.</p>
            <p className="text-xs text-[var(--color-text-muted)]">
              Use the search bar at the top to find a fund or stock, then invest from its page.
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-[var(--color-border-subtle)]">
            {investments.data.map((investment) => (
              <InvestmentRow key={investment.id} investment={investment} />
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
