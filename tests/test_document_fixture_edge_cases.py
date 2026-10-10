"""Edge cases: simulated document fixtures and field mappings (round 1)."""

from __future__ import annotations


class TestPriyaOffer:
    def test_target_india_software_engineer(self, conn):
        row = conn.execute(
            "SELECT * FROM document_fixtures WHERE filename = 'offer_letter_priya.pdf'"
        ).fetchone()
        assert row["target_name"] == "Priya Nair"
        assert row["country"] == "India"
        assert row["role"] == "Software Engineer"
        assert row["start_date"] == "2026-10-20"
        assert row["annual_gross"] == 1800000
        assert row["monthly_base"] == 150000
        assert row["all_fields_ok"] == 0

    def test_mapping_order_and_required_missing(self, conn):
        rows = list(
            conn.execute(
                """
                SELECT multiplier_field, status, confidence
                FROM document_field_mappings
                WHERE document_id = 'doc_priya'
                ORDER BY sort_order
                """
            )
        )
        assert rows[0]["multiplier_field"] == "Employee name"
        missing = [r for r in rows if r["status"] == "missing"]
        assert len(missing) == 2
        assert all("Required" in (r["confidence"] or "") for r in missing)


class TestArjunOffer:
    def test_after_cutoff_start_date(self, conn):
        row = conn.execute(
            "SELECT start_date, all_fields_ok FROM document_fixtures WHERE id = 'doc_arjun'"
        ).fetchone()
        assert row["start_date"] == "2026-10-27"
        assert row["all_fields_ok"] == 1

    def test_no_missing_mappings(self, conn):
        n = conn.execute(
            "SELECT COUNT(*) FROM document_field_mappings "
            "WHERE document_id = 'doc_arjun' AND status != 'mapped'"
        ).fetchone()[0]
        assert n == 0


class TestJamesBonus:
    def test_bonus_amount_eight_thousand(self, conn):
        row = conn.execute(
            "SELECT bonus_amount, resolves_issue_id, doc_type FROM document_fixtures "
            "WHERE filename = 'bonus_letter_james.pdf'"
        ).fetchone()
        assert row["doc_type"] == "bonus"
        assert row["bonus_amount"] == 8000
        assert row["resolves_issue_id"] == "issue_002"

    def test_bonus_fixture_does_not_mutate_seed_row(self, conn):
        """Until Drive extract / salary edit runs, seed keeps base £12,000 and sept £4,000."""
        row = conn.execute(
            "SELECT september_pay, base_salary FROM employees WHERE id = 'emp_james'"
        ).fetchone()
        assert row["september_pay"] == 4000
        assert row["base_salary"] == 12000


class TestChloeTravel:
    def test_travel_reimbursement_fixture(self, conn):
        row = conn.execute(
            "SELECT * FROM document_fixtures WHERE filename = 'travel_reimbursement_chloe.pdf'"
        ).fetchone()
        assert row is not None
        assert row["target_name"] == "Chloe Dubois"
        assert row["country"] == "UK"
        assert row["doc_type"] == "reimbursement"
        assert row["bonus_amount"] == 640


class TestFixtureIsolation:
    def test_fixtures_are_not_employees(self, conn):
        names = {
            r[0]
            for r in conn.execute("SELECT target_name FROM document_fixtures")
        }
        employee_names = {r[0] for r in conn.execute("SELECT name FROM employees")}
        assert "James Patel" in employee_names
        assert "Beatriz Costa" in employee_names
        assert "Priya Nair" not in employee_names
        assert "Arjun Mehta" not in employee_names
        assert names >= {"Priya Nair", "Arjun Mehta", "James Patel"}

    def test_unknown_filename_has_no_fixture(self, conn):
        row = conn.execute(
            "SELECT COUNT(*) FROM document_fixtures WHERE filename = 'random.pdf'"
        ).fetchone()[0]
        assert row == 0
