# Payroll Clarity — product requirements

People is the customer's HR system. Multiplier Payroll is a separate workflow with its own snapshot of that data. Names, dates, and screen rules stay in `context.md`.

## Problem

HR cannot see, before payday, which Workday changes have reached payroll, which employees are blocked, and what still needs a human decision. A global leader and each country admin need the same cycle, scoped to what they own.

## Who uses it

| Persona | Sees |
|---|---|
| Global HR admin | Every country, Write mail, company sign-off, and the global notification calendar |
| Country HR admin | That country only: stage tracker, Action needed, Review & approve, Employees, and the country inbox |
| Finance admin | Named on the funding stage and in the funding emails. No separate finance screen in this version |
| Employee | Add-details emails on the 10th, 13th, 14th, and 15th while required fields are still missing |

The persona is a prototype switch, not a login. Country filters lock when a country admin is signed in. Sidebar badges use that scope. When the scoped count is zero, the sidebar, the page, and the footer say there are no issues.

## Ownership

- **HR (Workday, simulated)** owns employment, salary, bonuses, leave, manager, and other compensation changes. Saving them confirms **Saved in HR tool**. The payroll snapshot does not change until sync.
- **Payroll** owns tax identifiers and bank details where the field model assigns them to the employee or to Multiplier. Saving them revalidates that issue immediately.
- One field has one owner. The owner list is `config/rules.json`.

Creating an employee, a one-time payment, or an exit still writes the payroll snapshot at once. Document extraction updates both records. Those are prototype limits.

## Sync

A **Sync from Workday** action sits in the Payroll header. It shows the last successful time, whether the run was Manual or Final, who ran it, and a short change summary.

- Manual full sync runs at most once per prototype day (`sync.maxPerDay`). The seed sync does not use that allowance.
- The scheduled final sync does not use that daily allowance. Running it again does not duplicate change events, the funding snapshot, or the finance email.
- A failed sync keeps the previous snapshot and the previous success timestamp.
- A targeted refresh updates one employee from the HR source. It is not a full sync and does not use the daily allowance.
- The timestamp uses the prototype date and the real time of day. A later-dated sync is not shown as the latest sync on an earlier date.

## Cycle

Engine dates come from `config/cycle.json` and repeat for October 2026, November 2026, December 2026, and January 2027. The display milestones below are the same day of the pay month. They are not a second copy of October.

| | Engine (`cycle.json`) | What the dashboard and mail say |
|---|---|---|
| Add employees, bonuses, hikes, missing details | — | Closes on the 15th. Later adds move to next month |
| Review window | Review stays open until the 22nd in the engine | 16th–19th on the tracker and in mail |
| Final report | — | 21st |
| Inputs, approvals, review close | 22nd | 22nd is the last day. Later changes apply next month |
| Final sync | 23rd | 23rd also sends the who-will-be-paid report |
| Add funds | Funding due the 26th | 24th–27th on the tracker. Mail on the 23rd, 25th, and 26th |
| Payroll submitted | 27th | Named on the deadline card |
| Pay day | 29th | Named on the tracker and the deadline card |
| Payment returned | Day after pay | Included in the 30th report and in the month-end snapshot |

Stages on the tracker, in order: **Input close → Review window → Final report → Review closed → Funding → Pay day**.

Before pay day the pay stage counts days left. On pay day it says Today. After pay day it says how many of how many were paid.

A change is in the current cycle only when Multiplier has synced and validated it on or before the engine deadline and required data and approvals are satisfied. Anything later still syncs, and is marked **Next cycle**.

## Overview

The deadline card follows the prototype date:

- Through the 15th: add employees, bonuses, hikes, and missing details by the 15th. Review by the 19th. Final closure on the 22nd. Payroll submitted and pay day stay visible.
- Through the 19th: complete review by the 19th.
- Through the 22nd: final closure.
- Then payroll submitted, then pay day.

When people will miss payment, that count is a short highlight inside the card and scrolls to Countries. The names stay on the country rows, not in a separate list on Overview. Every At risk chip uses the same amber colour. On track stays green. The country list is hidden when a country admin is signed in, because that status is already the page.

