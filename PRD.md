# Payroll Clarity — product requirements

Requirements for the working HR prototype. Names, dates and screen rules stay in `context.md`. This file records the decisions that the prototype now implements.

## Problem

HR cannot see, before payday, whether a new employee, a bonus, a salary change, or a missing detail will be paid in this cycle. The Payroll tab has to say what is still open, what it will do to pay, and where to fix it.

## Users

- **HR admin** (Maya Rao) works in the Payroll tab inside the HR tool.
- **Employee** receives a reminder and can add missing details.
- **Finance** receives the funding note. Finance does not edit payroll inputs.

## Payroll input cutoff

Inputs for a cycle close on the 15th.

- On or before the 15th, a new employee, a bonus, or a salary change belongs to this cycle and to this cycle's review.
- After the 15th, that input belongs to the next cycle. It appears on that cycle's review, which opens on the 17th. It does not appear on the locked month.
- Exception: a salary change for someone who already has a row on the open review stays on that review. The row is kept, marked approved, and Matched to a source increases.
- The employee profile shows a banner that says whether the person, a bonus, and a salary change will be paid, and in which cycle. Missing required fields hold that person. A bank return has its own sentence.

## Notifications

HR mail about the input deadline does not pretend the queue is empty, and it does not list every open item.

- **12 October:** "3 days left to add payroll inputs".
- **14 October:** "Cutoff tomorrow for adding payroll inputs".
- **15 October:** "Cutoff today for adding payroll inputs".
- The body says inputs close on 15 October. If an action is still open, or a new employee, salary change, or bonus is not added by then, that employee is affected. Pay may move entirely, or only in part, to the next cycle.
- **What to do** is one step: "Resolve actions in Action needed". It opens Action needed.
- **Payroll input policy** is a demo link. The page explains the cutoff. It does not change pay.
- The inbox is newest first, including mail created on the same day.
- Unread messages are numbered 1, 2, 3 from the top. The inbox and the Notifications navigation item show how many are unread. Opening a message marks it read. The read mark is stored.

Employee reminders keep a single **Add my details** button.

## Review and approve

The three cards are calculated from the employees and from which lines are approved. They are not a fixed 38 / 32 / 6.

- Changed lines, Matched to a source, and Need your check always add up.
- Approving a line moves that person from Need your check into Matched. Undoing the approval moves them back.
- The footer counts the rows in the table ("4 of 6 lines approved"). Need your check counts every unmatched change, including people who are not in that short table.
- The warning under the cards lists only lines that are still unapproved. The amount is the difference between last approved pay and this cycle: salary, allowances, one-time payments, and unpaid leave. A higher amount carries as an arrear. A lower amount carries as a deductible.
- Editing pay changes that amount on this review and on the next cycle. Approving the line removes the person from both.

## Action needed

- Missing details that hold pay stay until the fields are saved. Saving the last required field resolves the issue and removes the row.
- A payment returned by the bank is not a missed October input. It appears from 29 October, after payday. It is not labelled "Carried over" and it does not say "Missed October pay".
- Saving the new bank account resolves that return and removes it from Action needed. On a date before the account was saved, the row is still there.

## Out of scope

Slack, the AI assistant, the finance view, the calendar view, mobile, write-back to the HR tool, and instant off-cycle payment stay as later versions. They are visible and not built.

## Acceptance

- Input-deadline mail names the cutoff and does not list each open issue.
- Unread mail stays numbered until it is opened.
- A salary confirmed on the employee profile during the open review stays approved, and the cards still add up.
- A joiner, bonus, or salary change saved after the 15th shows on the next review, except a salary change that is already on the open review.
- Review cards change when a line is approved or when pay is edited. November carry uses the edited amount.
- After the bank account on a returned payment is saved, that row is gone from Action needed.
