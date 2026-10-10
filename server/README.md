# Clarity API (prototype)

Local backend for Payroll Clarity: **API Gateway + Clarity API + in-process services** over the illustrative issue & cycle store (`data/payroll_clarity.db`).

## Run

```bash
# from repo root — ensure DB is seeded
python3 data/seed_db.py

python3 -m server.app
# → http://127.0.0.1:8787/health
# → http://127.0.0.1:8787/clarity/v1/...
```

Demo tenancy header (optional; defaults to Acme):

```
X-Customer-Id: cust_acme
```

Pass prototype date as `?asOf=2026-10-12` (or in JSON body for POSTs).

`asOf` is a view date over the store, not just a pay-timing input:

- `GET /employees` and overview headcounts hide joiners whose `date_added` is after `asOf`; `GET /employees/{id}` stays reachable for deep links.
- Issues resolved on a later date read as `open` at an earlier `asOf` (lists, overview counts, approve gate).
- One-offs and missing fields carry no date and are always current.

`POST /employees` dedupes by work email (case-insensitive) within the customer: a match updates name/role/hire date/manager and returns the existing row with `200`; a new row returns `201`.

## Route list (`/clarity/v1`)

| Method | Path | Service(s) |
|---|---|---|
| GET | `/meta/prototype-dates` | Calendar |
| GET | `/cycles/current` | Calendar |
| GET | `/cycles/current/overview` | Calendar + Issue |
| GET | `/employees` | Validation + Issue |
| GET | `/employees/{id}` | Validation |
| POST | `/employees` | Connector + Validation |
| POST | `/employees/{id}/documents` | Validation |
| POST | `/employees/{id}/missing-fields` | Validation + Issue |
| GET | `/issues` | Issue |
| GET | `/issues/{id}` | Issue + AI Explain |
| POST | `/issues/{id}/resolve` | Issue (+ Validation) |
| GET | `/review` | Review |
| POST | `/review/approve` | Review + Submission |
| GET | `/notifications` | Notification |
| GET | `/notifications/{id}` | Notification |
| GET | `/documents/fixtures` | Validation |

## Layout

```
server/
  app.py                 # Gateway middleware + mount
  gateway/middleware.py
  clarity_api/routes.py
  services/              # Calendar, Connector, Validation, Issue, …
  db/                    # SQLite connection + repositories
```

## Tests

```bash
python3 -m pytest tests/test_api_contracts.py tests/ -q
```

Contract tests use a fresh seeded temp DB (they do not mutate `data/payroll_clarity.db`).

## Example

```bash
curl -s 'http://127.0.0.1:8787/clarity/v1/cycles/current/overview?asOf=2026-10-12' \
  -H 'X-Customer-Id: cust_acme' | python3 -m json.tool
```
