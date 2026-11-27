import type { ModuleResult } from '../api/advisor'

/** module id -> label, for the "Based on" chips. */
export function moduleLabels(modules: ModuleResult[]): Record<string, string> {
  return Object.fromEntries(modules.map((m) => [m.module, m.label]))
}
