import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AlertsPage } from './AlertsPage'

function jsonResponse(body: unknown, ok = true) {
  return { ok, status: ok ? 200 : 400, json: async () => body }
}

describe('AlertsPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders existing alerts with their trigger status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse([
          {
            id: '1',
            ticker: 'RELIANCE.NS',
            condition: 'above',
            target_price: 1500,
            threshold_pct: 5,
            is_active: true,
            triggered: false,
          },
        ]),
      ),
    )

    render(<AlertsPage />)

    expect(await screen.findByText('RELIANCE.NS')).toBeInTheDocument()
    expect(screen.getByText('Monitoring...')).toBeInTheDocument()
  })

  it('shows the empty state when there are no alerts', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse([])))

    render(<AlertsPage />)

    expect(await screen.findByText('No active rules')).toBeInTheDocument()
  })

  it('submits a new alert rule through the create form', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([])) // initial load
      .mockResolvedValueOnce(jsonResponse({ id: 'new-1' })) // POST /alerts
      .mockResolvedValueOnce(
        jsonResponse([
          {
            id: 'new-1',
            ticker: 'RELIANCE.NS',
            condition: 'above',
            target_price: 2000,
            threshold_pct: 5,
            is_active: true,
            triggered: false,
          },
        ]),
      ) // reload after create
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()

    render(<AlertsPage />)
    await screen.findByText('No active rules')

    await user.click(screen.getByText('New Alert'))
    await user.type(screen.getByPlaceholderText('0.00'), '2000')
    await user.click(screen.getByText('Create Rule'))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
    const postCall = fetchMock.mock.calls[1]
    expect(postCall[0]).toContain('/api/v1/alerts')
    expect(JSON.parse(postCall[1].body)).toMatchObject({
      ticker: 'RELIANCE.NS',
      condition: 'above',
      target_price: 2000,
    })
  })
})
