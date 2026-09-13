import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

describe('App', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows backend and database as connected once the health check succeeds', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: 'ok', database: 'connected' }),
      }),
    )

    render(<App />)

    expect(screen.getByText('IntelliVest AI')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getAllByText('connected')).toHaveLength(2)
    })
  })

  it('shows an error message when the backend is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))

    render(<App />)

    await waitFor(() => {
      expect(screen.getAllByText('unreachable')).toHaveLength(2)
    })
  })
})
