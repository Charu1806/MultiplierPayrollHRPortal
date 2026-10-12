"""SQL access layer — services must use this, not raw SQL elsewhere.

Every mutating method records created_at (default) and a `source`.
`as_of` parameters give the state *as seen on that prototype date*.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any, Dict, List, Optional


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def rows_to_dicts(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [{k: r[k] for k in r.keys()} for r in rows]


def now_iso() -> str:
    """Prototype datetime: demo date when the request clock is pinned, else today."""
    from server.services.clock import now as clock_now

    return clock_now()


class Store:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(review_lines)").fetchall()}
        if "requires_employee_notified" not in cols:
            self.conn.execute(
                "ALTER TABLE review_lines ADD COLUMN requires_employee_notified INTEGER NOT NULL DEFAULT 0"
            )
            self.conn.commit()
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_reads (
              notification_id TEXT PRIMARY KEY,
              read_on        TEXT NOT NULL,
              read_at        TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS hr_employees (
              employee_id TEXT PRIMARY KEY,
              base_salary REAL NOT NULL,
              allowances REAL NOT NULL DEFAULT 0,
              unpaid_leave_days INTEGER NOT NULL DEFAULT 0,
              role TEXT,
              manager_name TEXT,
              status TEXT,
              updated_at TEXT NOT NULL,
              updated_by TEXT
            );
            CREATE TABLE IF NOT EXISTS sync_runs (
              id TEXT PRIMARY KEY,
              customer_id TEXT NOT NULL,
              cycle_id TEXT NOT NULL,
              trigger TEXT NOT NULL,
              status TEXT NOT NULL,
              synced_at TEXT NOT NULL,
              actor TEXT NOT NULL,
              added INTEGER NOT NULL DEFAULT 0,
              changed INTEGER NOT NULL DEFAULT 0,
              exited INTEGER NOT NULL DEFAULT 0,
              summary TEXT,
              error TEXT
            );
            CREATE TABLE IF NOT EXISTS sync_changes (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              sync_id TEXT NOT NULL,
              employee_id TEXT,
              kind TEXT NOT NULL,
              summary TEXT NOT NULL,
              cycle_assignment TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS funding_snapshots (
              id TEXT PRIMARY KEY,
              customer_id TEXT NOT NULL,
              cycle_id TEXT NOT NULL,
              kind TEXT NOT NULL,
              taken_at TEXT NOT NULL,
              payload_json TEXT NOT NULL
            );
            """
        )
        hr_count = self.conn.execute("SELECT COUNT(*) FROM hr_employees").fetchone()[0]
        if hr_count == 0:
            self.conn.execute(
                """
                INSERT INTO hr_employees (
                  employee_id, base_salary, allowances, unpaid_leave_days, role, manager_name, status, updated_at, updated_by
                )
                SELECT id, base_salary, allowances, unpaid_leave_days, role, manager_name, status,
                       '2026-10-01T09:00:00', 'Workday'
                FROM employees
                """
            )
        sync_count = self.conn.execute("SELECT COUNT(*) FROM sync_runs").fetchone()[0]
        if sync_count == 0:
            cycle = self.conn.execute(
                "SELECT id, customer_id FROM payroll_cycles ORDER BY id ASC LIMIT 1"
            ).fetchone()
            if cycle:
                self.conn.execute(
                    """
                    INSERT INTO sync_runs (
                      id, customer_id, cycle_id, trigger, status, synced_at, actor, added, changed, exited, summary
                    ) VALUES ('sync_seed', ?, ?, 'Manual', 'success', '2026-10-01T09:00:00', 'Workday', 0, 0, 0, '+0 added, 0 changed, 0 exited')
                    """,
                    (cycle[1], cycle[0]),
                )
        self.conn.commit()
        self._schema_ready = True

    # ------------------------------------------------------------------ customer / cycle
    def get_customer(self, customer_id: str) -> Optional[Dict[str, Any]]:
        return row_to_dict(
            self.conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        )

    def get_current_cycle(self, customer_id: str) -> Optional[Dict[str, Any]]:
        return row_to_dict(
            self.conn.execute(
                "SELECT * FROM payroll_cycles WHERE customer_id = ? ORDER BY id ASC LIMIT 1",
                (customer_id,),
            ).fetchone()
        )

    def set_cycle_approved(self, cycle_id: str, approved: int = 1) -> None:
        self.conn.execute("UPDATE payroll_cycles SET approved = ? WHERE id = ?", (approved, cycle_id))
        self.conn.commit()

    def set_cycle_stage(self, cycle_id: str, stage: str) -> None:
        self.conn.execute("UPDATE payroll_cycles SET current_stage = ? WHERE id = ?", (stage, cycle_id))
        self.conn.commit()

    # ------------------------------------------------------------------ employees
    def list_employees(
        self,
        customer_id: str,
        country: Optional[str] = None,
        as_of: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM employees WHERE customer_id = ?"
        params: List[Any] = [customer_id]
        if country:
            sql += " AND country = ?"
            params.append(country)
        if as_of:
            sql += " AND (date_added IS NULL OR date_added <= ?)"
            params.append(as_of)
        rows = rows_to_dicts(self.conn.execute(sql, params).fetchall())
        rows.sort(key=lambda e: (e.get("name") or ""))
        rows.sort(key=lambda e: e.get("date_added") or "", reverse=True)
        rows.sort(key=lambda e: e.get("is_new") or 0, reverse=True)
        return rows

    def get_employee(self, employee_id: str) -> Optional[Dict[str, Any]]:
        return row_to_dict(
            self.conn.execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()
        )

    def get_employee_by_email(self, customer_id: str, email: str) -> Optional[Dict[str, Any]]:
        return row_to_dict(
            self.conn.execute(
                """
                SELECT * FROM employees
                WHERE customer_id = ? AND lower(work_email) = lower(?)
                ORDER BY date_added IS NULL, date_added, id LIMIT 1
                """,
                (customer_id, email.strip()),
            ).fetchone()
        )

    def count_by_country(self, customer_id: str, as_of: Optional[str] = None) -> Dict[str, int]:
        sql = "SELECT country, COUNT(*) AS n FROM employees WHERE customer_id = ?"
        params: List[Any] = [customer_id]
        if as_of:
            sql += " AND (date_added IS NULL OR date_added <= ?)"
            params.append(as_of)
        rows = self.conn.execute(sql + " GROUP BY country", params).fetchall()
        return {r["country"]: r["n"] for r in rows}

    def insert_employee(self, emp: Dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO employees (
              id, customer_id, name, role, country, currency, september_pay, base_salary,
              allowances, unpaid_leave_days, date_added, is_new, status, source, work_email,
              hire_date, manager_name, changed_this_cycle, matched_source, edited_by_you, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                emp["id"], emp["customer_id"], emp["name"], emp["role"], emp["country"], emp["currency"],
                emp["september_pay"], emp["base_salary"], emp.get("allowances", 0), emp.get("unpaid_leave_days", 0),
                emp.get("date_added"), emp.get("is_new", 0), emp.get("status", "Active"), emp.get("source", "HR tool"),
                emp.get("work_email"), emp.get("hire_date"), emp.get("manager_name"),
                emp.get("changed_this_cycle", 0), emp.get("matched_source"), emp.get("edited_by_you", 0), emp.get("notes"),
            ),
        )
        self.conn.commit()

    def update_employee_fields(self, employee_id: str, **fields: Any) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(f"UPDATE employees SET {cols} WHERE id = ?", (*fields.values(), employee_id))
        self.conn.commit()

    def get_hr_employee(self, employee_id: str) -> Optional[Dict[str, Any]]:
        return row_to_dict(
            self.conn.execute("SELECT * FROM hr_employees WHERE employee_id = ?", (employee_id,)).fetchone()
        )

    def list_hr_employees(self) -> List[Dict[str, Any]]:
        return rows_to_dicts(self.conn.execute("SELECT * FROM hr_employees").fetchall())

    def upsert_hr_employee(self, employee_id: str, **fields: Any) -> None:
        current = self.get_hr_employee(employee_id)
        if not current:
            emp = self.get_employee(employee_id)
            if not emp:
                raise LookupError("employee_not_found")
            self.conn.execute(
                """
                INSERT INTO hr_employees (
                  employee_id, base_salary, allowances, unpaid_leave_days, role, manager_name, status, updated_at, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    employee_id,
                    emp["base_salary"],
                    emp.get("allowances") or 0,
                    emp.get("unpaid_leave_days") or 0,
                    emp.get("role"),
                    emp.get("manager_name"),
                    emp.get("status"),
                    fields.get("updated_at"),
                    fields.get("updated_by"),
                ),
            )
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(
            f"UPDATE hr_employees SET {cols} WHERE employee_id = ?",
            (*fields.values(), employee_id),
        )
        self.conn.commit()

    def latest_successful_sync(self, customer_id: str, as_of: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Latest successful sync. With as_of, ignore runs dated after that prototype day."""
        sql = """
            SELECT * FROM sync_runs
            WHERE customer_id = ? AND status = 'success'
        """
        params: List[Any] = [customer_id]
        if as_of:
            sql += " AND substr(synced_at, 1, 10) <= ?"
            params.append(as_of[:10])
        sql += " ORDER BY synced_at DESC, rowid DESC LIMIT 1"
        return row_to_dict(self.conn.execute(sql, params).fetchone())

    def manual_syncs_on(self, customer_id: str, day: str) -> int:
        return int(
            self.conn.execute(
                """
                SELECT COUNT(*) FROM sync_runs
                WHERE customer_id = ? AND trigger = 'Manual' AND status = 'success'
                  AND id != 'sync_seed' AND synced_at LIKE ?
                """,
                (customer_id, f"{day}%"),
            ).fetchone()[0]
        )

    def successful_final_sync(self, cycle_id: str) -> Optional[Dict[str, Any]]:
        return row_to_dict(
            self.conn.execute(
                """
                SELECT * FROM sync_runs
                WHERE cycle_id = ? AND trigger = 'Final' AND status = 'success'
                ORDER BY synced_at DESC LIMIT 1
                """,
                (cycle_id,),
            ).fetchone()
        )

    def sync_changes_for(self, sync_id: str) -> List[Dict[str, Any]]:
        return rows_to_dicts(
            self.conn.execute(
                "SELECT * FROM sync_changes WHERE sync_id = ? ORDER BY id DESC",
                (sync_id,),
            ).fetchall()
        )

    def recent_sync_changes(self, customer_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        return rows_to_dicts(
            self.conn.execute(
                """
                SELECT c.* FROM sync_changes c
                JOIN sync_runs r ON r.id = c.sync_id
                WHERE r.customer_id = ?
                ORDER BY c.created_at DESC, c.id DESC
                LIMIT ?
                """,
                (customer_id, limit),
            ).fetchall()
        )

    def funding_snapshot(self, cycle_id: str, kind: str) -> Optional[Dict[str, Any]]:
        return row_to_dict(
            self.conn.execute(
                "SELECT * FROM funding_snapshots WHERE cycle_id = ? AND kind = ? ORDER BY taken_at DESC LIMIT 1",
                (cycle_id, kind),
            ).fetchone()
        )

    def notification_by_kind(self, cycle_id: str, kind: str) -> Optional[Dict[str, Any]]:
        return row_to_dict(
            self.conn.execute(
                "SELECT * FROM notifications WHERE cycle_id = ? AND kind = ? ORDER BY rowid DESC LIMIT 1",
                (cycle_id, kind),
            ).fetchone()
        )

    # ------------------------------------------------------------------ required / missing fields
    def required_missing_fields(self, employee_id: str) -> List[str]:
        """Fields that were empty when the record arrived (regardless of later fills)."""
        return [
            r[0]
            for r in self.conn.execute(
                "SELECT field_name FROM employee_missing_fields WHERE employee_id = ? ORDER BY id",
                (employee_id,),
            ).fetchall()
        ]

    def set_required_missing_fields(self, employee_id: str, fields: List[str]) -> None:
        self.conn.execute("DELETE FROM employee_missing_fields WHERE employee_id = ?", (employee_id,))
        for f in fields:
            self.conn.execute(
                "INSERT INTO employee_missing_fields (employee_id, field_name) VALUES (?, ?)",
                (employee_id, f),
            )
        self.conn.commit()

    def field_values(self, employee_id: str, as_of: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Latest value per field visible on `as_of` (all if None)."""
        sql = "SELECT * FROM employee_field_values WHERE employee_id = ?"
        params: List[Any] = [employee_id]
        if as_of:
            sql += " AND as_of <= ?"
            params.append(as_of)
        sql += " ORDER BY as_of, id"
        out: Dict[str, Dict[str, Any]] = {}
        for r in rows_to_dicts(self.conn.execute(sql, params).fetchall()):
            out[r["field_name"]] = r
        return out

    def missing_fields(self, employee_id: str, as_of: Optional[str] = None) -> List[str]:
        """Required fields still empty as seen on `as_of`."""
        values = self.field_values(employee_id, as_of)
        return [f for f in self.required_missing_fields(employee_id) if f not in values]

    def fields_completed_on(self, employee_id: str) -> Optional[str]:
        """Prototype date on which the last required field was filled (None if any still missing)."""
        required = self.required_missing_fields(employee_id)
        if not required:
            return None
        values = self.field_values(employee_id)
        if any(f not in values for f in required):
            return None
        return max(values[f]["as_of"] for f in required)

    def add_field_value(self, employee_id: str, field_name: str, value: str, *, source: str, as_of: str) -> None:
        self.conn.execute(
            """
            INSERT INTO employee_field_values (employee_id, field_name, value, source, as_of)
            VALUES (?, ?, ?, ?, ?)
            """,
            (employee_id, field_name, value, source, as_of),
        )
        self.conn.commit()

    # Backwards-compatible helpers used by older services
    def clear_missing_fields(self, employee_id: str) -> None:
        self.set_required_missing_fields(employee_id, [])

    def set_missing_fields(self, employee_id: str, fields: List[str]) -> None:
        self.set_required_missing_fields(employee_id, fields)

    # ------------------------------------------------------------------ one-time payments
    def one_time_payments(self, employee_id: str, as_of: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM one_time_payments WHERE employee_id = ?"
        params: List[Any] = [employee_id]
        if as_of:
            sql += " AND recorded_on <= ?"
            params.append(as_of)
        return rows_to_dicts(self.conn.execute(sql + " ORDER BY recorded_on, id", params).fetchall())

    def one_offs(self, employee_id: str, as_of: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.one_time_payments(employee_id, as_of)

    def add_one_time_payment(
        self,
        employee_id: str,
        *,
        type_: str,
        label: str,
        amount: float,
        recorded_on: str,
        source: str,
        document_name: Optional[str] = None,
    ) -> str:
        pid = f"otp_{uuid.uuid4().hex[:8]}"
        self.conn.execute(
            """
            INSERT INTO one_time_payments (id, employee_id, type, label, amount, recorded_on, document_name, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (pid, employee_id, type_, label, amount, recorded_on, document_name, source),
        )
        self.conn.commit()
        return pid

    def update_one_time_payment(self, payment_id: str, *, amount: float, label: str) -> None:
        self.conn.execute(
            "UPDATE one_time_payments SET amount = ?, label = ? WHERE id = ?",
            (amount, label, payment_id),
        )
        self.conn.commit()

    # ------------------------------------------------------------------ exits
    def get_exit(self, employee_id: str, as_of: Optional[str] = None) -> Optional[Dict[str, Any]]:
        sql = "SELECT * FROM exits WHERE employee_id = ?"
        params: List[Any] = [employee_id]
        if as_of:
            sql += " AND recorded_on <= ?"
            params.append(as_of)
        return row_to_dict(self.conn.execute(sql + " ORDER BY id DESC LIMIT 1", params).fetchone())

    def add_exit(self, employee_id: str, data: Dict[str, Any], *, recorded_on: str, source: str) -> str:
        xid = f"exit_{uuid.uuid4().hex[:8]}"
        self.conn.execute(
            """
            INSERT INTO exits (id, employee_id, last_working_day, reason, notice_pay, severance,
                               leave_encashment_days, recoveries, recorded_on, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                xid, employee_id, data["last_working_day"], data.get("reason"), data.get("notice_pay", 0),
                data.get("severance", 0), data.get("leave_encashment_days", 0), data.get("recoveries", 0),
                recorded_on, source,
            ),
        )
        self.conn.commit()
        return xid

    def delete_exits(self, employee_id: str) -> None:
        self.conn.execute("DELETE FROM exits WHERE employee_id = ?", (employee_id,))
        self.conn.commit()

    def delete_line_approvals(self, line_id: str) -> None:
        self.conn.execute("DELETE FROM approvals WHERE line_id = ?", (line_id,))
        self.conn.commit()

    # ------------------------------------------------------------------ issues
    @staticmethod
    def _issue_as_of(row: Dict[str, Any], as_of: Optional[str]) -> Optional[Dict[str, Any]]:
        if as_of and row.get("created_on") and row["created_on"] > as_of:
            return None
        resolved_at = row.get("resolved_at")
        if as_of and row.get("status") == "resolved" and resolved_at and resolved_at > as_of:
            row = {**row, "status": "open", "resolved_at": None, "resolved_by": None, "resolution_log": None}
        if as_of and row.get("reminder_sent_on") and row["reminder_sent_on"] > as_of:
            row = {**row, "reminder_sent_on": None, "reminder_sent_at": None}
        return row

    def list_issues(
        self, cycle_id: str, status: Optional[str] = None, as_of: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        rows = rows_to_dicts(self.conn.execute("SELECT * FROM issues WHERE cycle_id = ?", (cycle_id,)).fetchall())
        out = []
        for r in rows:
            v = self._issue_as_of(r, as_of)
            if v is None:
                continue
            if status and v["status"] != status:
                continue
            out.append(v)
        return out

    def get_issue(self, issue_id: str, as_of: Optional[str] = None) -> Optional[Dict[str, Any]]:
        row = row_to_dict(self.conn.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone())
        return self._issue_as_of(row, as_of) if row else None

    def open_issue_for_employee(self, employee_id: str, kind: str = "missing_fields") -> Optional[Dict[str, Any]]:
        return row_to_dict(
            self.conn.execute(
                "SELECT * FROM issues WHERE employee_id = ? AND kind = ? AND status = 'open' ORDER BY id LIMIT 1",
                (employee_id, kind),
            ).fetchone()
        )

    def insert_issue(self, issue: Dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO issues (id, cycle_id, title, severity, employee_id, country, owner, deadline, source,
                                impact, detail, ai_note, kind, created_on, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
            """,
            (
                issue["id"], issue["cycle_id"], issue["title"], issue["severity"], issue.get("employee_id"),
                issue["country"], issue.get("owner", "HR admin"), issue["deadline"], issue.get("source", "HR tool"),
                issue["impact"], issue.get("detail"), issue.get("ai_note"), issue.get("kind", "missing_fields"),
                issue.get("created_on"),
            ),
        )
        self.conn.commit()

    def update_issue(self, issue_id: str, **fields: Any) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(f"UPDATE issues SET {cols} WHERE id = ?", (*fields.values(), issue_id))
        self.conn.commit()

    def resolve_issue(self, issue_id: str, *, resolved_by: str, resolved_at: str, resolution_log: str) -> None:
        self.conn.execute(
            """
            UPDATE issues SET status = 'resolved', resolved_by = ?, resolved_at = ?, resolution_log = ?
            WHERE id = ? AND status = 'open'
            """,
            (resolved_by, resolved_at, resolution_log, issue_id),
        )
        self.conn.commit()

    def reopen_issue(self, issue_id: str) -> None:
        self.conn.execute(
            "UPDATE issues SET status = 'open', resolved_by = NULL, resolved_at = NULL, resolution_log = NULL WHERE id = ?",
            (issue_id,),
        )
        self.conn.commit()

    def reminders(self, cycle_id: str) -> List[Dict[str, Any]]:
        return rows_to_dicts(
            self.conn.execute(
                "SELECT * FROM cycle_reminders WHERE cycle_id = ? ORDER BY sort_order", (cycle_id,)
            ).fetchall()
        )

    # ------------------------------------------------------------------ document fixtures / documents
    def list_fixtures(self) -> List[Dict[str, Any]]:
        return rows_to_dicts(self.conn.execute("SELECT * FROM document_fixtures ORDER BY id").fetchall())

    def get_fixture_by_filename(self, filename: str) -> Optional[Dict[str, Any]]:
        return row_to_dict(
            self.conn.execute("SELECT * FROM document_fixtures WHERE filename = ?", (filename,)).fetchone()
        )

    def fixture_mappings(self, document_id: str) -> List[Dict[str, Any]]:
        return rows_to_dicts(
            self.conn.execute(
                "SELECT * FROM document_field_mappings WHERE document_id = ? ORDER BY sort_order",
                (document_id,),
            ).fetchall()
        )

    def add_document(
        self,
        employee_id: str,
        *,
        file_name: str,
        source: str,
        as_of: str,
        file_id: Optional[str] = None,
        doc_type: Optional[str] = None,
        used_fallback: bool = False,
        extracted: Optional[Dict[str, Any]] = None,
        mappings: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        did = f"doc_{uuid.uuid4().hex[:8]}"
        self.conn.execute(
            """
            INSERT INTO documents (id, employee_id, file_id, file_name, doc_type, source, used_fallback,
                                   extracted_json, mappings_json, as_of)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                did, employee_id, file_id, file_name, doc_type, source, 1 if used_fallback else 0,
                json.dumps(extracted or {}), json.dumps(mappings or []), as_of,
            ),
        )
        self.conn.commit()
        return did

    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        row = row_to_dict(
            self.conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        )
        if not row:
            return None
        row["extracted"] = json.loads(row.get("extracted_json") or "{}")
        row["mappings"] = json.loads(row.get("mappings_json") or "[]")
        return row

    def documents(self, employee_id: str, as_of: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM documents WHERE employee_id = ?"
        params: List[Any] = [employee_id]
        if as_of:
            sql += " AND as_of <= ?"
            params.append(as_of)
        rows = rows_to_dicts(self.conn.execute(sql + " ORDER BY created_at, id", params).fetchall())
        for r in rows:
            r["extracted"] = json.loads(r.get("extracted_json") or "{}")
            r["mappings"] = json.loads(r.get("mappings_json") or "[]")
        return rows

    # ------------------------------------------------------------------ form tokens
    def create_form_token(
        self,
        *,
        jti: str,
        employee_id: str,
        issue_id: Optional[str],
        created_on: str,
        expires_on: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO form_tokens (jti, employee_id, issue_id, created_on, expires_on)
            VALUES (?, ?, ?, ?, ?)
            """,
            (jti, employee_id, issue_id, created_on, expires_on),
        )
        self.conn.commit()

    def get_form_token(self, jti: str) -> Optional[Dict[str, Any]]:
        return row_to_dict(
            self.conn.execute("SELECT * FROM form_tokens WHERE jti = ?", (jti,)).fetchone()
        )

    def mark_form_token_used(self, jti: str, *, used_at: str) -> None:
        self.conn.execute(
            "UPDATE form_tokens SET used_at = ? WHERE jti = ?",
            (used_at, jti),
        )
        self.conn.commit()

    # ------------------------------------------------------------------ journey events
    def add_journey_events(self, employee_id: str, steps: List[Dict[str, Any]]) -> None:
        for s in steps:
            self.conn.execute(
                """
                INSERT INTO journey_events (employee_id, step_key, label, at, source, detail)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (employee_id, s["key"], s["label"], s["at"], s.get("source", "HR tool"), s.get("detail")),
            )
        self.conn.commit()

    def journey_events(self, employee_id: str) -> List[Dict[str, Any]]:
        rows = rows_to_dicts(
            self.conn.execute(
                "SELECT * FROM journey_events WHERE employee_id = ? ORDER BY id", (employee_id,)
            ).fetchall()
        )
        # keep only the latest run (last 'received' onwards)
        last_start = 0
        for i, r in enumerate(rows):
            if r["step_key"] == "received":
                last_start = i
        return rows[last_start:]

    def notification_read_ids(self) -> set:
        self.ensure_schema()
        return {row[0] for row in self.conn.execute("SELECT notification_id FROM notification_reads").fetchall()}

    def mark_notification_read(self, notification_id: str, *, read_on: str) -> None:
        self.ensure_schema()
        self.conn.execute(
            """
            INSERT INTO notification_reads (notification_id, read_on)
            VALUES (?, ?)
            ON CONFLICT(notification_id) DO UPDATE SET read_on = excluded.read_on
            """,
            (notification_id, read_on),
        )
        self.conn.commit()

    # ------------------------------------------------------------------ notifications
    def list_notifications(self, cycle_id: str) -> List[Dict[str, Any]]:
        return rows_to_dicts(
            self.conn.execute(
                "SELECT * FROM notifications WHERE cycle_id = ? ORDER BY send_date DESC, created_at DESC, rowid DESC",
                (cycle_id,),
            ).fetchall()
        )

    def get_notification(self, notification_id: str) -> Optional[Dict[str, Any]]:
        return row_to_dict(
            self.conn.execute("SELECT * FROM notifications WHERE id = ?", (notification_id,)).fetchone()
        )

    def notification_actions(self, notification_id: str) -> List[Dict[str, Any]]:
        return rows_to_dicts(
            self.conn.execute(
                "SELECT * FROM notification_actions WHERE notification_id = ? ORDER BY sort_order",
                (notification_id,),
            ).fetchall()
        )

    def add_notification(
        self,
        cycle_id: str,
        *,
        send_date: str,
        recipient: str,
        subject: str,
        body_summary: str,
        actions: List[Dict[str, Any]],
        recipient_employee_id: Optional[str] = None,
        cta_label: Optional[str] = None,
        cta_href: Optional[str] = None,
        kind: str = "stored",
    ) -> str:
        nid = f"notif_{uuid.uuid4().hex[:8]}"
        self.conn.execute(
            """
            INSERT INTO notifications (id, cycle_id, send_date, recipient, recipient_employee_id, channel, subject,
                                       body_summary, action_count, cta_label, cta_href, kind)
            VALUES (?, ?, ?, ?, ?, 'email', ?, ?, ?, ?, ?, ?)
            """,
            (nid, cycle_id, send_date, recipient, recipient_employee_id, subject, body_summary, len(actions),
             cta_label, cta_href, kind),
        )
        for i, a in enumerate(actions, start=1):
            self.conn.execute(
                """
                INSERT INTO notification_actions (notification_id, action_text, deadline, issue_id, sort_order)
                VALUES (?, ?, ?, ?, ?)
                """,
                (nid, a["action_text"], a.get("deadline"), a.get("issue_id"), i),
            )
        self.conn.commit()
        return nid

    # ------------------------------------------------------------------ review
    def review_lines(self, cycle_id: str, as_of: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = rows_to_dicts(
            self.conn.execute(
                "SELECT * FROM review_lines WHERE cycle_id = ? ORDER BY sort_order, rowid", (cycle_id,)
            ).fetchall()
        )
        if as_of:
            rows = [r for r in rows if not r.get("created_on") or r["created_on"] <= as_of]
        return rows

    def get_review_line(self, line_id: str) -> Optional[Dict[str, Any]]:
        return row_to_dict(self.conn.execute("SELECT * FROM review_lines WHERE id = ?", (line_id,)).fetchone())

    def review_line_for_employee(self, cycle_id: str, employee_id: str) -> Optional[Dict[str, Any]]:
        return row_to_dict(
            self.conn.execute(
                "SELECT * FROM review_lines WHERE cycle_id = ? AND employee_id = ? ORDER BY sort_order DESC, rowid DESC LIMIT 1",
                (cycle_id, employee_id),
            ).fetchone()
        )

    def current_review_line(self, cycle_id: str, employee_id: str) -> Optional[Dict[str, Any]]:
        """The line on this cycle's review, skipping next-cycle carry and exit rows."""
        for row in reversed(self.review_lines(cycle_id)):
            if row.get("employee_id") != employee_id:
                continue
            origin = row.get("origin") or ""
            if origin in ("october_carry", "exit") or str(row["id"]).startswith("rev_nov_"):
                continue
            return row
        return None

    def insert_review_line(self, line: Dict[str, Any]) -> None:
        self.ensure_schema()
        max_order = self.conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM review_lines WHERE cycle_id = ?", (line["cycle_id"],)
        ).fetchone()[0]
        self.conn.execute(
            """
            INSERT INTO review_lines (id, cycle_id, employee_id, employee_name, country, change_summary, why_flagged,
                                      matching_source, matching_source_resolved, linked_issue_id, origin, created_on,
                                      requires_employee_notified, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                line["id"], line["cycle_id"], line.get("employee_id"), line["employee_name"], line["country"],
                line["change_summary"], line["why_flagged"], line["matching_source"], line.get("matching_source_resolved"),
                line.get("linked_issue_id"), line.get("origin", "edited"), line.get("created_on"),
                1 if line.get("requires_employee_notified") else 0, max_order + 1,
            ),
        )
        self.conn.commit()

    def upsert_review_line(self, line: Dict[str, Any]) -> None:
        self.ensure_schema()
        existing = self.get_review_line(line["id"])
        if existing:
            self.update_review_line(
                line["id"],
                employee_id=line.get("employee_id"),
                employee_name=line["employee_name"],
                country=line["country"],
                change_summary=line["change_summary"],
                why_flagged=line["why_flagged"],
                matching_source=line["matching_source"],
                origin=line.get("origin", "edited"),
                created_on=line.get("created_on"),
                requires_employee_notified=1 if line.get("requires_employee_notified") else 0,
            )
        else:
            self.insert_review_line(line)

    def delete_review_line(self, line_id: str) -> None:
        self.conn.execute("DELETE FROM review_lines WHERE id = ?", (line_id,))
        self.conn.commit()

    def update_review_line(self, line_id: str, **fields: Any) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(f"UPDATE review_lines SET {cols} WHERE id = ?", (*fields.values(), line_id))
        self.conn.commit()

    def line_approval(self, line_id: str, as_of: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Active approval visible on as_of (approved_on <= as_of and not revoked by then)."""
        rows = rows_to_dicts(
            self.conn.execute(
                "SELECT * FROM approvals WHERE line_id = ? ORDER BY id DESC", (line_id,)
            ).fetchall()
        )
        for r in rows:
            if as_of and r["approved_on"] > as_of:
                continue
            if r.get("revoked_on") and (not as_of or r["revoked_on"] <= as_of):
                return None
            return r
        return None

    def approve_line(self, line_id: str, *, approved_on: str, approved_by: str) -> None:
        self.conn.execute(
            "INSERT INTO approvals (line_id, approved_on, approved_by) VALUES (?, ?, ?)",
            (line_id, approved_on, approved_by),
        )
        self.conn.commit()

    def revoke_line_approval(self, line_id: str, *, revoked_on: str, reason: str) -> bool:
        cur = self.conn.execute(
            "UPDATE approvals SET revoked_on = ?, revoke_reason = ? WHERE line_id = ? AND revoked_on IS NULL",
            (revoked_on, reason, line_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def active_signoff(self, cycle_id: str, as_of: Optional[str] = None) -> Optional[Dict[str, Any]]:
        rows = rows_to_dicts(
            self.conn.execute("SELECT * FROM signoffs WHERE cycle_id = ? ORDER BY id DESC", (cycle_id,)).fetchall()
        )
        for r in rows:
            if as_of and r["signed_on"] > as_of:
                continue
            return r
        return None

    def add_signoff(self, cycle_id: str, *, signed_on: str, signed_by: str) -> None:
        self.conn.execute(
            "INSERT INTO signoffs (cycle_id, signed_on, signed_at, signed_by) VALUES (?, ?, ?, ?)",
            (cycle_id, signed_on, now_iso(), signed_by),
        )
        self.conn.commit()

    def reopen_signoff(self, cycle_id: str, *, reopened_on: str, note: str) -> bool:
        cur = self.conn.execute(
            """
            UPDATE signoffs SET reopened_on = ?, reopened_note = ?
            WHERE id = (SELECT id FROM signoffs WHERE cycle_id = ? AND reopened_on IS NULL ORDER BY id DESC LIMIT 1)
            """,
            (reopened_on, note, cycle_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------ change log / meta
    def log_change(self, employee_id: str, field: str, old: Any, new: Any, *, source: str, as_of: str) -> None:
        self.conn.execute(
            """
            INSERT INTO change_log (employee_id, field, old_value, new_value, source, as_of)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (employee_id, field, None if old is None else str(old), None if new is None else str(new), source, as_of),
        )
        self.conn.commit()

    def change_log(self, employee_id: str, as_of: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM change_log WHERE employee_id = ?"
        params: List[Any] = [employee_id]
        if as_of:
            sql += " AND as_of <= ?"
            params.append(as_of)
        return rows_to_dicts(self.conn.execute(sql + " ORDER BY id", params).fetchall())

    def meta(self, key: str) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()
