import { ArrowRight, CheckCircle2, CircleDashed, Clock, XCircle } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { Advice, AdviceAction, ModuleStatus, SetupStep } from '../../api/advisor'
import { formatDate } from '../../lib/format'
import { cn } from '../../lib/utils'

const SEVERITY = {
  high: { label: 'Do first', bar: 'bg-[var(--color-losses)]', text: 'text-[var(--color-losses)]' },
  medium: { label: 'Worth doing', bar: 'bg-[#d4a72c]', text: 'text-[#d4a72c]' },
  low: { label: 'When you can', bar: 'bg-[var(--color-border-strong)]', text: 'text-[var(--color-text-muted)]' },
} as const

const STATUS: Record<ModuleStatus, { label: string; Icon: typeof CheckCircle2; color: string }> = {
  ok: { label: 'Used', Icon: CheckCircle2, color: 'text-[var(--color-gains)]' },
  stale: { label: 'Old data', Icon: Clock, color: 'text-[#d4a72c]' },
  not_set_up: { label: 'Not set up', Icon: CircleDashed, color: 'text-[var(--color-text-muted)]' },
  unavailable: { label: 'Unavailable', Icon: XCircle, color: 'text-[var(--color-losses)]' },
  not_built: { label: 'Not built', Icon: CircleDashed, color: 'text-[var(--color-text-muted)]' },
}

export function ActionCard({ action, index, labels }: { action: AdviceAction; index: number; labels: Record<string, string> }) {
  const severity = SEVERITY[action.severity]
  return (
    <article className="glass-card relative overflow-hidden rounded-2xl p-5 pl-6">
      <span className={cn('absolute inset-y-0 left-0 w-1.5', severity.bar)} aria-hidden />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className={cn('text-xs font-medium uppercase tracking-wider', severity.text)}>
            {index}. {severity.label}
          </p>
          <h3 className="mt-1 font-semibold text-[var(--color-text-primary)]">{action.title}</h3>
          <p className="mt-1 text-sm text-[var(--color-text-secondary)]">{action.detail}</p>
        </div>
        <Link to={action.link} className="inline-flex shrink-0 items-center gap-1 text-sm font-medium text-[var(--color-brand)] hover:text-[var(--color-brand-hover)]">
          Open <ArrowRight className="h-4 w-4" aria-hidden />
        </Link>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-1.5" aria-label="Based on">
        <span className="text-xs text-[var(--color-text-muted)]">Based on</span>
        {action.contributors.map((c) => (
          <span key={c} className="rounded-full bg-[var(--color-background-tertiary)] px-2 py-0.5 text-xs text-[var(--color-text-secondary)]">{labels[c] ?? c}</span>
        ))}
      </div>
      {action.facts.length > 0 && (
        <details className="mt-2 text-xs text-[var(--color-text-secondary)]">
          <summary className="cursor-pointer text-[var(--color-text-muted)]">Why</summary>
          <ul className="mt-1 list-disc space-y-0.5 pl-4">{action.facts.map((f) => <li key={f}>{f}</li>)}</ul>
        </details>
      )}
    </article>
  )
}

export function SetupSteps({ steps }: { steps: SetupStep[] }) {
  if (steps.length === 0) return null
  return (
    <section aria-labelledby="setup-heading" className="glass-card rounded-2xl p-5">
      <h2 id="setup-heading" className="text-sm font-medium text-[var(--color-text-primary)]">Unlock more advice</h2>
      <ul className="mt-2 space-y-2">
        {steps.map((s) => (
          <li key={s.title} className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span><span className="font-medium text-[var(--color-text-primary)]">{s.title}</span> <span className="text-[var(--color-text-secondary)]">— {s.detail}</span></span>
            <Link to={s.link} className="text-[var(--color-brand)] hover:text-[var(--color-brand-hover)]">Go</Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function ModuleStatusPanel({ advice }: { advice: Advice }) {
  return (
    <section aria-labelledby="modules-heading" className="glass-card rounded-2xl p-5">
      <h2 id="modules-heading" className="text-sm font-medium text-[var(--color-text-primary)]">What the advisor looked at</h2>
      <ul className="mt-3 divide-y divide-[var(--color-border-subtle)]">
        {advice.modules.map((m) => {
          const s = STATUS[m.status]
          return (
            <li key={m.module} className="flex flex-wrap items-start justify-between gap-2 py-2 text-sm">
              <div className="min-w-0">
                <span className="text-[var(--color-text-primary)]">{m.label}</span>
                {m.phase !== null && <span className="ml-1 text-xs text-[var(--color-text-muted)]">Phase {m.phase}</span>}
                {m.reason && <p className="text-xs text-[var(--color-text-muted)]">{m.reason}</p>}
              </div>
              <span className={cn('inline-flex items-center gap-1 text-xs', s.color)}>
                <s.Icon className="h-3.5 w-3.5" aria-hidden /> {s.label}
                {m.as_of && m.status !== 'not_set_up' && <span className="text-[var(--color-text-muted)]"> · {formatDate(m.as_of)}</span>}
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
