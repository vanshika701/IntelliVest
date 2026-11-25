// Payment provider seam. The app only ever talks to `paymentService`; swap
// the implementation (e.g. a RazorpayPaymentService opening Razorpay
// Checkout with an order id created by the backend) without touching the UI.
//
// TODO(mock): MockPaymentService simulates payments — no money moves. Razorpay
// is deliberately NOT integrated yet. When it is, the backend must create the
// Razorpay order and verify the payment signature before marking an
// investment completed (see backend investment_service.record_payment_result).

export interface PaymentRequest {
  investmentId: string
  amount: number
  description: string
}

export interface MandateRequest extends PaymentRequest {
  dayOfMonth: number
}

export interface PaymentResult {
  status: 'success' | 'failed'
  reference: string | null
  failureReason?: string
}

export interface PaymentService {
  readonly provider: string
  /** Collect a one-time payment. */
  payOneTime(request: PaymentRequest): Promise<PaymentResult>
  /** Set up a recurring SIP mandate (e-mandate / UPI AutoPay in a real provider). */
  authorizeSipMandate(request: MandateRequest): Promise<PaymentResult>
}

export interface MockPaymentOptions {
  delayMs?: number
  /** Amounts above this are "declined", so the failure path can be demoed. */
  declineAbove?: number
}

export const MOCK_DECLINE_ABOVE = 500_000

export class MockPaymentService implements PaymentService {
  readonly provider = 'mock'
  private readonly delayMs: number
  private readonly declineAbove: number

  constructor({ delayMs = 1500, declineAbove = MOCK_DECLINE_ABOVE }: MockPaymentOptions = {}) {
    this.delayMs = delayMs
    this.declineAbove = declineAbove
  }

  payOneTime(request: PaymentRequest): Promise<PaymentResult> {
    return this.simulate(request, 'mock_pay')
  }

  authorizeSipMandate(request: MandateRequest): Promise<PaymentResult> {
    return this.simulate(request, 'mock_mandate')
  }

  private simulate(request: PaymentRequest, prefix: string): Promise<PaymentResult> {
    return new Promise((resolve) => {
      setTimeout(() => {
        if (request.amount > this.declineAbove) {
          resolve({
            status: 'failed',
            reference: null,
            failureReason: `Declined by bank: amounts above ₹${this.declineAbove.toLocaleString('en-IN')} aren't allowed`,
          })
          return
        }
        resolve({ status: 'success', reference: `${prefix}_${request.investmentId.slice(-6)}_${Date.now().toString(36)}` })
      }, this.delayMs)
    })
  }
}

export function createPaymentService(provider: string | undefined = import.meta.env.VITE_PAYMENT_PROVIDER): PaymentService {
  switch (provider ?? 'mock') {
    case 'mock':
      return new MockPaymentService()
    // case 'razorpay': return new RazorpayPaymentService(import.meta.env.VITE_RAZORPAY_KEY_ID)  // TODO
    default:
      console.warn(`Unknown VITE_PAYMENT_PROVIDER "${provider}", using the mock payment service.`)
      return new MockPaymentService()
  }
}

export const paymentService: PaymentService = createPaymentService()
