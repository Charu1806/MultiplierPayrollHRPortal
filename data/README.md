# Illustrative data store

SQLite database for the Payroll Clarity prototype. All figures and names are **illustrative**.

## What’s in the DB

| Entity | Count | Notes |
|---|---|---|
| Customer | Acme Tech · Workday | Fully onboarded |
| Cycles | October 2026 – January 2027 | Engine: close the 22nd · final sync the 23rd · funding the 26th · submitted the 28th · pay the 29th. Display milestones repeat the 15th, 16th–19th, 20th, 22nd, funding the 23rd–27th, payroll submitted on the 28th of the pay month, and pay day in whichever month is open |
| **Employees** | **120** | Already onboarded (`date_added` NULL, `is_new` 0) |
| — India | 50 | Currency `₹` · Sept net bands |
| — UK | 30 | Currency `£` |
| — Germany | 22 | Currency `€` |
| — Brazil | 18 | Currency `R$` |
| Named seeds | 8 | Lena, James, Thiago, Ananya, David, Rajesh, Chloe, Mateo |
| Open issues | 4 | Tax ID, salary 3×, Brazil inputs, India joiners |
| Document fixtures | 3 | Priya / Arjun offers, James bonus (for demo attach) |
| Notifications | 5 | Email only; Slack is V2 |
| Review lines | 6 | Human-check exceptions (38/32/6 totals on cycle row) |

**Not in the 120:** Priya Nair and Arjun Mehta — they are new joiners created during the demo via document fixtures, not pre-onboarded staff.

## Files

| File | Purpose |
|---|---|
| `schema.sql` | Tables + indexes |
| `seed_db.py` | Idempotent rebuild (drops & recreates) |
| `payroll_clarity.db` | Generated SQLite database |

## Rebuild

```bash
python3 data/seed_db.py
# optional:
python3 data/seed_db.py --db data/payroll_clarity.db --seed 42
```

Filler names/pay use a fixed RNG seed (`42`) so rebuilds are deterministic.

## Quick queries

```bash
sqlite3 data/payroll_clarity.db "SELECT country, COUNT(*) FROM employees GROUP BY country;"
sqlite3 data/payroll_clarity.db "SELECT id, title, severity, status FROM issues;"
sqlite3 data/payroll_clarity.db "SELECT name, country, currency, monthly_net FROM employees WHERE id NOT LIKE 'emp_gen_%';"
```

## Baseline state

Matches prototype date **Oct 12**: stage `Input finalisation`, 4 open issues, no one-offs attached yet, approve not done. Document fixtures are ready for Oct 13 / Oct 17 demo actions.

## Domain rules + edge tests

Pure rule modules live in `data/domain/`. Extensive edge cases:

```bash
python3 -m pytest tests/ -v
```

See `tests/EDGE_CASES.md` for the catalog (seed, pay timing, calendar, issues, notifications, docs, review, demo script).

## Consumed by Clarity API

The prototype backend (`server/`) treats this SQLite file as the **issue & cycle store**. Start API:

```bash
python3 -m server.app
# http://127.0.0.1:8787/clarity/v1/...
```
