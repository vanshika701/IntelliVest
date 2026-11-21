import { TYPE_LABEL, type InstrumentType } from '../../api/instruments'
import { cn } from '../../lib/utils'

const styles: Record<InstrumentType, string> = {
  STOCK: 'bg-[var(--color-brand-light)] text-[var(--color-brand)]',
  MF: 'bg-[var(--color-gains-light)] text-[var(--color-gains)]',
  ETF: 'bg-amber-500/10 text-amber-400',
}

export function TypeTag({ type, className }: { type: InstrumentType; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide',
        styles[type],
        className,
      )}
    >
      {TYPE_LABEL[type]}
    </span>
  )
}
