import type { ReactNode } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { RefreshCw } from 'lucide-react'
import { BreadcrumbBar } from '@/components/Breadcrumb'
import { ConfirmModal, NoticeModal, ToastStack } from '@/components'
import { DatePicker } from '@/components/DatePicker'
import { MultiplierLogo } from '@/components/MultiplierLogo'
import { getClarityApiBase } from '@/api/clarityClient'
import { useAppStore, type PrototypeDate } from '@/store'

const payrollNav = [
  { to: '/payroll/overview', label: 'Overview', badgeKey: null },
  { to: '/payroll/actions', label: 'Action needed', badgeKey: 'actions' as const },
  { to: '/payroll/review', label: 'Review & approve', badgeKey: 'review' as const },
  { to: '/payroll/notifications', label: 'Notifications', badgeKey: null },
] as const

const stubNav = [
  { label: 'AI assistant', tag: 'V2', note: 'Planned for V2' },
  { label: 'Finance view', tag: 'V3', note: 'Planned for V3' },
  { label: 'Calendar view', tag: 'V3', note: 'Planned for V3' },
]

function itemClass(active: boolean) {
  return [
    'relative ml-3 flex items-center justify-between rounded-r px-2 py-1.5 text-[13px]',
    active
      ? 'bg-sky-50 font-medium text-sky-900 before:absolute before:inset-y-0 before:left-0 before:w-0.5 before:bg-sky-600'
      : 'text-text-secondary hover:bg-surface-recessed hover:text-text-primary',
  ].join(' ')
}

function inRange(value: string, min?: string, max?: string): boolean {
  const lo = min || '2026-10-01'
  const hi = max || '2027-01-31'
  return value >= lo && value <= hi
}

function GroupLabel({
  title,
  caption,
  captionColor,
  icon,
  captionOnly,
}: {
  title: string
  caption?: string
  captionColor?: string
  icon?: ReactNode
  captionOnly?: ReactNode
}) {
  return (
    <div className="mb-1 mt-6 flex items-center justify-between gap-2 px-2 first:mt-2">
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{title}</p>
      {captionOnly ? (
        <div className="flex items-center">{captionOnly}</div>
      ) : caption ? (
        <p
          className="flex items-center gap-1 text-[10px] leading-tight"
          style={{ color: captionColor || '#94a3b8' }}
        >
          {icon}
          <span className="truncate">{caption}</span>
        </p>
      ) : null}
    </div>
  )
}

