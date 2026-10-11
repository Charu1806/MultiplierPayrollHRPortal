# Payroll Clarity – Prototype Context

Context for building a clickable prototype in Cursor. **This file is the single source of truth** for names, numbers, dates, text, screens and rules. Read this first, then `PRD.md` for the product requirements of the working prototype, `ROADMAP.md` for what is done, `architecture.md` for the service/API design and `DESIGN.md` for visual styling. If code and this file disagree, this file wins.

## 1. What this is

An interview case study prototype for Multiplier (global EOR and payroll). The prompt: customers have no visibility after they submit payroll inputs, and problems surface only after an employee is paid wrongly.

The solution is a **Multiplier-branded Payroll tab embedded inside the customer's HR tool**, backed by a shared issue model. It catches issues as data arrives and routes each one to the person who can fix it before input finalisation.

**The panel grades product decisions, not code quality.** Keep it narrow, clear and consistent. What is deliberately left out must be visible as a greyed stub with a version tag.

## 2. Hard rules

- **Desktop web only**, designed at 1440px wide. No mobile layouts (mobile is V2). Tables never overflow the page: truncate long cells with a tooltip; horizontal scroll is allowed only *inside* the table container.
- **API-based.** The frontend is a thin client: every read and write goes through the backend API (`/api`, see §14 and `architecture.md`); no business data lives in frontend source files. Business rules are read from `/config` (dates, tax rates, thresholds, required fields) and are never hard-coded in components.
- **State persists.** User actions (fixes, uploads, edits, approvals, sign-off, reminders) are written to the SQLite store and survive page refresh and prototype-date changes. The prototype date is stored too. **Reset demo** (secondary button at the bottom of the left nav → confirmation → `POST /api/demo/reset`) reseeds from `config/seed.json` and reloads Overview. No other reset link.
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
- `company.json` – brand, admin name, HR tool name, “Powered by Multiplier” caption
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
│ Prototype bar: "Prototype date: [📅 calendar]" · API base      │
├──────────────┬────────────────────────────────────────────────┤
│ HR tool nav  │ Breadcrumb · ← Back (when not top-level)       │
│ Employees    │ Page title                                     │
│ Time off     │   tabs: All employees · Add employee           │
│ Payroll ▾    │                                                │
│  Overview    │                                                │
│  Action needed (badge = open issues)                          │
│  Review & approve (badge = lines needing approval when open)  │
│  Notifications                                                │
│  ─────────   │                                                │
│  AI assistant  [V2] (greyed)                                  │
│  Finance view  [V3] (greyed)                                  │
│  Calendar view [V3] (greyed)                                  │
│  ─────────   │                                                │
│  Reset demo  │  (secondary button, bottom of left nav)        │
└──────────────┴────────────────────────────────────────────────┘
```

- HR-tool shell is neutral, no real brand. Small grey label top-left: "Shown inside the customer's HR tool, e.g. Workday".
- Payroll pages header (one line): "Payroll · October 2026 · Powered by Multiplier" and "Synced with Workday 12 min ago".
- **One place for employees.** The HR-tool nav has a single **Employees** item with two tabs: **All employees** (`/people`) and **Add employee** (`/people/add`). There is no separate Payroll › Employees page (`/payroll/employees` redirects to `/people`).
- People pages use the HR-tool look, not the Payroll header.
- The employee form (`/form/:token`) is a standalone page styled like a Google Form, without the shell.
- **Breadcrumb** on every page, top left above the title. Each part except the last is a link, e.g. `HR tool / Payroll / Overview`, `HR tool / Employees / Priya Nair / Add one-time payment`.
- **← Back** next to the breadcrumb on every page that is not a top-level nav page (employee profile, add employee, one-time payment, record exit, employee form). Uses browser history; falls back to the parent crumb.
- **Reset demo** only at the bottom of the left nav (confirmation: "Reset all demo data to Oct 12?").

### Routes

| Route | Screen | API calls |
|---|---|---|
| `/payroll/overview` | Overview (default) | `GET /api/state` (overview, outcome) |
| `/payroll/actions?issue=<id>&country=` | Action needed; URL selects issue / country filter | `GET /api/issues`, resolve, remind |
| `/payroll/review` | Review & approve | `GET /api/review`, approve, reopen, signoff |
| `/payroll/notifications` | Notifications | `GET /api/notifications`, `GET /api/notifications/{id}` |
| `/people?page=&pageSize=&filter=&country=&q=&action=&status=` | All employees (server pagination + filters in URL) | `GET /api/employees?page=&pageSize=` |
| `/payroll/october-summary` | October summary (read-only, from Nov 1 or Oct 23–31) | `GET /api/cycles/october/summary` |
| `/people/add` | Add employee | `POST /api/employees`, `POST /api/documents/extract` |
| `/people/:id?panel=salary` | Employee profile with Payroll panel | `GET/PATCH /api/employees/{id}`, OTP, exit, extract |
| `/people/:id/one-time-payment` | Add one-time payment | `POST /api/employees/{id}/one-time-payments`, extract |
| `/people/:id/exit` | Record exit | `POST /api/employees/{id}/exit`, extract |
| `/form/:token` | Employee form (signed token) | `GET/POST /api/forms/{token}` |

## 5. Prototype date control

**Calendar date picker** (range **Oct 1 – Nov 30, 2026**), not a fixed dropdown. Key dates are marked with a dot and tooltip: Oct 15 Input finalisation, Oct 16 Calculation, Oct 17 Review opens, Oct 22 Review closes, Oct 23 Funding, Oct 25 Submitted, Oct 28 Pay day, Nov 15 November cutoff. Changing the date refetches every screen. **Any date in range must work** — outcomes are computed from current state, not hard-coded to a short list.

| Date | Stage | What the screens show |
|---|---|---|
| Oct 12–14 | Input finalisation | N days left · open actions |
| Oct 15 | Input finalisation (today) | "Cutoff today". Inputs lock at end of day |
| **Oct 16** | **Calculation & final checks** | Multiplier calculates pay; builds review list (38/32/6). Review still closed |
| **Oct 17–22** | **Review** | Review window open. Approve lines and sign off |
| End of Oct 22 | Review closes | Locked, read-only (Oct 23–31: closed October review view) |
| Oct 23 | Funding | Funds received (finance) |
| Oct 25 | Submitted | "Submitted for N employees" (in-run only) |
| Oct 28 | Paid | "N of N paid" |
| **Oct 29** | Paid | David Müller bank return → "N–1 of N paid · 1 payment returned" |
| **Nov 1** | November cycle open | Every screen is November; "View October summary →" for read-only October |
| Nov 15 | November input finalisation | |
| **Nov 17–22** | November Review | November review window (same rules as October) |

Countdown: before/on Oct 15 → "N days left" / "Cutoff today"; after → "Input finalisation closed". From Nov 1, use November dates from config.

## 6. Data

### Customer and calendar

- Customer: **Acme Tech**. HR tool: **Workday**.
- 120 employees before the demo: **India 50, UK 30, Germany 22, Brazil 18**. 4 countries only (no Philippines). Priya and Arjun are added during the demo (→ 122).
- October 2026: input finalisation **Oct 15** · calculation **Oct 16** · review window **Oct 17–22** · funding due **Oct 23** (finance) · submitted **Oct 25** · pay date **Oct 28**.
- November 2026: cycle opens **Nov 1** · input finalisation **Nov 15** · calculation **Nov 16** · review window **Nov 17–22** · pay date **Nov 28**.
- **Cycle-aware:** from Nov 1 every page shows the November cycle. October is only via "View October summary →" (read-only). No stale October copy ("fixed by Oct 15", "Review closed · Oct 22") in November.

### Stages (in order)

`Input finalisation → Calculation & final checks → Review → Funding → Submitted → Paid`

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

On the Overview and the top of Action needed, one neutral card until Oct 15:

> **Any October changes?** Add new joiners, exits, one-time payments and salary changes by **Oct 15** to include them in October pay. After that they move to November.
> [Add employee] [Record exit] [Add one-time payment]

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

### Seed: notifications (email only; Slack is a V2 stub)

Computed from state; only send what applies. Remove the old "Oct 20 – Payroll ready for your approval".

| Date | To | Subject | Condition | Button |
|---|---|---|---|---|
| Oct 12 | HR admin | 3 days left to add payroll inputs | Always (before cutoff) | Open Action needed |
| Oct 13 | Employee | Add your details… | Only if reminder sent | Add my details |
| Oct 14 | HR admin | Cutoff tomorrow for adding payroll inputs | Before cutoff | Open Action needed |
| Oct 15 | HR admin | Cutoff today for adding payroll inputs | Before/on cutoff | Open Action needed |
| Oct 16 | HR admin | Inputs locked – review opens Oct 17 | Always; lists anyone moved to November | Open Overview |
| **Oct 17** | HR admin | **Payroll ready for review: N lines need your check · approve by Oct 22** | Always | Open Review & approve |
| Oct 20 | HR admin | Reminder: 2 days left to review · N lines still open | Only if not signed off | Open Review & approve |
| Oct 22 | HR admin | Review closes today · N lines still open | Only if not signed off | Open Review & approve |
| Oct 22 | Finance | Funding due Oct 23 | Always | Open Overview |
| Oct 23 | HR admin | Payroll signed off – funding in progress | If signed off | Open Overview |
| Oct 23 | HR admin | Review closed without sign-off · N changes moved to November | If not signed off | Open Review & approve |
| Oct 28 | HR admin | October payroll paid… | After pay date | Open Overview |
| **Nov 1** | HR admin | **November cycle open · N carried over from October · fix by Nov 15** | Always from Nov 1 | Open Action needed |
| **Nov 17** | HR admin | **November review open · N lines (incl. N from October) · approve by Nov 22** | Always | Open Review & approve |

Sign-off also sends an in-app confirmation (and SMTP email if configured): "You signed off October payroll at HH:MM". Reminder emails stop once signed off.

**Input-deadline emails (Oct 12, 14 and 15)** do not list every open issue. The subject is the deadline for adding payroll inputs. The body says payroll inputs close on 15 October, and that unresolved actions, or a new employee, salary change, or bonus not added by then, may move all or part of that employee's pay to the next cycle. **What to do** is one step, "Resolve actions in Action needed", linking to Action needed. A **Payroll input policy** link opens a demo page (`/payroll/input-policy`); it does not change pay.

Inbox order is newest first, including mail sent on the same day (`created_at`). Unread rows are numbered 1, 2, 3 from the top. The inbox and the Notifications nav badge show "N unread messages". Opening a message marks it read. Read state is stored and survives refresh. Reset demo clears it.

**Employee reminder emails** (e.g. Lena tax ID): no raw URLs in the body — inline hyperlink "add your details here" + one button **Add my details** (a single arrow icon, not a second arrow in the label) to the same form. Deadline from current cycle config. Carried-over subject: "Add your tax ID for payroll – missed October pay". Body ends with "Your details go straight to payroll; you don't need to reply to this email." Block renamed "What we need" with field + reason. SMTP failure is an amber **system banner** above the email in Notifications, not inside the email body.

## 7. Screens

### The split between Action needed and Review & approve

| | **Action needed** | **Review & approve** |
|---|---|---|
| What | Data is **missing or wrong**, so the employee can't be paid correctly | Data is **complete**; only the pay amount needs a human check |
| Examples | Missing tax ID, PAN, bank, CPF, HR fields; salary entered as 3x and not explained | Salary spike or drop, raise above 10%, unpaid leave, statutory leave pay, vacation pay, arrears |
| Deadline | Input finalisation (Oct 15 / Nov 15) | Review window **Oct 17–22** / **Nov 17–22** |
| If not fixed | Employee moves to next cycle | Unapproved → September pay; November **arrears** (underpaid) or **recovery** (overpaid) |

**Why review waits:** Review can only start once inputs are locked and Multiplier has calculated pay. Reviewing earlier means reviewing numbers that can still change.

Missing-data items **never** appear in Review & approve. Review shows: "**N employees are not in this run**…" only while the window is **open**.

**Nav badges:**
- **Overview:** never.
- **Action needed:** open-issue count (after cutoff: November items only).
- **Review & approve:** while the review window is open (Oct 17–22 or Nov 17–22), badge = lines still needing approval (need your check + edited by you + reopened). Count drops as lines are approved. **No badge** after sign-off or when the window is closed.
- **Notifications:** unread email count. Drops when a message is opened.

### Screen 1 – Overview (`/payroll/overview`)

- Status line, stage tracker, countries, Up next (+ funding/submitted/outcome cards). No Action needed list. No "Start review now".
- **Status line by date:**
  - Up to Oct 15: "**N actions need you** before input finalisation on Oct 15 · N days left" → Action needed.
  - Oct 16: "Inputs locked. Multiplier is calculating pay. **Review opens Oct 17.**"
  - Oct 17–22, not signed off: "**Review open · N lines need your check** · closes Oct 22 · N days left" → Review & approve.
  - Signed off: "Payroll signed off · funding Oct 23".
  - After Oct 15 never say "actions need you before input finalisation".
- **Stage tracker:** Review box grey "Opens Oct 17" before; blue "Open · closes Oct 22" during; green "Signed off Oct 19" when signed off; red "Closed · N changes moved to November" if closed without sign-off. Calculation stage dated **Oct 16**, text "Pay calculated Oct 16 ✓" once past. Lock icon once closed.
- **Up next:** "Oct 17–22 · Review window · N lines" → Review & approve (during/before window).
- Countries and outcome cards as before.

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
- David Müller (from Oct 29): "Payment returned – update bank details". This is a bank return after October pay, not a missed October input, and it is not tagged Carried over. Deadline Nov 15. Saving the new bank account resolves the issue and removes it from Action needed. It stays visible on earlier dates, before the account was saved.
- From Nov 1: carried-over missing-data items (for example Lena's tax ID) say "Missed October pay. November pay at risk." A bank return does not use that sentence.

### Screen 3 – All employees (`/people`)

- **Server pagination:** `GET /api/employees?page=1&pageSize=25` (+ filters). Response includes `total`. Footer: "Showing 1–25 of 122" · Previous · page numbers · Next · rows-per-page (25/50/100). `?page=` and `?pageSize=` in URL.
- New employees pinned at top of page 1 ("New" tag), then sorted by name. Filters apply across all pages; changing a filter resets to page 1.
- **Live totals** from DB — never hard-code 120. After Priya + Arjun → 122.
- **One black primary button per screen** (DESIGN.md). Reset = secondary (white, slate border). Add employee = the primary on this screen.

### Screen 4 – Review & approve (`/payroll/review`) — cycle-aware windows

**Before open:** Grey "Review opens {date}." No numbers/table. Link to Action needed.

**Open (Oct 17–22 / Nov 17–22):** Header with closes date + days left. Numbers, approve, sign-off, not-in-run line, "Review any other employee". Nav badge = remaining need-check count.

**Closed October (Oct 23–31 only, or via October summary):** Read-only, greyed rows (slate-400). Badge "Moved to November review" + "Next approval: Nov 17–22" (from next cycle config). "View employee" text link (not black button). Header: "Review closed Oct 22 · not signed off · next review opens Nov 17". The warning lists only lines that are still unapproved. Top numbers stay live, grey, label "Final October numbers". Remove not-in-run and "Review any other employee". From **Nov 1** the Review page shows **November**, not this closed October view.

**Unsigned → November lines:** each unapproved October line carries the live difference between last approved pay and this cycle (salary, allowances, one-time payments, unpaid leave). Underpaid becomes arrears; overpaid becomes a deductible. Seed starting amounts are James +£8,000, Ananya +₹15,000, Rajesh +₹22,000, Thiago +R$6,170, Chloe –£1,450, Mateo –R$2,667. Editing pay before sign-off changes the amount that carries. Approving a line removes that person from the warning and from the November carry. Tag "From October review (not signed off)". Recoveries need approval + "Employee notified" checkbox.

### Screen 5 – Notifications (`/payroll/notifications`)

- Tab switch: **Email** | **Slack** (V2 stub).
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
| Existing employee, nothing missing, date < Oct 28 | "Payment on track for October" (green) |
| Existing employee, nothing missing, date ≥ Oct 28 | "Paid in October" (green) |
| Existing employee, missing required field, date ≤ Oct 15 | "Held until {field} is added – fix by Oct 15" (red) |
| New joiner, dateAdded ≤ Oct 15, nothing missing, date < Oct 28 | "Payment on track for October" (green) |
| New joiner, dateAdded ≤ Oct 15, nothing missing, date ≥ Oct 28 | "Paid in October" (green) |
| New joiner, dateAdded ≤ Oct 15, missing fields | "Missing {fields} – fix by Oct 15 for October pay" (amber) |
| dateAdded > Oct 15 | "Added after Oct 15 cutoff → paid in November" (red) + disabled Instant payment |
| Missing after Oct 15 (date Oct 16–28) | "Moved to November · fix by Nov 15" (amber) |
| Still missing after the Oct 28 pay date | **red** "Missed October pay. November pay at risk." The issue stays in Action needed with deadline **Nov 15** |
| Fixed before Nov 15 after missing October | "Paid in November payroll" |
| One-time payment / exit recorded ≤ Oct 15 | included in October ("FnF paid in October payroll") |
| One-time payment / exit recorded > Oct 15 | November ("FnF moves to November payroll") |

**AI-check rule (fixed, labelled "AI check")**: a saved pay change > 50% up or > 30% down versus September triggers the second confirmation. Thresholds in `config/rules.json`.

**Tax**: tax = rate × (base + allowances + one-time payments this cycle − unpaid-leave deduction); net = gross − tax. India 10%, UK 20%, Germany 25%, Brazil 15%.

**FnF** = base × (days worked in month / 30) + notice pay + severance + leave encashment (days × base / 30) − recoveries − tax.

**Other rules**

- Never hold the whole payroll: a blocking issue affects only the named employee. **Never hold the whole payroll for unsigned review either.**
- **Input cutoff is the 15th.** On or before that date, a new employee, bonus, or salary change belongs to this cycle. After the 15th it belongs to the next cycle's review, which opens on the 17th. Exception: a salary change for someone who already has a row on the open review stays on this review and is marked approved.
- **Unsigned review outcomes (October):** approved + auto-matched paid as calculated; unapproved paid at the previous salary. The gap is computed from current pay, not from a fixed list of names. November gets **arrears** when this cycle is higher, or a **deductible** when it is lower. The seed starts at James +£8,000, Ananya +₹15,000, Rajesh +₹22,000, Thiago +R$6,170, Chloe –£1,450, Mateo –R$2,667.
- **Signed off October:** all approved changes paid; November review has no arrears/recoveries from October — only November changes + carry-overs whose data was fixed.
- **David Müller:** bank return from Oct 29 ("Account closed"), after October pay. It is absent when inputs close on Oct 15. Paid box amber "N–1 of N · 1 payment returned". Issue "Payment returned – update bank details". Saving the bank account resolves it and it leaves Action needed. Unfixed by Nov 15 → paid with the November run.
- **Review windows** from config (Oct 17–22, Nov 17–22). From Nov 1 screens are November-cycle-aware.
- One owner per issue — derived from employee-owned vs HR-owned fields. Funding → finance.
- Email CTAs and Remind employee as §6 / employee reminder rules above.
- AI explains; it never changes a number or decides pay timing (`rules.py` does). Every write records `created_at` and `source`.
- **No hard-coded headcounts** (120/122): always from the database.

## 9. Stubs and versions (must be visible)

| Item | Version | How to show |
|---|---|---|
| AI assistant | V2 | Greyed nav item with tag |
| Write-back to HR tool | V2 | Greyed note on issue detail |
| Slack reminders | V2 | Greyed tab in Notifications |
| Mobile | V2 | Not built (mention in footer) |
| Finance view | V3 | Greyed nav item with tag |
| Calendar view | V3 | Greyed nav item with tag |
| Guided fix steps | V3 | Info icon tooltip on each issue |
| Instant / off-cycle payment | Not available | Disabled option with tooltip wherever an employee moves to November |
| Fix in Workday, Correct the amount | Not built | Toast "Not built in prototype" |

## 10. Do not build

"Run calculations" buttons, escrow, FX rates, dual-control signatures, SLA timers, audit banners, funding breakdown charts or amounts, bot banners, a full payroll calendar grid UI (the prototype date control is a date picker only), the Philippines or any fifth country, real Google Forms, login, "Approve all".

### Design references vs. this file

The screenshots in `stitch_multiplier_payroll_integration_prototype/` are visual references for **layout and style only**. If something appears in a screenshot but not here, leave it out: sync/isolation/audit cards, "Cycle Freeze" bar, "Strict Lock Window", "Gross estimated $…", "Payroll hold breakdown", "Dual Ledger Live View", Lena/James tabs, 12‑month charts, SOC2 footer, Export CSV, Preferences, Digest mode, print/archive icons, audit IDs, Multiplier ID chips, greetings such as "Hello Alex", the Payroll header bar on People pages.

## 11. Demo script (acceptance checks – round 5)

**Path A (signed off):** Fix all → approve all → sign off Oct 19 → Oct 25 submitted N → Oct 29 one returned (David) → Nov 1 Action needed has David → Nov 17 review has **no** arrears.

**Path B (not signed off):** Reset → leave Priya unfixed, approve nothing → Oct 23 red closed review (arrears/recovery banner) → Nov 1 Action needed has Priya + David → fix Priya → Nov 17 review shows Priya "October + November" + 4 arrears + 2 recoveries; Review nav badge shows the count.

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
- Email: "Hi Priya, we need your PAN and bank details… by **Oct 15**." Button **Add my details** → `APP_BASE_URL/form/<signed-token>`.
- Token is single-use and expires after the cycle cutoff.
- If SMTP is not configured: Remind still works; Notifications get the email + form link; UI shows "Email not sent – SMTP not set up (see README)".
