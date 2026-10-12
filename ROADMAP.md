# Payroll Clarity — roadmap

What the prototype does, and what is still a later version. Requirements are in `PRD.md`. Screen rules are in `context.md`.

## Done

### Who is signed in

- The prototype bar switches between the Global HR admin (Maya Rao) and a country HR admin (India, UK, Germany, Brazil). The choice is stored in the browser.
- Global sees every country: on track or at risk, the country admin, and Write mail. A miss link signs in as that country admin and opens the detailed page.
- A country admin sees only their country on Overview, Action needed, Review & approve, and Employees. Sidebar badges match that country. Zero open items reads “No issues”.
- Reset demo sits next to the signed-in name and still asks for confirmation.

### Cycle, dashboard, and previous payrolls

- The prototype date drives every screen. October 2026 through January 2027 use the same day-of-month pattern from `config/cycle.json`.
- Engine dates stay on the 22nd (inputs and review close), 23rd (final sync), 26th (funding), 27th (submitted), and 29th (pay). A returned payment is the day after pay.
- The stage tracker and the overview deadline card use display milestones in the pay month: input close on the 15th, review window the 16th–19th, final report on the 21st, review closed on the 22nd, add funds the 24th–27th, and pay day. Copy names the open month (Nov 15 in November, not a fixed October 22).
- “N will miss payment” is a short line inside that deadline card and scrolls to the country list. Names are not listed on Overview.
- The previous-month highlight shows only on the 30th and 31st of the pay month. From the 1st, closed cycles appear under Previous payrolls, frozen at month end so a return on the 30th is included.
- Every At risk chip uses the same amber style.

### Queues, mail, and pay

- Action needed is missing or invalid required data. Add details opens the missing-details form on the employee profile.
- When details are already in and pay is on track, the screen says “Thanks for adding your details. Payment is on track.” No confirmation email is sent.
- Remind employee saves an in-app email for that country admin and for the Global admin. A real Gmail send still needs SMTP in `.env`.
- Review & approve counts and the table follow the signed-in country. Company-wide sign-off stays with Global.
- Notifications follow the Global, country, and employee calendars in `PRD.md`. Each mail uses the open month and links to the action.
- On the 23rd, finance is asked to add funds and a separate report says who will be paid and who will miss. On the 30th, a report says who was actually paid.
- Funding estimates use gross pay plus configured employer contributions. The 25th and 26th demo mails assume funds are already added.
- Pay day reports non-overlapping outcomes. Payment returns stay on their own path.

### Already in the prototype

- People is the HR source. Payroll keeps a snapshot that updates on sync. Manual sync is one successful run per prototype day. A failed sync does not replace the last good snapshot.
- Employee list, documents, Google Drive when configured, and employee reminder forms.
- Illustrative data for India, the UK, Germany, and Brazil. The language model explains. It does not set the amount or the cycle.
- Tests cover the calendar across October, November, December, and January (`tests/test_dynamic_calendar.py`, `e2e/dynamic-calendar.spec.ts`).

## Not in this version

| Item | Version |
|---|---|
| Slack reminders | V2 |
| AI assistant | V2 |
| Write-back into Workday | V2 |
| Mobile | V2 |
| Time off, Insurance, Expenses | V2 |
| Bulk CSV upload | V2 |
| Finance view | V3 |
| Calendar view | V3 |
| In-app alerts | V3 |
| Guided fix steps | V3 |
| Instant / off-cycle payment | Not available |
| Partial sync as its own status | Not available |

Country payroll processing, funding collection, and payment stay simulated. Exchange rates and employer contribution rates in configuration are illustrative demo figures.

Creating an employee, recording a one-time payment, or recording an exit still writes the payroll snapshot immediately. Document extraction updates both the HR source and the snapshot. The funding email is one total, not a country breakdown.
