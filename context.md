# Payroll Clarity – Prototype Context

Context for building a clickable prototype in Cursor. **This file is the single source of truth** for names, numbers, dates, text, screens and rules. Read this first, then `PRD.md` for the product requirements of the working prototype, `ROADMAP.md` for what is done, `architecture.md` for the service/API design and `DESIGN.md` for visual styling. If code and this file disagree, this file wins.

## 1. What this is

An interview case study prototype for Multiplier (global EOR and payroll). The prompt: customers have no visibility after they submit payroll inputs, and problems surface only after an employee is paid wrongly.

The solution is a **Multiplier-branded Payroll tab embedded inside the customer's HR tool**, backed by a shared issue model. It catches issues as data arrives and routes each one to the person who can fix it before input finalisation.

**The panel grades product decisions, not code quality.** Keep it narrow, clear and consistent. What is deliberately left out must be visible as a greyed stub with a version tag.

## 2. Hard rules

- **Desktop web only**, designed at 1440px wide. No mobile layouts (mobile is V2). Tables never overflow the page: truncate long cells with a tooltip; horizontal scroll is allowed only *inside* the table container.
- **API-based.** The frontend is a thin client: every read and write goes through the backend API (`/api`, see §14 and `architecture.md`); no business data lives in frontend source files. Business rules are read from `/config` (dates, tax rates, thresholds, required fields) and are never hard-coded in components.
- **State persists.** User actions (fixes, uploads, edits, approvals, sign-off, reminders) are written to the SQLite store and survive page refresh and prototype-date changes. The prototype date (`clarity.asOf`) and the signed-in persona (`clarity.persona`) are stored in the browser. **Reset demo** sits next to the signed-in name in the prototype bar (confirmation → `POST /api/demo/reset`) and reseeds from `config/seed.json`.
- **Real vs simulated.** Real: Google Drive file picking, document text extraction, LLM field mapping, database persistence, **outgoing employee reminder emails** via Gmail SMTP when configured (§8 / §14.7). Simulated when SMTP is missing: email is still saved to Notifications with a form link. Country payroll processing, funding and payment remain simulated. Every real call has a **demo fallback** (§14.5) so the live demo never breaks.
- **Every change asks for confirmation** in a modal before it is saved (resolve, approve, edit, exit, one-time payment, sign-off). Pay edits that trip the AI-check rule (§8) get a second "AI check" confirmation.
- **Each fact appears once per screen.** No decorative stat tiles, banners or charts.
- Use the names, numbers and dates in this file exactly, everywhere. Do not invent new names, numbers or dates.
- Every stub shows a short note when clicked, e.g. "Coming in V2" or "Not built in prototype".
- All data is illustrative. Show a small "Illustrative data" label in the footer.

## 3. Tech stack

**Frontend** (`src/`)
- React + TypeScript + Vite; Tailwind CSS with tokens from `DESIGN.md` (Inter, slate neutrals, black primary buttons, red/amber/green status tokens, 4px radius, flat, tabular numbers)
- React Router for screens; one Zustand store used as a **cache of API responses** plus UI state (prototype date, toasts, confirmation modal)
- `src/api/clarityClient.ts` is the only HTTP entry point; `lucide-react` for icons
- Google Picker API + Google Identity Services for Drive (scope `drive.file` only)
- Valued copy (sentences with numbers/dates) lives in `src/copy/en.ts` as templates; the client only fills placeholders from the API

**Backend** (`server/`, Python/Flask — the existing Clarity API, extended; the Node/Express layout in the original brief is mapped 1:1 onto it)
- Flask API mounted at `/api` (alias `/clarity/v1`) with a thin gateway layer (CORS, `X-Request-Id`, demo tenancy header `X-Customer-Id: cust_acme`, Problem+JSON errors)
- Services: `rules.py`, `calendar.py`, `clock.py`, `pay_outlook.py`, `inputs.py`, `connector.py`, `validation.py`, `issue.py`, `review.py`, `notification.py`, `submission.py`, `extraction.py`, `llm.py`, `ai_explain.py`
- SQLite store `data/payroll_clarity.db`, schema `data/schema.sql`, seed `data/seed_db.py` which reads `config/seed.json` (or alt dataset via `DATASET=`)
- One command runs both: `npm run dev` (concurrently: Flask on :8787 + Vite on :5173; Vite proxies `/api`)

**Config** (`config/`)
- `cycle.json` – countries, October–January cycle dates, prototype date options
- `rules.json` – tax rates, AI-check thresholds, required fields with owners, formats
- `company.json` – brand, Global HR admin, country HR admins, finance admin, HR tool name, “Powered by Multiplier” caption (sidebar Payroll group only)
- `seed.json` – starting rows only (never imported by runtime app code except the seeder)
- Alt dataset under `config/alt/` + `seed/alt.json` for dual-suite (`DATASET=acme|alt`)
- `.env.example` – Google, LLM, SMTP, `DEMO_FALLBACK=true`. `.env` is git-ignored.

**Prototype date**: every read API accepts `?date=` (or `asOf=`); the backend derives stage, countdown, open issues, flags, review state, outcome and inbox from it. Employees with `date_added` after the date are hidden; issues created later are hidden; issues/fields resolved later read as open/missing.

### 3.1 Architecture: data-driven

| Kind of value | Source of truth |
|---|---|
| Today, cycle, stages, deadlines, review window, pay date | `clock.py` + `calendar_rules.py` + `config/cycle.json` |
| Company, admin, HR system, countries, currencies | `config/company.json` / `cycle.json` |
| Required fields, owners, formats, tax %, thresholds | `config/rules.json` |
| Employees, salaries, documents, payments, exits | SQLite |
| Issues | validation findings → `issues` table |
| Review lines and counts | `calculate_and_build_review` → `review_lines`; counts by query |
| Pay amounts, net, tax, proration, FnF | rules / salary structure |
| Statuses (“Pay this cycle”, Held, Paid, Returned) | `pay_outlook()` on the server; client only renders |
| Badges and summary counts | count queries |
| Emails | remind + cycle rules → notifications/emails table |
| Stage tracker | `stage_for_date()` + data |

