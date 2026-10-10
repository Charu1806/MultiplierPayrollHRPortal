export type FieldFormatSpec = {
  pattern: string
  hint: string
  strip?: string
}

/** Mirrors config/rules.json fieldFormats when store rules are unavailable. */
export const DEFAULT_FIELD_FORMATS: Record<string, FieldFormatSpec> = {
  PAN: { pattern: '^[A-Za-z]{5}[0-9]{4}[A-Za-z]$', hint: '5 letters, 4 digits, 1 letter', strip: '\\s' },
  CPF: { pattern: '^[0-9]{11}$', hint: '11 digits', strip: '[.\\-\\s]' },
  'Tax ID': { pattern: '^[0-9]{11}$', hint: '11 digits (Steuer-ID)', strip: '\\s' },
  'Bank account': { pattern: '^[0-9]{8,18}$', hint: '8–18 digits', strip: '\\s' },
  IFSC: { pattern: '^[A-Za-z]{4}0[A-Za-z0-9]{6}$', hint: 'e.g. HDFC0000123', strip: '\\s' },
  'NI number': { pattern: '^[A-Za-z]{2}[0-9]{6}[A-Za-z]$', hint: '2 letters, 6 digits, 1 letter', strip: '\\s' },
  'Sort code': { pattern: '^[0-9]{6}$', hint: '6 digits', strip: '[\\-\\s]' },
  IBAN: {
    pattern: '^[A-Za-z]{2}[0-9]{2}[A-Za-z0-9]{11,30}$',
    hint: 'Country code + check digits + account',
    strip: '\\s',
  },
}

export type FieldValidationResult =
  | { ok: true; normalised: string; error?: undefined }
  | { ok: false; normalised?: undefined; error: string }

export function validateFieldValue(
  field: string,
  value: string,
  formats: Record<string, FieldFormatSpec> = DEFAULT_FIELD_FORMATS,
): FieldValidationResult {
  const trimmed = value.trim()
  if (!trimmed) {
    return { ok: false, error: `${field} is required` }
  }
  const spec = formats[field]
  if (!spec) {
    return { ok: true, normalised: trimmed }
  }
  const stripSource = spec.strip ?? ''
  const cleaned = stripSource ? trimmed.replace(new RegExp(stripSource, 'g'), '') : trimmed
  const re = new RegExp(spec.pattern)
  if (!re.test(cleaned)) {
    return { ok: false, error: `${field}: expected ${spec.hint}` }
  }
  return { ok: true, normalised: cleaned }
}
