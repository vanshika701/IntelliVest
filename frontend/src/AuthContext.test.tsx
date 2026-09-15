import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from './AuthContext'

// A minimal consumer so we can exercise the hook's behavior through the
// DOM rather than reaching into context internals directly.
function Probe() {
  const { user, isLoading, login, logout } = useAuth()
  return (
    <div>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="user">{user ? user.email : 'none'}</span>
      <button onClick={() => login('fake-token', { id: '1', email: 'a@b.com', full_name: 'A B' })}>
        login
      </button>
      <button onClick={logout}>logout</button>
    </div>
  )
}

describe('AuthContext', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('starts with no user and isLoading false when there is no stored token', async () => {
    vi.stubGlobal('fetch', vi.fn())

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
    expect(screen.getByTestId('user').textContent).toBe('none')
  })

  it('login() stores the token and updates the user; logout() clears both', async () => {
    vi.stubGlobal('fetch', vi.fn())
    const user = userEvent.setup()

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))

    await user.click(screen.getByText('login'))
    expect(screen.getByTestId('user').textContent).toBe('a@b.com')
    expect(localStorage.getItem('intellivest_token')).toBe('fake-token')

    await user.click(screen.getByText('logout'))
    expect(screen.getByTestId('user').textContent).toBe('none')
    expect(localStorage.getItem('intellivest_token')).toBeNull()
  })

  it('clears a stored token that the server rejects as invalid (401)', async () => {
    localStorage.setItem('intellivest_token', 'stale-token')
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({ detail: 'Invalid token' }) }),
    )

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() => expect(localStorage.getItem('intellivest_token')).toBeNull())
  })

  it('keeps a stored token when the /me check fails from a network error, not a rejection', async () => {
    localStorage.setItem('intellivest_token', 'still-good-token')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
    // A transient network error isn't proof the token is bad — don't log
    // the user out over it.
    expect(localStorage.getItem('intellivest_token')).toBe('still-good-token')
  })
})
