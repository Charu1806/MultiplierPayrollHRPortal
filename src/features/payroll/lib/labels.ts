import type { CountryStatus, Severity } from '@/api/types'
import type { Tone } from '@/components/StatusChip'

/** Stage names only — dates come from cycle config / API, never hard-coded here. */
export const STAGE_KEYS = [
  'Input finalisation',
  'Calculation & final checks',
  'Review',
  'Funding',
  'Submitted',
  'Paid',
] as const

export function formatIsoDate(iso: string): string {
  // Accept date-only or full ISO datetime
  const raw = iso.includes('T') ? iso : `${iso}T00:00:00`
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

/** Journey step timestamps (e.g. 2026-10-10T11:33:18 → Oct 10, 11:33). */
export function formatJourneyAt(iso: string): string {
  const d = new Date(iso.includes('T') ? iso : `${iso}T00:00:00`)
  if (Number.isNaN(d.getTime())) return iso
  const date = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
  return `${date}, ${time}`
}

export function countryCode(country: string): string {
  switch (country) {
    case 'India':
      return 'IN'
    case 'UK':
      return 'UK'
    case 'Germany':
      return 'DE'
    case 'Brazil':
      return 'BR'
    default:
      return country.slice(0, 2).toUpperCase()
  }
}

export function countryStatusTone(status: CountryStatus): Tone {
  switch (status) {
    case 'On track':
      return 'ok'
    case 'Action needed':
      return 'warn'
    case 'Deadline risk':
      return 'danger'
    default:
      return 'neutral'
  }
}

export function severityTone(severity: Severity): Tone {
  switch (severity) {
    case 'blocking':
      return 'danger'
    case 'deadline_risk':
      return 'danger'
    case 'needs_confirmation':
      return 'warn'
    case 'next_cycle':
      return 'neutral'
    default:
      return 'neutral'
  }
}

export function severityLabel(severity: Severity): string {
  switch (severity) {
    case 'blocking':
      return 'Blocking'
    case 'deadline_risk':
      return 'Deadline risk'
    case 'needs_confirmation':
      return 'Needs confirmation'
    case 'next_cycle':
      return 'Next cycle'
    default:
      return severity
  }
}

export function whoLabel(issue: {
  title: string
  country: string
  employeeId?: string | null
  employeeName?: string | null
  who?: string
}): string {
  if (issue.employeeName) return issue.employeeName
  if (issue.who) return issue.who
  return issue.country
}

/** Shared currency formatter — India uses lakh grouping; others use en-GB thousands. */
export function formatMoney(currency: string, amount: number): string {
  const n = Number(amount)
  if (currency === '₹' || currency === 'INR') {
    return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
  }
  if (currency === '£' || currency === 'GBP') {
    return `£${n.toLocaleString('en-GB', { maximumFractionDigits: 2 })}`
  }
  if (currency === '€' || currency === 'EUR') {
    return `€${n.toLocaleString('de-DE', { maximumFractionDigits: 2 })}`
  }
  if (currency === 'R$' || currency === 'BRL') {
    return `R$${n.toLocaleString('pt-BR', { maximumFractionDigits: 2 })}`
  }
  return `${currency}${n.toLocaleString('en-GB', { maximumFractionDigits: 2 })}`
}
