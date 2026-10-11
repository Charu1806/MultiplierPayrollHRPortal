# Payroll Clarity — roadmap

What the prototype does today, and what is still a later version. Requirements are in `PRD.md`. Screen rules are in `context.md`.

## Done

### Payroll cycle

- Prototype date drives every screen. Reset demo restores the seed.
- Inputs close on the 15th. Calculation is the 16th. Review is the 17th–22nd. Pay is the 28th. November, December, and January follow the same pattern.
- A new employee, bonus, or salary change on or before the 15th stays in this cycle. After the 15th it lands in the next cycle's review.
- A salary change for someone already on the open review stays on that review and is marked approved.
- The employee profile banner says which cycle pays the person, a bonus, and a salary change, including missing fields, exit, and a bank return.

### Action needed

- Open issues, with owner, severity, and country filter.
- Employee reminders, including a real email when SMTP is set, and a saved notification when it is not.
- Saving the last missing field resolves the issue and removes the row.
- A bank return starts on 29 October. It is not treated as a missed October input. Saving the new bank account resolves it.

### Review and approve

- Review opens only inside the window. Before that the page explains when it opens.
- Cards are live: changed lines = matched to a source + need your check.
- Approving or undoing a line updates the cards. The table footer counts the rows on screen.
- Unapproved lines warn that previous pay is deposited and the difference carries. The amount comes from current pay, not from a fixed list of people.
- Sign-off is blocked until every line on the review is approved.

### Notifications

- Inbox is newest first.
- Unread messages are numbered. The inbox and the navigation item show the unread count. Opening a message marks it read.
- Input-deadline mail (12, 14 and 15 October) explains the cutoff, links to Action needed in one step, and links to a demo payroll input policy.
- Employee reminder button is **Add my details**, with one arrow.

### People and documents

- Employee list with server pagination and live totals.
- Add employee, one-time payment, salary edit, and exit, each with a confirmation that names the pay cycle.
- Offer, bonus, and other documents can be uploaded. Google Drive is used when it is configured.

## Not in this version

| Item | Version |
|---|---|
| Slack reminders | V2 |
| AI assistant | V2 |
| Write-back to the HR tool | V2 |
| Mobile | V2 |
| Bulk CSV upload | V2 |
| Finance view | V3 |
| Calendar view | V3 |
| Guided fix steps | V3 |
| Instant / off-cycle payment | Not available |
| Fix in the HR tool, Correct the amount | Not built |

Country payroll processing, funding, and payment stay simulated. The LLM explains; it does not set the pay amount or the cycle.
