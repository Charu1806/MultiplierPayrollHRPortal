-- Payroll Clarity — issue & cycle store schema
-- Source of truth: context.md (§6, §8, §14.3), architecture.md
-- All amounts and names are illustrative. Every write records created_at + source.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS customers (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  hr_tool       TEXT NOT NULL,
  employee_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS payroll_cycles (
  id                    TEXT PRIMARY KEY,
  customer_id           TEXT NOT NULL REFERENCES customers(id),
  label                 TEXT NOT NULL,          -- e.g. October 2026
  input_finalisation    TEXT NOT NULL,          -- ISO date
  approval_date         TEXT NOT NULL,
  funding_due           TEXT NOT NULL,
  submitted_date        TEXT,
  pay_date              TEXT NOT NULL,
  current_stage         TEXT NOT NULL,          -- Input finalisation | Validation | …
  approved              INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS employees (
  id              TEXT PRIMARY KEY,
  customer_id     TEXT NOT NULL REFERENCES customers(id),
  name            TEXT NOT NULL,
  role            TEXT NOT NULL,
  country         TEXT NOT NULL CHECK (country IN ('India', 'UK', 'Germany', 'Brazil')),
  currency        TEXT NOT NULL CHECK (currency IN ('₹', '£', '€', 'R$')),
  september_pay   REAL NOT NULL,                -- last approved (September) monthly base
  base_salary     REAL NOT NULL,                -- current monthly base
  allowances      REAL NOT NULL DEFAULT 0,
  unpaid_leave_days INTEGER NOT NULL DEFAULT 0,
  date_added      TEXT,                         -- NULL = Before cycle (already onboarded)
  is_new          INTEGER NOT NULL DEFAULT 0,
  status          TEXT NOT NULL DEFAULT 'Active' CHECK (status IN ('Active', 'Exiting', 'Exited')),
  source          TEXT NOT NULL,                -- Workday | Offer letter | Bonus letter | Google Drive | HR tool
  work_email      TEXT,
  hire_date       TEXT,
  manager_name    TEXT,
  changed_this_cycle INTEGER NOT NULL DEFAULT 0,
  matched_source  TEXT,                         -- auto-reconciled source, NULL if not reconciled
  edited_by_you   INTEGER NOT NULL DEFAULT 0,
  notes           TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_employees_country ON employees(country);
CREATE INDEX IF NOT EXISTS idx_employees_customer ON employees(customer_id);

-- Required fields that were empty when the record arrived. A field counts as
-- missing on prototype date D when no employee_field_values row exists with as_of <= D.
CREATE TABLE IF NOT EXISTS employee_missing_fields (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  employee_id   TEXT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  field_name    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS employee_field_values (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  employee_id   TEXT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  field_name    TEXT NOT NULL,
  value         TEXT NOT NULL,
  source        TEXT NOT NULL,                  -- HR tool | Google Drive | Employee form | Edited by HR admin
  as_of         TEXT NOT NULL,                  -- prototype date of the write
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_field_values_emp ON employee_field_values(employee_id);

CREATE TABLE IF NOT EXISTS one_time_payments (
  id            TEXT PRIMARY KEY,
  employee_id   TEXT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  type          TEXT NOT NULL CHECK (type IN ('Bonus', 'Reimbursement', 'Arrears', 'Other')),
  label         TEXT NOT NULL,
  amount        REAL NOT NULL,
  recorded_on   TEXT NOT NULL,                  -- prototype date; <= cutoff → October else November
  document_name TEXT,
  source        TEXT NOT NULL,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS exits (
  id                    TEXT PRIMARY KEY,
  employee_id           TEXT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  last_working_day      TEXT NOT NULL,
  reason                TEXT,
  notice_pay            REAL NOT NULL DEFAULT 0,
  severance             REAL NOT NULL DEFAULT 0,
  leave_encashment_days INTEGER NOT NULL DEFAULT 0,
  recoveries            REAL NOT NULL DEFAULT 0,
  recorded_on           TEXT NOT NULL,
  source                TEXT NOT NULL,
  created_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS issues (
  id            TEXT PRIMARY KEY,
  cycle_id      TEXT NOT NULL REFERENCES payroll_cycles(id),
  title         TEXT NOT NULL,
  severity      TEXT NOT NULL CHECK (severity IN (
                  'blocking', 'deadline_risk', 'needs_confirmation', 'next_cycle'
                )),
  employee_id   TEXT REFERENCES employees(id),
  country       TEXT NOT NULL,
  owner         TEXT NOT NULL,                  -- HR admin | Finance
  deadline      TEXT NOT NULL,
  source        TEXT NOT NULL,
  impact        TEXT NOT NULL,
  detail        TEXT,
  ai_note       TEXT,
  kind          TEXT NOT NULL DEFAULT 'missing_fields', -- missing_fields | pay_confirmation
  created_on    TEXT,                           -- NULL = seed (always visible); else prototype date it appeared
  reminder_sent_on TEXT,
  reminder_sent_at TEXT,                       -- wall-clock HH:MM when reminder was emailed
  status        TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
  resolved_at   TEXT,
  resolved_by   TEXT,
  resolution_log TEXT,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status);
CREATE INDEX IF NOT EXISTS idx_issues_cycle ON issues(cycle_id);

CREATE TABLE IF NOT EXISTS cycle_reminders (
  id            TEXT PRIMARY KEY,
  cycle_id      TEXT NOT NULL REFERENCES payroll_cycles(id),
  title         TEXT NOT NULL,
  deadline      TEXT NOT NULL,
  owner         TEXT NOT NULL,
  sort_order    INTEGER NOT NULL DEFAULT 0
);

-- Fixed extraction results for the known demo files (demo fallback).
CREATE TABLE IF NOT EXISTS document_fixtures (
  id              TEXT PRIMARY KEY,
  filename        TEXT NOT NULL UNIQUE,
  doc_type        TEXT NOT NULL CHECK (doc_type IN ('offer', 'bonus', 'reimbursement')),
  target_name     TEXT NOT NULL,
  country         TEXT,
  role            TEXT,
  start_date      TEXT,
  annual_gross    REAL,
  currency        TEXT,
  monthly_base    REAL,
  bonus_amount    REAL,
  all_fields_ok   INTEGER NOT NULL DEFAULT 0,
  resolves_issue_id TEXT,
  notes           TEXT
);

CREATE TABLE IF NOT EXISTS document_field_mappings (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id       TEXT NOT NULL REFERENCES document_fixtures(id) ON DELETE CASCADE,
  source_system     TEXT,
  source_field      TEXT,
  multiplier_field  TEXT NOT NULL,
  value             TEXT NOT NULL,
  status            TEXT NOT NULL,              -- mapped | missing
  confidence        TEXT,
  sort_order        INTEGER NOT NULL DEFAULT 0
);

-- Documents actually attached to an employee (Drive, upload or saved extraction).
CREATE TABLE IF NOT EXISTS documents (
  id              TEXT PRIMARY KEY,
  employee_id     TEXT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  file_id         TEXT,
  file_name       TEXT NOT NULL,
  doc_type        TEXT,
  source          TEXT NOT NULL,                -- Google Drive | Upload | Saved extraction
  used_fallback   INTEGER NOT NULL DEFAULT 0,
  extracted_json  TEXT,
  mappings_json   TEXT,
  as_of           TEXT NOT NULL,
  created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS journey_events (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  employee_id   TEXT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  step_key      TEXT NOT NULL,                  -- received | read | mapped | validated | stored
  label         TEXT NOT NULL,
  at            TEXT NOT NULL,                  -- real timestamp ISO
  source        TEXT NOT NULL,
  detail        TEXT
);

-- Single-use signed form tokens for employee reminder links (/form/<token>).
CREATE TABLE IF NOT EXISTS form_tokens (
  jti           TEXT PRIMARY KEY,
  employee_id   TEXT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  issue_id      TEXT,
  created_on    TEXT NOT NULL,                  -- prototype date when issued
  expires_on    TEXT NOT NULL,                  -- cycle cutoff (Oct 15)
  used_at       TEXT,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notifications (
  id            TEXT PRIMARY KEY,
  cycle_id      TEXT NOT NULL REFERENCES payroll_cycles(id),
  send_date     TEXT NOT NULL,
  recipient     TEXT NOT NULL,                  -- HR admin | Finance | employee name
  recipient_employee_id TEXT REFERENCES employees(id),
  channel       TEXT NOT NULL DEFAULT 'email',
  subject       TEXT NOT NULL,
  body_summary  TEXT,
  action_count  INTEGER,
  cta_label     TEXT,
  cta_href      TEXT,
  kind          TEXT NOT NULL DEFAULT 'stored', -- stored (e.g. employee reminder)
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notification_reads (
  notification_id TEXT PRIMARY KEY,
  read_on        TEXT NOT NULL,
  read_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notification_actions (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  notification_id   TEXT NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
  action_text       TEXT NOT NULL,
  deadline          TEXT,
  issue_id          TEXT,
  sort_order        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS review_lines (
  id                TEXT PRIMARY KEY,
  cycle_id          TEXT NOT NULL REFERENCES payroll_cycles(id),
  employee_id       TEXT REFERENCES employees(id),
  employee_name     TEXT NOT NULL,
  country           TEXT NOT NULL,
  change_summary    TEXT NOT NULL,
  why_flagged       TEXT NOT NULL,
  matching_source   TEXT NOT NULL,
  matching_source_resolved TEXT,                -- alternative text once the linked issue is resolved
  linked_issue_id   TEXT,
  origin            TEXT NOT NULL DEFAULT 'seed', -- seed | edited
  created_on        TEXT,                       -- prototype date the line appeared (NULL = seed)
  requires_employee_notified INTEGER NOT NULL DEFAULT 0,
  sort_order        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS approvals (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  line_id       TEXT NOT NULL REFERENCES review_lines(id) ON DELETE CASCADE,
  approved_on   TEXT NOT NULL,                  -- prototype date
  approved_by   TEXT NOT NULL,
  revoked_on    TEXT,                           -- set when the line changed after approval
  revoke_reason TEXT,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS signoffs (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  cycle_id      TEXT NOT NULL REFERENCES payroll_cycles(id),
  signed_on     TEXT NOT NULL,                  -- prototype date
  signed_at     TEXT NOT NULL,                  -- real timestamp
  signed_by     TEXT NOT NULL,
  reopened_on   TEXT,
  reopened_note TEXT,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS change_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  employee_id   TEXT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  field         TEXT NOT NULL,
  old_value     TEXT,
  new_value     TEXT,
  source        TEXT NOT NULL,
  as_of         TEXT NOT NULL,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- HR source (Workday). Payroll snapshot is `employees`. Sync copies HR → snapshot.
CREATE TABLE IF NOT EXISTS hr_employees (
  employee_id        TEXT PRIMARY KEY REFERENCES employees(id) ON DELETE CASCADE,
  base_salary        REAL NOT NULL,
  allowances         REAL NOT NULL DEFAULT 0,
  unpaid_leave_days  INTEGER NOT NULL DEFAULT 0,
  role               TEXT,
  manager_name       TEXT,
  status             TEXT,
  updated_at         TEXT NOT NULL,
  updated_by         TEXT
);

CREATE TABLE IF NOT EXISTS sync_runs (
  id            TEXT PRIMARY KEY,
  customer_id   TEXT NOT NULL,
  cycle_id      TEXT NOT NULL,
  trigger       TEXT NOT NULL,                 -- Manual | Final
  status        TEXT NOT NULL,                 -- success | failed
  synced_at     TEXT NOT NULL,
  actor         TEXT NOT NULL,
  added         INTEGER NOT NULL DEFAULT 0,
  changed       INTEGER NOT NULL DEFAULT 0,
  exited        INTEGER NOT NULL DEFAULT 0,
  summary       TEXT,
  error         TEXT
);

CREATE TABLE IF NOT EXISTS sync_changes (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  sync_id            TEXT NOT NULL,
  employee_id        TEXT,
  kind               TEXT NOT NULL,
  summary            TEXT NOT NULL,
  cycle_assignment   TEXT NOT NULL,            -- current | next
  created_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS funding_snapshots (
  id            TEXT PRIMARY KEY,
  customer_id   TEXT NOT NULL,
  cycle_id      TEXT NOT NULL,
  kind          TEXT NOT NULL,                 -- baseline | final
  taken_at      TEXT NOT NULL,
  payload_json  TEXT NOT NULL
);