**Hard rules:** no date literals or seed names/file names in runtime app code; seed is starting state only (see `docs/hardcoding-audit.md`). Client must not compute cutoffs, thresholds, or status mapping. Changing a config value (cutoff day, tax rate, admin name) must change UI/emails/calculations with no code change.

**HR edits and approval:**
- Any HR edit to pay inputs (base, allowances, one-time, leave) triggers Multiplier recalculation (gross → tax → net from `rules.json`); confirmation shows the new net before save.
- Cycle placement: on/before input cutoff → current cycle; during review → current **only** if correcting a line already in the run, otherwise next; after approval or after review window → next cycle as arrears/recovery.
- Editing a line already in review and confirming marks it “Approved · edited by {admin}” (one click). AI-check confirm first if spike/drop.
- If payroll was already approved and a line is edited in-window, approval reopens (“1 line changed since approval”).
- Confirmation always states new net + “Included in {month} pay” or “Moves to {next}”.

**Tests:** `npm test` runs check:dates, check:hardcoding, pytest, vitest, Playwright. Full suite must pass on both `DATASET=acme` and `DATASET=alt`. See `docs/test-report.md`.

## 4. Layout and navigation

```
┌───────────────────────────────────────────────────────────────┐
│ Prototype bar: date picker · persona dropdown · Reset demo    │
├──────────────┬────────────────────────────────────────────────┤
│ People       │ Breadcrumb · ← Back (when not top-level)       │
│  Employees   │ Page title                                     │
│  Time off    [V2]                                             │
│  Insurance   [V2]                                             │
│  Expenses    [V2]                                             │
│ Payroll · Powered by Multiplier                               │
│  Overview                                                     │
│  Action needed (badge = open issues in this persona's scope)  │
│  Review & approve (badge = lines needing approval in scope)   │
│  Employees                                                    │
│ Notifications · Powered by Multiplier                        │
│  Notifications (badge = unread mail for this persona)         │
│  ─────────                                                    │
│  AI assistant  [V2] (greyed)                                  │
│  Finance view  [V3] (greyed)                                  │
│  Employee payroll tool [V3] (greyed)                          │
└──────────────┴────────────────────────────────────────────────┘
```

- HR-tool shell is neutral, no real brand. The People group caption is “Sync from HRIS tools and third party channels”.
- **Powered by Multiplier** sits in the sidebar next to the Payroll label and the Notifications label. People and HR page headers do not repeat it.
- **Two places list employees.** People → Employees (`/people`) is the HR list. Payroll → Employees (`/payroll/employees`) is the payroll view of the same roster, scoped to the signed-in country when a country admin is selected.
- People pages use the HR-tool look, not a Payroll header. Notifications is its own group below Payroll. Its header says Notifications and does not repeat Powered by Multiplier.
- The employee form (`/form/:token`) is a standalone page styled like a Google Form, without the shell.
- **Breadcrumb** on every page, top left above the title. Each part except the last is a link.
- **← Back** next to the breadcrumb on every page that is not a top-level nav page (employee profile, add employee, one-time payment, record exit, employee form). Uses browser history; falls back to the parent crumb.
- **Reset demo** is a text button next to the signed-in name. It confirms before reseeding.

### Who is signed in

The prototype bar dropdown is the persona. It is not a login.

| Persona | Name | Scope |
|---|---|---|
| Global HR admin | Maya Rao | Every country. Write mail. Company sign-off |
| India HR admin | Priya Mehta | India |
| UK HR admin | Helen Clarke | UK |
| Germany HR admin | Greta Hoffmann | Germany |
| Brazil HR admin | Camila Rocha | Brazil |

Finance admin Noah Grant is named on the funding stage and in funding mail. There is no finance screen.

Global country rows show on track or at risk, the country admin, and Write mail. A miss link switches the dropdown to that country admin and opens the detailed page. At risk is one amber colour on every country. A country admin does not see the country list, because that status is already the page. Action needed, Review & approve, and Employees lock the country filter. Badges use the same scope. Zero items says “No issues” on the sidebar, the page, and the footer.

### Routes

| Route | Screen | API calls |
|---|---|---|
| `/payroll/overview` | Overview (default) | `GET /api/cycles/current/overview` |
| `/payroll/actions?issue=<id>&country=` | Action needed; URL selects issue / country filter | `GET /api/issues`, resolve, remind |
| `/payroll/review` | Review & approve | `GET /api/review`, approve, reopen, signoff |
| `/payroll/employees` | Payroll employees, country-scoped for a country admin | `GET /api/employees` |
| `/people/notifications` | Notifications (`/payroll/notifications` redirects here) | `GET /api/notifications`, `GET /api/notifications/{id}` |
| `/people?page=&pageSize=&filter=&country=&q=&action=&status=` | All employees (server pagination + filters in URL) | `GET /api/employees?page=&pageSize=` |
| `/people/add` | Add employee | `POST /api/employees`, `POST /api/documents/extract` |
| `/people/:id?panel=salary` | Employee profile with Payroll panel | `GET/PATCH /api/employees/{id}`, OTP, exit, extract |
| `/people/:id/one-time-payment` | Add one-time payment | `POST /api/employees/{id}/one-time-payments`, extract |
| `/people/:id/exit` | Record exit | `POST /api/employees/{id}/exit`, extract |
| `/form/:token` | Employee form (signed token) | `GET/POST /api/forms/{token}` |

## 5. Prototype date control

**Calendar date picker** (range **1 Oct 2026 – 31 Jan 2027**), not a fixed dropdown. Changing the date refetches every screen. **Any date in range must work.** Labels, deadlines, and mail use the open cycle’s month. November must not still say October.

Display milestones are the same day of the pay month. October is the worked example:

| Day of the pay month | What the screens show |
|---|---|
| 1–15 | Add employees, bonuses, hikes, and missing details by the 15th. People added after the 15th move to next month. Review by the 19th and final closure on the 22nd stay on the card, with payroll submitted and pay day |
| 16–19 | Complete review by the 19th |
| 20–22 | Final closure on the 22nd. Changes after the 22nd apply next month |
| 23–27 | Funding window, a customer setting. The fund manager gets a mail with Yes and No. Funds are added on the day they click Yes |
| 28 | Payroll submitted, the 28th of the pay month |
| 29 | Pay day. Before it, the tracker counts days left. On the day it says Today. After it, paid N of M |
| 30 | Final report of who was actually paid, including a payment return recorded that day |
| 30–31 | Yellow highlight for the payroll that just paid |
| 1st of the next month | Highlight is gone. That cycle appears under Previous payrolls |

