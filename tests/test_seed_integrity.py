"""Edge cases: seed DB integrity vs context.md / PRD (round 1)."""

from __future__ import annotations


COUNTRY_TARGETS = {"India": 50, "UK": 30, "Germany": 22, "Brazil": 18}
NAMED = {
    "Lena Fischer",
    "James Patel",
    "Beatriz Costa",
    "Thiago Santos",
    "Ananya Rao",
    "David Müller",
    "Rajesh Sharma",
    "Chloe Dubois",
    "Mateo Silva",
}


def test_exactly_120_employees(conn):
    assert conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 120


def test_country_splits_exact(conn):
    rows = dict(conn.execute("SELECT country, COUNT(*) FROM employees GROUP BY country"))
    assert rows == COUNTRY_TARGETS


def test_no_fifth_country_or_philippines(conn):
    countries = {r[0] for r in conn.execute("SELECT DISTINCT country FROM employees")}
    assert countries == set(COUNTRY_TARGETS)
    assert "Philippines" not in countries


def test_seed_employees_already_onboarded(conn):
    """Named + generated seeds (before Priya/Arjun) have no date_added."""
    bad = conn.execute(
        """
        SELECT COUNT(*) FROM employees
        WHERE date_added IS NOT NULL OR is_new != 0 OR source != 'Workday'
        """
    ).fetchone()[0]
    assert bad == 0


def test_named_seeds_present_with_expected_pay(conn):
    rows = {
        r["name"]: (r["country"], r["currency"], r["september_pay"], r["base_salary"], r["role"])
        for r in conn.execute(
            "SELECT name, country, currency, september_pay, base_salary, role FROM employees "
            "WHERE id NOT LIKE 'emp_gen_%'"
        )
    }
    assert set(rows) == NAMED
    assert rows["Lena Fischer"][:4] == ("Germany", "€", 4200, 4200)
    assert rows["James Patel"][:4] == ("UK", "£", 4000, 12000)
    assert rows["Beatriz Costa"][:4] == ("Brazil", "R$", 14000, 14000)
    assert rows["Ananya Rao"][:4] == ("India", "₹", 120000, 135000)
    assert rows["Thiago Santos"][:4] == ("Brazil", "R$", 18500, 18500)


def test_lena_and_beatriz_missing_fields(conn):
    fields = {
        r["employee_id"]: r["field_name"]
        for r in conn.execute(
            "SELECT employee_id, field_name FROM employee_missing_fields ORDER BY employee_id"
        )
    }
    assert fields == {"emp_lena": "Tax ID", "emp_beatriz": "CPF"}


def test_seed_one_time_payments(conn):
    rows = list(conn.execute("SELECT id, employee_id, amount FROM one_time_payments ORDER BY id"))
    assert len(rows) == 2
    by_id = {r["id"]: r for r in rows}
    assert by_id["otp_thiago_ferias"]["amount"] == 6170
    assert by_id["otp_rajesh_arrears"]["amount"] == 22000


def test_three_open_issues_exact_titles(conn):
    rows = list(
        conn.execute(
            "SELECT id, title, severity, country, owner, status FROM issues ORDER BY id"
        )
    )
    assert len(rows) == 3
    assert all(r["status"] == "open" for r in rows)
    by_id = {r["id"]: r for r in rows}
    assert by_id["issue_001"]["title"] == "Missing tax ID"
    assert by_id["issue_001"]["severity"] == "blocking"
    assert by_id["issue_001"]["country"] == "Germany"
    assert by_id["issue_002"]["title"] == "Salary up 3x"
    assert by_id["issue_002"]["severity"] == "needs_confirmation"
    assert by_id["issue_003"]["title"] == "Missing CPF"
    assert by_id["issue_003"]["severity"] == "blocking"
    assert by_id["issue_003"]["country"] == "Brazil"


def test_priya_and_arjun_not_in_employee_roster(conn):
    names = {r[0] for r in conn.execute("SELECT name FROM employees")}
    assert "Priya Nair" not in names
    assert "Arjun Mehta" not in names


