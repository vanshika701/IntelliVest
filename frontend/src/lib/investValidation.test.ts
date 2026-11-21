import { describe, expect, it } from 'vitest'
import { validateAmount } from './investValidation'
import { ordinal } from './ordinal'

describe('validateAmount', () => {
  it('accepts amounts at or above the minimum', () => {
    expect(validateAmount('1000', 1000, 'investment')).toBeNull()
    expect(validateAmount('1500.50', 1000, 'investment')).toBeNull()
  })

  it('rejects empty, zero, negative and over-precise input', () => {
    expect(validateAmount('', 500, 'SIP')).toBe('Enter an amount')
    expect(validateAmount('0', 500, 'SIP')).toBe('Enter an amount')
    expect(validateAmount('-5', 500, 'SIP')).toBe('Enter an amount')
    expect(validateAmount('600.123', 500, 'SIP')).toBe('Use at most 2 decimal places')
  })

  it('names the minimum in the error', () => {
    expect(validateAmount('499', 500, 'SIP')).toBe('Minimum SIP is ₹500')
  })

  it('caps a single order', () => {
    expect(validateAmount('10000001', null, 'investment')).toMatch(/Maximum per order/)
  })
})

describe('ordinal', () => {
  it('handles the teens and 21st–23rd', () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 28].map(ordinal)).toEqual([
      '1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '22nd', '23rd', '28th',
    ])
  })
})