## 6. Data

### Customer and calendar

- Customer: **Acme Tech**. HR tool: **Workday**.
- 120 employees before the demo: **India 50, UK 30, Germany 22, Brazil 18**. 4 countries only (no Philippines). Priya and Arjun are added during the demo (→ 122).
Engine dates in `config/cycle.json` (same pattern for October 2026, November 2026, December 2026, January 2027):

- Input deadline, input finalisation, and review close: the **22nd**.
- Final sync and calculation: the **23rd**.
- Funding request and funding due: the **26th**.
- Submitted: the **28th**.
- Pay date: the **29th**. A returned payment is recorded the next day (30 October for October).

The stage tracker does not copy those engine labels. It shows **Input close (15th) → Review window (16th–19th) → Final report (20th) → Review close (22nd) → Funding (23rd–27th) → Payroll submitted (28th of the pay month) → Pay day**. Input close, the review window, the final report, the funding window, and pay day are the customer’s settings. Multiplier recommends those dates; the customer can choose others. Review close on the 22nd is a deadline imposed by Multiplier. Payroll submitted is the 28th of the pay month. Funds are added on the day the fund manager clicks Yes. The days are the same day of whichever month is open. Global and country HR see the same tracker.

From the 1st, every page shows the cycle that contains that date. Closed cycles whose pay date is before the 1st of the current month appear under Previous payrolls. A change synced after the engine deadline is marked Next cycle.

### HR source and payroll snapshot

People is the customer's HR system (Workday, simulated). Multiplier Payroll keeps its own snapshot.

- HR owns employment, salary, bonus, leave, manager, and other compensation changes. Saving those fields updates the HR source only and confirms **Saved in HR tool**. It does not change the payroll snapshot.
- Payroll owns tax identifiers and bank details where the field owner is the employee or Multiplier. Saving those revalidates the issue immediately.
- The snapshot updates on **Sync from connector**. Manual sync can run any number of times on the same prototype day. The scheduled final sync does not duplicate events, funding snapshots, or emails if it runs again.
- A failed sync leaves the last successful snapshot and timestamp in place.
- The employee profile's payroll block is read-only and shows the last successful sync time. Payroll warnings stay off People screens.

### Types (reference; authoritative DTOs in `src/api/types.ts`, schema in `data/schema.sql`)

```ts
type Country = 'India' | 'UK' | 'Germany' | 'Brazil';
type Severity = 'blocking' | 'needs_confirmation';
type IssueStatus = 'open' | 'resolved';
type EmployeeStatus = 'Active' | 'Exiting' | 'Exited';

interface SalaryStructure {
  base: number;             // monthly base salary (the amounts in this file)
  allowances: number;
  oneTimePayments: { type: 'Bonus' | 'Reimbursement' | 'Arrears' | 'Other'; amount: number; label: string; recordedOn: string; cycle: 'October' | 'November' }[];
  unpaidLeaveDays: number;  // deduction = base × days / 30
  taxRate: number;          // from config: India 10%, UK 20%, Germany 25%, Brazil 15%
  tax: number;              // auto, read-only – "Tax calculated by Multiplier"
  net: number;              // auto
}

interface Employee {
  id: string; name: string; role: string; country: Country; currency: '₹' | '£' | '€' | 'R$';
  septemberPay: number;        // last approved base (September)
  salary: SalaryStructure;
  dateAdded: string | null;    // null = "Before cycle"
  isNew: boolean;
  status: EmployeeStatus;
  missingFields: string[];     // required fields per country still empty
  changedThisCycle: boolean; matchedSource: string | null; editedByYou: boolean;
}

interface Issue {
  id: string; title: string; severity: Severity; employeeId: string; country: Country;
  owner: 'HR admin'; deadline: string; status: IssueStatus;
  employeeOwnedFields: string[]; hrOwnedFields: string[];  // who must add what
  reminderSentOn: string | null;
}
```

### Seed: open issues on Oct 12 (3)

| # | Title | Severity | Who | Deadline | Owner fields (HR / employee) |
|---|---|---|---|---|---|
| 1 | Missing tax ID | blocking | Lena Fischer, Germany | Oct 15 | Employee-owned |
| 2 | Salary up 3x | needs_confirmation | James Patel, UK | Oct 15 | HR. £4,000 → £12,000. AI note: "Likely a one-off bonus entered as base salary. Last 12 months flat at £4,000." |
| 3 | Missing CPF | blocking | Beatriz Costa, Brazil | Oct 15 | Employee-owned |
| 4 | Missing PAN, bank account, manager | blocking | Priya Nair, India | Oct 15 | PAN + bank = employee; Manager = HR. **Appears only after Priya is added on Oct 13.** |

Seed on Oct 12: issues 1–3 open (3 actions). After Priya is added: 4. There is no "Inputs not submitted – Brazil" and no "Add 2 new joiners" issue: the system can't know about joiners HR hasn't entered yet.

Severity labels are fixed: Blocking, Needs confirmation. Impact text for a blocking issue: "Only {name} is held. The other employees will be paid on time."

### Demo values (placeholder text plus a small "Use demo value" link next to each field)

- Lena Fischer, German tax ID (Steuer-ID): `12 345 678 903`
- Beatriz Costa, CPF: `123.456.789-09`
- Priya Nair, PAN: `BNZPN4821K` · Bank account: `50100234567812` · IFSC: `HDFC0000123` · Manager: `Ananya Rao`

Any non-empty value in the right format is accepted. Validate the format only: PAN = 5 letters, 4 digits, 1 letter; CPF = 11 digits (punctuation ignored); Steuer-ID = 11 digits (spaces ignored).

### Reminder card (not an issue, no severity, not counted in the action count)

On the Overview, the deadline card names the open month. Through the 15th it reads, for October:

> Add employees, bonuses, hikes, and missing details by **Oct 15**. People added after Oct 15 move to next month. Complete review by **Oct 19**. Final closure **Oct 22**. Payroll submitted **Oct 28** · Pay day **Oct 29**.

