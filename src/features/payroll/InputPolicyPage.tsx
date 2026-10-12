import { Link } from 'react-router-dom'
import { PageHeader, StatusChip } from '@/components'

export function InputPolicyPage() {
  return (
    <div>
      <PageHeader
        title="Payroll input policy"
        subtitle="Demonstration document for this prototype. It is not company policy."
        actions={<StatusChip tone="neutral">Demo</StatusChip>}
      />

      <article className="max-w-2xl space-y-4 text-[13px] leading-relaxed text-text-primary">
        <p>
          Payroll inputs for a cycle close on the 15th of the month. Complete the
          work below on or before that date.
        </p>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            Resolve open items in{' '}
            <Link to="/payroll/actions" className="font-medium text-sky-800 underline">
              Action needed
            </Link>
            .
          </li>
          <li>Add new employees.</li>
          <li>Add salary changes.</li>
          <li>Add bonuses.</li>
        </ul>
        <p>
          If this work is not completed by the cutoff, affected employees may have
          all or part of their pay moved to the next cycle.
        </p>
        <p className="text-xs text-text-secondary">
          This page is a demo link from the cutoff email. It does not change pay.
        </p>
      </article>
    </div>
  )
}