The yellow previous-payroll highlight appears only on the 30th and 31st of the pay month. From the 1st of the next month it is gone, and closed cycles whose pay date is before that month appear under **Previous payrolls**, most recent first, frozen at the last day of their pay month.

## Queues

**Action needed** lists missing, invalid, or incomplete required data for the signed-in scope, with the owner, the deadline, and a way to fix it. Add details and Add details myself open `/people/{id}?panel=missing#missing-details`. When pay is already on track, the profile shows “Thanks for adding your details. Payment is on track.” and does not send a mail.

**Review & approve** lists compensation changes that need a person, scoped to the country when one is selected. Cards, the carry notice, employees not in the run, and the footer use that same set. Company-wide sign-off is hidden for a country admin. The model may flag a line. It does not approve pay.

## Funding and pay day

Required funding is gross pay for eligible employees plus the configured employer contribution, in the company's funding currency. Fees are not included. The first sync stores a baseline. Final sync stores one final snapshot. Variance splits into forex, employer contribution rates, and other changes, and those parts add up to the total. The funding email is one total.

On pay day the headline categories do not overlap:

1. Paid successfully.
2. Paid at the previous salary because approval was missing.
3. Eligible but not paid because inputs were missing.
4. Added after cutoff, so the amount moves to the next cycle.
5. Payment returned, counted on its own from the day after pay.

The 25th and 26th emails say funds are added. That answer is the demo default. Ignore the mail when funds are already in.

## Notifications

Email is the live channel. Slack stays a later version. The inbox shows mail for the signed-in persona. Global sees global mail and employee reminders. A country admin sees that country's mail and employee reminders. Write mail is an in-app note to a country admin, visible to Global and to that admin.

Dates below are the day of the open month. October is only the first example.

**Global HR admin**

| Day | Mail |
|---|---|
| 10 | Employee window is open, through the 15th |
| 15 | Employee window is closed |
| 16 | Review window is open, until the 19th |
| 19 | Review window closes today. Ignore if nothing is open |
| 20 | Final report. Three days to work with country admins. Ignore if nothing is open |
| 22 | Today is the last day. Ignore if nothing is open |
| 23 | Funding period started, with the amount finance should hold. A second mail is the who-will-be-paid report |
| 25 | Funds added. Ignore if already added |
| 26 | Last day to add funds. Ignore if already added |
| 29 | Pay sent: how many paid, how many affected, amount, and why |
| 30 | Final report of who was actually paid and who missed, including payment returns |

**Country HR admin**

| Day | Mail |
|---|---|
| 3 | Schedule and stages, linked to that country's overview |
| 10, 13, 14, 15 | Finish inputs by the 15th. Tone tightens toward the 15th |
| 16 | Review is open until the 19th |
| 18, 19 | Same review reminder, escalated. Ignore if nothing to do |
| 20, 21, 22 | Review window closed. Global is in copy. Inputs can still be added through the 22nd. Ignore if nothing to do |
| 23 | Ask finance to add funds by the 26th, plus a who-will-be-paid report |
| 25, 26 | Funds. Global is in copy. Ignore if already added |
| 29 | Pay submitted for that country: paid, moved to next cycle, and why |
| 30 | Who was actually paid, and why anyone missed |

**Employees with missing details:** the 10th, 13th, 14th, and 15th. Each mail says they will miss payment this cycle otherwise, and the button opens the missing-details form. Escalation increases toward the 15th. No mail once details are in and pay is on track.

Older input-deadline reminders on the 1st, 10th, 15th, 20th, 21st, and 22nd remain in the API. They have no persona audience, so the signed-in inbox does not show them.

## Acceptance

`tests/test_sync_lifecycle.py` covers HR edits staying off the snapshot until sync, sync failure, the daily limit, the idempotent final sync, late changes, funding variance, and pay-day categories.

`tests/test_dynamic_calendar.py` and `e2e/dynamic-calendar.spec.ts` check that the overview, the stage tracker, previous payrolls, and notifications follow November, December, and January, and do not keep October dates on those months.
