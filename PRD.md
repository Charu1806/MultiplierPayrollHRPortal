# Payroll Clarity — product requirements

People is the customer's HR system. Multiplier Payroll is a separate workflow with its own snapshot of that data. Names, dates, and screen rules stay in `context.md`.

## Problem

HR cannot see, before payday, which Workday changes have reached payroll, which employees are blocked, and what still needs a human decision. Payroll readiness, exceptions, approvals, funding, and payment outcomes have to describe the same cycle.

## Ownership

- **HR (Workday, simulated)** owns employment, salary, bonuses, leave, manager, and other compensation changes. Saving them confirms **Saved in HR tool**. The payroll snapshot does not change until sync.
- **Payroll** owns tax identifiers and bank details where the field model assigns them to the employee or to Multiplier. Saving them revalidates that issue immediately.
- One field has one owner. The owner list is `config/rules.json`.

## Sync

A **Sync from Workday** action sits in the Payroll header. It shows the last successful time, whether the run was Manual or Final, who ran it, and a short change summary.

- Manual full sync runs at most once per calendar day (`sync.maxPerDay`). It stays available after the input deadline, including on the October 23 final-sync day.
- The scheduled final sync does not use that daily allowance. Running it again does not duplicate change events, the funding snapshot, or the finance email.
- A failed sync keeps the previous snapshot and the previous success timestamp.
- A targeted refresh updates one employee from the HR source. It is not a full sync and does not use the daily allowance.
- The timestamp uses the prototype date and the real time of day.

## Cycle

Both Action needed and Review & approve use the input deadline.

| Cycle | Input deadline | Final sync | Funding request | Submitted | Pay date |
|---|---|---|---|---|---|
| October 2026 | Oct 22 | Oct 23 | Oct 23 | Oct 25 | Oct 28 |
| November 2026 | Nov 22 | Nov 23 | Nov 23 | Nov 25 | Nov 28 |

Stages are **Sync & resolve → Final sync → Funding → Submitted → Paid**.

A change is in the current cycle only when Multiplier has synced and validated it on or before the deadline and required data and approvals are satisfied. Anything later still syncs, and is marked **Next cycle**. It is not included in the current payroll.

## Overview

Before the deadline, headline counts are distinct employees and always add up:

`Changed employees = Need action + Need approval + Matched automatically`

Need action wins over need approval, which wins over matched. Missing mandatory data stays in Need action until the data is complete. Issue rows and change events are counted separately from those headlines.

After the final sync, the page shows funding status. After pay day, it shows the payment outcome categories below. If the cycle has never synced, the page shows an empty state and the sync action.

## Queues

**Action needed** lists missing, invalid, or incomplete required data, with the owner, the deadline, and a way to fix it. HR-owned fields link to the HR record. Payroll-owned fields use the existing correction flow.

**Review & approve** lists compensation changes that need a person: new joiners under policy, bonuses, salary increases and decreases, and unpaid leave or arrears when the rules say so. Actions are Approve, pay the previous amount when the rules allow it, and Fix in HR tool. Multiplier does not edit HR-owned amounts in place. An unexplained change needs a reason before approval. The model may flag a line. It does not approve pay.

## Funding and pay day

Required funding is gross pay for eligible employees plus the configured employer contribution, in the company's funding currency. Fees are not included. The first sync stores a baseline. Final sync stores one final snapshot and notifies finance once. Variance splits into forex, employer contribution rates, and other changes, and those parts add up to the total.

On pay day the headline categories do not overlap:

1. Paid successfully.
2. Paid at the previous salary because approval was missing.
3. Eligible but not paid because inputs were missing.
4. Added after cutoff, with the prorated amount for the next cycle.

A returned payment, including David Müller from 29 October, stays on its own existing path and is not also counted in those four.

## Notifications

Email is the live channel. Slack stays a later version. Reminders use `reminders.daysBefore` (3, 1, and 0 days before the input deadline) and are sent only when something is still open. Final sync, funding, pay day, and the next cycle opening each send once.

## Acceptance

The checks in the implementation brief are covered by `tests/test_sync_lifecycle.py` together with the existing suite: HR edits stay off the snapshot until sync, sync failure rolls back, the daily limit and the idempotent final sync hold, late changes are Next cycle, headline counts do not double-count an employee, funding variance reconciles, and pay-day categories do not overlap.
