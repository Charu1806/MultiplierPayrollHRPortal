import type { CompanyConfig, Country, NotificationListItem } from '@/api/types'

export type PersonaId = 'global' | 'IN' | 'UK' | 'DE' | 'BR'

export type CountryAdmin = {
  code: Exclude<PersonaId, 'global'>
  country: Country
  name: string
  role: string
  initials: string
  email: string
}

const FALLBACK_ADMINS: CountryAdmin[] = [
  { code: 'IN', country: 'India', name: 'Priya Mehta', role: 'Country HR admin', initials: 'PM', email: 'priya.mehta@acmetech.example' },
  { code: 'UK', country: 'UK', name: 'Helen Clarke', role: 'Country HR admin', initials: 'HC', email: 'helen.clarke@acmetech.example' },
  { code: 'DE', country: 'Germany', name: 'Greta Hoffmann', role: 'Country HR admin', initials: 'GH', email: 'greta.hoffmann@acmetech.example' },
  { code: 'BR', country: 'Brazil', name: 'Camila Rocha', role: 'Country HR admin', initials: 'CR', email: 'camila.rocha@acmetech.example' },
]

export function countryAdmins(company: CompanyConfig | null | undefined): CountryAdmin[] {
  const rows = company?.countryAdmins
  if (!rows?.length) return FALLBACK_ADMINS
  return rows.map((row) => ({
    code: row.code,
    country: row.country,
    name: row.name,
    role: row.role || 'Country HR admin',
    initials: row.initials,
    email: row.email,
  }))
}

export function personaCountry(persona: PersonaId, company: CompanyConfig | null | undefined): Country | null {
  if (persona === 'global') return null
  return countryAdmins(company).find((row) => row.code === persona)?.country ?? null
}

export function cycleDay(payDate: string, day: number): string {
  const [year, month] = payDate.split('-')
  return `${year}-${month}-${String(day).padStart(2, '0')}`
}

export function readStoredPersona(): PersonaId {
  if (typeof window === 'undefined') return 'global'
  const value = window.localStorage.getItem('clarity.persona')
  if (value === 'IN' || value === 'UK' || value === 'DE' || value === 'BR' || value === 'global') return value
  return 'global'
}

export function writeStoredPersona(persona: PersonaId) {
  window.localStorage.setItem('clarity.persona', persona)
}

export function notificationVisible(
  item: NotificationListItem,
  persona: PersonaId,
  company: CompanyConfig | null | undefined,
): boolean {
  const admin = countryAdmins(company).find((row) => row.code === persona)
  if (item.kind === 'hr_query') {
    if (persona === 'global') return true
    return Boolean(admin && item.recipient.includes(admin.name))
  }
  if (item.kind?.startsWith('employee_reminder')) {
    if (persona === 'global') return true
    return Boolean(admin && item.country === admin.country)
  }
  if (persona === 'global') return item.audience === 'global'
  if (!admin) return false
  return (item.audience === 'country' || item.audience === 'employee') && item.country === admin.country
}
