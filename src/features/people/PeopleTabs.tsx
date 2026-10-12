import { NavLink, useMatch } from 'react-router-dom'
import { Button } from '@/components'

export function PeopleTabs() {
  const adding = useMatch('/people/add')
  const tab =
    ({ isActive }: { isActive: boolean }) =>
      [
        'rounded px-3 py-1.5 text-[13px]',
        isActive
          ? 'bg-status-info-bg font-medium text-status-info-text'
          : 'text-text-secondary hover:bg-surface-recessed',
      ].join(' ')

  return (
    <div className="mb-3 flex items-center justify-between gap-3 border-b border-border pb-2">
      <div className="flex gap-1">
        <NavLink to="/people" end className={tab}>
          All employees
        </NavLink>
      </div>
      {adding ? null : (
        <NavLink to="/people/add">
          <Button variant="primary" data-testid="add-employee">
            Add employee
          </Button>
        </NavLink>
      )}
    </div>
  )
}
