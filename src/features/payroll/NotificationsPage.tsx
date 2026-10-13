import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, Bell, Mail, MessageSquare, Phone } from 'lucide-react'
import { Button, EmptyState, PageHeader, StatusChip } from '@/components'
import { formatIsoDate } from '@/features/payroll/lib/labels'
import { notificationVisible } from '@/features/persona'
import { useAppStore } from '@/store'
import type { NotificationListItem } from '@/api/types'

type RecipientFilter = 'all' | 'hr' | 'finance' | 'employees'

function recipientBucket(item: NotificationListItem): RecipientFilter | 'other' {
  if (item.audience === 'finance' || item.kind === 'funding_confirm' || item.recipient === 'Finance') return 'finance'
  if (item.recipient === 'HR admin') return 'hr'
  if (item.kind?.startsWith('employee_reminder') || item.kind?.startsWith('payroll_on_track')) return 'employees'
  return 'employees'
}

function isUndelivered(item: NotificationListItem): boolean {
  return (
    item.delivery === 'not_sent_smtp_missing' ||
    item.kind === 'employee_reminder_undelivered'
  )
}

function InboxItem({
  item,
  selected,
  unreadIndex,
  onSelect,
}: {
  item: NotificationListItem
  selected: boolean
  unreadIndex: number | null
  onSelect: () => void
}) {
  const unread = item.unread !== false
  return (
    <button
      type="button"
      onClick={onSelect}
      className={[
        'w-full rounded border px-3 py-2.5 text-left transition-colors',
        selected
          ? 'border-border bg-surface-recessed'
          : 'border-border bg-surface hover:bg-canvas',
      ].join(' ')}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-[11px] font-medium text-text-secondary">
          {unreadIndex != null ? (
            <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-sky-600 px-1 text-[10px] font-semibold tabular text-white">
              {unreadIndex}
            </span>
          ) : null}
          Multiplier Payroll
        </span>
        <span className="tabular text-[11px] text-text-muted">
          {formatIsoDate(item.sendDate)}
        </span>
      </div>
      <p
        className={[
          'mt-0.5 truncate text-[13px] text-text-primary',
          unread ? 'font-semibold' : 'font-medium text-text-secondary',
        ].join(' ')}
      >
        {item.subject}
      </p>
      <p className="mt-0.5 truncate text-xs text-text-secondary">
        {item.bodySummary}
      </p>
      <div className="mt-1.5 flex items-center gap-1.5">
        <StatusChip tone={item.recipient === 'Finance' ? 'info' : 'neutral'}>
          To: {item.recipient}
        </StatusChip>
        {item.actionCount ? (
          <StatusChip tone={item.actionCount > 1 ? 'warn' : 'neutral'}>
            {item.actionCount} action{item.actionCount === 1 ? '' : 's'}
          </StatusChip>
        ) : null}
        {isUndelivered(item) ? (
          <StatusChip tone="warn">Not sent · SMTP</StatusChip>
        ) : null}
      </div>
    </button>
  )
}

