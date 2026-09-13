import { useEffect, useState } from 'react'
import { apiGet } from './api/client'

interface HealthStatus {
  status: string
  database: string
}

function App() {
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    apiGet<HealthStatus>('/api/v1/health')
      .then(setHealth)
      .catch(() => setError('Could not reach the backend. Is it running on port 8000?'))
  }, [])

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-100">
      <div className="rounded-lg border border-slate-800 bg-slate-900 p-8 shadow-xl">
        <h1 className="text-2xl font-semibold">IntelliVest AI</h1>
        <p className="mt-1 text-sm text-slate-400">Phase 0 — foundations check</p>

        <div className="mt-6 space-y-2 text-sm">
          <StatusRow label="Backend" ok={health?.status === 'ok'} pending={!health && !error} error={error} />
          <StatusRow
            label="Database"
            ok={health?.database === 'connected'}
            pending={!health && !error}
            error={error}
          />
        </div>
      </div>
    </main>
  )
}

function StatusRow({
  label,
  ok,
  pending,
  error,
}: {
  label: string
  ok: boolean
  pending: boolean
  error: string | null
}) {
  const state = error ? 'error' : pending ? 'pending' : ok ? 'ok' : 'down'

  const dotColor = {
    ok: 'bg-emerald-500',
    down: 'bg-red-500',
    pending: 'bg-slate-500',
    error: 'bg-red-500',
  }[state]

  const text = {
    ok: 'connected',
    down: 'unreachable',
    pending: 'checking…',
    error: 'unreachable',
  }[state]

  return (
    <div className="flex items-center justify-between gap-8">
      <span className="text-slate-300">{label}</span>
      <span className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${dotColor}`} />
        {text}
      </span>
    </div>
  )
}

export default App
