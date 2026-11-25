import { describe, expect, it } from 'vitest'
import { cleanNumber, validateBirthDate, validateEmail, validateName, validateNewPassword, validateRange, validateTicker } from './validation'

describe('field validation', () => {
  it('checks email format', () => {
    for (const ok of ['a@example.com', ' first.last+tag@snu.edu.in ']) expect(validateEmail(ok)).toBeNull()
    for (const bad of ['', 'abc', 'a@b', 'a@b.', '@b.com', 'a b@c.com', 'a..b@c.com', 'a@-b.com', 'a@b.c']) {
      expect(validateEmail(bad)).not.toBeNull()
    }
  })

  it('checks names', () => {
    for (const ok of ['Asha', "Mary-Jane O'Neil Jr.", 'José', 'मुस्कान']) expect(validateName(ok)).toBeNull()
    for (const bad of ['', '  ', '123', 'Asha1', '<b>']) expect(validateName(bad)).not.toBeNull()
  })

  it('checks passwords, birth dates, tickers and ranges', () => {
    expect(validateNewPassword('1234567')).not.toBeNull()
    expect(validateNewPassword('12345678')).toBeNull()
    expect(validateNewPassword('é'.repeat(40))).not.toBeNull()
    expect(validateBirthDate('2026-01-01', '2026-01-01')).not.toBeNull()
    expect(validateBirthDate('1899-12-31', '2026-01-01')).not.toBeNull()
    expect(validateBirthDate('2000-05-17', '2026-01-01')).toBeNull()
    for (const ok of ['zomato.ns', 'M&M.NS', 'BAJAJ-AUTO.NS', 'AAPL']) expect(validateTicker(ok)).toBeNull()
    for (const bad of ['', 'A B', '$$$', '.NS']) expect(validateTicker(bad)).not.toBeNull()
    expect(validateRange('51', 0.1, 50)).not.toBeNull()
    expect(validateRange('', 0.1, 50)).not.toBeNull()
    expect(validateRange('5', 0.1, 50)).toBeNull()
  })
})

describe('cleanNumber', () => {
  it('keeps numbers and rejects anything else', () => {
    expect(cleanNumber('12.5', '12.')).toBe('12.5')
    expect(cleanNumber('₹80,000', '')).toBe('80000')
    for (const bad of ['12a', '1e5', '-1', '1.234', '1..2']) expect(cleanNumber(bad, '1')).toBe('1')
    expect(cleanNumber('1.5', '1', { decimals: 0 })).toBe('1')
    expect(cleanNumber('-5', '-', { negative: true })).toBe('-5')
  })

  it('lets an over-precise saved value be shortened', () => {
    expect(cleanNumber('1.234', '1.2345')).toBe('1.234')
  })
})
