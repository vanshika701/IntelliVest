import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { CalendarDays, CheckCircle2, ChevronDown, Loader2, XCircle } from 'lucide-react'
import type { InstrumentDetail } from '../../api/instruments'
import { investmentsApi, type Investment } from '../../api/investments'
import { ApiError } from '../../api/client'
import { useApi } from '../../hooks/useApi'
import { formatDate, formatINR } from '../../lib/format'
import { validateAmount } from '../../lib/investValidation'
import { ordinal } from '../../lib/ordinal'
import { cn } from '../../lib/utils'
import { paymentService, type PaymentResult } from '../../services/paymentService'
import { Button } from '../ui/Button'
import { NumberInput } from '../ui/NumberInput'
import { Skeleton } from '../ui/Skeleton'

type Tab = 'one_time' | 'sip'
const QUICK_PICKS = [500, 1000, 5000]

interface Outcome {
  investment: Investment
  payment: PaymentResult
}

function DayPicker({ day, onChange }: { day: number; onChange: (day: number) => void }) {
  const [open, setOpen] = useState(false)
  const popoverId = useId()
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onPointerDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={popoverId}
        aria-label={`SIP date: monthly on the ${ordinal(day)}. Change date`}
        className="flex w-full items-center justify-between rounded-md border border-[var(--color-border-strong)] px-3 py-2.5 text-sm text-[var(--color-text-primary)] hover:bg-[var(--color-background-tertiary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]"
      >
        <span className="flex items-center gap-2">
          <CalendarDays className="h-4 w-4 text-[var(--color-brand)]" aria-hidden="true" />
          Monthly on {ordinal(day)}
        </span>
        <ChevronDown className={cn('h-4 w-4 text-[var(--color-text-muted)] transition-transform', open && 'rotate-180')} aria-hidden="true" />
      </button>
      {open && (
        <div
          id={popoverId}
          role="dialog"
          aria-label="Choose SIP date"
          className="absolute left-0 right-0 z-20 mt-1 rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-background-secondary)] p-3 shadow-2xl"
        >
          <p className="mb-2 text-xs text-[var(--color-text-muted)]">
            Instalment date each month (1–28, so it exists in every month)
          </p>
          <div role="radiogroup" aria-label="Day of month" className="grid grid-cols-7 gap-1">
            {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
              <button
                key={d}
                type="button"
                role="radio"
                aria-checked={d === day}
                onClick={() => {
                  onChange(d)
                  setOpen(false)
                }}
                className={cn(
                  'rounded-md py-1.5 text-xs font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]',
                  d === day
                    ? 'bg-[var(--color-brand)] text-white'
                    : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-background-tertiary)] hover:text-[var(--color-text-primary)]',
                )}
              >
                {d}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function Confirmation({ outcome, onReset }: { outcome: Outcome; onReset: () => void }) {
  const { investment, payment } = outcome
  const success = payment.status === 'success'
  const isSip = investment.kind === 'sip'

  return (
    <div role="status" className="flex flex-col items-center gap-4 py-4 text-center">
      {success ? (
        <CheckCircle2 className="h-12 w-12 text-[var(--color-gains)]" aria-hidden="true" />
      ) : (
        <XCircle className="h-12 w-12 text-[var(--color-losses)]" aria-hidden="true" />
      )}
      <div>
        <h4 className="text-lg font-semibold text-[var(--color-text-primary)]">
          {success ? (isSip ? 'SIP started' : 'Order placed') : 'Payment failed'}
        </h4>
        <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
          {success
            ? isSip
              ? `${formatINR(investment.amount, 0)} every month on the ${ordinal(investment.day_of_month ?? 1)} into ${investment.instrument_name}.`
              : `${formatINR(investment.amount, 0)} into ${investment.instrument_name}.`
            : (payment.failureReason ?? 'The payment could not be completed.')}
        </p>
      </div>

      <dl className="grid w-full max-w-sm grid-cols-2 gap-x-4 gap-y-2 rounded-xl bg-[var(--color-background-tertiary)]/40 p-4 text-left text-sm">
        <dt className="text-[var(--color-text-muted)]">Account</dt>
        <dd className="text-[var(--color-text-primary)]">{investment.account_label}</dd>
        {success && isSip && (
          <>
            <dt className="text-[var(--color-text-muted)]">First instalment</dt>
            <dd className="text-[var(--color-text-primary)]">{formatDate(investment.next_installment_date)}</dd>
          </>
        )}
        {success && !isSip && investment.estimated_units !== null && (
          <>
            <dt className="text-[var(--color-text-muted)]">Est. units</dt>
            <dd className="text-[var(--color-text-primary)]">{investment.estimated_units.toLocaleString('en-IN')}</dd>
          </>
        )}
        <dt className="text-[var(--color-text-muted)]">Reference</dt>
        <dd className="break-all font-mono text-xs text-[var(--color-text-primary)]">{payment.reference ?? '—'}</dd>
      </dl>

      <div className="flex flex-wrap justify-center gap-2">
        <Button type="button" variant="outline" onClick={onReset}>
          {success ? 'Make another investment' : 'Try again'}
        </Button>
        <Link
          to="/investments"
          className="inline-flex h-10 items-center rounded-md bg-[var(--color-brand)] px-4 text-sm font-medium text-white hover:bg-[var(--color-brand-hover)]"
        >
          View my investments
        </Link>
      </div>
    </div>
  )
}

export function InvestPanel({ instrument }: { instrument: InstrumentDetail }) {
  const idPrefix = useId()
  const [tab, setTab] = useState<Tab>('one_time')
  const [amounts, setAmounts] = useState<Record<Tab, string>>({ one_time: '', sip: '' })
  const [touched, setTouched] = useState(false)
  const [day, setDay] = useState(1)
  const [accountId, setAccountId] = useState<string>('')
  const [processing, setProcessing] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [outcome, setOutcome] = useState<Outcome | null>(null)

  const accounts = useApi(`accounts-${instrument.type}`, () => investmentsApi.accounts(instrument.type))
  const selectedAccount = accountId || accounts.data?.[0]?.id || ''

  const { stats } = instrument
  const minimum = tab === 'sip' ? stats.min_sip : stats.min_investment
  const amount = amounts[tab]
  const amountError = validateAmount(amount, minimum, tab === 'sip' ? 'SIP' : 'investment')
  const canSubmit = !amountError && Boolean(selectedAccount) && !processing

  function setAmount(value: string) {
    setAmounts((prev) => ({ ...prev, [tab]: value }))
  }

  function reset() {
    setOutcome(null)
    setSubmitError(null)
    setTouched(false)
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setTouched(true)
    if (!canSubmit) return
    setProcessing(true)
    setSubmitError(null)
    try {
      const value = Number(amount)
      const investment =
        tab === 'sip'
          ? await investmentsApi.createSip({ instrument_id: instrument.id, amount: value, account_id: selectedAccount, day_of_month: day })
          : await investmentsApi.createOneTime({ instrument_id: instrument.id, amount: value, account_id: selectedAccount })

      const request = { investmentId: investment.id, amount: value, description: instrument.name }
      const payment =
        tab === 'sip'
          ? await paymentService.authorizeSipMandate({ ...request, dayOfMonth: day })
          : await paymentService.payOneTime(request)

      const recorded = await investmentsApi.recordPaymentResult(investment.id, {
        status: payment.status,
        reference: payment.reference,
        failure_reason: payment.failureReason ?? null,
      })
      setOutcome({ investment: recorded, payment })
    } catch (error) {
      setSubmitError(error instanceof ApiError ? error.message : 'Something went wrong. Please try again.')
    } finally {
      setProcessing(false)
    }
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: 'one_time', label: 'One-time' },
    { key: 'sip', label: 'Start SIP' },
  ]

  return (
    <section aria-labelledby={`${idPrefix}-heading`} className="glass-card rounded-2xl p-5 sm:p-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h3 id={`${idPrefix}-heading`} className="text-base font-semibold text-[var(--color-text-primary)]">
          Invest
        </h3>
      </div>

      {outcome ? (
        <Confirmation outcome={outcome} onReset={reset} />
      ) : (
        <>
          <div role="tablist" aria-label="Investment type" className="mb-5 grid grid-cols-2 rounded-lg border border-[var(--color-border-strong)] p-0.5">
            {tabs.map(({ key, label }) => (
              <button
                key={key}
                type="button"
                role="tab"
                id={`${idPrefix}-tab-${key}`}
                aria-selected={tab === key}
                aria-controls={`${idPrefix}-panel`}
                disabled={processing}
                onClick={() => {
                  setTab(key)
                  setTouched(false)
                  setSubmitError(null)
                }}
                className={cn(
                  'rounded-md py-2 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]',
                  tab === key ? 'bg-[var(--color-brand)] text-white' : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]',
                )}
              >
                {label}
              </button>
            ))}
          </div>

          <form
            id={`${idPrefix}-panel`}
            role="tabpanel"
            aria-labelledby={`${idPrefix}-tab-${tab}`}
            onSubmit={submit}
            noValidate
            className="space-y-4"
          >
            <div>
              <label htmlFor={`${idPrefix}-amount`} className="mb-1.5 block text-xs font-medium text-[var(--color-text-secondary)]">
                {tab === 'sip' ? 'Monthly SIP amount (₹)' : 'Amount (₹)'}
              </label>
              <NumberInput
                id={`${idPrefix}-amount`}
                placeholder={minimum ? `Min. ${formatINR(minimum, 0)}` : 'Enter amount'}
                value={amount}
                onValueChange={setAmount}
                onBlur={() => setTouched(true)}
                aria-invalid={touched && Boolean(amountError)}
                aria-describedby={`${idPrefix}-amount-hint`}
                disabled={processing}
              />
              <p id={`${idPrefix}-amount-hint`} className={cn('mt-1 text-xs', touched && amountError ? 'text-[var(--color-losses)]' : 'text-[var(--color-text-muted)]')}>
                {touched && amountError
                  ? amountError
                  : minimum !== null
                    ? `Minimum ${formatINR(minimum, 0)}${instrument.type === 'STOCK' ? ' (one share)' : ''}`
                    : null}
              </p>
              {tab === 'one_time' && (
                <div className="mt-2 flex flex-wrap gap-2" aria-label="Quick amounts">
                  {QUICK_PICKS.map((pick) => {
                    const belowMin = minimum !== null && pick < minimum
                    return (
                      <button
                        key={pick}
                        type="button"
                        disabled={processing || belowMin}
                        title={belowMin ? `Below the ${formatINR(minimum, 0)} minimum` : undefined}
                        aria-pressed={Number(amount) === pick}
                        onClick={() => {
                          setAmount(String(pick))
                          setTouched(true)
                        }}
                        className={cn(
                          'rounded-full border px-3 py-1 text-xs font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)] disabled:cursor-not-allowed disabled:opacity-40',
                          Number(amount) === pick
                            ? 'border-[var(--color-brand)] bg-[var(--color-brand-light)] text-[var(--color-brand)]'
                            : 'border-[var(--color-border-strong)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]',
                        )}
                      >
                        {formatINR(pick, 0)}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>

            {tab === 'sip' && (
              <div>
                <span className="mb-1.5 block text-xs font-medium text-[var(--color-text-secondary)]">Frequency & date</span>
                <DayPicker day={day} onChange={setDay} />
              </div>
            )}

            <div>
              <label htmlFor={`${idPrefix}-account`} className="mb-1.5 block text-xs font-medium text-[var(--color-text-secondary)]">
                {instrument.type === 'MF' ? 'Folio' : 'Demat account'}
              </label>
              {accounts.loading ? (
                <Skeleton className="h-10 w-full" />
              ) : accounts.error ? (
                <p className="flex items-center gap-2 text-xs text-[var(--color-losses)]">
                  Couldn't load accounts.
                  <button type="button" onClick={accounts.reload} className="underline">
                    Retry
                  </button>
                </p>
              ) : (
                <select
                  id={`${idPrefix}-account`}
                  value={selectedAccount}
                  onChange={(e) => setAccountId(e.target.value)}
                  disabled={processing}
                  className="h-10 w-full rounded-md border border-[var(--color-border-strong)] bg-[var(--color-background-secondary)] px-3 text-sm text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]"
                >
                  {(accounts.data ?? []).map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.label}
                    </option>
                  ))}
                </select>
              )}
            </div>

            {submitError && (
              <p role="alert" className="rounded-md bg-[var(--color-losses-light)] px-3 py-2 text-sm text-[var(--color-losses)]">
                {submitError}
              </p>
            )}

            <Button type="submit" size="lg" className="w-full" disabled={processing || (touched && !canSubmit)}>
              {processing ? (
                <span className="inline-flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  {tab === 'sip' ? 'Setting up mandate…' : 'Processing payment…'}
                </span>
              ) : tab === 'sip' ? (
                'Start SIP'
              ) : (
                'Invest'
              )}
            </Button>
          </form>
        </>
      )}
    </section>
  )
}
