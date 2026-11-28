import { useId } from 'react'
import { modelsApi, type ModelKind } from '../../api/models'
import { useApi } from '../../hooks/useApi'

interface ModelSelectProps {
  kind: ModelKind
  label: string
  /** null = the default model. */
  value: string | null
  onChange: (key: string | null) => void
}

/** A compact picker for which model computes a section. Hidden until the
 * catalog loads, and when there is only one model to choose from. */
export function ModelSelect({ kind, label, value, onChange }: ModelSelectProps) {
  const id = useId()
  const catalog = useApi('model-catalog', modelsApi.list)
  const options = (catalog.data?.[kind] ?? []).filter((option) => option.available)
  if (options.length < 2) return null
  const defaultKey = options.find((option) => option.default)?.key ?? options[0].key
  // A remembered choice the server no longer offers falls back to the default.
  const selected = value && options.some((option) => option.key === value) ? value : defaultKey
  const current = options.find((option) => option.key === selected)

  return (
    <div className="flex min-w-0 items-center gap-2 text-xs">
      <label htmlFor={id} className="shrink-0 text-[var(--color-text-muted)]">
        {label}
      </label>
      <select
        id={id}
        value={selected}
        title={current?.description}
        onChange={(e) => onChange(e.target.value === defaultKey ? null : e.target.value)}
        className="h-7 min-w-0 max-w-[14rem] truncate rounded-md border border-[var(--color-border-strong)] bg-[var(--color-background-secondary)] px-2 text-xs text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]"
      >
        {options.map((option) => (
          <option key={option.key} value={option.key} title={option.description}>
            {option.label}
            {option.default ? ' (default, best tested)' : ''}
          </option>
        ))}
      </select>
    </div>
  )
}
