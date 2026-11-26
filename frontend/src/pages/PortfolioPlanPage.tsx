import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { budgetApi } from '../api/budget'
import { ApiError } from '../api/client'
import { portfolioPlanApi, type Recommendation, type RecommendationInput, type RiskProfile } from '../api/portfolioPlan'
import { PlanForm } from '../components/portfolio/PlanForm'
import { RecommendationView } from '../components/portfolio/RecommendationView'
import { RiskProfileCard } from '../components/portfolio/RiskProfileCard'
import { RiskQuestionnaire } from '../components/portfolio/RiskQuestionnaire'
import { Skeleton } from '../components/ui/Skeleton'
import { useApi } from '../hooks/useApi'

const errorText = (e: unknown) => (e instanceof ApiError ? e.message : 'Something went wrong. Check your connection and try again.')

/** Phase 7: risk questionnaire -> portfolio recommendation. */
export function PortfolioPlanPage() {
  const questions = useApi('risk-questions', portfolioPlanApi.questions)
  const savedProfile = useApi('risk-profile', portfolioPlanApi.riskProfile)
  const latest = useApi('latest-recommendation', portfolioPlanApi.latest)
  const goals = useApi('budget-goals', budgetApi.goals)

  const [profile, setProfile] = useState<RiskProfile | null>(null)
  const [rec, setRec] = useState<Recommendation | null>(null)
  const [retaking, setRetaking] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const currentProfile = profile ?? savedProfile.data ?? null
  const currentRec = rec ?? latest.data ?? null

  if (questions.loading || savedProfile.loading) {
    return <div className="space-y-4" aria-label="Loading portfolio plan"><Skeleton className="h-40 rounded-2xl" /><Skeleton className="h-64 rounded-2xl" /></div>
  }
  // 404 just means "not answered yet"; anything else is a real failure.
  const profileFailed = savedProfile.error && savedProfile.status !== 404
  if (questions.error || !questions.data || profileFailed) {
    return (
      <div className="space-y-3">
        <p role="alert" className="text-sm text-[var(--color-losses)]">The portfolio planner couldn't be loaded. {questions.error ?? savedProfile.error}</p>
        <button type="button" onClick={() => { questions.reload(); savedProfile.reload() }} className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-border-strong)] px-3 py-1.5 text-sm text-[var(--color-text-primary)]"><RefreshCw className="h-4 w-4" aria-hidden /> Retry</button>
      </div>
    )
  }

  async function saveAnswers(answers: Record<string, string>) {
    setSaving(true)
    setError(null)
    try {
      setProfile(await portfolioPlanApi.saveRiskProfile(answers))
      setRetaking(false)
    } catch (e) {
      setError(errorText(e))
    } finally {
      setSaving(false)
    }
  }

  async function buildPlan(input: RecommendationInput) {
    setSaving(true)
    setError(null)
    try {
      setRec(await portfolioPlanApi.create(input))
    } catch (e) {
      setError(errorText(e))
    } finally {
      setSaving(false)
    }
  }

  if (!currentProfile || retaking) {
    return (
      <RiskQuestionnaire
        questionnaire={questions.data}
        initialAnswers={currentProfile?.answers}
        saving={saving}
        error={error}
        onSubmit={saveAnswers}
        onCancel={currentProfile ? () => setRetaking(false) : undefined}
      />
    )
  }

  return (
    <div className="space-y-6">
      <RiskProfileCard profile={currentProfile} onRetake={() => { setError(null); setRetaking(true) }} />
      <PlanForm goals={goals.data?.items ?? []} saving={saving} error={error} onSubmit={buildPlan} />
      {currentRec && <RecommendationView rec={currentRec} />}
    </div>
  )
}
