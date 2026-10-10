# Payroll Clarity (Multiplier)

Clickable prototype: Multiplier-branded Payroll tab inside a customer HR tool shell. React SPA → Clarity API (Flask) → SQLite. Names and figures are illustrative (Acme Tech · Workday · October 2026). Source of truth: `context.md`.

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

Set `SMTP_USER`, `SMTP_PASS` (Gmail app password), `DEMO_INBOX` (your Gmail), and `APP_BASE_URL=http://localhost:5173`. Remind employee then sends a real mail to plus-aliases such as `you+lena@gmail.com` / `you+priya@gmail.com` with **Add my details** → `/form/<signed-token>`. If SMTP is missing, Remind still saves the email to Notifications (with the form link) and shows **Email not sent – SMTP not set up (see README)**.

## Demo sequence (round 1)

Use **Prototype date** in the top bar. Outcomes are computed from what you fixed.

| Date | Where | What you should see |
|---|---|---|
| Oct 12 | Notifications | 1 email, **3** grouped actions → **Open Payroll tab** → Overview "3 actions · 3 days left" + reminder card |
| Oct 12 | Review & approve | Always open: 38 / 32 / 6; "2 employees are not in this run…"; **Sign off** disabled until lines approved |
| Oct 12 | Action needed | **Remind Lena** → email (or SMTP fallback with form link) → fill Steuer-ID → issue resolves; or **Add details myself** |
| Oct 13 | Employees → Add | Priya + offer letter → missing PAN/bank/manager → issue_004. Remind → **Add my details** `/form/<token>` → fill; Manager via HR **Add details** |
| Oct 13 | James salary | Open salary structure or attach `bonus_letter_james.pdf` → base £4,000 + bonus £8,000 |
| Oct 17 | Add Arjun | After cutoff → November + disabled Instant payment. Unfixed missing → "Moved to November · fix by Nov 15" |
| Oct 22 | Review | Per-line **Approve** (with confirm); **Sign off October payroll** when all approved |
| Oct 23–28 | Overview | Funding / Submitted / Paid + outcome card (on time / November / at risk) |
| Nov 2 | Notifications | November cycle open email |

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
python3 -m pytest tests/ -q    # domain rules, seed integrity, API contracts (tmp DB)
npm test                       # Vitest
npm run test:e2e               # Playwright demo path (own API :8788 + Vite :5174)
npm run build                  # tsc + vite
```

Sources of truth: `context.md`, `architecture.md`, `implementation.md`, `DESIGN.md`.
