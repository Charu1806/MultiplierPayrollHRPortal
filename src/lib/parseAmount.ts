/**
 * Parse a user-typed money string into a major-unit number.
 * Strips currency symbols, spaces and commas (Indian 2,00,000 and Western 200,000).
 * Returns null if invalid or ≤ 0.
 */
export function parseAmount(input: string): number | null {
  if (input == null) return null
  let s = String(input).trim()
  if (!s) return null
  s = s.replace(/^(₹|£|€|R\$|\$)\s*/i, '')
  s = s.replace(/\s+/g, '').replace(/,/g, '')
  if (!/^\d+(\.\d+)?$/.test(s)) return null
  const n = Number(s)
  if (!Number.isFinite(n) || n <= 0) return null
  return n
}

/** Major units → minor units (paise/pence/cents/centavos). */
export function toMinorUnits(major: number): number {
  return Math.round(major * 100)
}

/** Minor units → major units for display/calculation. */
export function fromMinorUnits(minor: number): number {
  return minor / 100
}

export function formatAmountForCountry(country: string, amount: number): string {
  const n = Number(amount)
  if (!Number.isFinite(n)) return ''
  switch (country) {
    case 'India':
      return n.toLocaleString('en-IN', { maximumFractionDigits: 2 })
    case 'Germany':
      return n.toLocaleString('de-DE', { maximumFractionDigits: 2 })
    case 'Brazil':
      return n.toLocaleString('pt-BR', { maximumFractionDigits: 2 })
    case 'UK':
    default:
      return n.toLocaleString('en-GB', { maximumFractionDigits: 2 })
  }
}
