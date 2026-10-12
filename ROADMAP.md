# Payroll Clarity — roadmap

What the prototype does, and what is still a later version. Requirements are in `PRD.md`. Screen rules are in `context.md`.

## Done

### Cycle and sync

- Prototype date drives every screen. Reset demo restores the seed.
- People is the HR source. Payroll keeps a snapshot that updates on sync.
- Manual sync is limited to one successful run per calendar day. The final sync is separate and can be repeated without duplicating funding or mail.
- A failed sync does not replace the last good snapshot.
- Input deadline, final sync, funding, submission, and pay date come from configuration. October uses 22, 23, 23, 25, and 28 October. November uses the same pattern.
- Action needed and Review & approve share that deadline.
- Changes synced after the deadline are marked Next cycle.
- The stage tracker is Sync & resolve, Final sync, Funding, Submitted, Paid.

### Queues, mail, and pay

- Action needed is missing or invalid required data. Saving a payroll-owned field rechecks the issue immediately.
- Review & approve is the human check on compensation changes. Approving a line updates the live counts.
- Unread mail is numbered, newest first, and stays read after refresh.
- Input reminders are scheduled from the configured offsets and are skipped when nothing is open.
- Funding estimates use gross pay plus configured employer contributions. The baseline and the final snapshot are stored. Variance splits into forex, rates, and other changes.
- Pay day reports four non-overlapping outcomes, plus the existing returned-payment case.
- Employee profile payroll figures are the last snapshot, with the sync time. HR saves confirm **Saved in HR tool**.

### Already in the prototype

- Employee list, documents, Google Drive when configured, and employee reminder forms.
- Bank return for a closed account from 29 October, resolved when the new account is saved.
- Illustrative data for India, the UK, Germany, and Brazil. The language model explains. It does not set the amount or the cycle.

## Not in this version

| Item | Version |
|---|---|
| Slack reminders | V2 |
| AI assistant | V2 |
| Write-back into Workday | V2 |
| Mobile | V2 |
| Bulk CSV upload | V2 |
| Finance view | V3 |
| Calendar view | V3 |
| Guided fix steps | V3 |
| Instant / off-cycle payment | Not available |

Country payroll processing, funding collection, and payment stay simulated. Exchange rates and employer contribution rates in configuration are illustrative demo figures.
