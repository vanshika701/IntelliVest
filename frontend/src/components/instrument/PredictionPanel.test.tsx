import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { instrumentsApi, type InstrumentDetail, type StockPrediction } from '../../api/instruments'
import { ApiError } from '../../api/client'
import { PredictionPanel } from './PredictionPanel'

const instrument = { id: 'stock-TCS.NS', name: 'Tata Consultancy Services', type: 'STOCK' } as InstrumentDetail

function prediction(overrides: Partial<StockPrediction> = {}): StockPrediction {
  return {
    instrument_id: 'stock-TCS.NS',
    ticker: 'TCS.NS',
    amount: 7,
    unit: 'days',
    trading_days: 5,
    as_of: '2026-11-26',
    target_date: '2026-12-03',
    last_close: 4000,
    chance_up: 0.58,
    low_pct: -4.2,
    mid_pct: 0.5,
    high_pct: 5.1,
    low_price: 3832,
    mid_price: 4020,
    high_price: 4204,
    rank: 4,
    rank_of: 20,
    model_version: '1.0.0',
    artifact_hash: 'abc',
    test_result: {
      horizon_group: 'Up to 1 week',
      test_years: [2020, 2025],
      range_hit_rate: 0.82,
      direction_accuracy: 0.51,
      always_up_accuracy: 0.52,
    },
    ...overrides,
  }
}

afterEach(() => vi.restoreAllMocks())

describe('PredictionPanel', () => {
  it('shows the range, chance up, rank and test results for the default week', async () => {
    const spy = vi.spyOn(instrumentsApi, 'prediction').mockResolvedValue(prediction())
    render(<PredictionPanel instrument={instrument} />)
    expect(await screen.findByText('58%')).toBeInTheDocument()
    expect(spy).toHaveBeenCalledWith('stock-TCS.NS', 7, 'days')
    expect(screen.getByText(/By 3 Dec 2026/)).toBeInTheDocument()
    expect(screen.getByText('4th of 20 tracked stocks')).toBeInTheDocument()
    expect(screen.getByText(/inside the range 82% of the time/)).toBeInTheDocument()
    expect(screen.getByText(/In tests on 2020–2025/)).toBeInTheDocument()
  })

  it('asks for the chosen unit and blocks horizons past the limit', async () => {
    const spy = vi.spyOn(instrumentsApi, 'prediction').mockResolvedValue(prediction({ amount: 2, unit: 'years' }))
    const user = userEvent.setup()
    render(<PredictionPanel instrument={instrument} />)
    await user.click(screen.getByRole('radio', { name: 'Years' }))
    expect(screen.getByText('Up to 2 years')).toBeInTheDocument()
    const input = screen.getByLabelText('How far ahead')
    await user.clear(input)
    await user.type(input, '2')
    await waitFor(() => expect(spy).toHaveBeenLastCalledWith('stock-TCS.NS', 2, 'years'))
    expect(spy).not.toHaveBeenCalledWith('stock-TCS.NS', 7, 'years')
  })

  it('explains when no prediction exists yet', async () => {
    vi.spyOn(instrumentsApi, 'prediction').mockRejectedValue(new ApiError('No prediction available yet', 404))
    render(<PredictionPanel instrument={instrument} />)
    expect(await screen.findByText(/No prediction for Tata Consultancy Services yet/)).toBeInTheDocument()
  })
})
