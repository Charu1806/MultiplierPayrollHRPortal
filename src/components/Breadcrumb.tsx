import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useAppStore } from '@/store'

export type Crumb = { label: string; to?: string }

const TOP_LEVEL = new Set(['/payroll/overview', '/people'])

function buildCrumbs(pathname: string, employeeName?: string | null): Crumb[] {
  const hr: Crumb = { label: 'HR workspace', to: '/payroll/overview' }

  if (pathname.startsWith('/payroll/employees')) {
    return [hr, { label: 'Payroll', to: '/payroll/overview' }, { label: 'Employees' }]
  }
  if (pathname.startsWith('/payroll/overview')) {
    return [hr, { label: 'Payroll', to: '/payroll/overview' }, { label: 'Overview' }]
  }
  if (pathname.startsWith('/payroll/actions')) {
    return [hr, { label: 'Payroll', to: '/payroll/overview' }, { label: 'Action needed' }]
  }
  if (pathname.startsWith('/payroll/review')) {
    return [hr, { label: 'Payroll', to: '/payroll/overview' }, { label: 'Review & approve' }]
  }
  if (pathname.startsWith('/people/notifications')) {
    return [hr, { label: 'People', to: '/people' }, { label: 'Notifications' }]
  }
  if (pathname.startsWith('/payroll/input-policy')) {
    return [
      hr,
      { label: 'Payroll', to: '/payroll/overview' },
      { label: 'Notifications', to: '/people/notifications' },
      { label: 'Payroll input policy' },
    ]
  }
  if (pathname === '/people' || pathname === '/people/') {
    return [hr, { label: 'Employees', to: '/people' }, { label: 'All employees' }]
  }
  if (pathname.startsWith('/people/add')) {
    return [hr, { label: 'Employees', to: '/people' }, { label: 'Add employee' }]
  }

  const otp = pathname.match(/^\/people\/([^/]+)\/one-time-payment/)
  if (otp) {
    const name = employeeName || 'Employee'
    return [
      hr,
      { label: 'Employees', to: '/people' },
      { label: name, to: `/people/${otp[1]}` },
      { label: 'Add one-time payment' },
    ]
  }
  const exit = pathname.match(/^\/people\/([^/]+)\/exit/)
  if (exit) {
    const name = employeeName || 'Employee'
    return [
      hr,
      { label: 'Employees', to: '/people' },
      { label: name, to: `/people/${exit[1]}` },
      { label: 'Record exit' },
    ]
  }
  const profile = pathname.match(/^\/people\/([^/]+)/)
  if (profile) {
    const name = employeeName || 'Employee'
    return [hr, { label: 'Employees', to: '/people' }, { label: name }]
  }

  return [hr, { label: 'Payroll', to: '/payroll/overview' }, { label: 'Overview' }]
}

export function BreadcrumbBar() {
  const location = useLocation()
  const navigate = useNavigate()
  const params = useParams()
  const employeeDetail = useAppStore((s) => s.employeeDetail)
  const employees = useAppStore((s) => s.employees)

  const id = params.id
  const name =
    (employeeDetail && id && employeeDetail.id === id ? employeeDetail.name : null) ||
    (id ? employees.find((e) => e.id === id)?.name : null)

  const crumbs = buildCrumbs(location.pathname, name)
  const showBack = !TOP_LEVEL.has(location.pathname.replace(/\/$/, '') || '/')
  const parent = [...crumbs].reverse().find((c) => c.to)

  return (
    <div className="mb-2 flex items-center gap-2 text-xs text-text-secondary">
      {showBack ? (
        <button
          type="button"
          className="shrink-0 text-text-secondary hover:text-text-primary"
          onClick={() => {
            if (window.history.length > 1) navigate(-1)
            else if (parent?.to) navigate(parent.to)
            else navigate('/payroll/overview')
          }}
        >
          ← Back
        </button>
      ) : null}
      <nav aria-label="Breadcrumb" className="flex min-w-0 flex-wrap items-center gap-1">
        {crumbs.map((c, i) => {
          const last = i === crumbs.length - 1
          return (
            <span key={`${c.label}-${i}`} className="flex items-center gap-1">
              {i > 0 ? <span className="text-text-muted">/</span> : null}
              {last || !c.to ? (
                <span className={last ? 'font-medium text-text-primary' : ''}>{c.label}</span>
              ) : (
                <Link to={c.to} className="hover:text-text-primary hover:underline">
                  {c.label}
                </Link>
              )}
            </span>
          )
        })}
      </nav>
    </div>
  )
}
