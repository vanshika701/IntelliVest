import { DASH, formatINR, formatSignedPct } from '../../lib/format'
import { cn } from '../../lib/utils'

export type GainView = 'both' | 'pct' | 'amount'

/** Profit green, loss red, unchanged white. */
function gainColor(gain: number): string {
  if (gain > 0) return 'text-[var(--color-gains)]'
  return gain < 0 ? 'text-[var(--color-losses)]' : 'text-white'
}

export function Gain({ gain, pct, view = 'both', className }: { gain: number | null; pct: number | null; view?: GainView; className?: string }) {
  if (gain === null) return <span className={cn('text-[var(--color-text-muted)]', className)}>{DASH}</span>
  const amount = `${gain > 0 ? '+' : gain < 0 ? '−' : ''}${formatINR(Math.abs(gain))}`
  const percent = gain === 0 ? '0.00%' : formatSignedPct(pct)
  return (
    <span className={cn(gainColor(gain), className)}>
      {view === 'pct' ? percent : view === 'amount' ? amount : `${amount} (${percent})`}
    </span>
  )
}
