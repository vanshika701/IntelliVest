import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MockPaymentService, createPaymentService } from './paymentService'

describe('MockPaymentService', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('succeeds after the simulated delay', async () => {
    const service = new MockPaymentService({ delayMs: 1000 })
    let settled = false
    const result = service.payOneTime({ investmentId: 'abc123456', amount: 5000, description: 'Test' })
    void result.then(() => (settled = true))

    await vi.advanceTimersByTimeAsync(999)
    expect(settled).toBe(false)
    await vi.advanceTimersByTimeAsync(1)

    const value = await result
    expect(value.status).toBe('success')
    expect(value.reference).toMatch(/^mock_pay_123456_/)
  })

  it('declines amounts above the demo limit', async () => {
    const service = new MockPaymentService({ delayMs: 10, declineAbove: 1000 })
    const result = service.authorizeSipMandate({ investmentId: 'x', amount: 1001, description: 'SIP', dayOfMonth: 5 })
    await vi.advanceTimersByTimeAsync(10)
    expect(await result).toMatchObject({ status: 'failed', reference: null })
  })

  it('falls back to the mock for unknown providers', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(createPaymentService('razorpay').provider).toBe('mock')
    expect(createPaymentService(undefined).provider).toBe('mock')
  })
})
