import type { RiskProfile } from '../../api/portfolioPlan'
import { Button } from '../ui/Button'

function ScoreBar({ label, value, hint }: { label: string; value: number; hint: string }) {
  return (
    <div>
      <div className="flex justify-between text-xs text-[var(--color-text-secondary)]">
        <span>{label} <span className="text-[var(--color-text-muted)]">({hint})</span></span>
        <span>{Math.round(value)} / 100</span>
      </div>
      <div className="mt-1 h-2 rounded-full bg-[var(--color-background-tertiary)]" role="meter" aria-label={label} aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-2 rounded-full bg-[var(--color-brand)]" style={{ width: `${value}%` }} />
      </div>
    </div>
  )
}

const LIMITED_BY = {
  capacity: 'Your situation set this profile: it allows less risk than you said you are comfortable with.',
  tolerance: 'Your attitude set this profile: you are comfortable with less risk than your situation allows.',
  both: 'Your situation and your attitude point to the same level of risk.',
}

export function RiskProfileCard({ profile, onRetake }: { profile: RiskProfile; onRetake: () => void }) {
  return (
    <section aria-labelledby="risk-profile-heading" className="glass-card space-y-4 rounded-2xl p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">Your risk profile</p>
          <h2 id="risk-profile-heading" className="text-xl font-semibold text-[var(--color-text-primary)]">{profile.label}</h2>
          <p className="text-sm text-[var(--color-text-secondary)]">{profile.description}</p>
        </div>
        <Button variant="outline" size="sm" onClick={onRetake}>Retake questionnaire</Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <ScoreBar label="Capacity" hint="what you can afford" value={profile.capacity_score} />
        <ScoreBar label="Tolerance" hint="what you're comfortable with" value={profile.tolerance_score} />
      </div>
      <p className="text-sm text-[var(--color-text-secondary)]">{LIMITED_BY[profile.limited_by]}</p>
      {profile.notes.length > 0 && (
        <ul className="list-disc space-y-1 pl-5 text-sm text-[var(--color-text-secondary)]">
          {profile.notes.map((n) => <li key={n}>{n}</li>)}
        </ul>
      )}
    </section>
  )
}
