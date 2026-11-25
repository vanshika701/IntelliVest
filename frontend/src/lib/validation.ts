// Form field checks. Each returns an error message, or null if valid.
// The backend schemas check the same fields.

const EMAIL_RE = /^[A-Za-z0-9_%+-]+(\.[A-Za-z0-9_%+-]+)*@([A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}$/
const NAME_RE = /^\p{L}[\p{L}\p{M} .'’-]*$/u
const TICKER_RE = /^[A-Z0-9][A-Z0-9&-]*(\.[A-Z]{1,3})?$/

export function validateEmail(raw: string): string | null {
  const value = raw.trim()
  if (!value) return 'Enter your email address'
  return EMAIL_RE.test(value) && value.length <= 254 ? null : 'Enter a valid email address, like you@example.com'
}

export function validateName(raw: string): string | null {
  const value = raw.trim()
  if (!value) return 'Enter your full name'
  if (value.length > 120) return 'Use at most 120 characters'
  return NAME_RE.test(value) ? null : 'Use letters only (spaces, dots, hyphens and apostrophes are fine)'
}

export function validateNewPassword(value: string): string | null {
  if (!value) return 'Enter a password'
  if (value.length < 8) return 'Use at least 8 characters'
  // bcrypt's limit, counted in bytes
  return new TextEncoder().encode(value).length > 72 ? 'Password is too long' : null
}

/** `raw` and `today` are YYYY-MM-DD. */
export function validateBirthDate(raw: string, today: string): string | null {
  if (!raw) return 'Enter your date of birth'
  if (raw < '1900-01-01') return 'Enter a valid date of birth'
  return raw >= today ? 'Date of birth must be in the past' : null
}

export function validateTicker(raw: string): string | null {
  const value = raw.trim().toUpperCase()
  if (!value) return 'Enter a ticker'
  return TICKER_RE.test(value) && value.length <= 20 ? null : 'Enter a valid ticker, like ZOMATO.NS'
}

export function validateRange(raw: string, min: number, max: number): string | null {
  const value = Number(raw)
  return raw.trim() === '' || !Number.isFinite(value) || value < min || value > max
    ? `Enter a number from ${min} to ${max}`
    : null
}

/**
 * What a number field should hold after the user types `raw`: the cleaned
 * text, or `previous` if it isn't a number. ₹, commas and spaces (as in a
 * pasted "₹80,000") are dropped.
 */
export function cleanNumber(raw: string, previous: string, { decimals = 2, negative = false } = {}): string {
  const cleaned = raw.replace(/[₹,\s]/g, '')
  const fraction = decimals > 0 ? `(\\.\\d{0,${decimals}})?` : ''
  if (new RegExp(`^${negative ? '-?' : ''}\\d*${fraction}$`).test(cleaned)) return cleaned
  // Let an over-precise saved value be shortened.
  return cleaned.length < previous.length && /^-?\d*\.?\d*$/.test(cleaned) ? cleaned : previous
}