In November the same card says Nov 15, Nov 19, Nov 22, Nov 27, and Nov 29. When anyone will miss payment, a short “N will miss payment” line inside the card scrolls to Countries. The names are not listed on Overview.

[Add employee] [Record exit] [Add one-time payment] sit with that card. [Add employee] → `/people/add`. [Record exit] and [Add one-time payment] open Payroll employees with a hint to pick an employee.

[Add employee] → `/people/add`. [Record exit] and [Add one-time payment] open All employees with a hint "Pick an employee".

### Seed: employees (named; generate the rest to reach 120)

| Name | ID | Country | Role | Base (September) | Notes |
|---|---|---|---|---|---|
| Lena Fischer | `emp_lena` | Germany | Senior Product Designer | €4,200 | Missing tax ID |
| James Patel | `emp_james` | UK | Staff Backend Engineer | £4,000 | Base captured as £12,000 from Workday → Salary up 3x |
| Beatriz Costa | `emp_beatriz` | Brazil | Software Engineer | R$14,000 | Before cycle. Missing CPF |
| Thiago Santos | `emp_thiago` | Brazil | Solutions Architect | R$18,500 | On track; vacation pay in review |
| Ananya Rao | `emp_ananya` | India | Senior Frontend Engineer | ₹1,20,000 | Raise to ₹1,35,000 in review |
| David Müller | `emp_david` | Germany | Data Engineer | €4,800 | On track until Oct 29: bank returned payment ("Account closed") → Action needed |
| Rajesh Sharma | `emp_rajesh` | India | QA Lead | ₹95,000 | Arrears in review |
| Chloe Dubois | `emp_chloe` | UK | Product Ops Lead | £3,600 | Maternity leave: statutory pay in review |
| Mateo Silva | `emp_mateo` | Brazil | Infrastructure Engineer | R$16,000 | On track; 5 days unpaid leave in review |

New joiners added during the demo (one role and one ID each, used everywhere):

| Name | ID | Country | Role | Added |
|---|---|---|---|---|
| Priya Nair | `emp_priya_nair` | India | Software Engineer | Oct 13 (new) |
| Arjun Mehta | `emp_arjun_mehta` | India | Data Analyst | Oct 17 (new) |

James Patel is an existing employee (Date added "Before cycle"), not a new joiner. Every employee has a **salary structure** (Base salary, Allowances, One-time payments this cycle, Deductions (unpaid leave), Taxes (auto, read-only), Net pay (auto)) with a small "Tax calculated by Multiplier" label. Fixed tax rates per country: India 10%, UK 20%, Germany 25%, Brazil 15%.

