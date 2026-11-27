import { useCallback, useState } from 'react'
import type { ModelKind } from '../api/models'

const STORAGE_KEY = 'intellivest.modelChoice'

function readAll(): Partial<Record<ModelKind, string>> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') ?? {}
  } catch {
    return {}
  }
}

/** The model the user picked for `kind`, remembered across pages and visits.
 * null = the server's default (no ?model= sent). */
export function useModelChoice(kind: ModelKind): [string | null, (key: string | null) => void] {
  const [choice, setChoice] = useState<string | null>(() => readAll()[kind] ?? null)
  const update = useCallback(
    (key: string | null) => {
      setChoice(key)
      const all = readAll()
      if (key) all[kind] = key
      else delete all[kind]
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(all))
      } catch {
        // Storage full or blocked: the choice still applies to this page.
      }
    },
    [kind],
  )
  return [choice, update]
}
