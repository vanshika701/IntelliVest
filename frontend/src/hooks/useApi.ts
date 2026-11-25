import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'

export interface ApiState<T> {
  data: T | undefined
  error: string | null
  status: number | null
  loading: boolean
  reload: () => void
}

function describe(error: unknown): { message: string; status: number | null } {
  if (error instanceof ApiError) return { message: error.message, status: error.status }
  return { message: 'Something went wrong. Check your connection and try again.', status: null }
}

/** Fetch when `key` is non-null; refetch when it changes or on reload().
 * Loading is derived (no response yet for the current key), so stale
 * responses from a previous key are never shown. With `refreshMs`, refetches
 * quietly while the tab is visible; a failed refresh keeps what's shown. */
export function useApi<T>(key: string | null, fetcher: () => Promise<T>, refreshMs?: number): ApiState<T> {
  const [nonce, setNonce] = useState(0)
  const [result, setResult] = useState<{ token: string; data?: T; error?: string; status?: number | null } | null>(null)
  const fetcherRef = useRef(fetcher)
  const token = key === null ? null : `${key}#${nonce}`

  // Declared first so it runs before the fetch effect below.
  useEffect(() => {
    fetcherRef.current = fetcher
  })

  useEffect(() => {
    if (token === null) return
    let cancelled = false
    fetcherRef.current().then(
      (data) => !cancelled && setResult({ token, data }),
      (error: unknown) => {
        if (cancelled) return
        const { message, status } = describe(error)
        setResult({ token, error: message, status })
      },
    )
    return () => {
      cancelled = true
    }
  }, [token])

  useEffect(() => {
    if (token === null || !refreshMs) return
    let cancelled = false
    const timer = setInterval(() => {
      if (document.hidden) return
      fetcherRef.current().then(
        (data) => !cancelled && setResult({ token, data }),
        () => {},
      )
    }, refreshMs)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [token, refreshMs])

  const reload = useCallback(() => setNonce((n) => n + 1), [])
  const current = result && result.token === token ? result : null
  return {
    data: current?.data,
    error: current?.error ?? null,
    status: current?.status ?? null,
    loading: token !== null && current === null,
    reload,
  }
}
