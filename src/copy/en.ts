/** User-facing templates with named placeholders — values come from the API. */

export const copy = {
  statusLine: '{count} {actionsWord} need you before input finalisation on {cutoff} · {daysLeft} days left',
  poweredBy: 'Powered by Multiplier',
  payThisCycle: 'Pay this cycle',
  reminderWaiting: 'Reminder emailed {when} · waiting for {name}',
  includedInPay: 'Included in {month} pay',
  movesTo: 'Moves to {month}',
  smtpMissing: 'Not sent · SMTP not set up',
  emptyEmployees: 'No employees match these filters.',
  emptyIssues: 'Nothing needs you right now.',
} as const

export function fill(template: string, vars: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(vars[key] ?? ''))
}