All employees table default view shows the named people above (plus Priya/Arjun once added) with the label "Showing 9 of 120"; **Show all** or any filter widens to the full roster. For employees with no changes: "If no action: will be paid **₹1,20,000 – same as September**" (each row's own base and currency).

### Seed: documents (extraction results; used by the demo fallback)

**offer_letter_priya.pdf** (attached Oct 13)

| Source | Source field | Multiplier field | Value | Status |
|---|---|---|---|---|
| HR tool | Legal name | Employee name | Priya Nair | ✓ |
| HR tool | Work location | Country | India | ✓ |
| HR tool | Hire date | Start date | Oct 20, 2026 | ✓ |
| Offer letter | "Annual CTC" | Annual gross salary | ₹18,00,000 | ✓ High |
| Offer letter | "Designation" | Job title | Software Engineer | ✓ High |
| — | — | PAN | Not found | ✗ Required for India |
| — | — | Bank account | Not found | ✗ Required |

**offer_letter_arjun.pdf** (attached Oct 17): Arjun Mehta · India · Data Analyst · start Oct 27, 2026 · ₹12,00,000 · all required fields present.

**bonus_letter_james.pdf** (attached Oct 13): James Patel · UK · one-off performance bonus **£8,000** · paid October 2026. Saving it **resolves issue #2**: the backend splits the captured £12,000 into Base £4,000 + One-time bonus £8,000 and recalculates tax.

**travel_reimbursement_chloe.pdf**: Chloe Dubois · UK · client travel reimbursement **£640**.

Documents are added via **Use demo file**, **Upload from computer**, or **Choose from Google Drive** (§6 attachments / §14). With the demo fallback, known file names map to these fixed results and show a small grey note "Used saved extraction".

### Seed: review lines (the 6 "need your check" lines – pay changes only, nothing about missing data)

| Employee | Change | Why flagged | Matching source |
|---|---|---|---|
| James Patel (UK) | £4,000 → £12,000 | Spike > 50% | "Workday comp change, awaiting confirmation", or "Bonus letter, one-off £8,000" once resolved |
| Ananya Rao (IN) | ₹1,20,000 → ₹1,35,000 | Raise above 10% | No matching approval found |
| Chloe Dubois (UK) | £3,600 → £2,150 | Maternity leave: statutory pay | HMRC rate table |
| Mateo Silva (BR) | R$16,000 → R$13,333 | 5 days unpaid leave | Leave record in Workday |
| Thiago Santos (BR) | R$18,500 → R$24,670 | Vacation pay + 1/3 bonus (férias) | Leave record in Workday |
| Rajesh Sharma (IN) | ₹95,000 → ₹1,17,000 | Arrears ₹22,000 for September | No matching approval found |

Top numbers start at **38 changed lines · 32 matched to a source · 6 need your check.** They are computed, never a fixed total: changed employees with a matched source, plus every approved review line, count as matched. Need your check is the rest. The three cards always add up. Approving a line in the table moves that person into Matched and drops Need your check. A changed flag with no pay difference and no review line is not counted. The footer ("4 of 6 lines approved") counts only the rows in the table. Edits made by the HR admin add lines ("Edited by you – needs approval"). A salary confirmed from the employee profile during an open review stays on that review, is marked approved, and increases Matched.

### Notifications (email only; Slack is a V2 stub)

Mail is computed for the open month. Subjects start with that month or that country. A November inbox must not cite October deadlines. The full calendar is in `PRD.md`. In short:

- **Global:** 10, 15, 16, 19, 20, 22, 23 (funding plus who-will-be-paid), 25, 26, pay day (29), and the 30th actual-paid report. Several say to ignore the mail when nothing is open or funds are already in.
- **Country HR admin:** 3 (schedule), 10, 13, 14, 15, 16, 18, 19, 20, 21, 22, 23 (ask finance, plus who-will-be-paid), 25, 26, pay day, and the 30th. Global is in copy on the late review and funding notes.
- **Employees with missing details:** 10, 13, 14, 15. The button opens `/people/{id}?panel=missing#missing-details`. Each mail says the month’s payroll will be missed otherwise. When the saved details put payroll on track, the employee gets “Thanks for adding your details. {month} payroll is on track.” The screen still says “Thanks for adding your details. Payment is on track.”

The inbox on `/people/notifications` shows only mail for the signed-in persona. Global sees global mail, the fund manager’s mail, and employee reminders. Noah Grant, the fund manager, sees the funds email and can click Yes or No. A country admin sees that country and its employee reminders. Write mail is an in-app note from Global to a country admin.

Older reminder rows with no audience stay in the API and stay out of this inbox.

Inbox order is newest first. Opening a message marks it read. Read state survives refresh. Reset demo clears it.

**Remind employee** (for example Lena’s tax ID) saves that email in Notifications for the country admin and for Global, with a link to the missing-details form. Without SMTP this in-app email is the send. A real Gmail delivery needs `SMTP_USER`, `SMTP_PASS`, `DEMO_INBOX`, and `APP_BASE_URL`. If SMTP is configured and the send fails, the row stays undelivered and the message includes the error.

## 7. Screens

### The split between Action needed and Review & approve

| | **Action needed** | **Review & approve** |
|---|---|---|
| What | Data is **missing or wrong**, so the employee can't be paid correctly | Data is **complete**; only the pay amount needs a human check |
| Examples | Missing tax ID, PAN, bank, CPF, HR fields; salary entered as 3x and not explained | Salary spike or drop, raise above 10%, unpaid leave, statutory leave pay, vacation pay, arrears |
| Deadline | Add-details window closes the 15th. Engine input deadline is the 22nd | Review window on the tracker and in mail is the **16th–19th**. Engine review close is the **22nd** |
| If not fixed | Employee moves to next cycle | Unapproved → September pay; November **arrears** (underpaid) or **recovery** (overpaid) |

**Why review waits:** Review can only start once inputs are locked and Multiplier has calculated pay. Reviewing earlier means reviewing numbers that can still change.

Missing-data items **never** appear in Review & approve. Review shows: "**N employees are not in this run**…" only while the window is **open**.

**Nav badges** use the signed-in country. Global counts every country. A country admin counts only theirs. Zero shows no badge, and the page says there are no issues.
- **Overview:** never.
- **Action needed:** open issues in scope.
- **Review & approve:** lines in scope that still need approval. Company-wide sign-off is hidden for a country admin.
- **Notifications:** unread email for this persona. Drops when a message is opened.

### Screen 1 – Overview (`/payroll/overview`)

- Deadline card, seven-stage tracker, and (for Global) a country list. No separate list of people who will miss payment.
- The deadline card follows §5. “N will miss payment” is a short line in that card and scrolls to Countries.
- **Stage tracker:** Input close, Review window, Final report, Funding window (23rd–27th), and Pay day are your settings; Multiplier recommends the dates. Review close is seven days before pay day (the 22nd when pay day is the 29th) and is a deadline imposed by Multiplier. Payroll submitted is the 28th of the pay month (“The 28th of the pay month. Multiplier calculating the payment.”). Funding names the fund manager. Funds are added on the day they click Yes in their email. The same tracker shows for Global and country HR. Dates are the pay month. Before pay day the last stage counts days left. On pay day it says Today. After pay day it says paid N of M.
- **Previous payroll:** a yellow highlight only on the 30th and 31st of the pay month. From the 1st, **Previous payrolls** lists earlier cycles, most recent first, frozen at the last day of each pay month.
- Country rows are Global only. Each row is on track or at risk, names the country admin, and offers Write mail.

### Screen 2 – Action needed (`/payroll/actions`)

- Reminder card until the current cycle's input finalisation date.
- **Country filter** from `?country=`. Clicking a card selects it (`?issue=<id>`); only one selected.
- **Card styling:** selected = 2px sky-600 border + sky-50 background. Unselected = white, 1px slate-200, hover slate-50. **No red left border.** Severity via badge only: Blocking = rose, Needs confirmation = amber, Waiting on employee = sky, Carried over = slate. Carried-over items also get tag "Carried over from October".
- **Owner:** computed from field ownership. Beatriz CPF / Lena tax ID → "Owner: {name} (employee)". HR-owned fields → "HR admin".
- **James "Salary up 3x"** only in October Action needed (≤ Oct 15). After Oct 15 it is resolved or went to October review — never a November Action needed item. In November it appears only as an arrears review line if October wasn't signed off.
- **Needs confirmation** issues (generic pattern, not only James), buttons in order:
  1. Primary fix (e.g. "Split into base + bonus") — black — confirmation modal with pre-filled split + optional document.
  2. Secondary "{amount} is correct" — white border — required reason (Promotion · Role change · Retention / market correction · Contract correction · Other) + optional document → resolves; Review line becomes matched ("HR confirmation").
  3. Text link "Open salary structure" → employee profile. Remove separate "Correct the amount".
- David Müller (from Oct 30, the day after October pay): "Payment returned – update bank details". This is a bank return after October pay, not a missed October input, and it is not tagged Carried over. Saving the new bank account resolves the issue and removes it from Action needed. It stays hidden on dates before the return was recorded.
- From Nov 1: carried-over missing-data items (for example Lena's tax ID) say "Missed October pay. November pay at risk." A bank return does not use that sentence.

### Screen 3 – All employees (`/people`)

- **Server pagination:** `GET /api/employees?page=1&pageSize=25` (+ filters). Response includes `total`. Footer: "Showing 1–25 of 122" · Previous · page numbers · Next · rows-per-page (25/50/100). `?page=` and `?pageSize=` in URL.
- New employees pinned at top of page 1 ("New" tag), then sorted by name. Filters apply across all pages; changing a filter resets to page 1.
- **Live totals** from DB — never hard-code 120. After Priya + Arjun → 122.
- **One black primary button per screen** (DESIGN.md). Reset = secondary (white, slate border). Add employee = the primary on this screen.

### Screen 4 – Review & approve (`/payroll/review`) — cycle-aware windows

**Before open:** Grey "Review opens {date}." No numbers/table. Link to Action needed.

**Open (Oct 17–22 / Nov 17–22):** Header with closes date + days left. Numbers, approve, sign-off, not-in-run line, "Review any other employee". Nav badge = remaining need-check count.

**Closed October (after Oct 22, through Oct 31):** Read-only. The warning lists only lines that are still unapproved. From **Nov 1** the Review page shows **November**. October is a previous payroll, not a separate summary route.

**Unsigned → November lines:** each unapproved October line carries the live difference between last approved pay and this cycle (salary, allowances, one-time payments, unpaid leave). Underpaid becomes arrears; overpaid becomes a deductible. Seed starting amounts are James +£8,000, Ananya +₹15,000, Rajesh +₹22,000, Thiago +R$6,170, Chloe –£1,450, Mateo –R$2,667. Editing pay before sign-off changes the amount that carries. Approving a line removes that person from the warning and from the November carry. Tag "From October review (not signed off)". Recoveries need approval + "Employee notified" checkbox.

### Screen 5 – Notifications (`/people/notifications`)

- Tab switch: **Email** | **AI Voice call** (V2 stub) | **Slack** (V2 stub) | **In-app alerts** (V3 stub).
- Left: inbox, newest first, with unread count and numbers 1, 2, 3 on unread rows. Right: selected email + CTA per §6 notifications (Open Action needed / Open Review & approve / Overview / Add my details). Opening a message marks it read.

### Attachments (Add employee, Employee profile, One-time payment, Record exit)

Every attachment block:

```
Document type: [Offer letter ▾]
  Offer letter · Bonus letter · Reimbursement bill · Salary revision letter · Resignation / exit letter · Other
Add the document:
  [Use demo file]  [Upload from computer]  [Choose from Google Drive]
```

- **Use demo file**: demo files for that type (offer_letter_priya/arjun, bonus_letter_james, travel_reimbursement_chloe).
- **Upload from computer**: real file input (PDF, DOCX, JPG, PNG) → `POST /api/documents/extract` (multipart).
- **Choose from Google Drive**: real Picker. If Google env vars missing: button **visible but disabled**, hint "Google Drive not set up – see README". Do not hide or replace it.
- Helper text per type (e.g. Offer letter: "We'll read name, job title, start date and salary.").
- After extraction: mapping table with **editable values**; missing required ✗; line "Read from *filename* · edit anything that looks wrong."
- Document stays linked to the record with **View document**; also shown on Review lines.

### Screen A – Add employee (`/people/add`)

- Form fields + attachment block above. Save → confirmation → `dateAdded = prototype date` → `/people/:id`. Priya creates issue #4.

### Screen B – Employee profile (`/people/:id`)

- A pay banner under the header states whether this person, a bonus, and a salary change will be paid, and in which cycle. Missing required fields hold the person. A bank return has its own sentence.
- Editable fields; Payroll panel: Data journey · Salary structure · One-time payments · Pay status · Actions.
- **Add one-time payment** → `/people/:id/one-time-payment`: Type → attach document → fields **pre-filled from document** (editable) → **Confirm** modal ("Add £8,000 bonus for James Patel to October pay?") → `POST /api/employees/:id/one-time-payments` → toast → salary structure + OTP list update, tax/net recalculate, Review line "One-time payment – needs approval" with document (or "No supporting document"). Timing: ≤ Oct 15 → October; after → November (stated in confirmation).
- **Record exit** → `/people/:id/exit` with FnF as before + attachment block.
- Instant payment disabled wherever moved to November.

### Screen F – Employee form (`/form/:token`)

Standalone page (no HR nav). Signed single-use token expires after the cycle cutoff. Only missing employee-owned fields, format validation, Submit. On submit: save (source "Employee form"), journey "Received from employee form", issue resolves when complete, HR gets in-app notification "Priya added her PAN and bank details".

## 8. Business rules

**Pay timing rule (missing data, joiners, one-time payments, exits)**

| Condition | Result shown |
|---|---|
| Existing employee, nothing missing, date before pay day (Oct 29) | "Payment on track for October" (green) |
| Existing employee, nothing missing, date on or after pay day | "Paid in October" (green) |
| Existing employee, missing required field, date ≤ Oct 15 | "Held until {field} is added – fix by Oct 15" (red) |
| New joiner, dateAdded ≤ Oct 15, nothing missing, date before pay day | "Payment on track for October" (green) |
| New joiner, dateAdded ≤ Oct 15, nothing missing, date on or after pay day | "Paid in October" (green) |
| New joiner, dateAdded ≤ Oct 15, missing fields | "Missing {fields} – fix by Oct 15 for October pay" (amber) |
| dateAdded > Oct 15 | "Added after Oct 15 cutoff → paid in November" (red) + disabled Instant payment |
| Missing after Oct 15 (date Oct 16 through the day before pay) | "Moved to November · fix by Nov 15" (amber) |
| Still missing after the Oct 29 pay date | **red** "Missed October pay. November pay at risk." The issue stays in Action needed |
| Fixed before Nov 15 after missing October | "Paid in November payroll" |
| One-time payment / exit recorded ≤ Oct 15 | included in October ("FnF paid in October payroll") |
| One-time payment / exit recorded > Oct 15 | November ("FnF moves to November payroll") |

**AI-check rule (fixed, labelled "AI check")**: a saved pay change > 50% up or > 30% down versus September triggers the second confirmation. Thresholds in `config/rules.json`.

**Tax**: tax = rate × (base + allowances + one-time payments this cycle − unpaid-leave deduction); net = gross − tax. India 10%, UK 20%, Germany 25%, Brazil 15%.

**FnF** = base × (days worked in month / 30) + notice pay + severance + leave encashment (days × base / 30) − recoveries − tax.

**Other rules**

- Never hold the whole payroll: a blocking issue affects only the named employee. **Never hold the whole payroll for unsigned review either.**
- **The add-employee window closes on the 15th** of the pay month. On or before that date, a new employee, bonus, or salary change belongs to this cycle. After the 15th it belongs to the next cycle. The engine input deadline and review close stay the 22nd. Exception: a salary change for someone who already has a row on the open review stays on this review and is marked approved.
- **Unsigned review outcomes (October):** approved + auto-matched paid as calculated; unapproved paid at the previous salary. The gap is computed from current pay, not from a fixed list of names. November gets **arrears** when this cycle is higher, or a **deductible** when it is lower. The seed starts at James +£8,000, Ananya +₹15,000, Rajesh +₹22,000, Thiago +R$6,170, Chloe –£1,450, Mateo –R$2,667.
- **Signed off October:** all approved changes paid; November review has no arrears/recoveries from October — only November changes + carry-overs whose data was fixed.
- **David Müller:** bank return from Oct 30 ("Account closed"), the day after October pay. It is absent on earlier dates. It is its own pay outcome, not also counted as missing inputs. Issue "Payment returned – update bank details". Saving the bank account resolves it and it leaves Action needed. The 30th and 31st highlight, and the October row under Previous payrolls from Nov 1, include that return.
- **Review window on the tracker and in mail** is the 16th–19th of the pay month. The engine review close is the 22nd. From the 1st of a month, screens use that month’s cycle.
- One owner per issue — derived from employee-owned vs HR-owned fields. Funding → finance.
- Email CTAs and Remind employee as §6 / employee reminder rules above.
- AI explains; it never changes a number or decides pay timing (`rules.py` does). Every write records `created_at` and `source`.
- **No hard-coded headcounts** (120/122): always from the database.

## 9. Stubs and versions (must be visible)

| Item | Version | How to show |
|---|---|---|
| AI assistant | V2 | Greyed nav item with tag |
| AI Voice call | V2 | Greyed tab in Notifications, before Slack |
| Write-back to HR tool | V2 | Greyed note on issue detail |
| Slack reminders | V2 | Greyed tab in Notifications |
| Time off, Insurance, Expenses | V2 | Greyed under People |
| Mobile | V2 | Not built (mention in footer) |
| Finance view | V3 | Greyed nav item with tag |
| Employee payroll tool | V3 | Greyed nav item with tag |
| In-app alerts | V3 | Email is the inbox |
| Guided fix steps | V3 | Info icon tooltip on each issue |
| Instant / off-cycle payment | Not available | Disabled option with tooltip wherever an employee moves to November |
| Fix in Workday, Correct the amount | Not built | Toast "Not built in prototype" |

## 10. Do not build

"Run calculations" buttons, escrow, FX rates, dual-control signatures, SLA timers, audit banners, funding breakdown charts or amounts, bot banners, a full payroll calendar grid UI (the prototype date control is a date picker only), the Philippines or any fifth country, real Google Forms, login, "Approve all".

### Design references vs. this file

The screenshots in `stitch_multiplier_payroll_integration_prototype/` are visual references for **layout and style only**. If something appears in a screenshot but not here, leave it out: sync/isolation/audit cards, "Cycle Freeze" bar, "Strict Lock Window", "Gross estimated $…", "Payroll hold breakdown", "Dual Ledger Live View", Lena/James tabs, 12‑month charts, SOC2 footer, Export CSV, Preferences, Digest mode, print/archive icons, audit IDs, Multiplier ID chips, greetings such as "Hello Alex", the Payroll header bar on People pages.

## 11. Demo script (acceptance checks – round 5)

**Path A (signed off):** Fix all → approve all → sign off → Oct 28 payroll submitted → Oct 29 pay day → Oct 30 David’s payment returned → Nov 1 Action needed has David and October sits under Previous payrolls.

**Path B (not signed off):** Reset → leave Priya unfixed, approve nothing → after the 22nd the closed review carries unapproved amounts → Nov 1 Action needed has Priya and David → fix Priya → the November review shows the carry. Review nav badge shows that country’s count when a country admin is signed in.

Also: server pagination on People; Action needed selection/owner/James buttons; employee reminder email body clean; live employee totals.

**Further checks (working prototype):** input-deadline mail does not list every action; unread mail is numbered; a salary saved from the profile stays approved on the open review; a post-15th joiner, bonus, or hike appears on the next review; a bank return resolves when the account is saved; review cards follow approvals and carry amounts follow the edited pay.

## 12. Where the product is written down

- `PRD.md` — requirements for the behaviour above.
- `ROADMAP.md` — what is done, and what is still a later version.

## 13. Running and testing

```bash
cp .env.example .env             # fill Google / LLM keys (optional; demo fallback covers the demo)
npm run dev                      # Flask API :8787 + Vite :5173 together
python3 data/seed_db.py          # (re)seed from config/seed.json — or use "Reset demo" in the app
python3 -m pytest tests/ -q      # domain + API contract tests
npm test                         # Vitest: API client + store cache
npm run test:e2e                 # Playwright: demo script on its own API/SPA
```

## 14. Backend, config and real Google Drive

### 14.1 Structure

```
src/               React + TS + Vite (frontend)
server/            Flask API
  clarity_api/     routes: state, employees, issues, forms, review, notifications, drive, demo
  services/        rules.py (pay timing, AI-check, tax, FnF, outcome) · calendar · connector · validation · issue · review · notification · submission · extraction.py · llm.py
  db/              connection.py, repositories.py
data/              schema.sql, seed_db.py (reads config/seed.json), payroll_clarity.db, domain/* (pure rules shared with tests)
config/            cycle.json · rules.json · seed.json
.env.example       GOOGLE_CLIENT_ID, GOOGLE_API_KEY, GOOGLE_APP_ID, LLM_API_KEY, LLM_MODEL, LLM_BASE_URL, DEMO_FALLBACK=true
```

### 14.2 API (REST, JSON, base `/api`)

- `GET /api/state?date=Oct 12` → everything the UI needs for that date (cycle, overview, issues, employees, review, outcome, emails), computed by `rules.py`
- `GET /api/config` → cycle + rules (frontend reads thresholds/rates from here, never hard-codes them)
- `GET/PATCH /api/employees/{id}`, `POST /api/employees`, `POST /api/employees/{id}/exit`, `POST /api/employees/{id}/one-time-payments`, `POST /api/employees/{id}/documents`
- `POST /api/issues/{id}/resolve`, `POST /api/issues/{id}/remind`, `GET/POST /api/forms/{employeeId}`
- `POST /api/review/{lineId}/approve`, `POST /api/review/signoff`
- `POST /api/drive/extract` body `{ fileId, accessToken, fileName, employeeId?, date }` → mapping table result
- `POST /api/documents/extract` multipart upload (PDF/DOCX/images) → same mapping path
- `POST /api/review/{lineId}/reopen` → move an auto-matched employee back into need-your-check
- `POST /api/demo/reset` → reseed; `GET/PUT /api/demo/date` → any ISO date in Oct 1–Nov 30, 2026
- Forms use signed tokens: `GET/POST /api/forms/{token}`

### 14.3 Data

SQLite tables: employees, employee_field_values, employee_missing_fields, one_time_payments, exits, issues, review_lines, approvals, signoffs, notifications (+ actions), documents, journey_events, change_log, meta. Every write records `created_at` and `source`.

### 14.4 Real Google Drive

- Frontend: Google Picker API with OAuth via Google Identity Services, scope **`https://www.googleapis.com/auth/drive.file`** only. Picker opens on a folder view filtered to PDF, DOCX and images.
- After picking, the frontend sends `{ fileId, accessToken }` to `/api/drive/extract`. The server downloads `GET https://www.googleapis.com/drive/v3/files/{fileId}?alt=media` (Google Docs: export as PDF), extracts text (`pypdf` for PDF, `python-docx` for DOCX), then calls the LLM.
- LLM step (`llm.py`): document text + fixed JSON schema (employee name, job title, start date, annual salary, currency, document type, one-time payment amount and type, PAN/tax ID/bank if present). JSON only, confidence per field, `null` when not found; validated server-side. The LLM never decides pay timing, deadlines or routing.
- Data-journey steps carry **real timestamps**. The access token is never stored or logged; only file id, name and extracted fields are stored.
- UI errors: "Couldn't open this file – check you have access", "This doesn't look like an offer or bonus letter", "Salary not found – please add it".

### 14.5 Demo fallback

- If `DEMO_FALLBACK=true` and Drive or the LLM fails or takes longer than 8 seconds, use a **generic rule-based parser** (regex for amounts, dates, names, tax IDs) — never a lookup by file name. Low-confidence fields are marked for HR to check. A small grey note may show "Used rule-based extraction".
- Known demo PDFs (`offer_letter_priya.pdf`, etc.) remain available as **UI presets** only; the pipeline treats them like any other document.
- If Google sign-in can't load (no network, blocked popup, missing keys), show "Upload from computer instead" with the same extraction path.

### 14.8 Dynamic inputs (any date, any employee)

Seed names and files (`Priya`, `James`, `offer_letter_priya.pdf`, …) are **starting state only**. Runtime behaviour must not branch on specific names, ids or filenames. See `docs/dynamic-inputs-audit.md`.

Every input (new employee, offer/bonus/reimbursement letter, salary revision, exit) goes through one pipeline (`server/services/inputs.py`):

`Received → Read document → Mapped → Validated → Cycle assigned → Stored → Issues / review lines updated`

**Cycle assignment** (calendar only, `config/cycle.json` including Dec 2026 and Jan 2027):

- **Input cycle** = current cycle if `created_at ≤ inputFinalisation`, else the next cycle.
- **New employee first pay** = later of input cycle and the cycle containing the start date. First month is **prorated** (days from start to month end ÷ days in month × monthly salary). Backdated joiners get missed months as arrears; future start dates are “Scheduled · first pay \<month\>”.
- **One-time payment** = input cycle; if the letter’s pay month is earlier → “Late input” flag and paid as arrears in the landing cycle.
- **Exit / FnF** = cycle of last working day, or input cycle if later (“Late exit input”).

Confirmation modals always show the result before save, e.g. “Will be paid in **December 2026** (Dec 28) · inputs for November closed Nov 15”.

Validation findings come from `config/rules.json` (required fields + owners, formats, spike/drop, duplicates). Each finding becomes/updates an issue with deadline = that cycle’s input cutoff; fixing data re-runs validation and resolves automatically. Review lines are built by `calculate_and_build_review` from inputs in the cycle — counts are always live.

**Generate sample document** (next to upload): form for type/country/name/amounts/dates/omit-fields → server PDF → same pipeline. Bulk CSV is V2.

### 14.6 Setup checklist (also in README)

1. Google Cloud project → enable **Google Drive API** and **Google Picker API**.
2. OAuth consent screen: External, Testing mode, add your own Gmail as a test user.
3. Create an OAuth client ID (Web), authorized JavaScript origin `http://localhost:5173`.
4. Create an API key, restricted to the Picker API and your origin.
5. App ID = the project number. Fill `.env`.
6. Create the demo PDFs from §6 (including `travel_reimbursement_chloe.pdf`), put them in a Drive folder "HR Documents".

### 14.7 Real employee reminder email (SMTP)

- `.env`: `SMTP_USER`, `SMTP_PASS` (Gmail app password), `DEMO_INBOX`, `APP_BASE_URL=http://localhost:5173`, optional `FORM_TOKEN_SECRET`.
- Backend sends via SMTP (Flask + smtplib / equivalent). Seed employees get plus-alias addresses derived from `DEMO_INBOX` (Priya → `you+priya@gmail.com`, Lena → `you+lena@gmail.com`).
- Email: "Hi Priya, we need your PAN and bank details… by the 15th of the open month." Button **Add my details** → the missing-details form on that employee’s profile.
- Token is single-use and expires after the cycle cutoff.
- If SMTP is not configured: Remind still works. Notifications store the email for the country admin and for Global, and the button reads as sent. A real Gmail delivery needs the four SMTP settings above. If SMTP is configured and the send fails, the row stays undelivered and the message includes the error.
- Add-details links, including Remind, open `/people/{id}?panel=missing#missing-details`.
- When the saved details put pay on track, the screen says “Thanks for adding your details. Payment is on track.” The employee also gets an email: “Thanks for adding your details. {month} payroll is on track.”
