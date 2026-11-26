import { useState } from 'react'
import type { Questionnaire } from '../../api/portfolioPlan'
import { cn } from '../../lib/utils'
import { Button } from '../ui/Button'

interface Props {
  questionnaire: Questionnaire
  initialAnswers?: Record<string, string>
  saving: boolean
  error: string | null
  onSubmit: (answers: Record<string, string>) => void
  onCancel?: () => void
}

/** Phase 7 risk questionnaire: one radio group per question. */
export function RiskQuestionnaire({ questionnaire, initialAnswers, saving, error, onSubmit, onCancel }: Props) {
  const [answers, setAnswers] = useState<Record<string, string>>(initialAnswers ?? {})
  const [showMissing, setShowMissing] = useState(false)
  const missing = questionnaire.questions.filter((q) => !answers[q.id])

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (missing.length) {
      setShowMissing(true)
      return
    }
    onSubmit(answers)
  }

  return (
    <form onSubmit={submit} noValidate className="glass-card space-y-6 rounded-2xl p-5">
      <div>
        <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">Your risk profile</h2>
        <p className="text-sm text-[var(--color-text-secondary)]">
          Eight questions: four about your situation (how much risk you can afford) and four about your attitude
          (how much you're comfortable with). Your profile follows whichever is lower.
        </p>
      </div>

      {questionnaire.questions.map((q, index) => {
        const unanswered = showMissing && !answers[q.id]
        return (
          <fieldset key={q.id} aria-invalid={unanswered || undefined} className="space-y-2">
            <legend className={cn('text-sm font-medium', unanswered ? 'text-[var(--color-losses)]' : 'text-[var(--color-text-primary)]')}>
              {index + 1}. {q.text}
            </legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {q.options.map((o) => (
                <label
                  key={o.id}
                  className={cn(
                    'flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm',
                    answers[q.id] === o.id
                      ? 'border-[var(--color-brand)] bg-[var(--color-brand-light)] text-[var(--color-text-primary)]'
                      : 'border-[var(--color-border-subtle)] text-[var(--color-text-secondary)] hover:border-[var(--color-border-strong)]',
                  )}
                >
                  <input
                    type="radio"
                    name={q.id}
                    value={o.id}
                    checked={answers[q.id] === o.id}
                    onChange={() => setAnswers((a) => ({ ...a, [q.id]: o.id }))}
                    className="accent-[var(--color-brand)]"
                  />
                  {o.label}
                </label>
              ))}
            </div>
          </fieldset>
        )
      })}

      {showMissing && missing.length > 0 && (
        <p role="alert" className="text-sm text-[var(--color-losses)]">
          Answer every question ({missing.length} left).
        </p>
      )}
      {error && <p role="alert" className="text-sm text-[var(--color-losses)]">{error}</p>}

      <div className="flex gap-2">
        <Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'See my profile'}</Button>
        {onCancel && <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>}
      </div>
    </form>
  )
}
