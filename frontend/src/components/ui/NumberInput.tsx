import type { InputHTMLAttributes } from 'react'
import { cleanNumber } from '../../lib/validation'
import { Input } from './Input'

interface Props extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type' | 'value' | 'onChange'> {
  value: string
  onValueChange: (value: string) => void
  /** Digits allowed after the point; 0 = whole numbers only. */
  decimals?: number
  negative?: boolean
}

/** Text input that only accepts numbers. */
export function NumberInput({ value, onValueChange, decimals = 2, negative = false, ...props }: Props) {
  return (
    <Input
      autoComplete="off"
      inputMode={negative ? 'text' : decimals > 0 ? 'decimal' : 'numeric'}
      {...props}
      value={value}
      onChange={(e) => onValueChange(cleanNumber(e.target.value, value, { decimals, negative }))}
    />
  )
}
