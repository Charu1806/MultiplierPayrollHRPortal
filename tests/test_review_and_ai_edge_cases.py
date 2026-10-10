"""Edge cases: exception-first review and AI explain-only rules (round 1)."""

from __future__ import annotations

from domain.issues import can_approve, resolve_issue


class TestReviewLineSeed:
    def test_six_human_check_lines(self, conn):
        n = conn.execute("SELECT COUNT(*) FROM review_lines").fetchone()[0]
        assert n == 6

    def test_flagged_names_match_context(self, conn):
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

    def test_no_missing_data_in_review(self, conn):
        """Missing-data people (Lena, Beatriz, Priya) never appear in Review."""
        names = {
            r[0] for r in conn.execute("SELECT employee_name FROM review_lines")
        }
        assert "Lena Fischer" not in names
        assert "Beatriz Costa" not in names
        assert "Priya Nair" not in names

    def test_james_review_linked_to_salary_spike(self, conn):
        src = conn.execute(
            "SELECT matching_source, why_flagged, change_summary FROM review_lines "
            "WHERE employee_name = 'James Patel'"
        ).fetchone()
        assert "Spike" in src["why_flagged"] or "50%" in src["why_flagged"]
        assert "12,000" in src["change_summary"] or "12000" in src["change_summary"].replace(",", "")


class TestAiExplainOnly:
    def test_james_ai_note_present_september_unchanged(self, conn):
        note = conn.execute(
            "SELECT ai_note FROM issues WHERE id = 'issue_002'"
        ).fetchone()[0]
        assert "one-off bonus" in note.lower() or "Likely" in note
        sept = conn.execute(
            "SELECT september_pay, base_salary FROM employees WHERE id = 'emp_james'"
        ).fetchone()
        assert sept["september_pay"] == 4000
        assert sept["base_salary"] == 12000  # captured as 3x until HR confirms / splits

    def test_confirm_logs_human_decision_not_ai(self, baseline_issues):
        out = resolve_issue(
            baseline_issues,
            "issue_002",
            log="Confirmed by HR admin, Oct 12",
        )
        row = next(i for i in out if i["id"] == "issue_002")
        assert "HR admin" in row["resolution_log"]
        assert "AI" not in row["resolution_log"]


class TestApproveInteractionWithReview:
    def test_approve_blocked_while_blocking_open(self, baseline_issues):
        blocking_open = [
            i
            for i in baseline_issues
            if i["status"] == "open" and i["severity"] == "blocking"
        ]
        assert len(blocking_open) == 2  # Lena + Beatriz
        assert can_approve(baseline_issues) is False

    def test_non_blocking_open_does_not_block_approve(self, baseline_issues):
        after = resolve_issue(baseline_issues, "issue_001")
        after = resolve_issue(after, "issue_003")
        remaining = [i for i in after if i["status"] == "open"]
        assert remaining  # James still open
        assert can_approve(after) is True