export function NotificationsPage() {
  const navigate = useNavigate()
  const asOf = useAppStore((s) => s.asOf)
  const notifications = useAppStore((s) => s.notifications)
  const persona = useAppStore((s) => s.persona)
  const company = useAppStore((s) => s.company)
  const selected = useAppStore((s) => s.selectedNotification)
  const loadNotification = useAppStore((s) => s.loadNotification)
  const confirmFunding = useAppStore((s) => s.confirmFunding)
  const pushToast = useAppStore((s) => s.pushToast)
  const [confirming, setConfirming] = useState<'yes' | 'no' | null>(null)
  const [recipientFilter, setRecipientFilter] = useState<RecipientFilter>('all')

  const inbox = useMemo(() => {
    const sorted = [...notifications].sort((a, b) => {
      const byDate = b.sendDate.localeCompare(a.sendDate)
      if (byDate !== 0) return byDate
      const aHas = a.createdAt ? 1 : 0
      const bHas = b.createdAt ? 1 : 0
      if (aHas !== bHas) return bHas - aHas
      return (b.createdAt || '').localeCompare(a.createdAt || '')
    })
    const scoped = sorted.filter((item) => notificationVisible(item, persona, company))
    if (recipientFilter === 'all') return scoped
    return scoped.filter((item) => recipientBucket(item) === recipientFilter)
  }, [notifications, recipientFilter, persona, company])

  const unreadCount = inbox.filter((item) => item.unread !== false).length
  let unreadCursor = 0
  const unreadLabel =
    unreadCount === 0
      ? 'No unread messages'
      : unreadCount === 1
        ? '1 unread message'
        : `${unreadCount} unread messages`

  const filterChips: { key: RecipientFilter; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'hr', label: 'To HR' },
    { key: 'finance', label: 'To finance' },
    { key: 'employees', label: 'To employees' },
  ]

  // Keep a valid selection: newest first, re-pick when the asOf window changes.
  useEffect(() => {
    if (!inbox.length) return
    const stillVisible = selected && inbox.some((n) => n.id === selected.id)
    if (!stillVisible) {
      void loadNotification(inbox[0].id)
    }
  }, [inbox, selected, loadNotification])

  return (
    <div>
      <PageHeader
        title="Notifications"
        subtitle="Reminder-first: one grouped email per nudge · AI Voice call and Slack arrive in V2 · In-app alerts arrive in V3"
      />

      <div className="mb-3 flex items-center gap-1 border-b border-border">
        <button
          type="button"
          className="flex items-center gap-1.5 border-b-2 border-text-primary px-3 py-2 text-[13px] font-medium text-text-primary"
        >
          <Mail size={14} />
          Email
          <span
            className={[
              'rounded border px-1 text-[10px] tabular',
              unreadCount > 0
                ? 'border-rose-200 bg-rose-50 text-rose-700'
                : 'border-border text-text-secondary',
            ].join(' ')}
          >
            {unreadCount > 0 ? unreadCount : inbox.length}
          </span>
        </button>
        <button
          type="button"
          className="flex items-center gap-1.5 px-3 py-2 text-[13px] text-text-muted opacity-60"
          onClick={() => pushToast('AI Voice call is coming in V2')}
        >
          <Phone size={14} />
          AI Voice call
          <span className="rounded border border-border px-1 text-[10px] font-medium">
            V2
          </span>
        </button>
        <button
          type="button"
          className="flex items-center gap-1.5 px-3 py-2 text-[13px] text-text-muted opacity-60"
          onClick={() => pushToast('Slack reminders are coming in V2')}
        >
          <MessageSquare size={14} />
          Slack
          <span className="rounded border border-border px-1 text-[10px] font-medium">
            V2
          </span>
        </button>
        <button
          type="button"
          className="flex items-center gap-1.5 px-3 py-2 text-[13px] text-text-muted opacity-60"
          onClick={() => pushToast('In-app alerts are coming in V3')}
        >
          <Bell size={14} />
          In-app alerts
          <span className="rounded border border-border px-1 text-[10px] font-medium">
            V3
          </span>
        </button>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-1.5">
        {filterChips.map((chip) => (
          <button
            key={chip.key}
            type="button"
            onClick={() => setRecipientFilter(chip.key)}
            className={[
              'rounded-full border px-2.5 py-1 text-[12px]',
              recipientFilter === chip.key
                ? 'border-sky-600 bg-sky-50 font-medium text-sky-900'
                : 'border-border bg-surface text-text-secondary hover:bg-surface-recessed',
            ].join(' ')}
          >
            {chip.label}
          </button>
        ))}
      </div>

      {inbox.length === 0 ? (
        <EmptyState
          title="No emails yet"
          description={`Nothing sent on or before ${formatIsoDate(asOf)}.`}
        />
      ) : (
        <div className="grid grid-cols-[320px_1fr] gap-4">
          <aside className="space-y-2" data-testid="inbox">
            <p className="px-1 text-[11px] font-medium uppercase tracking-wide text-text-muted">
              Inbox · newest first · {unreadLabel}
            </p>
            {inbox.map((item) => {
              const unreadIndex = item.unread !== false ? ++unreadCursor : null
              return (
                <InboxItem
                  key={item.id}
                  item={item}
                  unreadIndex={unreadIndex}
                  selected={selected?.id === item.id}
                  onSelect={() => void loadNotification(item.id)}
                />
              )
            })}
          </aside>

          <section
            className="rounded border border-border bg-surface"
            data-testid="email-detail"
          >
            {selected && inbox.some((n) => n.id === selected.id) ? (
              <>
                <div className="border-b border-border px-5 py-4">
                  <h2 className="text-base font-semibold text-text-primary">
                    {selected.subject}
                  </h2>
                  <p className="mt-1 text-xs text-text-secondary">
                    From Multiplier Payroll · To: {selected.recipient}
                    {selected.cc ? ` · Cc: ${selected.cc}` : ''} ·{' '}
                    <span className="tabular">{formatIsoDate(selected.sendDate)}</span>
                  </p>
                </div>
                <div className="space-y-4 px-5 py-4 text-[13px] text-text-primary">
                  {selected && isUndelivered(selected) ? (
                    <p className="rounded border border-status-warn-border bg-status-warn-bg px-3 py-2 text-xs text-status-warn-text">
                      Not delivered – SMTP not set up (see README). Use the button below to open
                      Missing details on the employee profile.
                    </p>
                  ) : null}
                  <p className="whitespace-pre-wrap">{selected.bodySummary}</p>

                  {selected.policy ? (
                    <p className="text-[13px]">
                      <Link
                        to={selected.policy.href}
                        className="font-medium text-sky-800 underline decoration-sky-800/40 underline-offset-2"
                      >
                        {selected.policy.label}
                      </Link>
                      {selected.policy.note ? (
                        <span className="ml-2 text-[11px] font-medium uppercase tracking-wide text-text-muted">
                          {selected.policy.note}
                        </span>
                      ) : null}
                    </p>
                  ) : null}

                  {selected.actions.length > 0 ? (
                    <div>
                      <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-text-muted">
                        {selected.kind?.startsWith('employee_reminder')
                          ? 'What we need'
                          : selected.actions.length === 1
                            ? 'What to do'
                            : `${selected.actions.length} actions, grouped`}
                      </p>
                      <ol className="divide-y divide-border rounded border border-border">
                        {selected.actions.map((a, index) => (
                          <li
                            key={`${a.actionText}-${index}`}
                            className="flex items-center justify-between gap-3 px-3 py-2"
                          >
                            {a.href ? (
                              <Link
                                to={a.href}
                                className="font-medium text-sky-800 underline decoration-sky-800/40 underline-offset-2"
                              >
                                {a.actionText}
                              </Link>
                            ) : (
                              <span>{a.actionText}</span>
                            )}
                            {a.deadline ? (
                              <span className="shrink-0 tabular text-xs text-text-secondary">
                                Deadline {formatIsoDate(a.deadline)}
                              </span>
                            ) : null}
                          </li>
                        ))}
                      </ol>
                    </div>
                  ) : null}

                  <p className="text-xs text-text-secondary">
                    Everything above is resolved in one place; no replies or
                    attachments needed.
                  </p>

                  {selected.fundingConfirm ? (
                    <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
                      <Button
                        variant={selected.fundingConfirm.decision === 'yes' ? 'primary' : 'secondary'}
                        data-testid="funding-yes"
                        disabled={confirming !== null}
                        onClick={() => {
                          const cycleKey = selected.fundingConfirm?.cycleKey
                          if (!cycleKey) return
                          setConfirming('yes')
                          void confirmFunding('yes', cycleKey).finally(() => setConfirming(null))
                        }}
                      >
                        Yes
                      </Button>
                      <Button
                        variant={selected.fundingConfirm.decision === 'no' ? 'primary' : 'secondary'}
                        data-testid="funding-no"
                        disabled={confirming !== null}
                        onClick={() => {
                          const cycleKey = selected.fundingConfirm?.cycleKey
                          if (!cycleKey) return
                          setConfirming('no')
                          void confirmFunding('no', cycleKey).finally(() => setConfirming(null))
                        }}
                      >
                        No
                      </Button>
                      <span className="text-[11px] text-text-muted">
                        {selected.fundingConfirm.fundsAddedOn
                          ? `Funds added ${formatIsoDate(selected.fundingConfirm.fundsAddedOn)}`
                          : selected.fundingConfirm.decision === 'no'
                            ? 'Funds are not added'
                            : 'Yes adds the funds today. No leaves them unadded.'}
                      </span>
                    </div>
                  ) : (
                  <div className="flex items-center gap-3 border-t border-border pt-4">
                    <Button
                      variant="primary"
                      onClick={() => navigate(selected.cta.href)}
                    >
                      {selected.cta.label.replace(/\s*→\s*$/, '')}
                      <ArrowRight size={14} className="ml-1.5" />
                    </Button>
                    <span className="text-[11px] text-text-muted">
                      {selected.cta.href.includes('panel=missing')
                        ? 'Opens Missing details on the employee profile'
                        : selected.cta.href.startsWith('/form/')
                          ? 'Opens the employee form'
                          : 'Opens the Payroll tab inside your HR tool'}
                    </span>
                  </div>
                  )}
                </div>
              </>
            ) : (
              <EmptyState title="Select an email" />
            )}
          </section>
        </div>
      )}
    </div>
  )
}
