// Which models users can pick for predictions, sentiment and summaries (GET /api/v1/models).
import { apiGet } from './client'

export type ModelKind = 'prediction' | 'sentiment' | 'summarizer'

export interface ModelOption {
  /** Pass as ?model= */
  key: string
  label: string
  description: string
  version: string | null
  /** False: the model's file isn't on the server (not trained yet). */
  available: boolean
  /** Used when no model is picked; the best one in our comparisons. */
  default: boolean
}

export type ModelCatalog = Record<ModelKind, ModelOption[]>

let catalog: Promise<ModelCatalog> | null = null

export const modelsApi = {
  /** Fetched once per page load; a failed fetch is retried next time. */
  list: (): Promise<ModelCatalog> => {
    catalog ??= apiGet<ModelCatalog>('/api/v1/models').catch((error: unknown) => {
      catalog = null
      throw error
    })
    return catalog
  },
}

/** For tests. */
export function resetModelCatalog() {
  catalog = null
}
