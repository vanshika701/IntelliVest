import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../AuthContext'
import { AuthPage } from './AuthPage'

const reply = (status: number, body?: unknown) => ({ ok: status < 400, status, json: async () => body })
const show = () => render(<MemoryRouter><AuthProvider><AuthPage /></AuthProvider></MemoryRouter>)

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

async function fillReset(user: ReturnType<typeof userEvent.setup>, confirm: string) {
  await user.click(await screen.findByRole('button', { name: 'Forgot password?' }))
  await user.type(screen.getByLabelText('Email address'), 'a@example.com')
  await user.type(screen.getByLabelText('Date of birth'), '2000-05-17')
  await user.type(screen.getByLabelText('New password'), 'new-password1')
  await user.type(screen.getByLabelText('Confirm new password'), confirm)
  await user.click(screen.getByRole('button', { name: 'Reset Password' }))
}

describe('AuthPage', () => {
  it('resets the password and returns to sign in', async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(204))
    vi.stubGlobal('fetch', fetchMock)
    show()
    await fillReset(userEvent.setup(), 'new-password1')
    expect(await screen.findByRole('status')).toHaveTextContent('Password changed')
    expect(screen.getByRole('button', { name: 'Sign In' })).toBeInTheDocument()
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ email: 'a@example.com', date_of_birth: '2000-05-17', new_password: 'new-password1' })
  })

  it('does not send mismatched passwords', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    show()
    await fillReset(userEvent.setup(), 'different-1')
    expect(screen.getByRole('alert')).toHaveTextContent("don't match")
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('does not send a malformed email', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    show()
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Email address'), 'not-an-email')
    await user.type(screen.getByLabelText('Password'), 'password123')
    await user.click(screen.getByRole('button', { name: 'Sign In' }))
    expect(screen.getByRole('alert')).toHaveTextContent('valid email')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('asks for a date of birth when creating an account', async () => {
    show()
    await userEvent.setup().click(await screen.findByRole('button', { name: 'create a new account' }))
    expect(screen.getByLabelText('Date of birth')).toBeRequired()
  })

  it('asks an older account for its date of birth', async () => {
    localStorage.setItem('intellivest_token', 't')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, { id: '1', email: 'a@example.com', full_name: 'A', has_date_of_birth: false })))
    show()
    expect(await screen.findByText('One more step')).toBeInTheDocument()
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
  })
})
