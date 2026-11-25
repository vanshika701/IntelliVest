import type { SectorWindow } from '../api/sectors'

export const WINDOWS: { id: SectorWindow; label: string }[] = [
  { id: '1d', label: '1 day' },
  { id: '1w', label: '1 week' },
  { id: '1m', label: '1 month' },
  { id: '3m', label: '3 months' },
]

export function changeColor(value: number | null) {
  if (value === null || value === 0) return 'text-[var(--color-text-secondary)]'
  return value > 0 ? 'text-[var(--color-gains)]' : 'text-[var(--color-losses)]'
}
