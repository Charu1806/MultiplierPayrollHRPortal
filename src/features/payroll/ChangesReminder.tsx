import { Link } from 'react-router-dom'
import { Button } from '@/components'
import type { ChangesReminder as ChangesReminderDto } from '@/api/types'

export function ChangesReminder({ reminder }: { reminder: ChangesReminderDto | null | undefined }) {
  if (!reminder) return null
  const body = reminder.body.replace(/\*\*(.*?)\*\*/g, '$1')
  return (
    <section className="rounded border border-border bg-surface px-4 py-3">
      <p className="text-[13px] font-semibold text-text-primary">{reminder.title}</p>
      <p className="mt-1 text-xs text-text-secondary">{body}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {reminder.actions.map((a) => (
          <Link key={a.href} to={a.href}>
            <Button variant="secondary">{a.label}</Button>
          </Link>
        ))}
      </div>
    </section>
  )
}
