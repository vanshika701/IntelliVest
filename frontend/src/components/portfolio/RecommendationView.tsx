import { AlertTriangle, Info } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip as RechartsTooltip } from 'recharts'
import type { Recommendation, RecommendedHolding } from '../../api/portfolioPlan'
import { formatDate, formatINR } from '../../lib/format'
import { ASSET_CLASSES, formatFraction, formatHorizon, groupByClass } from '../../lib/portfolioPlan'

function AllocationChart({ rec }: { rec: Recommendation }) {
  const pct = { equity: rec.allocation.equity_pct, debt: rec.allocation.debt_pct, gold: rec.allocation.gold_pct }
  const slices = ASSET_CLASSES.map((c) => ({ ...c, value: pct[c.id] })).filter((s) => s.value > 0)
  return (
    <div className="glass-card rounded-2xl p-5">
      <h3 className="mb-2 text-sm font-medium text-[var(--color-text-primary)]">How the money is split</h3>
      <div className="flex flex-wrap items-center gap-6">
        <div className="h-40 w-40" aria-hidden>
          <ResponsiveContainer>
            <PieChart>
              <Pie data={slices} dataKey="value" nameKey="label" innerRadius={45} outerRadius={70} stroke="none">
                {slices.map((s) => <Cell key={s.id} fill={s.color} />)}
              </Pie>
              <RechartsTooltip formatter={(v) => `${v}%`} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <ul className="space-y-1 text-sm" aria-label="Asset split">
          {slices.map((s) => (
            <li key={s.id} className="flex items-center gap-2 text-[var(--color-text-secondary)]">
              <span className="h-3 w-3 rounded-sm" style={{ background: s.color }} aria-hidden />
              <span className="w-14 text-[var(--color-text-primary)]">{s.label}</span> {s.value}%
            </li>
          ))}
        </ul>
      </div>
      {rec.allocation.adjustments.map((a) => (
        <p key={a.asset} className="mt-3 text-xs text-[var(--color-text-muted)]">
          {a.asset === 'equity' ? 'Stocks' : 'Gold'} reduced from {a.from_pct}% to {a.to_pct}%: {a.reason}
        </p>
      ))}
      {!rec.allocation.base_is_sourced && (
        <p className="mt-3 text-xs text-[var(--color-text-muted)]">
          This profile's starting split is our own, halfway between two published model splits.
        </p>
      )}
    </div>
  )
}

function RiskSummary({ rec }: { rec: Recommendation }) {
  const { risk } = rec
  return (
    <div className="glass-card space-y-3 rounded-2xl p-5">
      <h3 className="text-sm font-medium text-[var(--color-text-primary)]">How much it could swing</h3>
      {risk.volatility_upper_bound === null ? (
        <p className="text-sm text-[var(--color-text-secondary)]">
          Not enough data to estimate this right now (missing: {risk.missing.join(', ')}).
        </p>
      ) : (
        <dl className="grid grid-cols-2 gap-3">
          <div>
            <dt className="text-xs text-[var(--color-text-muted)]">Yearly swing (at most)</dt>
            <dd className="text-2xl font-semibold text-[var(--color-text-primary)]">{formatFraction(risk.volatility_upper_bound)}</dd>
          </div>
          <div>
            <dt className="text-xs text-[var(--color-text-muted)]">A bad year (about 1 in 20)</dt>
            <dd className="text-2xl font-semibold text-[var(--color-losses)]">{formatFraction(risk.bad_year_loss)}</dd>
          </div>
        </dl>
      )}
      <p className="text-xs text-[var(--color-text-muted)]">{risk.explanation}</p>
    </div>
  )
}