export function Shell() {
  const location = useLocation()
  const navigate = useNavigate()
  const isPayroll = location.pathname.startsWith('/payroll')
  const isPeople = location.pathname.startsWith('/people')

  const asOf = useAppStore((s) => s.asOf)
  const setAsOf = useAppStore((s) => s.setAsOf)
  const overview = useAppStore((s) => s.overview)
  const company = useAppStore((s) => s.company)
  const prototypeDates = useAppStore((s) => s.prototypeDates)
  const isRefreshing = useAppStore((s) => s.isRefreshing)
  const pushToast = useAppStore((s) => s.pushToast)
  const resetDemo = useAppStore((s) => s.resetDemo)
  const askConfirm = useAppStore((s) => s.askConfirm)
  const confirm = useAppStore((s) => s.confirm)
  const confirmBusy = useAppStore((s) => s.confirmBusy)
  const confirmError = useAppStore((s) => s.confirmError)
  const cancelConfirm = useAppStore((s) => s.cancelConfirm)
  const notice = useAppStore((s) => s.notice)
  const dismissNotice = useAppStore((s) => s.dismissNotice)

  const openActions = overview?.statusLine.openActions ?? 0
  const review = useAppStore((s) => s.review)
  const reviewBadge =
    review?.windowState === 'open' && !review.signedOff
      ? (review.badgeCount ?? review.remaining ?? 0)
      : 0
  const cycleLabel = overview?.cycle.label ?? 'Payroll'

  const co = company || {
    name: 'Acme Tech',
    logoInitials: 'AT',
    logoBg: '#0f172a',
    logoFg: '#ffffff',
    workspaceSubtitle: 'HR workspace',
    hrTool: 'Workday',
    syncCaption: 'Synced from Workday',
    syncAgoMinutes: 12,
    payrollCaption: 'Powered by Multiplier',
    multiplierBrandColor: '#863bff',
    admin: { name: 'Maya Rao', role: 'HR admin', initials: 'MR' },
    prototypeBar:
      "Prototype · Acme Tech's HR workspace (employee data synced from Workday) with Multiplier Payroll embedded",
  }

  function badgeFor(key: 'actions' | 'review' | null): number {
    if (key === 'actions') return openActions
    if (key === 'review') return reviewBadge
    return 0
  }

  const syncCaption = `${co.syncCaption} · ${co.syncAgoMinutes} min ago`

  return (
    <div className="flex min-h-full min-w-[1440px] flex-col bg-canvas">
      <div className="flex h-9 items-center justify-between gap-4 border-b border-border bg-surface px-4 text-xs text-text-secondary">
        <div className="flex min-w-0 flex-1 items-center gap-4">
          <span className="truncate">{co.prototypeBar}</span>
          <label className="flex shrink-0 items-center gap-1.5 text-text-primary">
            <span className="text-text-secondary">Prototype date:</span>
            <DatePicker
              value={asOf}
              busy={isRefreshing}
              onChange={(iso) => {
                if (!inRange(iso, prototypeDates?.min, prototypeDates?.max)) return
                void setAsOf(iso as PrototypeDate)
              }}
            />
            {isRefreshing ? <span className="text-text-muted">Refreshing…</span> : null}
          </label>
        </div>
        <span className="tabular shrink-0 text-text-muted">API: {getClarityApiBase()}</span>
      </div>

      <div className="flex min-h-0 flex-1">
        <aside className="flex w-64 shrink-0 flex-col border-r border-border bg-surface">
          <div className="flex items-center gap-2.5 border-b border-border px-4 py-3.5">
            <div
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[11px] font-semibold"
              style={{ background: co.logoBg, color: co.logoFg }}
              aria-hidden
            >
              {co.logoInitials}
            </div>
            <div className="min-w-0">
              <p className="truncate text-[13px] font-semibold text-text-primary">{co.name}</p>
              <p className="truncate text-[11px] text-text-muted">{co.workspaceSubtitle}</p>
            </div>
          </div>

          <nav className="flex flex-1 flex-col overflow-y-auto px-2 pb-2">
            <GroupLabel
              title="People"
              caption={syncCaption}
              icon={<RefreshCw size={10} className="shrink-0 opacity-70" />}
            />
            <NavLink to="/people" className={() => itemClass(isPeople)} end={false}>
              <span>Employees</span>
            </NavLink>
            <button
              type="button"
              className={`${itemClass(false)} cursor-default opacity-50`}
              disabled
              title="Planned for V2"
            >
              <span>Time off</span>
            </button>

            <div className="mx-2 mt-6 border-t border-border" />
            <GroupLabel
              title="Payroll"
              captionOnly={
                <span className="flex max-w-[9.5rem] items-center gap-1">
                  <MultiplierLogo size={12} className="shrink-0 opacity-90" alt="" />
                  <span
                    className="truncate text-[10px] font-medium leading-tight"
                    style={{ color: co.multiplierBrandColor || 'var(--multiplier-brand)' }}
                  >
                    {co.payrollCaption || 'Powered by Multiplier'}
                  </span>
                </span>
              }
            />
            {payrollNav.map((item) => {
              const count = badgeFor(item.badgeKey)
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => itemClass(isActive)}
                >
                  <span>{item.label}</span>
                  {count > 0 ? (
                    <span className="rounded border border-status-danger-border bg-status-danger-bg px-1 text-[10px] font-medium tabular text-status-danger-text">
                      {count}
                    </span>
                  ) : null}
                </NavLink>
              )
            })}

            <div className="mx-2 mt-6 border-t border-border" />
            <GroupLabel title="Coming next" />
            {stubNav.map((item) => (
              <button
                key={item.label}
                type="button"
                title={item.note}
                className={`${itemClass(false)} w-full cursor-default opacity-50`}
                onClick={() => pushToast(item.note)}
              >
                <span>{item.label}</span>
                <span className="rounded border border-border px-1 text-[10px] font-medium">
                  {item.tag}
                </span>
              </button>
            ))}

            <div className="mt-auto border-t border-border pt-3">
              <div className="mb-2 flex items-center gap-2 px-2">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-200 text-[10px] font-semibold text-slate-700">
                  {co.admin.initials}
                </div>
                <p className="min-w-0 truncate text-[12px] text-text-primary">
                  <span className="font-medium">{co.admin.name}</span>
                  <span className="text-text-muted"> · {co.admin.role}</span>
                </p>
              </div>
              <button
                type="button"
                className="w-full rounded border border-border bg-surface px-2 py-1.5 text-left text-[12px] text-text-secondary hover:bg-surface-recessed hover:text-text-primary"
                onClick={() =>
                  askConfirm({
                    title: 'Reset demo',
                    body: `Reset all demo data to the default prototype date?`,
                    confirmLabel: 'Reset',
                    onConfirm: async () => {
                      await resetDemo()
                      navigate('/payroll/overview')
                    },
                  })
                }
              >
                Reset demo
              </button>
            </div>
          </nav>
        </aside>

        <main className="flex min-w-0 flex-1 flex-col">
          {isPayroll || isPeople ? (
            <header className="flex h-11 items-center justify-between border-b border-border bg-surface px-6 text-[13px]">
              <div className="flex items-center">
                <p className="font-medium text-text-primary">
                  {isPayroll ? `Payroll · ${cycleLabel}` : 'People'}
                </p>
                <MultiplierLogo size={18} className="ml-3" />
                <span
                  className="ml-1.5 font-medium"
                  style={{ color: co.multiplierBrandColor || 'var(--multiplier-brand)' }}
                >
                  {co.payrollCaption}
                </span>
              </div>
            </header>
          ) : null}

          <div className="flex-1 px-6 py-5">
            <BreadcrumbBar />
            <Outlet />
          </div>

          <footer className="flex items-center justify-between border-t border-border px-6 py-2 text-[11px] text-text-muted">
            <span>
              Illustrative data · as of <span className="tabular">{asOf}</span>
              {overview ? (
                <>
                  {' '}
                  · {overview.statusLine.openActions} open actions ·{' '}
                  {overview.statusLine.countdown}
                </>
              ) : null}
            </span>
            <span>Desktop prototype (1440px) · Mobile in V2</span>
          </footer>
        </main>
      </div>

      <ToastStack />
      <ConfirmModal
        request={confirm}
        busy={confirmBusy}
        error={confirmError}
        onCancel={cancelConfirm}
      />
      <NoticeModal message={notice} onOk={dismissNotice} />
    </div>
  )
}
