import { describe, expect, it } from 'vitest'
import { parseAmount } from './parseAmount'

describe('parseAmount', () => {
  it('parses Indian and Western grouped amounts', () => {
    expect(parseAmount('2,00,000')).toBe(200000)
    expect(parseAmount('200,000')).toBe(200000)
    expect(parseAmount('200000')).toBe(200000)
  })

  it('strips currency symbols', () => {
    expect(parseAmount('₹2,00,000')).toBe(200000)
    expect(parseAmount('£8,000.50')).toBe(8000.5)
  })

  it('rejects invalid or non-positive values', () => {
    expect(parseAmount('abc')).toBeNull()
    expect(parseAmount('')).toBeNull()
    expect(parseAmount('-500')).toBeNull()
    expect(parseAmount('0')).toBeNull()
  })
})