function HoldingRow({ h, showLump, showMonthly }: { h: RecommendedHolding; showLump: boolean; showMonthly: boolean }) {
  return (
    <tr className="border-t border-[var(--color-border-subtle)] align-top">
      <td className="py-3 pr-3">
        {h.instrument_id ? (
          <Link to={`/instrument/${h.instrument_id}`} className="font-medium text-[var(--color-text-primary)] hover:text-[var(--color-brand)]">{h.name}</Link>
        ) : (
          <span className="font-medium text-[var(--color-text-primary)]">{h.name}</span>
        )}
        <details className="mt-1 text-xs text-[var(--color-text-secondary)]">
          <summary className="cursor-pointer text-[var(--color-text-muted)]">Why</summary>
          <ul className="mt-1 list-disc space-y-0.5 pl-4">{h.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        </details>
        {h.warnings.map((w) => (
          <p key={w} className="mt-1 flex items-start gap-1 text-xs text-[var(--color-warning,#d4a72c)]">
            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden /> {w}
          </p>
        ))}
        {h.already_held_value !== null && (
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">You already hold {formatINR(h.already_held_value, 0)}.</p>
        )}
      </td>
      <td className="py-3 pr-3 text-right text-[var(--color-text-secondary)]">{formatFraction(h.weight)}</td>
      {showLump && <td className="py-3 pr-3 text-right text-[var(--color-text-primary)]">{formatINR(h.lump_sum_amount, 0)}</td>}
      {showMonthly && <td className="py-3 text-right text-[var(--color-text-primary)]">{formatINR(h.monthly_amount, 0)}</td>}
    </tr>
  )
}

function EquityComparison({ rec }: { rec: Recommendation }) {
  const c = rec.equity_comparison
  if (!c) return null
  const rows = [
    ['This plan', c.optimized],
    ['Lowest risk, before news', c.minimum_variance],
    ['Equal amounts in every stock', c.equal_weight],
  ] as const
  return (
    <div className="glass-card rounded-2xl p-5">
      <h3 className="text-sm font-medium text-[var(--color-text-primary)]">The stock part compared</h3>
      <p className="mb-3 text-xs text-[var(--color-text-muted)]">
        Swings measured on the same two years of prices used to pick the weights, so they flatter this plan.
      </p>
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-[var(--color-text-muted)]">
          <tr><th className="pb-2 font-medium">Stock mix</th><th className="pb-2 text-right font-medium">Yearly swing</th><th className="pb-2 text-right font-medium">Stocks</th><th className="pb-2 text-right font-medium">Acts like</th></tr>
        </thead>
        <tbody>
          {rows.map(([name, s]) => (
            <tr key={name} className="border-t border-[var(--color-border-subtle)] text-[var(--color-text-secondary)]">
              <td className="py-2 text-[var(--color-text-primary)]">{name}</td>
              <td className="py-2 text-right">{formatFraction(s.annual_volatility)}</td>
              <td className="py-2 text-right">{s.holdings}</td>
              <td className="py-2 text-right">{s.effective_holdings.toFixed(1)} equal stocks</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Phase 7: one stored recommendation, with its reasons and caveats. */
export function RecommendationView({ rec }: { rec: Recommendation }) {
  const showLump = rec.inputs.lump_sum > 0
  const showMonthly = rec.inputs.monthly_sip > 0
  const horizon = formatHorizon(rec.inputs.horizon_months)
  return (
    <section aria-labelledby="plan-heading" className="space-y-4">
      <div>
        <h2 id="plan-heading" className="text-lg font-semibold text-[var(--color-text-primary)]">
          Plan for {rec.inputs.goal ? `"${rec.inputs.goal.name}" (${horizon})` : horizon}
        </h2>
        <p className="text-xs text-[var(--color-text-muted)]">
          {rec.profile.label} profile · built {formatDate(rec.created_at)}
          {rec.versions.market_stats_as_of ? ` · prices up to ${formatDate(String(rec.versions.market_stats_as_of))}` : ''}
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <AllocationChart rec={rec} />
        <RiskSummary rec={rec} />
      </div>

      {rec.notes.map((n) => (
        <p key={n} className="flex items-start gap-2 rounded-lg border border-[var(--color-border-subtle)] p-3 text-sm text-[var(--color-text-secondary)]">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-brand)]" aria-hidden /> {n}
        </p>
      ))}

      <div className="glass-card overflow-x-auto rounded-2xl p-5">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-[var(--color-text-muted)]">
            <tr>
              <th className="pb-2 font-medium">Holding</th>
              <th className="pb-2 text-right font-medium">Share</th>
              {showLump && <th className="pb-2 text-right font-medium">One-time</th>}
              {showMonthly && <th className="pb-2 text-right font-medium">Monthly</th>}
            </tr>
          </thead>
          {groupByClass(rec.holdings).map((group) => (
            <tbody key={group.id}>
              <tr><th colSpan={4} scope="rowgroup" className="pt-4 text-left text-xs uppercase tracking-wider text-[var(--color-text-muted)]">{group.label}</th></tr>
              {group.holdings.map((h) => <HoldingRow key={`${h.instrument_id}-${h.name}`} h={h} showLump={showLump} showMonthly={showMonthly} />)}
            </tbody>
          ))}
        </table>
      </div>

      <EquityComparison rec={rec} />

      {rec.not_held.length > 0 && (
        <div className="glass-card rounded-2xl p-5">
          <h3 className="text-sm font-medium text-[var(--color-text-primary)]">You hold these, but they aren't in this plan</h3>
          <ul className="mt-2 space-y-1 text-sm text-[var(--color-text-secondary)]">
            {rec.not_held.map((h) => <li key={h.instrument_id}><Link to={`/instrument/${h.instrument_id}`} className="hover:text-[var(--color-brand)]">{h.name}</Link> · {formatINR(h.current_value, 0)}</li>)}
          </ul>
        </div>
      )}

      <p className="text-xs text-[var(--color-text-muted)]">{rec.disclaimer}</p>
    </section>
  )
}
