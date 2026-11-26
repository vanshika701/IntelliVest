import { describe, expect, it } from 'vitest'
import { describeHorizon, validateHorizon } from './predictionHorizon'

describe('validateHorizon', () => {
  it('accepts whole numbers within each unit limit', () => {
    expect(validateHorizon('7', 'days')).toBeNull()
    expect(validateHorizon('730', 'days')).toBeNull()
    expect(validateHorizon('24', 'months')).toBeNull()
    expect(validateHorizon('2', 'years')).toBeNull()
  })

  it('rejects empty, zero, decimals and values past the limit', () => {
    expect(validateHorizon('', 'days')).toBe('Enter a whole number')
    expect(validateHorizon('0', 'months')).toBe('Enter a whole number')
    expect(validateHorizon('1.5', 'years')).toBe('Enter a whole number')
    expect(validateHorizon('731', 'days')).toBe('Up to 730 days')
    expect(validateHorizon('3', 'years')).toBe('Up to 2 years')
  })
})

describe('describeHorizon', () => {
  it('uses singular for one', () => {
    expect(describeHorizon(1, 'months')).toBe('1 month')
    expect(describeHorizon(3, 'years')).toBe('3 years')
  })
})
