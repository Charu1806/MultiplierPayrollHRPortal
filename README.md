# Payroll Clarity (Multiplier)

Clickable prototype: Multiplier-branded Payroll tab inside a customer HR tool shell. React SPA → Clarity API (Flask) → SQLite. Names and figures are illustrative (Acme Tech · Workday). The prototype date runs from 1 Oct 2026 through 31 Jan 2027. Dashboard dates and notification subjects follow the open month. Source of truth: `context.md`. Requirements: `PRD.md`. What is done: `ROADMAP.md`.

| Layer | Location |
|---|---|
| Config (dates, rules, seed) | `config/{cycle,rules,seed}.json` |
| Issue & cycle store | `data/payroll_clarity.db` (rebuild with `data/seed_db.py`) |
| Clarity API | `server/` → `http://127.0.0.1:8787/api` |
| Frontend SPA | `src/` (Vite + React) → `http://localhost:5173` |

## Run it

```bash
python3 data/seed_db.py   # once (or after Reset demo / schema changes)
cp .env.example .env      # optional Google / LLM / SMTP keys
npm install
npm run dev               # API :8787 + Vite :5173 (concurrently)
```

Or separately: `python3 -m server.app` and `npm run dev:web`.

Env: see `.env.example`. The browser talks to `/api` (Vite proxy). State persists across refresh until **Reset demo**.

### Employee reminder email (optional SMTP)

Set `SMTP_USER`, `SMTP_PASS` (Gmail app password), `DEMO_INBOX` (your Gmail), and `APP_BASE_URL=http://localhost:5173`. Remind employee then sends a real mail to plus-aliases such as `you+lena@gmail.com`. **Add details** opens `/people/{id}?panel=missing#missing-details`. If SMTP is missing, Remind still saves that email in Notifications for the country admin and for the Global HR admin. The in-app email is the send. A failed send is marked undelivered only when SMTP is configured and the message does not go out.

The prototype bar switches persona (Global HR admin Maya Rao, or a country HR admin) and holds **Reset demo**.

## Demo sequence (round 1)

Use **Prototype date** in the top bar. Outcomes are computed from what you fixed.

Sign in as Maya Rao (Global) unless a step names a country admin. The overview deadline card on Oct 12 cites Oct 15, Oct 19, Oct 22, payroll submitted Oct 28, and pay day Oct 29.

| Date | Where | What you should see |
|---|---|---|
| Oct 12 | Overview | Deadline card for October. “N will miss payment” scrolls to Countries. Stage tracker runs through Pay day |
| Oct 12 | Review & approve | 38 changed · 32 matched · 6 need check, for Global. A country admin sees only that country |
| Oct 12 | Action needed | **Remind Lena** saves an email in Notifications. **Add details** opens the missing-details form. Filling the last field shows “Thanks for adding your details. Payment is on track.” and emails the employee that the month’s payroll is on track |
| Oct 13 | Employees → Add | Priya + offer letter → missing PAN, bank, and manager |
| Oct 13 | James salary | Open salary structure or attach `bonus_letter_james.pdf` → base £4,000 + bonus £8,000 |
| Oct 30–31 | Overview | Yellow highlight for the October payroll that just paid, including a payment return on the 30th |
| Nov 1 onward | Overview | Highlight is gone. October is under Previous payrolls |
| Nov 14 | Overview and Notifications | Nov 15, Nov 19, Nov 22, Nov 27, Nov 29. Inbox subject “November: employee window is open” |

**Reset demo** in the prototype bar (or `POST /api/demo/reset` / re-run `seed_db.py`) restores the Oct 12 seed: 120 employees · 3 open issues · 6 review lines.

## Google Drive setup (optional)

Without keys, the UI offers **Upload from computer instead** and `DEMO_FALLBACK=true` uses saved extractions for the three demo PDFs.

1. Google Cloud project → enable **Google Drive API** and **Google Picker API**.
2. OAuth consent screen: External, Testing mode; add your Gmail as a test user.
3. OAuth client ID (Web), authorized JavaScript origin `http://localhost:5173`.
4. API key restricted to the Picker API and your origin.
5. App ID = the project number. Fill `.env` (`GOOGLE_*` / `VITE_GOOGLE_*`, `LLM_*`, `DEMO_FALLBACK=true`).
6. Put `offer_letter_priya.pdf`, `offer_letter_arjun.pdf`, `bonus_letter_james.pdf`, `travel_reimbursement_chloe.pdf` in a Drive folder "HR Documents".

## Tests

```bash
python3 -m pytest tests/ -q    # domain rules, seed integrity, API contracts, dynamic calendar (tmp DB)
npm test                       # Vitest
npm run test:e2e               # Playwright demo path (own API :8788 + Vite :5174)
npm run build                  # tsc + vite
```

Sources of truth: `context.md`, `architecture.md`, `implementation.md`, `DESIGN.md`.
