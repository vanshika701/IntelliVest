import { useState, type ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { walletErrorMessage } from '../../lib/chain/wallet'

export function Card({ id, icon: Icon, title, children, aside }: {
  id: string
  icon: LucideIcon
  title: string
  children: ReactNode
  aside?: ReactNode
}) {
  return (
    <section aria-labelledby={id} className="glass-card rounded-2xl">
      <div className="flex items-center gap-2 border-b border-[var(--color-border-subtle)] p-5">
        <Icon className="h-5 w-5 text-[var(--color-text-secondary)]" aria-hidden="true" />
        <h3 id={id} className="text-base font-semibold text-[var(--color-text-primary)]">{title}</h3>
        {aside && <div className="ml-auto">{aside}</div>}
      </div>
      <div className="space-y-4 p-5">{children}</div>
    </section>
  )
}

/** Runs one wallet action at a time and keeps its error or success line. */
export function useAction() {
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)

  async function run(label: string, action: () => Promise<unknown>, success?: string) {
    setBusy(label)
    setError(null)
    setDone(null)
    try {
      await action()
      if (success) setDone(success)
      return true
    } catch (err) {
      setError(walletErrorMessage(err))
      return false
    } finally {
      setBusy(null)
    }
  }

  return { busy, error, done, run }
}

export function ActionMessage({ error, done }: { error: string | null; done: string | null }) {
  if (error) return <p role="alert" className="text-sm text-[var(--color-losses)]">{error}</p>
  if (done) return <p role="status" className="text-sm text-[var(--color-gains)]">{done}</p>
  return null
}

export const label = 'text-xs font-medium text-[var(--color-text-muted)]'
export const muted = 'text-sm text-[var(--color-text-muted)]'

export const shortAddress = (a: string) => `${a.slice(0, 6)}…${a.slice(-4)}`
