import type { Country } from '@/api/types'

export type OfferDemoFile = 'offer_letter_priya.pdf' | 'offer_letter_arjun.pdf'

export type DemoPrefill = {
  filename: OfferDemoFile
  legalName: string
  workEmail: string
  workLocation: Country
  hireDate: string
  monthlySalary?: number
  jobTitle: string
  manager: string
}

export const OFFER_DEMO_FILES: DemoPrefill[] = [
  {
    filename: 'offer_letter_priya.pdf',
    legalName: 'Priya Nair',
    workEmail: 'priya.nair@acmetech.example',
    workLocation: 'India',
    hireDate: '2026-10-20',
    monthlySalary: 150000,
    jobTitle: 'Software Engineer',
    manager: '',
  },
  {
    filename: 'offer_letter_arjun.pdf',
    legalName: 'Arjun Mehta',
    workEmail: 'arjun.mehta@acmetech.example',
    workLocation: 'India',
    hireDate: '2026-10-27',
    monthlySalary: 95000,
    jobTitle: 'Data Analyst',
    manager: 'Neha Kapoor',
  },
]

export const BONUS_DEMO_FILE = 'bonus_letter_james.pdf'
export const TRAVEL_DEMO_FILE = 'travel_reimbursement_chloe.pdf'