def test_document_fixtures_exist(conn):
    files = {r[0] for r in conn.execute("SELECT filename FROM document_fixtures")}
    assert files == {
        "offer_letter_priya.pdf",
        "offer_letter_arjun.pdf",
        "bonus_letter_james.pdf",
        "travel_reimbursement_chloe.pdf",
    }


def test_priya_mapping_has_required_missing_fields(conn):
    missing = list(
        conn.execute(
            """
            SELECT multiplier_field, value, status FROM document_field_mappings
            WHERE document_id = 'doc_priya' AND status = 'missing'
            ORDER BY sort_order
            """
        )
    )
    assert [m["multiplier_field"] for m in missing] == ["PAN", "Bank account"]


def test_arjun_all_fields_mapped(conn):
    missing = conn.execute(
        "SELECT COUNT(*) FROM document_field_mappings "
        "WHERE document_id = 'doc_arjun' AND status = 'missing'"
    ).fetchone()[0]
    assert missing == 0
    assert (
        conn.execute(
            "SELECT all_fields_ok FROM document_fixtures WHERE id = 'doc_arjun'"
        ).fetchone()[0]
        == 1
    )


def test_james_bonus_resolves_issue_002(conn):
    row = conn.execute(
        "SELECT bonus_amount, resolves_issue_id FROM document_fixtures WHERE id = 'doc_james_bonus'"
    ).fetchone()
    assert row["bonus_amount"] == 8000
    assert row["resolves_issue_id"] == "issue_002"


def test_cycle_dates(conn):
    c = conn.execute("SELECT * FROM payroll_cycles WHERE id = 'cycle_2026_10'").fetchone()
    assert c["input_finalisation"] == "2026-10-22"
    assert c["approval_date"] == "2026-10-22"
    assert c["funding_due"] == "2026-10-26"
    assert c["submitted_date"] == "2026-10-27"
    assert c["pay_date"] == "2026-10-29"
    assert c["approved"] == 0


def test_review_lines_six_pay_changes(conn):
    names = [
        r[0]
        for r in conn.execute(
            "SELECT employee_name FROM review_lines ORDER BY sort_order, id"
        )
    ]
    assert names == [
        "James Patel",
        "Ananya Rao",
        "Chloe Dubois",
        "Mateo Silva",
        "Thiago Santos",
        "Rajesh Sharma",
    ]


def test_emails_are_computed_not_seeded_rows(conn):
    """Round 1: notifications are computed from templates + stored reminders."""
    n = conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
    assert n == 0


def test_unique_employee_emails(conn):
    total = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    distinct = conn.execute(
        "SELECT COUNT(DISTINCT work_email) FROM employees"
    ).fetchone()[0]
    assert total == distinct == 120


def test_currencies_match_country(conn):
    bad = conn.execute(
        """
        SELECT COUNT(*) FROM employees WHERE
          (country = 'India' AND currency != '₹') OR
          (country = 'UK' AND currency != '£') OR
          (country = 'Germany' AND currency != '€') OR
          (country = 'Brazil' AND currency != 'R$')
        """
    ).fetchone()[0]
    assert bad == 0


def test_positive_base_salary(conn):
    assert (
        conn.execute("SELECT COUNT(*) FROM employees WHERE base_salary <= 0").fetchone()[0]
        == 0
    )


def test_rebuild_is_deterministic(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    seed = root / "data" / "seed_db.py"
    a = tmp_path / "a.db"
    b = tmp_path / "b.db"
    for out in (a, b):
        subprocess.check_call(
            [sys.executable, str(seed), "--db", str(out), "--seed", "42"],
            cwd=str(root),
        )
    import sqlite3

    def snapshot(path):
        c = sqlite3.connect(path)
        names = [
            r[0]
            for r in c.execute(
                "SELECT name || '|' || country || '|' || base_salary "
                "FROM employees ORDER BY id"
            )
        ]
        c.close()
        return names

    assert snapshot(a) == snapshot(b)
