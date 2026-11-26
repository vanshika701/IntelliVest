import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, RefreshCw, Sparkles } from 'lucide-react'
import { advisorApi, type Advice } from '../api/advisor'
import { ApiError } from '../api/client'
import { ActionCard, ModuleStatusPanel, SetupSteps } from '../components/advisor/AdviceViews'
import { moduleLabels } from '../lib/advisor'
import { Button } from '../components/ui/Button'
import { Skeleton } from '../components/ui/Skeleton'
import { useApi } from '../hooks/useApi'
import { formatDate } from '../lib/format'

const errorText = (e: unknown) => (e instanceof ApiError ? e.message : 'Something went wrong. Check your connection and try again.')

/** Phase 9: one prioritised, explained list of what to do next. */
export function AdvisorPage() {
  const latest = useApi('advisor-latest', advisorApi.latest)
  const [fresh, setFresh] = useState<Advice | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const autoRequested = useRef(false)

  async function refresh() {
    setRefreshing(true)
    setError(null)
    try {
      setFresh(await advisorApi.refresh())
    } catch (e) {
      setError(errorText(e))
    } finally {
      setRefreshing(false)
    }
  }

  // First visit: nothing saved yet, so build advice once automatically.
  useEffect(() => {
    if (latest.status === 404 && !autoRequested.current) {
      autoRequested.current = true
      void refresh()
    }
  }, [latest.status])

  const advice = fresh ?? latest.data ?? null
  const firstLoad = latest.loading || (latest.status === 404 && !fresh && !error)

  if (firstLoad) {
    return <div className="space-y-4" aria-label="Loading advice"><Skeleton className="h-28 rounded-2xl" /><Skeleton className="h-40 rounded-2xl" /><Skeleton className="h-40 rounded-2xl" /></div>
  }
  if (!advice) {
    return (
      <div className="space-y-3">
        <p role="alert" className="text-sm text-[var(--color-losses)]">Advice couldn't be loaded. {error ?? latest.error}</p>
        <Button variant="outline" size="sm" onClick={() => { latest.reload(); void refresh() }}><RefreshCw className="mr-1.5 h-4 w-4" aria-hidden /> Retry</Button>
      </div>
    )
  }

  const labels = moduleLabels(advice.modules)
  return (
    <div className="space-y-6">
      <section aria-labelledby="advice-heading" className="glass-card space-y-3 rounded-2xl p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 id="advice-heading" className="text-lg font-semibold text-[var(--color-text-primary)]">Your next steps</h2>
            <p className="text-xs text-[var(--color-text-muted)]">Built {formatDate(advice.created_at, 'd MMM yyyy, h:mm a')}</p>
          </div>
          <Button variant="outline" size="sm" onClick={refresh} disabled={refreshing}>
            <RefreshCw className={refreshing ? 'mr-1.5 h-4 w-4 animate-spin' : 'mr-1.5 h-4 w-4'} aria-hidden />
            {refreshing ? 'Updating…' : 'Update advice'}
          </Button>
        </div>
        <p className="text-[var(--color-text-primary)]">{advice.summary.text}</p>
        {advice.summary.source === 'llm' && (
          <p className="inline-flex items-center gap-1 text-xs text-[var(--color-text-muted)]">
            <Sparkles className="h-3.5 w-3.5" aria-hidden /> Worded by an AI model from the steps below; every number was checked against them.
          </p>
        )}
        {advice.partial && (
          <p className="flex items-start gap-1.5 text-xs text-[#d4a72c]">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
            Some information couldn't be loaded ({advice.modules_unavailable.map((m) => labels[m] ?? m).join(', ')}), so this may be incomplete.
          </p>
        )}
        {error && <p role="alert" className="text-sm text-[var(--color-losses)]">{error}</p>}
      </section>

      {advice.actions.length > 0 && (
        <section aria-label="Actions" className="space-y-3">
          {advice.actions.map((a, i) => <ActionCard key={`${a.id}-${a.title}`} action={a} index={i + 1} labels={labels} />)}
        </section>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <SetupSteps steps={advice.setup} />
        <ModuleStatusPanel advice={advice} />
      </div>

      <p className="text-xs text-[var(--color-text-muted)]">{advice.disclaimer}</p>
    </div>
  )
}
